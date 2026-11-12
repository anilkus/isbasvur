"""Render a package's cover letter as a clean one-page PDF.

The public copy (docs/data/applications/<id>-cover-letter.pdf) has no email/phone,
because the repo is public. The email draft uses a private copy with CONTACT_LINE.
"""
import datetime as dt
import os
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from common import load_profile

FONT, BOLD = "Helvetica", "Helvetica-Bold"
for base in ["/usr/share/fonts/truetype/dejavu"]:  # Turkish characters need a TTF font
    if Path(base, "DejaVuSans.ttf").exists():
        pdfmetrics.registerFont(TTFont("DejaVu", f"{base}/DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", f"{base}/DejaVuSans-Bold.ttf"))
        FONT, BOLD = "DejaVu", "DejaVu-Bold"


def render(pkg, out_path, contact_line=""):
    profile = load_profile()
    links = profile["links"]
    body = ParagraphStyle("b", fontName=FONT, fontSize=10.5, leading=15, spaceAfter=8)
    name = ParagraphStyle("n", fontName=BOLD, fontSize=15, leading=18)
    small = ParagraphStyle("s", fontName=FONT, fontSize=9, leading=12, textColor="#555555")

    contact = " · ".join(x for x in [contact_line, links.get("website"), links.get("linkedin")] if x)
    job = pkg.get("job") or {}
    story = [
        Paragraph(escape(profile["name"]), name),
        Paragraph(escape(profile["headline"]), small),
        Paragraph(escape(contact), small),
        Spacer(1, 10 * mm),
        Paragraph(dt.date.today().strftime("%d %B %Y"), body),
        Paragraph(escape(f"Re: {job.get('title', '')}"
                         + (f" ({pkg['application']['reference_code']})"
                            if (pkg.get('application') or {}).get('reference_code') else "")), body),
        Spacer(1, 3 * mm),
    ]
    for para in (pkg.get("cover_letter") or "").split("\n\n"):
        story.append(Paragraph(escape(para.strip()).replace("\n", "<br/>"), body))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                      topMargin=20 * mm, bottomMargin=18 * mm,
                      title=f"Cover letter - {profile['name']}", author=profile["name"]).build(story)
    return out_path


if __name__ == "__main__":
    import json
    import sys
    pkg = json.load(open(sys.argv[1], encoding="utf-8"))
    print(render(pkg, sys.argv[2], os.environ.get("CONTACT_LINE", "")))
