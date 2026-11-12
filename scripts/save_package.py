"""Save an application package written in a Claude chat (no API needed).

Usage: python save_package.py --file pkg.json --url JOB_URL
The JSON follows SCHEMA in prepare_application.py. This script cleans the text
(dashes, AI phrasing check), assigns an id, updates the index and renders the
public cover letter PDF. Pushing it triggers the Gmail-draft workflow when the
posting asks for an email application.
"""
import argparse
import datetime as dt
import json

from common import APPS_DIR, ai_flags, humanize, load_json, save_json, slugify
import cover_letter_pdf


def clean(obj):
    if isinstance(obj, str):
        return humanize(obj)
    if isinstance(obj, list):
        return [clean(x) for x in obj]
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    return obj


def all_text(pkg):
    parts = [pkg.get("cover_letter", ""), pkg.get("short_pitch", ""), (pkg.get("email") or {}).get("body", "")]
    parts += list((pkg.get("answers") or {}).values())
    parts += [q.get("answer", "") for q in pkg.get("custom_questions") or []]
    return "\n".join(p for p in parts if isinstance(p, str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--url", required=True)
    a = ap.parse_args()

    pkg = clean(json.load(open(a.file, encoding="utf-8")))
    job = pkg.get("job") or {}
    old = next((i for i in (load_json(APPS_DIR / "index.json", []) or []) if i.get("url") == a.url), None)
    slug = old["id"] if old else \
        f"{dt.date.today().isoformat()}-{slugify((job.get('company') or '') + ' ' + (job.get('title') or 'job'))}"

    pkg.update({
        "id": slug, "url": a.url,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "model": "claude-chat", "style_flags": ai_flags(all_text(pkg)), "status": "ready",
    })
    save_json(APPS_DIR / f"{slug}.json", pkg)

    index = [i for i in (load_json(APPS_DIR / "index.json", []) or []) if i["id"] != slug]
    index.insert(0, {
        "id": slug, "url": a.url, "title": job.get("title"), "company": job.get("company"),
        "score": (pkg.get("fit") or {}).get("score"), "verdict": (pkg.get("fit") or {}).get("verdict"),
        "created": pkg["created"], "status": "ready",
        "method": (pkg.get("application") or {}).get("method"),
    })
    save_json(APPS_DIR / "index.json", index)
    cover_letter_pdf.render(pkg, APPS_DIR / f"{slug}-cover-letter.pdf")

    print(f"saved {slug}")
    if pkg["style_flags"]:
        print("STYLE FLAGS:", ", ".join(pkg["style_flags"]))


if __name__ == "__main__":
    main()
