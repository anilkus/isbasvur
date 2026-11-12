"""Fetch job listings from public sources, score them against the profile,
and write docs/data/jobs.json for the site. Runs daily in GitHub Actions."""
import datetime as dt
import sys
import xml.etree.ElementTree as ET

import requests

from common import (DATA_DIR, PROFILE_DIR, SUPPORTED_FORMS, UA, load_json, load_profile, resolve_apply_url,
                    save_json, score_job, strip_html)

S = requests.Session()
S.headers["User-Agent"] = UA


def arbeitnow(cfg):
    jobs = []
    for page in range(1, cfg.get("pages", 3) + 1):
        r = S.get("https://www.arbeitnow.com/api/job-board-api", params={"page": page}, timeout=30)
        r.raise_for_status()
        for j in r.json().get("data", []):
            jobs.append({
                "title": j.get("title"),
                "company": j.get("company_name"),
                "location": (j.get("location") or "") + (" (remote)" if j.get("remote") else ""),
                "url": j.get("url"),
                "description": strip_html(j.get("description")),
                "posted": dt.datetime.fromtimestamp(j.get("created_at", 0), dt.timezone.utc).date().isoformat(),
                "source": "Arbeitnow",
            })
    return jobs


def remotive(cfg):
    jobs, seen = [], set()
    for q in cfg.get("searches", []):
        r = S.get("https://remotive.com/api/remote-jobs", params={"search": q, "limit": 50}, timeout=30)
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            if j["url"] in seen:
                continue
            seen.add(j["url"])
            jobs.append({
                "title": j.get("title"),
                "company": j.get("company_name"),
                "location": j.get("candidate_required_location") or "Remote",
                "url": j.get("url"),
                "description": strip_html(j.get("description")),
                "posted": (j.get("publication_date") or "")[:10],
                "source": "Remotive",
            })
    return jobs


def rss(feed):
    r = S.get(feed["url"], timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    jobs = []
    for item in root.iter("item"):
        get = lambda tag: (item.findtext(tag) or "").strip()
        jobs.append({
            "title": strip_html(get("title")),
            "company": feed["name"],
            "location": "",
            "url": get("link"),
            "description": strip_html(get("description")),
            "posted": get("pubDate"),
            "source": feed["name"],
        })
    return jobs


def main():
    profile = load_profile()
    cfg = load_json(PROFILE_DIR / "sources.json")
    collected, errors = [], []

    tasks = []
    if cfg["arbeitnow"].get("enabled"):
        tasks.append(("Arbeitnow", lambda: arbeitnow(cfg["arbeitnow"])))
    if cfg["remotive"].get("enabled"):
        tasks.append(("Remotive", lambda: remotive(cfg["remotive"])))
    for feed in cfg.get("rss", []):
        tasks.append((feed["name"], lambda f=feed: rss(f)))

    for name, fn in tasks:
        try:
            got = fn()
            print(f"{name}: {len(got)} listings")
            collected += got
        except Exception as e:  # one broken source should not kill the run
            print(f"{name}: FAILED {e}", file=sys.stderr)
            errors.append(f"{name}: {e}")

    # Keep previous decisions (hidden / applied) across runs.
    old = {j["url"]: j for j in (load_json(DATA_DIR / "jobs.json", {}) or {}).get("jobs", [])}

    out, seen = [], set()
    for j in collected:
        if not j.get("url") or j["url"] in seen:
            continue
        seen.add(j["url"])
        score, matched = score_job(j, profile)
        if score < cfg.get("min_score", 25):
            continue
        j["score"], j["matched"] = score, matched[:8]
        j["description"] = j["description"][:4000]
        j["status"] = old.get(j["url"], {}).get("status", "new")
        out.append(j)

    out.sort(key=lambda j: j["score"], reverse=True)
    out = out[: cfg.get("max_jobs", 150)]

    # Keep only jobs whose real application page is a form we can submit.
    if cfg.get("forms_only", True):
        kept = []
        for j in out:
            prev = old.get(j["url"], {})
            j["apply_url"] = resolve_apply_url(prev.get("apply_url") or j["url"], S)
            if j["apply_url"] and SUPPORTED_FORMS.search(j["apply_url"]):
                kept.append(j)
        print(f"{len(kept)} of {len(out)} have a supported application form")
        out = kept
    save_json(DATA_DIR / "jobs.json", {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "count": len(out),
        "errors": errors,
        "jobs": out,
    })
    print(f"Saved {len(out)} matching jobs")


if __name__ == "__main__":
    main()
