"""Build an application package for one job link:
fit analysis, tailored cover letter and answers to typical form questions.

Usage: python prepare_application.py --url URL [--text-file posting.txt] [--summary-out summary.md]
LLM: any OpenAI-compatible API (default: Groq free tier) via LLM_API_KEY,
or Anthropic if ANTHROPIC_API_KEY is set.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

from common import (APPS_DIR, UA, ai_flags, humanize, load_cv, load_json, load_profile,
                    save_json, slugify, strip_html)

API_URL = "https://api.anthropic.com/v1/messages"
LLM_BASE_URL = (os.environ.get("LLM_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")
USE_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY"))
MODEL = (os.environ.get("CLAUDE_MODEL") or "claude-sonnet-5-5") if USE_ANTHROPIC \
    else (os.environ.get("LLM_MODEL") or "openai/gpt-oss-120b")


def fetch_posting(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = strip_html(str(main))
    return text[:9000]


def call_openai_compatible(system, user, max_tokens=4000):
    key = os.environ.get("LLM_API_KEY")
    if not key:
        sys.exit("LLM_API_KEY secret is missing (free key: https://console.groq.com/keys).")
    import time
    body = {
        "model": MODEL, "max_tokens": max_tokens, "temperature": 0.7,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if "gpt-oss" in MODEL:
        body["reasoning_effort"] = "low"
    for attempt in range(4):
        r = requests.post(f"{LLM_BASE_URL}/chat/completions", timeout=180, json=body,
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        if r.status_code == 429 and attempt < 3:  # free tier: wait for the per-minute window
            time.sleep(min(int(float(r.headers.get("retry-after", "20"))) + 2, 65))
            continue
        if r.status_code >= 400:
            sys.exit(f"LLM API error {r.status_code}: {r.text[:500]}")
        try:
            return r.json()["choices"][0]["message"]["content"]
        except Exception:
            sys.exit(f"LLM API unexpected reply {r.status_code}: {r.text[:300]!r}")
    sys.exit("LLM API rate limit: try again later.")


def call_claude(system, user, max_tokens=4000):
    """Name kept for compatibility: uses the free OpenAI-compatible API unless an Anthropic key exists."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return call_openai_compatible(system, user, max_tokens)
    r = requests.post(API_URL, timeout=180, headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }, json={
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    })
    if r.status_code >= 400:
        sys.exit(f"Claude API error {r.status_code}: {r.text[:500]}")
    return "".join(b.get("text", "") for b in r.json()["content"])


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Model did not return JSON:\n" + text[:500])
    return json.loads(m.group(0))


SCHEMA = """{
  "job": {"title": "", "company": "", "location": "", "deadline": "", "language": "en"},
  "fit": {"score": "integer 0-100", "verdict": "apply | maybe | skip", "strengths": [""], "gaps": [""]},
  "cover_letter": "",
  "short_pitch": "",
  "answers": {
    "why_this_role": "",
    "why_this_organisation": "",
    "relevant_experience": "",
    "research_interests": "",
    "additional_information": ""
  },
  "custom_questions": [{"question": "", "answer": ""}],
  "application": {
    "method": "email | form | unknown",
    "email": "",
    "reference_code": "",
    "required_documents": ["cv", "cover_letter"]
  },
  "email": {"subject": "", "body": ""}
}"""

DOC_KEYS = ["cv", "cover_letter", "transcript", "degree_certificate", "publications",
            "research_statement", "teaching_statement", "references", "language_certificate"]


def build_prompts(profile, cv, posting, url):
    style = "\n".join(f"- {s}" for s in profile["writing_style"])
    system = f"""You prepare job applications for {profile['name']}. You write in his voice, first person.

Writing rules:
{style}
- Use only facts that appear in the CV. Never invent publications, numbers, employers, skills or dates.
  If the posting asks for something the CV does not show, do not claim it. Mention it under "gaps".
- Pick two or three specific things from the CV that match the posting and talk about them concretely.
- Cover letter: 230 to 330 words, 3 or 4 short paragraphs, starts with "Dear Hiring Committee," unless a
  contact name is in the posting, ends with "Best regards,\\n{profile['name']}". No address block, no date.
- If the posting is in German or another language, still write in English unless it says applications
  must be in that language.
- Answers to form questions: 40 to 120 words each, plain and specific.
- custom_questions: any explicit questions or required statements found in the posting, answered.
  Empty list if none.
- Do not fill salary, notice period or work permit answers. The candidate handles those.
- application.method is "email" only if the posting says to send applications to an email address.
  Put that exact address in application.email and any reference/job code in application.reference_code.
- application.required_documents: what the posting asks for, using only these keys:
  {", ".join(DOC_KEYS)}. Always include "cv" and "cover_letter".
- email.subject: short, includes the job title and reference code if there is one.
- email.body: 70 to 130 words, a plain email (not the cover letter), says which documents are attached,
  ends with "Best regards,\\n{profile['name']}". Fill email even if method is "form".

Return ONLY valid JSON in exactly this shape:
{SCHEMA}"""
    user = f"""CANDIDATE CV:
{cv}

JOB POSTING ({url}):
{posting}"""
    return system, user


def clean(obj):
    if isinstance(obj, str):
        return humanize(obj)
    if isinstance(obj, list):
        return [clean(x) for x in obj]
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    return obj


def collect_text(pkg):
    parts = [pkg.get("cover_letter", ""), pkg.get("short_pitch", ""), (pkg.get("email") or {}).get("body", "")]
    parts += list((pkg.get("answers") or {}).values())
    parts += [q.get("answer", "") for q in pkg.get("custom_questions") or []]
    return "\n".join(p for p in parts if isinstance(p, str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--text-file", help="posting text pasted by the user (used if the page can't be read)")
    ap.add_argument("--summary-out", default="summary.md")
    ap.add_argument("--apply-url", help="employer's application form, if different from --url")
    a = ap.parse_args()

    profile, cv = load_profile(), load_cv()

    posting = ""
    if a.text_file and os.path.exists(a.text_file):
        posting = open(a.text_file, encoding="utf-8").read().strip()
    if len(posting) < 300:
        try:
            fetched = fetch_posting(a.url)
            posting = (posting + "\n\n" + fetched).strip()
        except Exception as e:
            print(f"Could not fetch the page: {e}", file=sys.stderr)
    if len(posting) < 300:
        sys.exit("Posting text is too short. The page is probably rendered with JavaScript. "
                 "Paste the posting text into the issue body and try again.")

    system, user = build_prompts(profile, cv, posting[:9000], a.url)
    pkg = clean(parse_json(call_claude(system, user)))
    fit = pkg.get("fit") or {}
    if isinstance(fit.get("score"), (int, float)) and fit["score"] <= 10:  # model used a 0-10 scale
        fit["score"] = int(fit["score"] * 10)

    flags = ai_flags(collect_text(pkg))
    if flags:  # one revision pass if machine-sounding phrases slipped through
        fix = (f"These phrases sound machine-written: {', '.join(flags)}. Rewrite every text field "
               f"without them, keep the same facts and length. Return the full JSON again.\n\n"
               + json.dumps(pkg, ensure_ascii=False))
        pkg = clean(parse_json(call_claude(system, fix)))
        flags = ai_flags(collect_text(pkg))

    job = pkg.get("job", {})
    today = dt.date.today().isoformat()
    slug = f"{today}-{slugify((job.get('company') or '') + ' ' + (job.get('title') or 'job'))}"
    pkg.update({
        "id": slug,
        "url": a.url,
        "apply_url": a.apply_url or a.url,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "model": MODEL,
        "style_flags": flags,
        "status": "ready",
    })
    save_json(APPS_DIR / f"{slug}.json", pkg)

    index = load_json(APPS_DIR / "index.json", []) or []
    index = [i for i in index if i["id"] != slug and i.get("url") != a.url]
    index.insert(0, {
        "id": slug, "url": a.url, "title": job.get("title"), "company": job.get("company"),
        "score": pkg.get("fit", {}).get("score"), "verdict": pkg.get("fit", {}).get("verdict"),
        "created": pkg["created"], "status": "ready",
        "method": (pkg.get("application") or {}).get("method"),
    })
    save_json(APPS_DIR / "index.json", index)

    # Tell the workflow whether to build a Gmail draft.
    app = pkg.get("application") or {}
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"app_id={slug}\nmethod={app.get('method', 'unknown')}\n")

    fit = pkg.get("fit", {})
    lines = [
        f"### {job.get('title', '?')} at {job.get('company', '?')}",
        f"**Uyum:** {fit.get('score', '?')}/100, öneri: `{fit.get('verdict', '?')}`",
        "", "**Güçlü yanlar:**", *[f"- {s}" for s in fit.get("strengths", [])],
        "", "**Eksikler:**", *([f"- {g}" for g in fit.get("gaps", [])] or ["- yok"]),
        "", f"**Başvuru yolu:** {app.get('method', '?')}"
            + (f" → {app.get('email')}" if app.get("email") else ""),
        f"**İstenen belgeler:** {', '.join(app.get('required_documents') or [])}",
        "", f"Paket hazır. Kontrol edip göndermek için: https://anilkus.github.io/isbasvur/?app={slug} → **Onayla ve gönder**",
    ]
    if flags:
        lines.append(f"\n⚠️ Metinde hâlâ şu kalıplar var, göndermeden önce bak: {', '.join(flags)}")
    with open(a.summary_out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
