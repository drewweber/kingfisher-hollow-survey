"""Mark a generated static review build and retain same-site review links."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit


def prepare(public: Path, survey_url: str) -> int:
    parsed = urlsplit(survey_url)
    if (parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith(".kingfisher-survey.pages.dev")
            or parsed.username or parsed.password or parsed.port
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Expected an HTTPS kingfisher-survey.pages.dev preview host")
    survey_url = survey_url.rstrip("/")
    pages = list(public.rglob("*.html"))
    for path in pages:
        if 'id="trigger-update"' in path.read_text():
            raise ValueError("Rebuild with KH_REVIEW_PREVIEW=1 before preparing a review")
    count = 0
    for path in pages:
        # Offline field-guide documents participate in a content-hashed manifest.
        if path.relative_to(public).parts[0] == "field":
            continue
        html = path.read_text()
        if 'name="robots"' not in html:
            html = html.replace("</head>", '<meta name="robots" content="noindex, nofollow"></head>', 1)
        html = re.sub(r'(<a\b[^>]*\bhref=")https://survey\.kingfisher-hollow\.com(?=[/"?#])',
                      lambda match: match[1] + survey_url, html)
        if 'aria-label="Review status"' not in html:
            html = html.replace("</body>", '<aside aria-label="Review status" style="position:fixed;right:12px;bottom:10px;z-index:90;background:#f3f5f2;color:#18231e;border:1px solid #bdc9c0;border-radius:3px;padding:5px 9px;font:11px/1.4 system-ui">Review preview</aside></body>', 1)
        path.write_text(html)
        count += 1
    headers = public / "_headers"
    existing = headers.read_text() if headers.exists() else ""
    rule = "/*\n  X-Robots-Tag: noindex, nofollow\n"
    if rule not in existing:
        headers.write_text(existing + "\n" + rule)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--survey-url", required=True)
    parser.add_argument("--public", type=Path, default=Path(__file__).resolve().parents[1] / "public")
    args = parser.parse_args()
    print(f"Prepared {prepare(args.public, args.survey_url)} static review documents.")
