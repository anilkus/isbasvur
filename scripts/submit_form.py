"""Submit an approved application through the employer's web form, headless.

Reuses userscript/job-autofill.user.js inside Playwright (GM_* functions are shimmed),
so the browser extension and this script fill forms the same way.

Never submits when something looks wrong: unknown portal, login wall, CAPTCHA,
or a required field it could not fill. Those come back as "manual".

Env: APPLICANT_JSON (personal details), DOCS_PASSPHRASE (decrypts private/*.gpg)
Usage: python submit_form.py --id PACKAGE_ID [--url OVERRIDE] [--dry-run] [--chrome PATH]
Prints one JSON line: {"result": "submitted|manual|failed", "reason": ..., ...}
"""
import argparse
import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import requests

from common import APPS_DIR, ROOT, UA, load_json
from email_draft import collect_attachments

SITE = "https://anilkus.github.io/isbasvur/"
SUPPORTED = re.compile(r"greenhouse\.io|lever\.co|ashbyhq\.com|workable\.com|personio\.(de|com)|"
                       r"smartrecruiters\.com|recruitee\.com|teamtailor\.com|join\.com|bamboohr\.com|"
                       r"localhost|127\.0\.0\.1")
SUCCESS = re.compile(r"thank you|thanks for applying|application (has been )?(received|submitted|sent)|"
                     r"we('ve| have) received|successfully (submitted|applied)|danke für ihre bewerbung|"
                     r"bewerbung (wurde )?(erfolgreich )?(eingegangen|versendet|übermittelt)|bedankt", re.I)
SUBMIT_TEXT = re.compile(r"^\s*(submit( application)?|apply( now)?|send( application)?|"
                         r"bewerbung (absenden|senden)|absenden|solliciteer|verzenden)\s*$", re.I)


def out(result, **kw):
    print(json.dumps({"result": result, **kw}, ensure_ascii=False))
    sys.exit(0)


def shim_js(me, docs):
    """GM_* replacements for the userscript; network goes through a Python binding."""
    return f"""
window.__JA_AUTOMATION = true;
(() => {{
  const store = {json.dumps({"me": me, **docs})};
  window.GM_getValue = (k, d) => (k in store ? store[k] : d);
  window.GM_setValue = (k, v) => {{ store[k] = v; }};
  window.GM_registerMenuCommand = () => {{}};
  window.GM_xmlhttpRequest = (o) => {{
    window.__jaFetch(o.url, o.responseType || "text").then(r => {{
      if (o.responseType === "arraybuffer") {{
        const bin = atob(r.body), buf = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
        o.onload && o.onload({{ status: r.status, response: buf.buffer }});
      }} else o.onload && o.onload({{ status: r.status, responseText: r.body }});
    }}).catch(e => o.onerror && o.onerror(e));
  }};
}})();
"""


def py_fetch(url, kind):
    # Packages come straight from the checked-out repo, so a fresh package works before Pages redeploys.
    if url.startswith(SITE):
        local = ROOT / "docs" / url[len(SITE):].split("?")[0]
        if local.exists():
            raw = local.read_bytes()
            return {"status": 200, "body": base64.b64encode(raw).decode() if kind == "arraybuffer" else raw.decode("utf-8")}
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    body = base64.b64encode(r.content).decode() if kind == "arraybuffer" else r.text
    return {"status": r.status_code, "body": body}


def doc_store(pkg, workdir):
    """Decrypted documents as data URLs, keyed like the userscript expects (doc_cv, ...)."""
    files, missing = collect_attachments(pkg, workdir)
    store = {}
    docs_cfg = load_json(ROOT / "profile" / "documents.json", {}) or {}
    by_name = {v.get("name"): k for k, v in docs_cfg.items()}
    for path, name in files:
        key = by_name.get(name)
        if not key or key == "cover_letter":
            continue  # the userscript fetches the public cover letter PDF itself
        data = base64.b64encode(Path(path).read_bytes()).decode()
        store["doc_" + key] = {"name": name, "type": "application/pdf", "data": f"data:application/pdf;base64,{data}"}
    return store, missing


def answer_choices(page, me):
    """Radios and checkboxes the userscript skips: sponsorship, work permit, relocation, consent."""
    return page.evaluate("""(me) => {
      const yes = /^(yes|ja|evet|oui|sí|si)$/i, no = /^(no|nein|hayır|non)$/i;
      const rules = [
        [/sponsor/i, me.sponsorship], [/work.?(permit|authori)|right to work|arbeitserlaubnis/i, me.work_authorization],
        [/relocat/i, me.relocation],
      ];
      let n = 0;
      const groups = {};
      document.querySelectorAll('input[type=radio]').forEach(r => (groups[r.name] ||= []).push(r));
      for (const radios of Object.values(groups)) {
        if (radios.some(r => r.checked)) continue;
        const q = (radios[0].closest('fieldset, [role=radiogroup], .field, div')?.innerText || '').toLowerCase();
        const rule = rules.find(([re]) => re.test(q)); if (!rule || !rule[1]) continue;
        const want = /^no/i.test(rule[1]) ? no : yes;
        const pick = radios.find(r => want.test((r.labels?.[0]?.innerText || r.value || '').trim()));
        if (pick) { pick.click(); n++; }
      }
      // Required consent boxes (privacy policy / data processing). Approved by the user per package.
      document.querySelectorAll('input[type=checkbox]').forEach(c => {
        const t = (c.closest('label, div')?.innerText || '').toLowerCase();
        if (!c.checked && (c.required || c.getAttribute('aria-required') === 'true') &&
            /privacy|consent|agree|data protection|datenschutz|processing of (my )?(personal )?data|gdpr/.test(t)) { c.click(); n++; }
      });
      return n;
    }""", me)


def open_form(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    if page.locator("input[type=email], input[name*=mail i]").count():
        return
    # Job page first: follow the Apply link/button.
    for sel in ["a:has-text('Apply for this job')", "a:has-text('Apply now')", "a:has-text('Apply')",
                "button:has-text('Apply')", "a:has-text('Jetzt bewerben')", "a:has-text('Bewerben')"]:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.click()
            page.wait_for_timeout(3000)
            if page.locator("input[type=email], input[name*=mail i]").count():
                return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--url")
    ap.add_argument("--dry-run", action="store_true", help="fill but do not click submit")
    ap.add_argument("--chrome", help="use a local Chrome binary (testing)")
    a = ap.parse_args()

    pkg = load_json(APPS_DIR / f"{a.id}.json")
    if not pkg:
        out("failed", reason=f"package {a.id} not found")
    url = a.url or pkg["url"]
    if not SUPPORTED.search(url):
        out("manual", reason="Bu başvuru portalı otomatik gönderim için desteklenmiyor (hesap ya da özel form gerekiyor olabilir).")
    me = json.loads(os.environ.get("APPLICANT_JSON") or "{}")
    if not me.get("email"):
        out("failed", reason="APPLICANT_JSON secret eksik (e-posta yok).")

    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        docs, missing = doc_store(pkg, tmp)
        if "doc_cv" not in docs:
            out("manual", reason="CV repoda yok (private/cv.pdf.gpg) ya da DOCS_PASSPHRASE eksik.")
        browser = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
        page = browser.new_page(user_agent=UA, locale="en-US")
        page.expose_function("__jaFetch", py_fetch)
        page.add_init_script(shim_js(me, docs))
        page.add_init_script(path=str(ROOT / "userscript" / "job-autofill.user.js"))

        open_form(page, url)
        # Only an interactive CAPTCHA stops us; invisible ones (e.g. reCAPTCHA v3 on Greenhouse) are tried,
        # and the success check below catches a rejected submission.
        visible_captcha = page.locator(
            "iframe[src*='recaptcha/api2/anchor'], iframe[src*='recaptcha/enterprise/anchor'], "
            "iframe[src*='hcaptcha'], .cf-turnstile, .g-recaptcha:not([data-size=invisible]), .h-captcha").count()
        if visible_captcha:
            out("manual", reason="Sayfada CAPTCHA var.")
        if page.locator("input[type=password]").count():
            out("manual", reason="Başvuru için giriş yapmak/hesap açmak gerekiyor.")
        if not page.locator("input[type=email], input[name*=mail i]").count():
            out("manual", reason="Başvuru formu bulunamadı.")

        page.wait_for_function("typeof window.__jaFill === 'function'", timeout=15000)
        res = page.evaluate("id => window.__jaFill(id)", a.id)
        extra = answer_choices(page, me)
        page.wait_for_timeout(1500)

        # Anything required and still empty means we stop.
        empty = page.evaluate("""() => [...document.querySelectorAll('input, textarea, select')]
          .filter(el => (el.required || el.getAttribute('aria-required') === 'true') && !el.disabled)
          .filter(el => el.type === 'file' ? !(el.files && el.files.length)
                     : el.type === 'checkbox' ? !el.checked
                     : el.type === 'radio' ? !document.querySelector(`input[type=radio][name="${el.name}"]:checked`)
                     : !String(el.value || '').trim())
          .map(el => (el.labels?.[0]?.innerText || el.name || el.id || el.type).trim().slice(0, 60))""")
        info = {"filled": res.get("filled"), "uploaded": res.get("uploaded"), "choices": extra}
        if empty:
            out("manual", reason="Doldurulamayan zorunlu alanlar: " + "; ".join(sorted(set(empty))[:8]), **info)
        if a.dry_run:
            out("dry-run", reason="Form dolduruldu, gönderilmedi.", **info)

        btn = None
        for loc in [page.locator("button[type=submit], input[type=submit]"), page.get_by_role("button", name=SUBMIT_TEXT)]:
            if loc.count():
                btn = loc.last
                break
        if not btn:
            out("manual", reason="Gönder butonu bulunamadı.", **info)
        before = page.url
        btn.click()
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(3000)
        text = page.inner_text("body")[:5000]
        if SUCCESS.search(text) or (page.url != before and re.search(r"confirm|success|thank", page.url, re.I)):
            out("submitted", reason="Başvuru gönderildi, onay sayfası görüldü.", **info)
        err = re.search(r"(required|invalid|please (fill|enter|select)|error)[^\n]{0,80}", text, re.I)
        out("failed", reason="Gönderim onaylanmadı" + (f": {err.group(0)}" if err else "."), **info)


if __name__ == "__main__":
    main()
