"""Send an approved application: email (Gmail SMTP) or web form (headless).

Usage: python submit.py --id PACKAGE_ID [--summary-out summary.md]
Updates the package/index status: submitted | manual | failed.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

from common import APPS_DIR, load_json, save_json


def set_status(pid, status, reason):
    pkg = load_json(APPS_DIR / f"{pid}.json")
    pkg["status"] = status
    pkg["submission"] = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                         "result": status, "reason": reason}
    save_json(APPS_DIR / f"{pid}.json", pkg)
    index = load_json(APPS_DIR / "index.json", []) or []
    for i in index:
        if i["id"] == pid:
            i["status"] = status
    save_json(APPS_DIR / "index.json", index)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--summary-out", default="summary.md")
    ap.add_argument("--dry-run", action="store_true", help="fill the form but do not submit")
    a = ap.parse_args()

    pkg = load_json(APPS_DIR / f"{a.id}.json")
    if not pkg:
        sys.exit(f"Package not found: {a.id}")
    if pkg.get("status") == "submitted":
        result, reason = "submitted", "Bu başvuru zaten gönderilmiş, tekrar gönderilmedi."
    else:
        app = pkg.get("application") or {}
        if app.get("method") == "email" and app.get("email") and not os.environ.get("GMAIL_APP_PASSWORD"):
            result = "manual"
            reason = (f"Bu ilan mail ile başvuru istiyor ({app['email']}). Sitede pakette **Gmail'de aç** de, "
                      "userscript'in **Ekleri ekle** butonuyla CV ve cover letter'ı ekle, sonra gönder.")
        elif app.get("method") == "email" and app.get("email"):
            r = subprocess.run([sys.executable, "email_draft.py", "--id", a.id, "--send",
                                "--summary-out", "/tmp/mail.md"], capture_output=True, text=True)
            ok = r.returncode == 0
            result = "submitted" if ok else "failed"
            reason = f"Mail gönderildi → {app['email']}" if ok else (r.stderr or r.stdout).strip()[-400:]
        else:
            r = subprocess.run([sys.executable, "submit_form.py", "--id", a.id] + (["--dry-run"] if a.dry_run else []),
                               capture_output=True, text=True)
            try:
                res = json.loads(r.stdout.strip().splitlines()[-1])
            except Exception:
                res = {"result": "failed", "reason": (r.stderr or r.stdout).strip()[-400:]}
            result, reason = res["result"], res.get("reason", "")
            if res.get("uploaded"):
                reason += f" Yüklenen: {', '.join(res['uploaded'])}."
        if not a.dry_run:
            set_status(a.id, result, reason)

    job = pkg.get("job") or {}
    icon = {"submitted": "✅", "manual": "✋", "failed": "❌", "dry-run": "🧪"}.get(result, "•")
    if result == "dry-run":
        reason = "Deneme: form dolduruldu, GÖNDERİLMEDİ. " + reason
    lines = [f"{icon} **{job.get('title', '')} · {job.get('company', '')}**", "", reason]
    if result == "manual" and (pkg.get("application") or {}).get("method") != "email":
        lines += ["", f"Bunu elle tamamlaman gerekiyor: {pkg['url']}",
                  "İlan sayfasında userscript'in **Formu doldur** butonu alanların çoğunu doldurur."]
    if result == "failed":
        lines += ["", f"Elle başvurmak için: {pkg['url']}"]
    with open(a.summary_out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
