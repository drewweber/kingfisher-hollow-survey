"""Static, progressively enhanced seasonal chapters for Kingfisher Hollow."""
from calendar import month_name
from datetime import date, datetime
from hashlib import sha256
from html import escape
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SEASONS = {
    'spring': ('Spring', [3,4,5], 'spring.webp', 'The pond and woodland seen from above in late spring.', 'May 25, 2026 · Property landscape'),
    'summer': ('Summer', [6,7,8], 'summer.webp', 'The pond surrounded by dense green woodland in summer.', 'June 24, 2025 · Property landscape'),
    'autumn': ('Autumn', [9,10,11], 'autumn.jpg', 'Gold and green woodland beneath a slate autumn sky.', 'Owner-provided landscape · Capture date unrecorded'),
    'winter': ('Winter', [12,1,2], 'winter.jpg', 'A dark creek meets the snow-covered pond among bare trees and conifers.', 'Owner-provided landscape · Capture date unrecorded'),
}
GROUP_ROUTES = {'Plants':('/plants/','plant'), 'Fungi':('/fungi/','fungal'), 'Mammals':('/mammals/','mammal'), 'Moths':('/moths/','moth'), 'Butterflies':('/butterflies/','butterfly'), 'Odonates':('/dragonflies/','dragonfly and damselfly'), 'Amphibians':('/herps/','amphibian and reptile')}


def esc(value):
    return escape(str(value if value is not None else ''), quote=True)


def safe_url(value):
    value = str(value or '')
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ''
    return value if parsed.scheme == 'https' and parsed.netloc and not parsed.username and not any(ord(c)<32 for c in value) else ''


def ident(value):
    return re.sub(r'[^a-zA-Z0-9_-]', '-', str(value)) or 'record'


def asset(name):
    path = ROOT / 'assets' / 'seasons' / name
    digest = sha256(path.read_bytes() if path.exists() else name.encode()).hexdigest()[:12]
    return f'/assets/seasons/{name}?v={digest}'


def pretty_date(value):
    try:
        return date.fromisoformat(str(value)[:10]).strftime('%B %-d, %Y')
    except (ValueError, TypeError):
        return str(value or 'Date unrecorded')


def base_chapter(key):
    label, months, *_ = SEASONS[key]
    return dict(key=key, label=label, months=f'{month_name[months[0]]}–{month_name[months[-1]]}', month_numbers=months, route=f'/seasons/{key}/', title=f'{label} at the Hollow', intro='A season of one place, read through its landscape and dated observations.', framing='This chapter is awaiting supporting seasonal records. Gaps in reporting do not establish absence.', passages=[], rows=[], coverage=[], source_years=[], as_of='', next_observation='Keep a dated photograph and a note of what you observed. Repeated visits help build the seasonal picture.', sources=[], bird_examples=[])


def nav(active, home_url):
    links=''.join(f'<a href="/seasons/{key}/"'+(' aria-current="page"' if key==active else '')+f'>{label}</a>' for key,(label,*_) in SEASONS.items())
    return f'''<a class="skip-link" href="#main">Skip to the story</a>
<header class="site-header"><a class="wordmark" href="{esc(home_url)}">Kingfisher Hollow<span>A living record of one place</span></a><a class="survey-link" href="/">Biodiversity survey <span aria-hidden="true">↗</span></a></header>
<nav class="season-nav" aria-label="Seasons"><a class="all-seasons" href="/seasons/"{' aria-current="page"' if not active else ''}>The seasons</a><div>{links}</div></nav>'''


def document(title, description, route, body, *, active, home_url, survey_url):
    canonical=survey_url.rstrip('/')+route
    image_name=SEASONS[active or 'autumn'][2]
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Kingfisher Hollow</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}"><meta property="og:type" content="website"><meta property="og:title" content="{esc(title)} · Kingfisher Hollow"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{esc(canonical)}"><meta property="og:image" content="{esc(survey_url.rstrip('/')+asset(image_name))}">
<meta name="theme-color" content="#f3f5f2"><link rel="preload" href="/assets/fonts/playfair-display-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin><link rel="preload" href="/assets/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{asset('seasonal.css')}"><script defer src="{asset('seasonal.js')}"></script></head>
<body class="season-{esc(active or 'hub')}">{nav(active,home_url)}<main id="main">{body}</main>
<footer class="site-footer"><a class="wordmark" href="{esc(home_url)}">Kingfisher Hollow</a><p>Look closely. Keep a record. Return through the seasons.</p><a href="/seasons/">All four seasons</a><a href="/life-list/">Complete life list</a></footer></body></html>'''


def landscape(key, *, eager=True):
    label, months, filename, alt, caption=SEASONS[key]
    return f'''<figure class="landscape"><div class="landscape-frame"><img src="{asset(filename)}" alt="{esc(alt)}" width="1280" height="720" loading="{'eager' if eager else 'lazy'}" decoding="async" {'fetchpriority="high"' if eager else ''}></div><figcaption>{esc(caption)}</figcaption></figure>'''


def selected_photo(records):
    return next((r for r in records if safe_url(r.get('photo_url')) and r.get('photo_credit') and r.get('photo_license')),None)


def dated_photo(records, record_id, months):
    """Use only an explicit reviewed voucher whose actual date fits the image role."""
    if record_id is None or not months:
        return None
    for record in records:
        if record.get('id') != record_id:
            continue
        try:
            observed = date.fromisoformat(str(record.get('date', '')))
        except (TypeError, ValueError):
            continue
        if observed.month in months and selected_photo([record]):
            return record
    return None


def opening_detail(chapter):
    record_id = chapter.get('opening_detail_record_id')
    for row in chapter.get('rows', []):
        record = dated_photo(row.get('records', []), record_id, chapter['month_numbers'])
        if not record:
            continue
        name = row.get('name', 'Seasonal observation')
        event = record.get('event_type') or 'Unspecified encounter'
        return f'''<figure class="opening-detail"><img src="{esc(safe_url(record['photo_url']))}" alt="{esc(name)} · {esc(event)}" width="281" height="500" decoding="async"><figcaption><span class="detail-kicker">A closer {esc(chapter["key"])} view</span><strong>{esc(name)}</strong><span>{esc(event)} · {esc(pretty_date(record['date']))}</span><small>{esc(record.get('photo_credit'))} · {esc(record.get('photo_license'))}</small><a href="#evidence-{ident(row['id'])}">Read the dated evidence ↘</a></figcaption></figure>'''
    return ''


def record_photo(record, name):
    if not record:
        return ''
    return f'''<figure class="detail-photo"><img src="{esc(safe_url(record.get('photo_url')))}" alt="{esc(name)} in the dated observation" loading="lazy" decoding="async" width="640" height="480"><figcaption><span class="photo-subject">{esc(name)} · {esc(record.get('event_type') or 'Unspecified encounter')}</span>{esc(pretty_date(record.get('date')))}<br>{esc(record.get('photo_credit'))} · {esc(record.get('photo_license'))}</figcaption></figure>'''


def passage_html(passage, rows, key, used_photos):
    pid=ident(passage.get('id'))
    matches=[r for r in rows if r.get('id') in passage.get('row_ids',[])]
    photo=None; photo_name=''
    for row in matches:
        candidate=dated_photo(row.get('records',[]), passage.get('photo_record_id'), [passage.get('phase_month')])
        if candidate and candidate.get('photo_url') not in used_photos:
            photo=candidate; photo_name=row.get('name','Observation'); used_photos.add(candidate['photo_url']); break
    links=''.join(f'<a href="#evidence-{ident(r["id"])}">{esc(r.get("name"))} <span aria-hidden="true">↘</span></a>' for r in matches)
    evidence=f'<div class="passage-links"><span>Behind this passage</span>{links}</div>' if links else ''
    look_for=f'<aside class="look-for"><h3>A closer look</h3><p>{esc(passage.get("look_for"))}</p></aside>' if passage.get('look_for') else ''
    return f'''<article class="passage {'with-photo' if photo else 'text-only'}" id="{pid}" tabindex="-1"><div class="passage-copy"><p class="eyebrow">{esc(passage.get('phase'))}</p><h2>{esc(passage.get('title'))}</h2><p>{esc(passage.get('body'))}</p>{look_for}{evidence}</div>{record_photo(photo,photo_name)}</article>'''


def month_axis(months):
    return '<div class="month-axis">'+''.join(f'<span>{esc(month_name[int(m)])}</span>' for m in months)+'</div>'


def marks(records):
    result=[]
    for r in records:
        try: position=max(0,min(1,float(r.get('position',0))))
        except (TypeError,ValueError): position=0
        result.append(f'<span class="record-mark" style="--position:{position*100:.4f}%"></span>')
    return '<div class="mark-track" aria-hidden="true">'+''.join(result)+'</div>'


def records_html(records):
    result=[]
    for r in records:
        quality={'needs_id':'Identification under review','research':'Research grade','casual':'Casual grade'}.get(r.get('quality'),'Identification status unrecorded')
        when=f'<time datetime="{esc(r.get("date"))}">{esc(pretty_date(r.get("date")))}</time>'
        url=safe_url(r.get('url'))
        link=f'<a href="{esc(url)}">{when} <span class="source-label">iNaturalist record ↗</span></a>' if url else when+'<span class="source-label">Source link unavailable</span>'
        result.append(f'<li data-record-period="{esc(r.get("period"))}">{link}<span>{esc(r.get("event_type") or "Unspecified encounter")}<small>{esc(quality)}</small></span><span class="record-period">{esc(r.get("period"))}</span></li>')
    return '<ul class="record-list">'+''.join(result)+'</ul>' if result else '<p>No supporting records are available for this account.</p>'


def evidence_html(chapter):
    """Keep curated vouchers accessible without presenting a shortlist as the community."""
    items=[]
    key=chapter['key']
    purpose={
        'spring':'spring-water reproduction, woodland plants, and spring insects',
        'summer':'water-margin animals, night-flying moths, and wetland plants',
        'autumn':'late flowers, wood fungi, and late-season insects',
        'winter':'sheltered insects and active mammals',
    }[key]
    for row in chapter.get('rows', []):
        rid=ident(row['id'])
        specialist=''
        if row.get('group') in GROUP_ROUTES:
            target,noun=GROUP_ROUTES[row['group']]
            context=quote(f'/seasons/{key}/#evidence-{rid}',safe='')
            specialist=f'<a href="{target}?from={context}">All-season {noun} records ↗</a>'
        items.append(f'<details class="voucher-row" id="evidence-{rid}"><summary>{esc(row.get("name"))}</summary>{records_html(row.get("records",[]))}{specialist}</details>')
    return f'''<details class="voucher-appendix" id="evidence"><summary>Selected observation sources</summary><p>These {len(items)} selected taxa offer local examples of {purpose}. They are examples, not a sample of the whole community. The community summary above uses all eligible seasonal iNaturalist records.</p>{''.join(items) or '<p>No supporting records in this register.</p>'}</details>'''


def community_html(chapter):
    community=chapter.get('community',{})
    if not community or not community.get('record_count'):
        return '<section class="community-section" id="community"><h2>The local record is still taking shape</h2><p>No eligible seasonal records are available for this summary yet.</p></section>'
    key=chapter['key']
    groups=community.get('groups',[])
    periods=community.get('periods',[])
    years=', '.join(str(p['period']) for p in periods)
    count=community['taxa_count']
    first=pretty_date(community.get('first_date'))
    latest=pretty_date(community.get('as_of'))
    if key=='winter':
        title='A season larger than its records'
        lead=f"Winter’s iNaturalist record is still small: {count:,} taxa across {community['reporting_days']} reporting days. It cannot describe the full winter community or tell us which groups are scarce. The chapter’s account of sheltered life and winter resources draws on natural history; local winter coverage remains a gap."
    else:
        title={'spring':'Many lives share the spring opening','summer':'Diversity across the summer community','autumn':'Life continues beyond the turning canopy'}[key]
        lead=f"The {key} iNaturalist record brings together {count:,} taxa across {len(groups)} broad groups. These are the organisms documented in that source through the available years, including provisional identifications. Each group opens a different view of the season; the unequal totals also reflect where and how often people looked."
    group_html=''.join(f'<li><span>{esc(g["label"])}</span><strong>{g["taxa_count"]:,}</strong></li>' for g in groups)
    breadth=f'<div class="community-breadth"><p class="data-label">Documented taxa · {esc(years)}</p><ul>{group_html}</ul></div>' if key!='winter' else ''
    moths=community.get('moths',{})
    moth_block=''
    if key=='summer' and moths.get('taxa_count'):
        family=f' across {moths["family_count"]} identified families' if moths.get('family_count') else ''
        comparisons=[m for m in moths.get('months',[])[1:] if m.get('shared_with_previous') is not None]
        overlap=''
        if comparisons:
            m=comparisons[-1]; previous=12 if m['month']==1 else m['month']-1
            overlap=f"Of the {m['taxa_count']:,} moth taxa recorded in {month_name[m['month']]}, {m['shared_with_previous']:,} also have {month_name[previous]} records; {m['only_this_month']:,} do not. This describes a changing set of recorded taxa, not arrivals, departures, or a measured change in abundance."
        moth_block=f'''<div class="assemblage"><p class="eyebrow">The moth community</p><h3>Hundreds of life histories, sharing a season</h3><p>The summer records contain {moths['taxa_count']:,} moth taxa{family}. Their larvae use different foods and their life cycles do not follow a single summer schedule.</p><p>{esc(overlap)}</p><p class="quiet">Months pool all available years. Uneven observation effort and different years represented can also change which moths appear in the record.</p><a href="/moths/?from={quote('/seasons/summer/#community',safe='')}">Explore the complete moth inventory ↗</a></div>'''
    moth_month_rows=''.join(f'<tr><th scope="row">{month_name[m["month"]]}</th><td>{m["taxa_count"]:,}</td><td>{m.get("reporting_days",0):,}</td><td>{esc(", ".join(str(y) for y in m.get("source_years",[]))) or "None"}</td></tr>' for m in moths.get('months',[]))
    moth_coverage=f'<table><caption>Moth coverage behind the month comparison</caption><thead><tr><th scope="col">Month</th><th scope="col">Taxa</th><th scope="col">Reporting days</th><th scope="col">Years</th></tr></thead><tbody>{moth_month_rows}</tbody></table>' if key=='summer' else ''
    month_rows=''.join(f'<tr><th scope="row">{month_name[m["month"]]}</th><td>{m["taxa_count"]:,}</td><td>{m["reporting_days"]:,}</td></tr>' for m in community.get('months',[]))
    period_rows=''.join(f'<tr><th scope="row">{esc(p["period"])}</th><td>{p["taxa_count"]:,}</td><td>{p["reporting_days"]:,}</td><td>{p.get("moth_taxa_count",0):,}</td></tr>' for p in periods)
    group_rows=''.join(f'<tr><th scope="row">{esc(g["label"])}</th><td>{g["taxa_count"]:,}</td><td>{g.get("reporting_days", "—")}</td></tr>' for g in groups)
    return f'''<section class="community-section" id="community"><div class="community-intro"><p class="eyebrow">The recorded community</p><h2>{title}</h2><p>{esc(lead)}</p><p class="quiet community-scope">iNaturalist records · Bird observations are tracked separately in <a href="/birds/">the eBird-based bird inventory</a>.</p></div>{breadth}{moth_block}<details class="community-methods"><summary>Years, coverage &amp; what these counts mean</summary><p>All eligible iNaturalist property records dated {esc(first)}–{esc(latest)} contribute to this seasonal summary. Birds are tracked separately through eBird; the bird life list does not measure seasonal frequency.</p><p>“Taxa” counts distinct species-level or finer identification IDs, including provisional identifications. Species and subspecies may have separate IDs, so these are not normalized species totals. Captive, future-dated, invalid-date and duplicate records are excluded. Coarser identifications contribute to reporting days, but not taxon counts. Totals describe documented breadth, not abundance or a complete census.</p><p>A reporting day has at least one eligible observation; it is not a visit or a measure of search time. Months pool the available years. Monthly and yearly totals overlap and must not be added together. Missing records do not establish absence.</p><div class="coverage-tables">{moth_coverage}<table><caption>Calendar months, all available years</caption><thead><tr><th scope="col">Month</th><th scope="col">Taxa</th><th scope="col">Reporting days</th></tr></thead><tbody>{month_rows}</tbody></table><table><caption>Contributing seasonal periods</caption><thead><tr><th scope="col">Period</th><th scope="col">Taxa</th><th scope="col">Reporting days</th><th scope="col">Moth taxa</th></tr></thead><tbody>{period_rows}</tbody></table><table><caption>Coverage by group · dates with records of the taxa counted</caption><thead><tr><th scope="col">Group</th><th scope="col">Taxa</th><th scope="col">Reporting days</th></tr></thead><tbody>{group_rows}</tbody></table></div><p><a href="/life-list/?from={quote('/seasons/'+key+'/#community',safe='')}">Browse the complete life list and source records ↗</a></p></details></section>'''


def chapter_body(chapter):
    key=chapter['key']; label=SEASONS[key][0]
    used_photos=set()
    title=chapter.get('title','')
    subtitle=f'<p class="opening-title">{esc(title)}</p>' if title not in ('', f'{label} at Kingfisher Hollow', f'{label} at the Hollow') else ''
    passage_links=''.join(f'<a href="#{ident(p["id"])}">{esc(p.get("phase") or p.get("title"))}</a>' for p in chapter.get('passages',[]))
    passages=''.join(passage_html(p,chapter.get('rows',[]),key,used_photos) for p in chapter.get('passages',[]))
    sources=''.join(f'<li><a href="{esc(safe_url(s.get("url")))}">{esc(s.get("label"))} ↗</a></li>' for s in chapter.get('sources',[]) if safe_url(s.get('url')))
    source_block=f'<details class="reading-sources"><summary>Sources & further reading</summary><ul>{sources}</ul></details>' if sources else ''
    birds=''
    if chapter.get('bird_examples'):
        examples=''.join(f'<li><a href="{esc(safe_url(b.get("url")))}">{esc(b.get("name"))} · {esc(pretty_date(b.get("date")))}</a><p>{esc(b.get("note"))}</p></li>' for b in chapter['bird_examples'] if safe_url(b.get('url')))
        birds=f'<section class="bird-examples"><h2>Checklist glimpses</h2><p>These eBird checklists are individual illustrations, separate from the iNaturalist calendar. They are not comprehensive seasonal bird coverage.</p><ul>{examples}</ul></section>'
    keys=list(SEASONS); following=keys[(keys.index(key)+1)%4]
    context=quote(f'/seasons/{key}/#next-observation',safe='')
    return f'''<section class="chapter-opening"><div class="opening-copy"><p class="eyebrow">{esc(chapter.get('months'))} · Through the recorded years</p><h1>{label}<span>at the Hollow</span></h1>{subtitle}<p class="intro">{esc(chapter.get('intro'))}</p></div>{landscape(key)}</section><nav class="chapter-contents" aria-label="In this chapter"><span>Read the season</span>{passage_links}<a href="#community">The local community</a><a href="#next-observation">A next observation</a></nav><div class="story">{passages}</div>{community_html(chapter)}{evidence_html(chapter)}<section class="next-observation" id="next-observation"><p class="eyebrow">Carry the question outside</p><h2>A next observation</h2><p>{esc(chapter.get('next_observation'))}</p><a href="/field/?from={context}">Open the complete field guide ↗</a>{source_block}</section><a class="next-season" href="/seasons/{following}/"><span>Keep reading through the year</span><strong>Continue into {following}</strong><span aria-hidden="true">→</span></a>'''


def hub_body(chapters):
    current_month=datetime.now(ZoneInfo('America/New_York')).month
    features=[]
    for key,(label,months,*_) in SEASONS.items():
        c=chapters[key]; current=' · Current calendar season' if current_month in months else ''
        features.append(f'''<article class="season-feature season-{key}"><a class="season-feature-image" href="/seasons/{key}/" aria-label="Explore {key}">{landscape(key,eager=False)}</a><div><p class="eyebrow">{esc(c.get('months'))}{current}</p><h2><a href="/seasons/{key}/">{label} <span aria-hidden="true">↗</span></a></h2><p>{esc(c.get('intro'))}</p><a class="text-link" href="/seasons/{key}/">Read the {key} chapter</a></div></article>''')
    return f'''<section class="hub-opening"><p class="eyebrow">Kingfisher Hollow · Seasonal field stories</p><h1>One place.<br>A changing year.</h1><p>Light, water, leaves, and shelter connect the Hollow’s woodland, creek, pond, and edges. Follow the communities that grow, feed, reproduce, and find refuge as those conditions change through the year.</p></section><div class="season-features">{''.join(features)}</div><aside class="hub-note"><h2>A living, uneven record</h2><p>These chapters bring together dated encounters across the available years. Some parts of the season are better documented than others. Each story keeps its sources close, and leaves room for what we have yet to notice.</p><a href="/">Explore the full biodiversity survey ↗</a></aside>'''


def write_seasonal_pages(chapters, output_dir, *, home_url='https://www.kingfisher-hollow.com', survey_url='https://survey.kingfisher-hollow.com'):
    """Write hub and four canonical chapters without mutating their source data."""
    complete={key:{**base_chapter(key),**chapters.get(key,{}),'key':key,'route':f'/seasons/{key}/'} for key in SEASONS}
    pages=[('/seasons/', 'The seasons', 'Four seasonal stories from Kingfisher Hollow, with dated observations across the years.',hub_body(complete),None)]
    pages.extend((f'/seasons/{key}/',f'{SEASONS[key][0]} at the Hollow',c.get('intro',''),chapter_body(c),key) for key,c in complete.items())
    written=[]
    for route,title,description,body,key in pages:
        target=Path(output_dir)/route.strip('/')/'index.html'; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(document(title,description,route,body,active=key,home_url=home_url,survey_url=survey_url),encoding='utf-8'); written.append(target)
    return written
