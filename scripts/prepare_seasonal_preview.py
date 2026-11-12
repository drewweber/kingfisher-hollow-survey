"""Mark generated preview documents and keep their internal journeys on preview hosts."""
from pathlib import Path
import re

HOME = "https://seasonal-redesign-odd-flower-3d7b.drewweber.workers.dev"
SURVEY = "https://seasonal-chapters-2026-11-11.kingfisher-survey.pages.dev"
PUBLIC = Path(__file__).resolve().parents[1] / "public"

for path in PUBLIC.rglob("*.html"):
    # The field guide has a content-hashed offline manifest; leave its bytes intact.
    if path.relative_to(PUBLIC).parts[0] == "field":
        continue
    html = path.read_text()
    html = html.replace("</head>", '<meta name="robots" content="noindex, nofollow"></head>', 1)
    for original, replacement in [("https://www.kingfisher-hollow.com", HOME), ("https://survey.kingfisher-hollow.com", SURVEY)]:
        html = re.sub(r'(<a\b[^>]*\bhref=")' + re.escape(original), lambda m: m[1] + replacement, html)
    html = html.replace("</body>", '<aside aria-label="Review status" style="position:fixed;right:12px;bottom:10px;z-index:90;background:#f3f5f2;color:#18231e;border:1px solid #bdc9c0;border-radius:3px;padding:5px 9px;font:11px/1.4 system-ui;box-shadow:0 1px 5px #0001">Review preview</aside></body>', 1)
    if 'id="trigger-update"' in html:
        raise RuntimeError(f"Preview must not offer live refresh: {path}")
    path.write_text(html)
print("Prepared seasonal review routes; production hosts and refresh unchanged.")

headers = PUBLIC / "_headers"
existing = headers.read_text() if headers.exists() else ""
headers.write_text(existing + "\n/field/*\n  X-Robots-Tag: noindex, nofollow\n")
