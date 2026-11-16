"""Publish complete chart tables as bounded, script-free HTML documents.

Only the markup contract emitted by viz._with_data is parsed here. The report
keeps a small preview in each disclosure; all original rows remain accessible
through ordinary pagination links, without growing the survey's initial DOM.
"""
from html import escape, unescape
from pathlib import Path
import hashlib
import re

PREVIEW_ROWS = 12
PAGE_ROWS = 100
_DETAILS = re.compile(r'<details data-chart-table\b[^>]*>.*?</details>', re.S)
_ROWS = re.compile(r'<tr\b[^>]*>.*?</tr>', re.S)


def publish_tables(markup: str, public_dir: Path, back_url: str, back_label=None, stylesheet="/assets/survey.css") -> str:
    """Write full tables and replace only large inline bodies with previews."""
    back_label = back_label or ('Overview' if back_url == '/' else back_url.strip('/').title())

    def publish(match):
        details = match.group()
        body = re.search(r'<tbody>(.*?)</tbody>', details, re.S)
        rows = _ROWS.findall(body[1])
        if len(rows) <= PREVIEW_ROWS:
            return details
        caption = re.search(r'<caption id="([^"]+)"[^>]*>(.*?)</caption>', details, re.S)
        table_id, title = caption.groups()
        description = re.search(r'data-chart-description="([^\"]*)"', details)
        summary = escape(unescape(description[1])) if description else ""
        table_open = details[details.index('<table '):body.start()]
        total_pages = (len(rows) + PAGE_ROWS - 1) // PAGE_ROWS
        route_key = hashlib.sha256(back_url.encode()).hexdigest()[:8]
        directory = f'{table_id}-{route_key}'
        target = public_dir / 'chart-data' / directory
        target.mkdir(parents=True, exist_ok=True)

        for page_index in range(total_pages):
            number = page_index + 1
            first = page_index * PAGE_ROWS
            page_rows = rows[first:first + PAGE_ROWS]
            links = []
            if number > 1:
                links.append(f'<a href="{number - 1:03}.html" class="underline py-3">Previous page</a>')
            links.append(f'<span aria-current="page">Page {number} of {total_pages}</span>')
            if number < total_pages:
                links.append(f'<a href="{number + 1:03}.html" class="underline py-3">Next page</a>')
            nav = '<nav aria-label="Table pages" class="flex flex-wrap items-center gap-6 my-6">' + ''.join(links) + '</nav>'
            table = table_open + '<tbody>' + ''.join(page_rows) + '</tbody></table>'
            # Full data pages use a light surface regardless of the source card.
            table = table.replace('bg-hollow-950', 'bg-white').replace('border-white/10', 'border-stone-200')
            html = (
                '<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>{title} · Page {number} | Kingfisher Hollow</title>'
                '<meta name="robots" content="noindex">'
                f'<link rel="stylesheet" href="{escape(stylesheet, quote=True)}"></head>'
                '<body data-mode="all" class="bg-stone-50 text-hollow-900 font-sans">'
                '<main class="max-w-6xl mx-auto p-5 md:p-10">'
                f'<a class="inline-block underline py-3" href="{escape(back_url, quote=True)}#{table_id}-summary">Back to {escape(back_label)}</a>'
                f'<h1 class="text-2xl font-serif mt-4">{title}</h1>'
                f'<p class="mt-4 text-pretty">{summary}</p>'
                f'<p class="mt-4">Rows {first + 1:,}–{first + len(page_rows):,} of {len(rows):,}. '
                'Values match the chart data. Scroll the table to read all columns.</p>'
                f'{nav}<div tabindex="0" role="region" aria-labelledby="{table_id}" '
                f'class="max-h-[70vh] overflow-auto bg-white p-3">{table}</div>{nav}'
                '</main></body></html>'
            )
            (target / f'{number:03}.html').write_text(html, encoding='utf-8')
        link = (f'<p class="my-3 text-sm">Showing the first {PREVIEW_ROWS} of {len(rows):,} rows. '
                f'<a class="underline inline-block py-2" href="/chart-data/{directory}/001.html">'
                f'Read all {len(rows):,} rows of {title.lower()}</a>.</p>')
        preview = details[:body.start(1)] + ''.join(rows[:PREVIEW_ROWS]) + details[body.end(1):]
        return preview.replace('</summary>', '</summary>' + link, 1)

    return _DETAILS.sub(publish, markup)
