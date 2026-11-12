"""Turn an application package into a Gmail draft with attachments.

Usage: python email_draft.py --id <package id> [--to override@x] [--dry-run out.eml] [--summary-out summary.md]

Env (GitHub secrets):
  GMAIL_ADDRESS, GMAIL_APP_PASSWORD   Gmail account + app password (IMAP, used to save a draft)
  DOCS_PASSPHRASE                     decrypts private/*.gpg documents
  CONTACT_LINE                        optional, e.g. "you@gmail.com · +90 ..." for the cover letter header
Nothing is sent. The draft waits in Gmail until you press Send.
"""
import argparse
import datetime as dt
import imaplib
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from common import APPS_DIR, PROFILE_DIR, ROOT, load_json, save_json
import cover_letter_pdf


def decrypt(src, dst, passphrase):
    subprocess.run(["gpg", "--batch", "--yes", "--quiet", "--pinentry-mode", "loopback",
                    "--passphrase", passphrase, "-o", str(dst), "-d", str(src)], check=True)


def collect_attachments(pkg, workdir):
    """Return ([(path, filename)], [missing keys])."""
    docs = load_json(PROFILE_DIR / "documents.json", {}) or {}
    wanted = list(dict.fromkeys((pkg.get("application") or {}).get("required_documents") or ["cv", "cover_letter"]))
    for must in ("cv", "cover_letter"):
        if must not in wanted:
            wanted.insert(0, must)

    out, missing = [], []
    passphrase = os.environ.get("DOCS_PASSPHRASE", "")
    for key in wanted:
        if key == "cover_letter":
            p = Path(workdir) / "cover_letter.pdf"
            cover_letter_pdf.render(pkg, p, os.environ.get("CONTACT_LINE", ""))
            out.append((p, docs.get("cover_letter", {}).get("name", "Cover_Letter.pdf")))
            continue
        entry = docs.get(key)
        src = ROOT / entry["file"] if entry else None
        if not entry or not src.exists():
            missing.append(key)
            continue
        if src.suffix == ".gpg":
            if not passphrase:
                missing.append(key)
                continue
            dst = Path(workdir) / src.stem
            decrypt(src, dst, passphrase)
        else:
            dst = src
        out.append((dst, entry.get("name", dst.name)))
    return out, missing


def build_message(pkg, sender, to, attachments):
    mail = pkg.get("email") or {}
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = mail.get("subject") or f"Application: {(pkg.get('job') or {}).get('title', '')}"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(mail.get("body") or "")
    for path, name in attachments:
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(Path(path).read_bytes(), maintype=maintype, subtype=subtype, filename=name)
    return msg


def drafts_folder(imap):
    _, boxes = imap.list()
    for raw in boxes or []:
        line = raw.decode(errors="ignore")
        if "\\Drafts" in line:
            m = re.search(r'"([^"]+)"\s*$', line) or re.search(r"(\S+)\s*$", line)
            return '"' + m.group(1).strip('"') + '"'
    return '"[Gmail]/Drafts"'


def save_draft(msg, user, password):
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(user, password)
    folder = drafts_folder(imap)
    typ, resp = imap.append(folder, "(\\Draft)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    imap.logout()
    if typ != "OK":
        raise RuntimeError(f"IMAP append failed: {resp}")
    return folder


def send_mail(msg, user, password):
    import smtplib
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, password)
        s.send_message(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--to", help="override recipient")
    ap.add_argument("--send", action="store_true", help="send now via Gmail SMTP instead of saving a draft")
    ap.add_argument("--dry-run", help="write .eml here instead of saving to Gmail")
    ap.add_argument("--summary-out", default="summary.md")
    a = ap.parse_args()

    path = APPS_DIR / f"{a.id}.json"
    pkg = load_json(path)
    if not pkg:
        sys.exit(f"Package not found: {a.id}")
    to = a.to or (pkg.get("application") or {}).get("email")
    if not to:
        sys.exit("No application email in this package. Use --to.")

    sender = os.environ.get("GMAIL_ADDRESS", "me@example.com")
    with tempfile.TemporaryDirectory() as tmp:
        attachments, missing = collect_attachments(pkg, tmp)
        msg = build_message(pkg, sender, to, attachments)
        if a.dry_run:
            Path(a.dry_run).write_bytes(msg.as_bytes())
            where = a.dry_run
        else:
            if not os.environ.get("GMAIL_APP_PASSWORD"):
                sys.exit("GMAIL_APP_PASSWORD secret is missing.")
            if a.send:
                if missing and any(m != "cover_letter" for m in missing):
                    sys.exit(f"Not sending: required documents missing from the repo: {', '.join(missing)}")
                send_mail(msg, sender, os.environ["GMAIL_APP_PASSWORD"])
                where = "gönderildi"
            else:
                where = "Gmail " + save_draft(msg, sender, os.environ["GMAIL_APP_PASSWORD"])

    names = [n for _, n in attachments]
    pkg["email_draft"] = {
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "to": to, "subject": msg["Subject"], "attachments": names, "missing": missing,
    }
    status = "submitted" if a.send and not a.dry_run else "draft"
    pkg["status"] = status
    save_json(path, pkg)
    index = load_json(APPS_DIR / "index.json", []) or []
    for i in index:
        if i["id"] == a.id:
            i["status"] = status
    save_json(APPS_DIR / "index.json", index)

    title = "📧 **Mail gönderildi**" if status == "submitted" else f"📧 **Taslak hazır** ({where})"
    lines = ["", "---", f"{title} → `{to}`",
             f"Ekler: {', '.join(names)}"]
    if missing:
        lines.append(f"⚠️ Repoda olmayan belgeler: {', '.join(missing)}. Taslağa elle ekle.")
    if status != "submitted":
        lines.append("Gmail > Taslaklar'dan kontrol edip gönder.")
    with open(a.summary_out, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
