"""After the daily scan: write application packages for the best new matches.

Picks jobs from docs/data/jobs.json that score high enough and have no package yet,
runs prepare_application.py for each (free GitHub Models), and records the outcome
on the job so it is not retried every day. Packages wait on the site for approval.
"""
import subprocess
import sys

from common import APPS_DIR, DATA_DIR, PROFILE_DIR, load_json, save_json


def main():
    cfg = (load_json(PROFILE_DIR / "sources.json", {}) or {}).get("auto_prepare", {})
    limit, min_score = cfg.get("max_per_day", 4), cfg.get("min_score", 40)

    data = load_json(DATA_DIR / "jobs.json", {}) or {}
    done = {i.get("url") for i in (load_json(APPS_DIR / "index.json", []) or [])}
    picked = [j for j in data.get("jobs", [])
              if j["score"] >= min_score and j.get("status", "new") in ("new", "failed") and j["url"] not in done][:limit]

    print(f"Preparing {len(picked)} packages")
    for j in picked:
        # The scan already has the posting text, which helps when the page is rendered with JavaScript.
        with open("/tmp/posting.txt", "w", encoding="utf-8") as f:
            f.write(f"{j['title']}\n{j.get('company', '')} · {j.get('location', '')}\n\n{j.get('description', '')}")
        r = subprocess.run([sys.executable, "prepare_application.py", "--url", j["url"], "--text-file", "/tmp/posting.txt",
                            "--summary-out", "/tmp/auto_summary.md"], capture_output=True, text=True)
        j["status"] = "prepared" if r.returncode == 0 else "failed"
        print(j["status"], j["title"], "|", (r.stdout + r.stderr).strip().splitlines()[-1:] )

    save_json(DATA_DIR / "jobs.json", data)


if __name__ == "__main__":
    main()
