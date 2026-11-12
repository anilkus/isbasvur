"""Shared helpers: paths, profile loading, scoring, text cleanup."""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "profile"
DATA_DIR = ROOT / "docs" / "data"
APPS_DIR = DATA_DIR / "applications"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_profile():
    return load_json(PROFILE_DIR / "profile.json")


def load_cv():
    return (PROFILE_DIR / "cv.md").read_text(encoding="utf-8")


def strip_html(text):
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def slugify(text, maxlen=60):
    text = text.lower()
    for a, b in {"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"}.items():
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:maxlen].strip("-") or "job"


def _count(term, text):
    return len(re.findall(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text))


def score_job(job, profile):
    """Return (score 0-100, matched keywords). Title hits weigh more than body hits."""
    kw = profile["keywords"]
    title = (job.get("title") or "").lower()
    body = (job.get("description") or "").lower()
    loc = (job.get("location") or "").lower() + " " + body[:400]

    raw, matched = 0, []
    for term in kw["strong"]:
        t, b = _count(term, title), min(_count(term, body), 3)
        if t or b:
            raw += 14 * t + 4 * b
            matched.append(term)
    for term in kw["medium"]:
        t, b = _count(term, title), min(_count(term, body), 3)
        if t or b:
            raw += 6 * t + 2 * b
            matched.append(term)
    for role in profile["target_roles"]:
        if role in title:
            raw += 15
    for term in kw["negative"]:
        if term in title:
            raw -= 40
    if any(p in loc for p in profile["preferred_locations"]):
        raw += 8

    score = max(0, min(100, raw))
    return score, matched


# Words and phrases that make text read as machine-written.
BANNED = [
    "delve", "leverage", "tapestry", "testament", "passionate", "thrilled",
    "excited to apply", "i am writing to express", "furthermore", "moreover",
    "in today's", "fast-paced", "dynamic team", "synergy", "cutting-edge",
    "seamless", "embark", "realm", "navigate the", "unwavering", "spearhead",
    "game-changer", "it is worth noting", "in conclusion", "esteemed",
    "honed", "eager to", "innovative", "solid grounding", "equips me", "aligns with",
    "i am confident", "unique opportunity", "invaluable", "robust understanding", "deeply",
    "showcase", "foster", "pivotal", "commitment to excellence", "look forward to the opportunity",
]


def humanize(text):
    """Deterministic cleanup on top of the model's own style instructions."""
    if not isinstance(text, str):
        return text
    text = re.sub("[‐‑­]", "-", text)  # unicode hyphens -> plain hyphen
    text = re.sub(r"\s*[—–]\s*", ", ", text)  # em/en dash -> comma
    text = re.sub(r"\s+--\s+", ", ", text)
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def ai_flags(text):
    low = (text or "").lower()
    return [w for w in BANNED if w in low]


# Application portals the headless submitter can handle (no login wall).
SUPPORTED_FORMS = re.compile(
    r"greenhouse\.io|lever\.co|ashbyhq\.com|workable\.com|personio\.(de|com)|smartrecruiters\.com|"
    r"recruitee\.com|teamtailor\.com|join\.com|bamboohr\.com")


def resolve_apply_url(url, session=None):
    """Follow the job board's Apply link to the employer's real application page."""
    import requests
    s = session or requests.Session()
    candidates = [url.rstrip("/") + "/apply"] if "arbeitnow." in url else [url]
    for c in candidates:
        try:
            r = s.get(c, headers={"User-Agent": UA}, timeout=20, allow_redirects=True)
            if r.url and r.url != c:
                return r.url.split("?utm_")[0]
            if SUPPORTED_FORMS.search(r.url or ""):
                return r.url
        except Exception:
            pass
    return url

