#!/usr/bin/env python3
"""Build the Kingfisher Hollow biodiversity report as a single branded page
(public/index.html), styled to match kingfisher-hollow.com and composed like an
editorial infographic. Charts come from viz.py; this module owns the page shell,
typography, and the photo/table/showcase sections.

Deploy: changes to this file pushed to main trigger .github/workflows/update.yml
(sync + build + Cloudflare Pages deploy). public/index.html is gitignored and
built by CI — never deploy it by hand."""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import analyze  # noqa: E402
import inat_api  # noqa: E402
import viz  # noqa: E402
import weather  # noqa: E402
from config import MY_USERNAME, PROPERTY_PROJECT_ID, PUBLIC_DIR  # noqa: E402
from db import connect, init_db  # noqa: E402

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"
SITE = "https://www.kingfisher-hollow.com"
PROJECT_URL = "https://www.inaturalist.org/projects/kingfisher-hollow-biodiversity-survey"
TAXON_URL = "https://www.inaturalist.org/taxa/"   # + taxon_id → species page
OBS_URL   = "https://www.inaturalist.org/observations/"  # + obs_id → observation
HERO_PHOTO = f"{SITE}/aerial/dji_fly_20251020_173830_305_1760996794506_photo_optimized.JPG"

# Belted Kingfisher mark, lifted from the main site for visual continuity.
LOGO = """<svg class="w-9 h-9 flex-shrink-0" viewBox="0 0 40 40" fill="none">
<path d="M19 11l-1.2-4 1.4 2.2-.4-4.5 1.6 3.2.6-4.2 1 3.5 1.4-3.2.2 3.2 1.2-2.2-.2 3" stroke="#5b8fa8" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="#5b8fa8"/>
<ellipse cx="22" cy="12.5" rx="5" ry="4" fill="#5b8fa8"/>
<path d="M18.5 11.5h6v1.2h-6z" fill="white" opacity="0.4"/>
<circle cx="23.5" cy="11.8" r="1.3" fill="#1a2332"/><circle cx="23.9" cy="11.5" r="0.4" fill="white"/>
<path d="M27 12l8.5.8L27 14z" fill="#3a4a56"/>
<path d="M13 16c-1.5 3-2 7-1 10 .8 2.5 3 4 6 4.2h4c3.5-.5 6-3 6-6.5 0-3.5-1.5-6.5-4-8l-5-1.5c-3-.3-5 .5-6 1.8z" fill="#5b8fa8"/>
<path d="M14.5 19c1-2 3-3.5 5.5-3.5l3 .5c-2 1-3.5 3-4 5.5l-2.5-1c-1-.3-1.7-1-2-1.5z" fill="#4a7a90" opacity="0.5"/>
<path d="M15 24c.3-2.5 2-4.5 4.5-5h3.5c2.2 0 3.8 1.5 4 3.8.2 2.5-1.5 5-4 5.5h-3.5c-3 0-4.8-1.8-4.5-4.3z" fill="#edf2f7"/>
<path d="M15.5 21.5h10.5v2.2H15.5z" fill="#5b8fa8" opacity="0.7"/>
<path d="M12.5 25l-5 2.5.5-4z" fill="#4a7a90"/></svg>"""


def sval(x, default=""):
    """Pandas NaN is truthy, so `series_value or fallback` silently keeps NaN.
    This collapses NaN/None to a default for safe `sval(a) or sval(b)` chains."""
    if x is None:
        return default
    try:
        if x != x:                      # NaN
            return default
    except (TypeError, ValueError):
        pass
    return x


def esc(x):
    return ("" if x is None else str(sval(x))).replace("&", "&amp;").replace(
        "<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def fdate(x, fmt="%b %-d, %Y"):
    try:
        return x.strftime(fmt)
    except (ValueError, AttributeError):
        return ""


def _num(x):
    """Render numeric cells, blanking out NaN."""
    try:
        if x != x:                      # NaN
            return ""
        return f"{int(x):,}"
    except (ValueError, TypeError):
        return esc(x)


def taxon_link(taxon_id, text, cls=""):
    """Link a species name to its iNaturalist taxon page ('investigate further')."""
    tid = sval(taxon_id)
    if tid in ("", None) or tid != tid:
        return esc(text)
    cls_attr = f' class="{cls}"' if cls else ""
    return (f'<a href="{TAXON_URL}{int(tid)}" target="_blank" rel="noopener"'
            f'{cls_attr}>{esc(text)}</a>')


# ── section scaffold ────────────────────────────────────────────────────────
def section(id_, eyebrow, title_html, body, intro="", dark=False, tint=""):
    bg = "bg-hollow-950" if dark else (tint or "")
    eb = "text-hollow-400" if dark else "text-hollow-500"
    tc = "text-white" if dark else "text-stone-900"
    ic = "text-white/55" if dark else "text-stone-500"
    intro_html = (f'<p class="{ic} text-[1.05rem] leading-relaxed max-w-2xl '
                  f'mx-auto mt-5">{intro}</p>') if intro else ""
    return f"""
<section id="{id_}" class="reveal py-24 px-6 {bg}">
  <div class="max-w-6xl mx-auto">
    <div class="text-center mb-14">
      <p class="{eb} font-medium tracking-[0.25em] uppercase text-xs mb-4">{eyebrow}</p>
      <span class="rule block mx-auto mb-6"></span>
      <h2 class="font-serif text-4xl md:text-5xl {tc} font-bold leading-tight">{title_html}</h2>
      {intro_html}
    </div>
    {body}
  </div>
</section>"""


def chart_card(html, note="", dark=False):
    # Dark-themed charts have light text/lines, so they must sit on a dark card.
    if dark:
        wrap = "bg-white/[0.04] border border-white/10 rounded-2xl p-5 md:p-7"
        note_cls = "text-white/40"
    else:
        wrap = "bg-white border border-stone-100 rounded-2xl p-5 md:p-7 shadow-sm"
        note_cls = "text-stone-400"
    note_html = (f'<p class="{note_cls} text-xs mt-4 italic">{note}</p>'
                 if note else "")
    return f'<div class="{wrap}">{html}{note_html}</div>'


def takeaway(text, dark=False):
    """A plain-language 'what this shows' callout under a chart — sci-comm
    interpretation so a curious non-scientist gets the point without decoding."""
    if dark:
        border, badge, body = "border-hollow-400", "text-hollow-300", "text-white/70"
        bg = "bg-white/[0.04]"
    else:
        border, badge, body = "border-hollow-500", "text-hollow-600", "text-stone-600"
        bg = "bg-hollow-50"
    return (f'<div class="mt-6 mb-10 max-w-2xl mx-auto border-l-2 {border} {bg} rounded-r-lg px-5 py-4">'
            f'<span class="{badge} text-[0.62rem] font-semibold tracking-[0.18em] uppercase">'
            f'What this shows</span>'
            f'<p class="{body} text-[0.97rem] leading-relaxed mt-1.5">{text}</p></div>')


# ── hero ─────────────────────────────────────────────────────────────────────
def hero(s, county_firsts):
    def stat(num, label):
        return (f'<div class="text-center"><div class="font-serif text-4xl '
                f'md:text-5xl font-bold text-white">{num}</div>'
                f'<div class="text-hollow-200/80 text-[0.7rem] md:text-xs mt-1 '
                f'uppercase tracking-[0.18em]">{label}</div></div>')
    rng = f"{fdate(s['first_obs'], '%b %Y')} – {fdate(s['latest_obs'], '%b %Y')}"
    return f"""
<section class="relative min-h-[88vh] flex items-center justify-center overflow-hidden">
  <div class="absolute inset-0">
    <img src="{HERO_PHOTO}" class="absolute inset-0 w-full h-full object-cover" alt="Aerial view of Kingfisher Hollow">
    <div class="hero-overlay absolute inset-0"></div>
  </div>
  <div class="relative z-10 text-center px-6 max-w-4xl mx-auto pt-24 md:pt-36">
    <p class="fade-up text-hollow-300 font-medium tracking-[0.35em] uppercase text-xs md:text-sm mb-5">Biodiversity Survey · {esc(rng)}</p>
    <h1 class="fade-up delay-1 font-serif text-5xl md:text-7xl text-white font-bold leading-[1.05] mb-6">
      Life at <em class="font-normal text-hollow-200" style="font-style:italic;">the Hollow</em>
    </h1>
    <p class="fade-up delay-2 text-white/70 text-lg md:text-xl max-w-xl mx-auto leading-relaxed mb-12">
      {s['species']:,} species across 30 riparian acres in Tioga County, NY — {county_firsts:,} of them new to the county record. The survey is a year old and still nowhere near done.
    </p>
    <div class="fade-up delay-3 flex flex-wrap items-center justify-center gap-8 md:gap-12">
      {stat(f"{s['species']:,}", "Species")}
      <div class="w-px h-12 bg-white/20"></div>
      {stat(f"{s['observations']:,}", "Observations")}
      <div class="w-px h-12 bg-white/20"></div>
      {stat(f"{s['observers']:,}", "Observers")}
      <div class="w-px h-12 bg-white/20"></div>
      {stat(f"{county_firsts:,}", "County firsts")}
    </div>
  </div>
  <div class="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1.5 text-white/40 animate-bounce">
    <span class="text-[10px] tracking-[0.25em] uppercase">Explore</span>
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
  </div>
</section>"""


# ── what's new ───────────────────────────────────────────────────────────────
def whats_new_body(recent):
    if recent.empty:
        return ('<p class="text-center text-stone-500">No new observations in '
                'the last couple of days.</p>')
    new_species = recent[recent["is_new_for_property"]]
    cards = []
    for _, r in new_species.head(8).iterrows():
        name = esc(sval(r.get("common_name")) or sval(r.get("taxon_name")) or "Unidentified")
        sci = esc(r.get("taxon_name"))
        who = esc(sval(r.get("user_name")) or sval(r.get("user_login")))
        state_n = r.get("state_obs_count")
        flag = ""
        if r.get("is_county_first") == 1:
            flag = '<span class="badge badge-accent">County first</span>'
        elif state_n == state_n and state_n is not None and state_n <= 25:
            flag = f'<span class="badge badge-green">{int(state_n)} in NY</span>'
        photo = r.get("photo_url")
        img = (f'<img src="{esc(photo)}" class="w-full aspect-square object-cover" alt="{name}">'
               if photo == photo and photo else
               '<div class="w-full aspect-square bg-hollow-100 flex items-center justify-center text-hollow-400 text-3xl">🪶</div>')
        cards.append(f"""
        <a href="{esc(r.get('url') or '#')}" target="_blank" rel="noopener" class="lift block bg-white border border-stone-100 rounded-2xl overflow-hidden shadow-sm">
          <div class="relative">{img}<div class="absolute top-3 left-3">{flag}</div></div>
          <div class="p-5">
            <div class="text-hollow-600 text-[0.65rem] font-semibold tracking-[0.15em] uppercase mb-1">New for the property</div>
            <div class="font-serif text-lg font-bold text-stone-900 leading-snug">{name}</div>
            <div class="text-stone-400 text-sm italic">{sci}</div>
            <div class="text-stone-500 text-xs mt-2">{fdate(r.get('observed_on'))} · {who}</div>
          </div>
        </a>""")
    lead = (f'<p class="text-center text-stone-500 mb-10 -mt-6">'
            f'<strong class="text-hollow-600">{len(new_species)}</strong> new species added to the Kingfisher Hollow list · '
            f'from <strong class="text-stone-700">{len(recent)}</strong> recent observations</p>')
    if not cards:
        return lead + ('<p class="text-center text-stone-400">No brand-new '
                       'species in this batch — but the count keeps climbing.</p>')
    return lead + ('<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">'
                   + "".join(cards) + "</div>")


# ── county-first showcase ────────────────────────────────────────────────────
def showcase_body(show):
    if show.empty:
        return ('<p class="text-center text-stone-500">County-first records will '
                'appear here once stats finish caching.</p>')
    cards = []
    for _, r in show.iterrows():
        name = esc(r["label"])
        sci = esc(r.get("taxon_name") or "")
        state_n = r.get("state_obs_count")
        ny = f"{int(state_n)} in all of NY" if state_n == state_n else ""
        photo = r.get("photo_url")
        img = (f'<img src="{esc(photo)}" class="photo-img w-full h-full object-cover" alt="{name}">'
               if photo == photo and photo else
               '<div class="w-full h-full bg-gradient-to-br from-hollow-200 to-hollow-400 flex items-center justify-center text-white/70 text-4xl">🪶</div>')
        tid = sval(r.get("taxon_id"))
        href = f"{TAXON_URL}{int(tid)}" if tid not in ("", None) and tid == tid else "#"
        cards.append(f"""
        <a href="{href}" target="_blank" rel="noopener" class="photo-card relative rounded-2xl overflow-hidden block" style="height:300px;">
          <div class="absolute inset-0 overflow-hidden">{img}</div>
          <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/15 to-transparent"></div>
          <div class="absolute top-3 left-3"><span class="badge badge-accent">County first</span></div>
          <div class="absolute bottom-0 inset-x-0 p-5">
            <div class="font-serif text-xl font-bold text-white leading-snug">{name}</div>
            <div class="text-white/70 text-sm italic">{sci}</div>
            <div class="text-hollow-300 text-xs mt-1.5 font-medium">{ny}</div>
          </div>
        </a>""")
    return ('<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">'
            + "".join(cards) + "</div>")


# ── rarest finds ─────────────────────────────────────────────────────────────
def rarest_body(rare):
    if rare.empty:
        return '<p class="text-center text-stone-500">Stats still caching.</p>'
    rmax = max(int(r["state_obs_count"]) for _, r in rare.iterrows()) or 1
    rows = []
    for i, (_, r) in enumerate(rare.iterrows(), 1):
        sci = esc(r.get("taxon_name") or "")
        ny = int(r["state_obs_count"])
        pct = max(4, round(100 * ny / rmax))   # inline magnitude bar (rarer = shorter)
        link = taxon_link(r.get("taxon_id"), r["label"],
                          cls="font-medium text-stone-900 hover:text-hollow-600")
        rows.append(f"""
        <div class="flex items-center gap-4 py-3.5 border-b border-stone-100 last:border-0">
          <div class="font-serif text-2xl font-bold text-hollow-300 w-8 text-right">{i}</div>
          <div class="flex-1 min-w-0">
            <div class="truncate">{link}</div>
            <div class="text-stone-400 text-sm italic truncate">{sci}</div>
            <div class="mt-1.5 h-1 rounded-full bg-stone-100"><div class="h-1 rounded-full" style="width:{pct}%;background:#c2703d"></div></div>
          </div>
          <div class="text-right">
            <div class="font-serif text-xl font-bold text-hollow-600">{ny}</div>
            <div class="text-stone-400 text-[0.7rem] uppercase tracking-wider">in NY</div>
          </div>
        </div>""")
    return (f'<div class="max-w-2xl mx-auto bg-white border border-stone-100 '
            f'rounded-2xl p-6 md:p-8 shadow-sm">{"".join(rows)}</div>')


# ── life list (searchable / filterable) ──────────────────────────────────────
def life_list_body(life):
    if life.empty:
        return '<p class="text-center text-stone-500">No species yet.</p>'
    # Pin the biggest groups as pills; the long tail goes in a dropdown so the
    # filter bar stays scannable instead of a 28-button wall. Counts aid the eye.
    counts = life["group"].value_counts()
    total = int(len(life))
    pinned = counts.index[:6].tolist()
    rest = counts.index[6:].tolist()

    def short(label):
        return label if len(label) <= 22 else label[:20].rstrip(" ,&") + "…"

    btns = [f'<button class="ll-filter ll-active" data-group="all">All <span class="ll-n">{total}</span></button>']
    btns += [f'<button class="ll-filter" data-group="{esc(g)}">{esc(short(g))} '
             f'<span class="ll-n">{int(counts[g])}</span></button>' for g in pinned]
    select = ""
    if rest:
        opts = "".join(f'<option value="{esc(g)}">{esc(g)} ({int(counts[g])})</option>'
                       for g in rest)
        select = (f'<select id="ll-select" class="ll-select px-3 py-1.5 rounded-full '
                  f'border border-stone-200 text-sm text-stone-600 bg-white">'
                  f'<option value="">More groups…</option>{opts}</select>')
    rows = []
    for _, r in life.iterrows():
        name = r["label"]
        sci = esc(r.get("taxon_name") or "")
        grp = esc(r.get("group") or "Other")
        link = taxon_link(r["taxon_id"], name, cls="font-medium text-stone-800 hover:text-hollow-600")
        rows.append(f"""
      <tr class="ll-row border-b border-stone-100" data-group="{grp}" data-name="{esc(name).lower()} {sci.lower()}">
        <td class="py-2.5 pr-4">{link}
            <span class="text-stone-400 italic text-sm block sm:inline sm:ml-2">{sci}</span></td>
        <td class="py-2.5 pr-4 text-stone-500 text-sm whitespace-nowrap">{grp}</td>
        <td class="py-2.5 pr-4 text-stone-500 text-sm text-right">{int(r['observations'])}</td>
        <td class="py-2.5 text-stone-400 text-sm whitespace-nowrap text-right">{fdate(r['first_seen'], '%b %Y')}</td>
      </tr>""")
    return f"""
    <div class="max-w-4xl mx-auto">
      <div class="flex flex-col sm:flex-row gap-4 mb-6 items-center justify-between">
        <input id="ll-search" type="search" placeholder="Search species…"
          class="w-full sm:w-72 px-4 py-2.5 rounded-full border border-stone-200 focus:border-hollow-400 focus:ring-2 focus:ring-hollow-100 outline-none text-sm">
        <div class="flex flex-wrap gap-2 justify-center items-center" role="group" aria-label="Filter by group">{''.join(btns)}{select}</div>
      </div>
      <div class="bg-white border border-stone-100 rounded-2xl p-5 md:p-7 shadow-sm max-h-[560px] overflow-y-auto">
        <table class="w-full text-[0.95rem]"><thead class="text-stone-400 text-xs uppercase tracking-wider border-b-2 border-stone-100">
          <tr><th class="text-left pb-2 font-semibold">Species</th><th class="text-left pb-2 font-semibold">Group</th>
          <th class="text-right pb-2 font-semibold">Obs</th><th class="text-right pb-2 font-semibold">First seen</th></tr>
        </thead><tbody id="ll-body">{''.join(rows)}</tbody></table>
      </div>
      <p id="ll-count" class="text-center text-stone-400 text-sm mt-4"></p>
    </div>"""


# ── photo gallery ────────────────────────────────────────────────────────────
def gallery_body(photos):
    if photos.empty:
        return ('<p class="text-center text-stone-500">Photos populate after the '
                'next sync.</p>')
    cells = []
    for _, r in photos.iterrows():
        name = esc(r["label"])
        cells.append(f"""
      <a href="{esc(r.get('url') or '#')}" target="_blank" rel="noopener" class="photo-card group relative rounded-xl overflow-hidden block" style="aspect-ratio:1;">
        <img src="{esc(r['photo_url'])}" class="photo-img w-full h-full object-cover" alt="{name}" loading="lazy">
        <div class="absolute inset-0 bg-gradient-to-t from-black/75 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
        <div class="absolute bottom-0 inset-x-0 p-3 opacity-0 group-hover:opacity-100 transition-opacity">
          <div class="text-white text-xs font-medium leading-tight">{name}</div>
        </div>
      </a>""")
    return ('<div class="grid grid-cols-3 md:grid-cols-6 gap-2.5">'
            + "".join(cells) + "</div>")


# ── moth view ("After Dark") ─────────────────────────────────────────────────
def _dark_stat(num, label, sub=""):
    sub_html = (f'<div class="text-white/35 text-[0.62rem] mt-1 max-w-[9.5rem] '
                f'mx-auto leading-tight normal-case tracking-normal">{sub}</div>'
                if sub else "")
    return (f'<div class="text-center"><div class="font-serif text-4xl md:text-5xl '
            f'font-bold text-hollow-300">{num}</div>'
            f'<div class="text-white/45 text-[0.7rem] mt-1 uppercase '
            f'tracking-[0.18em]">{label}</div>{sub_html}</div>')


def _dark_divider():
    return '<div class="w-px h-12 bg-white/15"></div>'


def property_profile_body():
    """Three-column ecological explanation of why Michigan Creek drives moth diversity."""
    col1 = (
        '<div class="space-y-3">'
        + _dark_stat("35–50% richer", "Creek Ecotone")
        + '<p class="text-white/50 text-sm leading-relaxed mt-2">'
        'Arthropod richness at a stream-hardwood edge runs 35–50% above comparable upland sites. '
        'The transition between water and forest stacks microhabitats and host-plant niches that '
        'a uniform woodland can\'t provide.'
        '</p></div>'
    )
    col2 = (
        '<div class="space-y-3">'
        + _dark_stat("50–100 m from bank", "Humidity Buffer")
        + '<p class="text-white/50 text-sm leading-relaxed mt-2">'
        'Dry air below ~65°F suppresses moth flight — but creek-side humidity counters that within '
        '50–100 m of the bank. Marginal nights that shut down upland sites often stay productive here.'
        '</p></div>'
    )
    col3 = (
        '<div class="space-y-3">'
        + _dark_stat("253 species · 30 acres", "Host Plants")
        + '<p class="text-white/50 text-sm leading-relaxed mt-2">'
        '2–3× the NY mixed-hardwood baseline. Eastern Lepidoptera are mostly host-plant specialists; '
        '253 plants × ~1.8 predicted moths per plant species predicts ~455. '
        'Observed: 576 — the creek concentrates the high-value host genera, which pushes the count above the prediction.'
        '</p></div>'
    )
    return (
        '<div class="grid md:grid-cols-3 gap-8 text-center max-w-4xl mx-auto">'
        + col1 + col2 + col3
        + '</div>'
    )


def moth_stats(msum, comp):
    """Headline stat band for the moth view."""
    tiles = [_dark_stat(f"{msum['species']:,}", "Moth species"),
             _dark_stat(f"{msum['records']:,}", "Records")]
    if comp:
        ci = (f"Chao2 estimate; 95% CI {comp['low']}–{comp['high']}"
              if comp.get("high", 0) > comp.get("low", 0) else "Chao2 estimate")
        tiles.append(_dark_stat(f"{comp['pct_complete']}%", "Est. complete",
                                "of the ~780 species estimated on this site (Chao2)"))
        tiles.append(_dark_stat(f"~{comp['estimated']:,}", "Likely total", ci))
    if msum.get("top_month"):
        tiles.append(_dark_stat(esc(msum["top_month"]), "Peak month"))
    return ('<div class="flex flex-wrap items-start justify-center gap-8 md:gap-12">'
            + _dark_divider().join(tiles) + "</div>")


def moth_showcase(highlights):
    cards = []
    for _, r in highlights.iterrows():
        name = esc(r["label"])
        sci = esc(r.get("taxon_name"))
        photo = r.get("photo_url")
        state_n = r.get("state_obs_count")
        if state_n == state_n and state_n is not None:
            tag = f'<span class="badge badge-accent">{int(state_n)} in NY</span>'
        else:
            tag = (f'<span class="badge badge-green">seen {int(r["obs_count"])}×</span>'
                   if r.get("obs_count") == r.get("obs_count") else "")
        img = (f'<img src="{esc(photo)}" class="photo-img w-full h-full object-cover" alt="{name}" loading="lazy">'
               if photo == photo and photo else
               '<div class="w-full h-full bg-hollow-800 flex items-center justify-center text-3xl">🦋</div>')
        oid = sval(r.get("first_obs_id"))
        tid = sval(r.get("taxon_id"))
        if oid not in ("", None) and oid == oid:
            href = f"{OBS_URL}{int(float(oid))}"
        elif tid not in ("", None) and tid == tid:
            href = f"{TAXON_URL}{int(tid)}"
        else:
            href = "#"
        cards.append(f"""
        <a href="{href}" target="_blank" rel="noopener" class="photo-card relative rounded-2xl overflow-hidden ring-1 ring-white/10 block" style="height:240px;">
          <div class="absolute inset-0 overflow-hidden">{img}</div>
          <div class="absolute inset-0 bg-gradient-to-t from-black/85 via-black/15 to-transparent"></div>
          <div class="absolute top-3 left-3">{tag}</div>
          <div class="absolute bottom-0 inset-x-0 p-4">
            <div class="font-serif text-base font-bold text-white leading-snug">{name}</div>
            <div class="text-white/55 text-xs italic">{sci}</div>
          </div>
        </a>""")
    return ('<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">'
            + "".join(cards) + "</div>") if cards else ""


_GRID_CLASSES = "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3"


def _taxa_card(r, placeholder, gmax):
    cc = int(r["ref_count"])
    bar_pct = max(4, round(100 * cc / gmax))
    taxon_id = r.get("taxon_id")
    common = r["label"]
    sci = r.get("taxon_name", "")
    photo_url = r.get("photo_url") or ""
    inat_url = f"https://www.inaturalist.org/taxa/{taxon_id}" if taxon_id else "#"
    if photo_url:
        photo_html = (
            f'<img src="{esc(photo_url)}" alt="{esc(common)}" loading="lazy" '
            f'class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105">'
        )
    else:
        photo_html = (
            f'<div class="w-full h-full flex items-center justify-center">'
            f'<span class="text-white/20 text-3xl">{placeholder}</span></div>'
        )
    return (
        f'<a href="{inat_url}" target="_blank" rel="noopener" '
        f'class="group relative block rounded-xl overflow-hidden bg-white/[0.04] '
        f'border border-white/10 hover:border-hollow-400/60 transition-colors">'
        f'  <div class="aspect-square overflow-hidden bg-white/5">{photo_html}</div>'
        f'  <div class="p-2.5">'
        f'    <div class="text-sm font-medium text-white leading-tight truncate">{esc(common)}</div>'
        f'    <div class="text-[0.65rem] text-white/35 italic truncate mt-0.5">{esc(sci)}</div>'
        f'    <div class="mt-2 flex items-center justify-between gap-1">'
        f'      <div class="flex-1 h-1 rounded-full bg-white/10">'
        f'        <div class="h-1 rounded-full" style="width:{bar_pct}%;background:#8ec8b1"></div>'
        f'      </div>'
        f'      <span class="text-[0.65rem] text-hollow-300 font-medium ml-1.5 whitespace-nowrap">{cc}×</span>'
        f'    </div>'
        f'  </div>'
        f'</a>'
    )


def _gap_photo_grid(missing, placeholder="?", group_by=None):
    """Shared photo grid for any taxa DataFrame.

    When group_by is set (e.g. "family_name"), renders each taxonomic group
    with a small header label and its own sub-grid, using family_common as
    the display name (falling back to family_name when unavailable).
    """
    if missing is None or missing.empty:
        return '<p class="text-center text-white/50 py-8">No gap data yet.</p>'
    gmax = max(int(r["ref_count"]) for _, r in missing.iterrows()) or 1

    if not group_by or group_by not in missing.columns:
        cards = [_taxa_card(r, placeholder, gmax) for _, r in missing.iterrows()]
        return f'<div class="{_GRID_CLASSES}">' + "".join(cards) + "</div>"

    # Every cell gets an identical fixed-height label slot so the grid stays
    # aligned. The first card of each family shows the label text; all others
    # get an invisible placeholder of the same height.
    LABEL_SLOT = '<div class="h-4 mb-1"></div>'
    items = []
    for key, group in missing.groupby(group_by, sort=False):
        label_col = "family_common" if "family_common" in missing.columns else group_by
        raw_label = group.iloc[0].get(label_col) or ""
        sci_label = key if group_by == "family_name" else ""
        if sci_label and raw_label and raw_label != sci_label:
            header_text = f"{sci_label} · {raw_label}"
        else:
            header_text = raw_label or sci_label
        for i, (_, r) in enumerate(group.iterrows()):
            if i == 0 and header_text:
                label = (f'<div class="h-4 mb-1 text-[0.62rem] font-semibold '
                         f'tracking-[0.1em] uppercase text-white/30 truncate">'
                         f'{esc(header_text)}</div>')
            else:
                label = LABEL_SLOT
            items.append(f'<div class="flex flex-col">{label}{_taxa_card(r, placeholder, gmax)}</div>')

    return f'<div class="{_GRID_CLASSES}">' + "".join(items) + "</div>"


def moth_gap_body(gap):
    """Regional moths not yet found here — photo grid ranked by nearby frequency."""
    if not gap or gap.get("missing_count", 0) == 0:
        return '<p class="text-center text-white/50">No gap data yet.</p>'
    radius = gap.get("region_radius_km", 80)
    miles = round(radius / 1.609)
    region_total = gap.get("region_total", 0)
    county_line = ""
    if gap.get("county_total"):
        county_line = (f' That already represents <strong class="text-hollow-300">{gap["county_pct"]}%</strong>'
                       f' of the {gap["county_total"]} moths ever recorded across all of Tioga County — a county'
                       f' sparsely enough documented that the ~{miles}-mile regional pool is the truer completeness yardstick.')
    lead = (f'<p class="text-center text-white/60 max-w-2xl mx-auto mb-8">Kingfisher Hollow has recorded '
            f'<strong class="text-hollow-300">{gap["have"]}</strong> of the '
            f'<strong class="text-hollow-300">{region_total}</strong> moth species documented within '
            f'~{miles} miles — <strong class="text-hollow-300">{gap["pct"]}%</strong> of the regional '
            f'pool.{county_line} The <strong class="text-hollow-300">{gap["missing_count"]}</strong> '
            f'species below have all been seen by someone nearby. They\'re not rare. They\'re not '
            f'hypothetical. They need the right night, the right trap position, or the right observer '
            f'paying attention.</p>')
    return lead + _gap_photo_grid(gap["missing"])


def mammal_gap_body(gap):
    """Regional mammals not yet documented — photo grid."""
    if not gap or gap.get("missing_count", 0) == 0:
        return '<p class="text-center text-white/50">No gap data yet.</p>'
    miles = round(gap.get("region_radius_km", 80) / 1.609)
    lead = (f'<p class="text-center text-white/60 max-w-2xl mx-auto mb-8">'
            f'<strong class="text-hollow-300">{gap["have"]}</strong> of '
            f'<strong class="text-hollow-300">{gap["region_total"]}</strong> mammal species documented within '
            f'~{miles} miles have been recorded here. '
            f'The <strong class="text-hollow-300">{len(gap["missing"])}</strong> species below '
            f'have county or regional records for this time of year — all realistic targets.</p>')
    return lead + _gap_photo_grid(gap["missing"], placeholder="🦌")


def amphibian_found_body(found):
    """Amphibians recorded on the property — photo grid, grouped by family."""
    if found is None or found.empty:
        return ('<p class="text-center text-white/50 py-8">Amphibian roster not '
                'synced yet.</p>')
    return _gap_photo_grid(found, placeholder="🐸", group_by="family_name")


def amphibian_gap_body(gap):
    """Regional amphibians not yet documented — photo grid."""
    if not gap or gap.get("missing_count", 0) == 0:
        return '<p class="text-center text-white/50">No gap data yet.</p>'
    miles = round(gap.get("region_radius_km", 80) / 1.609)
    lead = (f'<p class="text-center text-white/60 max-w-2xl mx-auto mb-8">'
            f'<strong class="text-hollow-300">{gap["have"]}</strong> of '
            f'<strong class="text-hollow-300">{gap["region_total"]}</strong> amphibian species recorded within '
            f'~{miles} miles have turned up here. '
            f'The <strong class="text-hollow-300">{len(gap["missing"])}</strong> species below '
            f'are documented in the surrounding region but not yet here — ranked by how common they are nearby.</p>')
    return lead + _gap_photo_grid(gap["missing"], placeholder="🐸")


def butterfly_found_body(found):
    """Butterflies recorded on the property — photo grid, grouped by family."""
    if found is None or found.empty:
        return ('<p class="text-center text-white/50 py-8">Butterfly roster not '
                'synced yet.</p>')
    return _gap_photo_grid(found, placeholder="🦋", group_by="family_name")


def butterfly_gap_body(gap):
    """Regional butterflies not yet documented — photo grid."""
    if not gap or gap.get("missing_count", 0) == 0:
        return '<p class="text-center text-white/50">No gap data yet.</p>'
    miles = round(gap.get("region_radius_km", 80) / 1.609)
    lead = (f'<p class="text-center text-white/60 max-w-2xl mx-auto mb-8">'
            f'<strong class="text-hollow-300">{gap["have"]}</strong> of '
            f'<strong class="text-hollow-300">{gap["region_total"]}</strong> butterfly species recorded within '
            f'~{miles} miles have turned up here. '
            f'The <strong class="text-hollow-300">{len(gap["missing"])}</strong> species below '
            f'are documented in the surrounding region but not yet here — ranked by how common they are nearby.</p>')
    return lead + _gap_photo_grid(gap["missing"], placeholder="🦋")


def mammal_found_body(found):
    """Mammals recorded on the property — photo grid, grouped by family."""
    if found is None or found.empty:
        return ('<p class="text-center text-white/50 py-8">Mammal roster not '
                'synced yet.</p>')
    return _gap_photo_grid(found, placeholder="🦊", group_by="family_name")


def plant_found_body(found):
    """Plants recorded on the property — four major group sections, each family-grouped."""
    if found is None or found.empty:
        return ('<p class="text-center text-white/50 py-8">Plant roster not '
                'synced yet.</p>')

    GROUP_META = [
        ("Angiosperm",        "Angiosperms",              "Flowering seed plants — the largest group on Earth, encompassing all broadleaf trees, shrubs, wildflowers, and grasses. Seeds are enclosed inside a fruit or ovary."),
        ("Seedless Vascular", "Seedless Vascular Plants", "Plants with vascular tissue (xylem and phloem) that reproduce by spores rather than seeds. Ferns and horsetails."),
        ("Gymnosperm",        "Gymnosperms",              "Non-flowering seed plants with \"naked\" seeds not enclosed in an ovary. Conifers — pines, hemlocks, redcedar."),
        ("Bryophyte",         "Bryophytes",               "Non-vascular plants — mosses, liverworts, hornworts. No true roots or vascular tissue; absorb water by osmosis and reproduce by spores."),
    ]

    has_group = "plant_group" in found.columns
    parts = []
    for key, label, desc in GROUP_META:
        grp = found[found["plant_group"] == key] if has_group else found
        if grp.empty:
            continue
        count = len(grp)
        header = (
            f'<div class="mt-10 mb-4 border-t border-white/10 pt-6">'
            f'<h3 class="text-hollow-300 text-xs font-semibold tracking-[0.18em] '
            f'uppercase mb-1">{esc(label)} <span class="text-white/30">· {count} species</span></h3>'
            f'<p class="text-white/45 text-xs max-w-2xl leading-relaxed">{esc(desc)}</p>'
            f'</div>'
        )
        parts.append(header + _gap_photo_grid(grp, placeholder="🌿", group_by="family_name"))
    return "".join(parts)


def reptile_found_body(found):
    """Reptiles recorded on the property — photo grid, grouped by family."""
    if found is None or found.empty:
        return ('<p class="text-center text-white/50 py-8">Reptile roster not '
                'synced yet.</p>')
    return _gap_photo_grid(found, placeholder="🐍", group_by="family_name")


def reptile_gap_body(gap):
    """Regional reptiles not yet documented — photo grid."""
    if not gap or gap.get("missing_count", 0) == 0:
        return '<p class="text-center text-white/50">No gap data yet.</p>'
    miles = round(gap.get("region_radius_km", 80) / 1.609)
    lead = (f'<p class="text-center text-white/60 max-w-2xl mx-auto mb-8">'
            f'<strong class="text-hollow-300">{gap["have"]}</strong> of '
            f'<strong class="text-hollow-300">{gap["region_total"]}</strong> reptile species recorded within '
            f'~{miles} miles have turned up here. '
            f'The <strong class="text-hollow-300">{len(gap["missing"])}</strong> species below '
            f'are documented in the surrounding region but not yet here — ranked by how common they are nearby.</p>')
    return lead + _gap_photo_grid(gap["missing"], placeholder="🐍")


def plant_gap_body(gap):
    """Regional plants not yet documented — photo grid."""
    if not gap or gap.get("missing_count", 0) == 0:
        return '<p class="text-center text-white/50">No gap data yet.</p>'
    miles = round(gap.get("region_radius_km", 80) / 1.609)
    lead = (f'<p class="text-center text-white/60 max-w-2xl mx-auto mb-8">'
            f'<strong class="text-hollow-300">{gap["have"]}</strong> of '
            f'<strong class="text-hollow-300">{gap["region_total"]}</strong> plant species documented within '
            f'~{miles} miles have been recorded here. '
            f'The ~{miles}-mile regional pool includes many habitat types the property doesn\'t have, '
            f'so the raw completeness figure understates how thoroughly the property flora is known. '
            f'The <strong class="text-hollow-300">{len(gap["missing"])}</strong> species below '
            f'are ranked by how often they turn up in county records this month — all plausible finds '
            f'on a careful walk.</p>')
    return lead + _gap_photo_grid(gap["missing"], placeholder="🌿")


def moth_diversity_body(div):
    simp_pct = round(float(div["simpson"]) * 100, 1)
    tiles = [
        _dark_stat(div["shannon"], "Shannon H′", f"equivalent to {round(2**float(div['shannon']), 0):.0f} equally common species"),
        _dark_stat(div["simpson"], "Simpson",
                   f"two random records are different species {simp_pct}% of the time"),
        _dark_stat(div["evenness"], "Evenness", "near 1.0 — the community is unusually well-balanced, no species dominates"),
    ]
    return ('<div class="flex flex-wrap items-start justify-center gap-8 md:gap-12 mb-10">'
            + _dark_divider().join(tiles) + "</div>")


# ── field journal / activity log ────────────────────────────────────────────
def id_changes_body(changes):
    """Render recent improving/maverick identifications on the property observations."""
    if not changes:
        return '<p class="text-stone-400 text-sm text-center py-4">No recent identification changes.</p>'

    taxon_url = "https://www.inaturalist.org/taxa/"
    rows = []
    for c in changes:
        date_str = c["obs_date"]
        id_date = c["id_created_at"][:10] if c["id_created_at"] else ""

        prev_name = c["prev_taxon_common"] or c["prev_taxon_name"] or "—"
        new_name = c["new_taxon_common"] or c["new_taxon_name"] or "—"

        prev_html = (
            f'<a href="{taxon_url}{c["prev_taxon_id"]}" target="_blank" rel="noopener" '
            f'class="text-stone-600 italic">{esc(prev_name)}</a>'
            if c["prev_taxon_id"] else f'<span class="text-stone-500 italic">{esc(prev_name)}</span>'
        )
        new_html = (
            f'<a href="{taxon_url}{c["new_taxon_id"]}" target="_blank" rel="noopener" '
            f'class="font-medium text-stone-800 italic">{esc(new_name)}</a>'
            if c["new_taxon_id"] else f'<span class="font-medium text-stone-800 italic">{esc(new_name)}</span>'
        )

        if c["category"] == "improving":
            badge = '<span class="text-xs font-medium px-1.5 py-0.5 rounded bg-green-50 text-green-700">refined</span>'
        else:
            badge = '<span class="text-xs font-medium px-1.5 py-0.5 rounded bg-amber-50 text-amber-700">disagrees</span>'

        identifier_url = f"https://www.inaturalist.org/people/{c['identifier_login']}"
        identifier_html = (
            f'<a href="{identifier_url}" target="_blank" rel="noopener" '
            f'class="text-stone-500 hover:text-stone-700">{esc(c["identifier_login"])}</a>'
        )

        obs_link = (
            f'<a href="{c["obs_url"]}" target="_blank" rel="noopener" '
            f'class="text-stone-400 hover:text-hollow-600 text-xs ml-1" title="View observation">↗</a>'
        )

        rows.append(
            f'<div class="flex items-start gap-3 py-2.5 border-b border-stone-100 last:border-0">'
            f'  <div class="w-20 shrink-0 text-xs text-stone-400 pt-0.5">'
            f'    <div>{esc(id_date)}</div>'
            f'    <div class="text-stone-300">obs {esc(date_str)}</div>'
            f'  </div>'
            f'  <div class="flex-1 min-w-0 text-sm">'
            f'    {prev_html} → {new_html} {obs_link}'
            f'  </div>'
            f'  <div class="flex items-center gap-2 shrink-0">'
            f'    {badge}'
            f'    <span class="text-xs text-stone-400">by {identifier_html}</span>'
            f'  </div>'
            f'</div>'
        )

    return (
        '<div class="max-w-3xl mx-auto mt-12">'
        '<h3 class="font-serif text-2xl font-bold text-stone-900 mb-1">ID Updates</h3>'
        '<p class="text-sm text-stone-400 mb-4">Identifications on your observations refined or disputed by other users — not shown in iNat notifications.</p>'
        '<div class="rounded-lg border border-stone-200 bg-white px-4 divide-y divide-stone-100">'
        + "".join(rows)
        + '</div></div>'
    )


def _ordinal(n):
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th','st','nd','rd','th','th','th','th','th','th'][n % 10]}"


def _rarity_badge(sp):
    """Return inline rarity annotation for one species, e.g. '★ first for Tioga · 9th for NY'."""
    parts = []
    if sp.get("is_county_first"):
        parts.append("★ first for Tioga")
    elif sp.get("county_obs") is not None and sp["county_obs"] < 10:
        parts.append(f"{_ordinal(sp['county_obs'])} for Tioga")
    if sp.get("state_obs") is not None and sp["state_obs"] < 10:
        if sp["state_obs"] == 1:
            parts.append("only NY record")
        else:
            parts.append(f"{_ordinal(sp['state_obs'])} for NY")
    return " · ".join(parts)


def _weather_line(w):
    """Compact weather summary string for a journal entry (9 PM conditions)."""
    if not w:
        return ""
    parts = []
    temp = w.get("temp_f_9pm") if w.get("temp_f_9pm") is not None else w.get("temp_f_hi")
    if temp is not None:
        parts.append(f"{temp}°F")
    hum = w.get("humidity_9pm") if w.get("humidity_9pm") is not None else w.get("humidity_pct")
    if hum is not None:
        parts.append(f"{hum}% humidity")
    wd = w.get("wind_desc_9pm") or w.get("wind_desc")
    if wd:
        parts.append(wd)
    moon = w.get("moon")
    if moon:
        parts.append(moon)
    return " · ".join(parts)


def activity_log_body(log_entries, weather_cache):
    """Render the full field journal as a timeline of dated entries."""
    if not log_entries:
        return '<p class="text-center text-stone-500">No entries yet.</p>'

    month_names = ["", "January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]

    html_parts = ['<div class="max-w-3xl mx-auto">']
    current_year = None

    for entry in reversed(log_entries):
        d = entry["date"]
        year = d.year

        if year != current_year:
            current_year = year
            html_parts.append(
                f'<div class="flex items-center gap-4 mt-12 mb-6 first:mt-0">'
                f'<span class="font-serif text-3xl font-bold text-stone-900">{year}</span>'
                f'<span class="flex-1 h-px bg-stone-200"></span></div>'
            )

        has_morning = entry.get("has_morning", False)
        date_label = f"Night of {month_names[d.month]} {d.day}"

        w = weather_cache.get(str(d))
        weather_str = _weather_line(w)
        weather_html = (
            f'<p class="text-stone-400 text-sm mt-1">{esc(weather_str)}</p>'
            if weather_str else ""
        )

        observers = entry.get("observers", [])
        observers_html = (
            f'<p class="text-stone-400 text-xs mt-1">{esc(", ".join(observers))}</p>'
            if observers else ""
        )

        def _sp_html(sp):
            badge = _rarity_badge(sp)
            obs_id = sp.get("obs_id")
            if obs_id:
                name_html = (f'<a href="{OBS_URL}{obs_id}" target="_blank" rel="noopener">'
                             f'{esc(sp["label"])}</a>')
            else:
                name_html = taxon_link(sp["taxon_id"], sp["label"])
            if badge:
                return (f'{name_html} <span class="text-hollow-600 text-xs font-medium '
                        f'whitespace-nowrap">({badge})</span>')
            return name_html

        def _group_html(species_list):
            """Render a list of species into labelled group paragraph(s)."""
            moths = [sp for sp in species_list if sp["is_moth"]]
            others = [sp for sp in species_list if not sp["is_moth"]]
            parts = []
            if moths:
                parts.append(
                    f'<span class="font-medium text-stone-700">Moths:</span> '
                    + ", ".join(_sp_html(sp) for sp in moths)
                )
            if others:
                groups_seen = {}
                for sp in others:
                    grp = sp["group"] or "Other"
                    groups_seen.setdefault(grp, []).append(sp)
                if len(groups_seen) == 1:
                    grp_name, grp_sps = next(iter(groups_seen.items()))
                    parts.append(
                        f'<span class="font-medium text-stone-700">{esc(grp_name)}:</span> '
                        + ", ".join(_sp_html(sp) for sp in grp_sps)
                    )
                else:
                    lbl = "Other species" if moths else "Species"
                    parts.append(
                        f'<span class="font-medium text-stone-700">{lbl}:</span> '
                        + ", ".join(_sp_html(sp) for sp in others)
                    )
            if not parts:
                return ""
            return (
                '<p class="text-stone-700 leading-relaxed mt-2 text-[0.95rem]">'
                + " &nbsp;·&nbsp; ".join(parts)
                + "</p>"
            )

        def _badge(n):
            return (
                f'<span class="inline-flex items-center justify-center w-6 h-6 '
                f'rounded-full bg-hollow-100 text-hollow-700 text-xs font-bold '
                f'flex-shrink-0 mt-0.5">{n}</span>'
            )

        section_label_cls = (
            'text-stone-400 text-[0.68rem] font-semibold tracking-[0.15em] uppercase mb-1'
        )

        if has_morning:
            morning_sps = [sp for sp in entry["new_species"] if sp["is_morning"]]
            evening_sps = [sp for sp in entry["new_species"] if not sp["is_morning"]]
            morning_html = _group_html(morning_sps)
            evening_html = _group_html(evening_sps)

            morning_row = ""
            if morning_html:
                morning_row = f"""
  <div class="grid grid-cols-[8rem_1fr] gap-x-6 pb-3">
    <div></div>
    <div>
      <div class="{section_label_cls}">Morning</div>
      <div class="flex items-start gap-2">
        {_badge(len(morning_sps))}
        <div class="flex-1 min-w-0">{morning_html}</div>
      </div>
    </div>
  </div>
  <hr class="border-stone-100 ml-[calc(8rem+1.5rem)]">"""

            evening_meta = f"""
      <div class="{section_label_cls}">Evening</div>
      {weather_html}
      {observers_html}"""

            html_parts.append(f"""
<div class="py-5 border-b border-stone-100 group">{morning_row}
  <div class="grid grid-cols-[8rem_1fr] gap-x-6 pt-3">
    <div class="text-right pt-0.5">
      <span class="font-serif text-lg font-bold text-stone-900 leading-snug">{date_label}</span>
    </div>
    <div>
      <div class="flex items-start gap-2">
        {_badge(len(evening_sps) or len(entry["new_species"]))}
        <div class="flex-1 min-w-0">{evening_meta}
          {evening_html}
        </div>
      </div>
    </div>
  </div>
</div>""")

        else:
            species_html = _group_html(entry["new_species"])
            new_count = len(entry["new_species"])
            html_parts.append(f"""
<div class="grid grid-cols-[8rem_1fr] gap-x-6 py-5 border-b border-stone-100 group">
  <div class="text-right pt-0.5">
    <span class="font-serif text-lg font-bold text-stone-900 leading-snug">{date_label}</span>
  </div>
  <div>
    <div class="flex items-start gap-2">
      {_badge(new_count)}
      <div class="flex-1 min-w-0">
        {weather_html}
        {observers_html}
        {species_html}
      </div>
    </div>
  </div>
</div>""")

    html_parts.append("</div>")
    return "".join(html_parts)


# ── head / nav / footer ──────────────────────────────────────────────────────
def head(s, county_firsts):
    desc = (f"Biodiversity survey of Kingfisher Hollow — {s['species']:,} species on 30 riparian acres along Michigan Creek, "
            "Tioga County, NY. Stream-edge habitat at the Appalachian / northern hardwood / mid-Atlantic junction: "
            f"{county_firsts:,} county-first records, 576 moth species, plant diversity 2–3× the NY upland baseline. "
            "Data updated nightly.")
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kingfisher Hollow · Biodiversity Survey</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="https://survey.kingfisher-hollow.com/">
<meta property="og:type" content="website">
<meta property="og:title" content="Kingfisher Hollow · Biodiversity Survey">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="https://survey.kingfisher-hollow.com/">
<meta property="og:image" content="{HERO_PHOTO}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Kingfisher Hollow · Biodiversity Survey">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{HERO_PHOTO}">
<script src="{PLOTLY_CDN}"></script>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400;1,600&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<script>
tailwind.config = {{ theme: {{ extend: {{
  fontFamily: {{ serif: ['Playfair Display','Georgia','serif'], sans: ['Inter','system-ui','sans-serif'] }},
  colors: {{ hollow: {{ 50:'#f0f7f4',100:'#dcefe6',200:'#bbdfd0',300:'#8ec8b1',400:'#5eab8d',500:'#3d8f72',600:'#2e735c',700:'#265d4b',800:'#214a3d',900:'#1d3d33',950:'#0d221c' }} }}
}} }} }}
</script>
<style>
  html {{ scroll-behavior: smooth; }}
  body {{ background:#fafaf9; }}
  .nav-transparent {{ background: rgba(13,34,28,0.15); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border-bottom:1px solid rgba(255,255,255,0.10); }}
  .nav-solid {{ background: rgba(255,255,255,0.94); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border-bottom:1px solid rgba(0,0,0,0.07); }}
  .hero-overlay {{ background: linear-gradient(160deg, rgba(13,34,28,0.30) 0%, rgba(13,34,28,0.55) 55%, rgba(13,34,28,0.85) 100%); }}
  .rule {{ display:block; width:52px; height:3px; border-radius:2px; background: linear-gradient(to right,#3d8f72,#8ec8b1); }}
  .fade-up {{ animation: fadeUp 0.85s ease-out both; }}
  @keyframes fadeUp {{ from {{ opacity:0; transform: translateY(28px); }} to {{ opacity:1; transform: translateY(0); }} }}
  .delay-1{{animation-delay:.15s}} .delay-2{{animation-delay:.30s}} .delay-3{{animation-delay:.45s}}
  .lift {{ transition: transform .3s ease, box-shadow .3s ease; }}
  .lift:hover {{ transform: translateY(-4px); box-shadow: 0 20px 40px rgba(13,34,28,0.12); }}
  .photo-card .photo-img {{ transition: transform .65s cubic-bezier(.25,.46,.45,.94); }}
  .photo-card:hover .photo-img {{ transform: scale(1.05); }}
  .badge {{ display:inline-block; font-size:.62rem; font-weight:600; letter-spacing:.08em; text-transform:uppercase; padding:.22rem .55rem; border-radius:9999px; }}
  .badge-accent {{ background:#c2703d; color:white; }}
  .badge-green {{ background:#dcefe6; color:#265d4b; }}
  .ll-filter {{ font-size:.8rem; padding:.35rem .85rem; border-radius:9999px; border:1px solid #e7e5e4; color:#57534e; background:white; transition: all .2s; cursor:pointer; }}
  .ll-filter:hover {{ border-color:#8ec8b1; }}
  .ll-active {{ background:#2e735c; color:white; border-color:#2e735c; }}
  .ll-n {{ opacity:.55; font-variant-numeric:tabular-nums; margin-left:.15rem; }}
  .ll-select {{ cursor:pointer; outline:none; }} .ll-select:focus {{ border-color:#8ec8b1; }}
  .chart-empty {{ text-align:center; color:#a8a29e; padding:2rem; font-style:italic; }}
  .reveal {{ opacity:0; transform: translateY(24px); transition: opacity .7s ease, transform .7s ease; }}
  .reveal.in {{ opacity:1; transform:none; }}
  /* Mode toggle (All life / Moths) */
  .mode-btn {{ font-size:.78rem; font-weight:600; padding:.3rem .8rem; border-radius:9999px; color:rgba(255,255,255,0.7); transition:all .2s; cursor:pointer; white-space:nowrap; }}
  .mode-btn.mode-active {{ background:#8ec8b1; color:#0d221c; }}
  /* Mobile menu is always dark: keep its mode chips legible + tappable regardless of nav scroll state. */
  #mob .mode-btn {{ background:rgba(255,255,255,0.06); padding:.4rem .85rem; }}
  #mob .mode-btn:not(.mode-active) {{ color:rgba(255,255,255,0.82) !important; }}
  #mob .mode-btn.mode-active {{ background:#8ec8b1; color:#0d221c !important; }}
  /* Moths mode = night: dark page + dark nav regardless of scroll */
  body[data-mode="moths"] {{ background:#0d221c; }}
  body[data-mode="moths"] #navbar.nav-solid {{ background:rgba(13,34,28,0.92); border-bottom:1px solid rgba(255,255,255,0.08); }}
  body[data-mode="moths"] #navbar.nav-solid #nav-brand {{ color:#fff !important; }}
  body[data-mode="moths"] #navbar.nav-solid .nav-link {{ color:rgba(255,255,255,0.8) !important; }}
  /* Log mode: no hero, so force solid nav appearance immediately */
  body[data-mode="log"] #navbar {{ background:rgba(255,255,255,0.94) !important; backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); border-bottom:1px solid rgba(0,0,0,0.07) !important; }}
  body[data-mode="log"] #navbar #nav-brand {{ color:#1c1917 !important; }}
  body[data-mode="log"] #navbar .nav-link {{ color:#44403c !important; }}
  /* Mode-toggle button text: dark on light nav backgrounds (all life scrolled + log), white in moths */
  body:not([data-mode="moths"]) #navbar.nav-solid .mode-btn:not(.mode-active),
  body[data-mode="log"] #navbar .mode-btn:not(.mode-active) {{ color:rgba(13,34,28,0.55); }}
  /* Section nav: secondary bar separator line */
  #section-bar {{ border-top: 1px solid rgba(255,255,255,0.12); }}
  #navbar.nav-solid #section-bar {{ border-top: 1px solid rgba(0,0,0,0.07); }}
  body[data-mode="moths"] #navbar.nav-solid #section-bar {{ border-top: 1px solid rgba(255,255,255,0.08); }}
  body[data-mode="log"] #navbar #section-bar {{ border-top: 1px solid rgba(0,0,0,0.07) !important; }}
  .log-rarity {{ color:#2e735c; font-size:.78rem; font-weight:500; }}
  .log-moth-label {{ color:#57534e; font-size:.8rem; font-weight:600; letter-spacing:.04em; text-transform:uppercase; }}
</style></head>
<body class="font-sans text-stone-800 antialiased" data-mode="all">"""


def nav():
    all_links = [("#whats-new", "What's New"), ("#discovery", "Discovery"),
                 ("#unique", "Unique Finds"), ("#life-list", "Life List"),
                 ("#gallery", "Gallery")]
    moth_links = [("#moth-why-here", "Why Here"), ("#moth-gap", "Gap List"),
                  ("#moth-families", "Families"), ("#moth-standouts", "Standouts"),
                  ("#moth-completeness", "Inventory"), ("#moth-diversity", "Diversity"),
                  ("#moth-calendar", "Calendar"), ("#moth-methods", "Find More")]
    butterfly_links = [("#butterflies", "Found"), ("#butterfly-gap", "Gap List"),
                       ("#butterfly-methods", "Find More")]
    mammal_links = [("#mammals", "Found"), ("#mammal-gap", "Gap List"),
                    ("#mammal-methods", "Find More")]
    plant_links = [("#plants", "Found"), ("#plant-gap", "Gap List"),
                   ("#plant-methods", "Find More")]
    amphibian_links = [("#amphibians", "Amphibians"), ("#reptiles-found", "Reptiles"),
                       ("#amphibian-gap", "Gap List"), ("#amphibian-methods", "Find More")]
    log_links = [("#log-journal", "Field Journal")]

    # One source of truth for the view switcher, used by both toggles.
    modes = [("all", "All life"), ("moths", "Moths"), ("butterflies", "Butterflies"),
             ("mammals", "Mammals"), ("plants", "Plants"),
             ("amphibians", "Herps"), ("log", "Log")]

    def mode_buttons():
        return "".join(
            f'<button class="mode-btn{" mode-active" if m == "all" else ""}" '
            f'data-mode="{m}" aria-pressed="{"true" if m == "all" else "false"}">{label}</button>'
            for m, label in modes)

    def links_html(links, item_cls):
        return "".join(f'<a href="{h}" class="{item_cls}">{t}</a>' for h, t in links)
    desk_cls = "nav-link text-white/80 hover:text-white text-sm font-medium transition-colors"
    mob_cls = "text-white/80 hover:text-white text-sm py-1"
    desktop_links = (
        f'<span class="links-all flex items-center gap-6">{links_html(all_links, desk_cls)}</span>'
        f'<span class="links-moths hidden items-center gap-6">{links_html(moth_links, desk_cls)}</span>'
        f'<span class="links-butterflies hidden items-center gap-6">{links_html(butterfly_links, desk_cls)}</span>'
        f'<span class="links-mammals hidden items-center gap-6">{links_html(mammal_links, desk_cls)}</span>'
        f'<span class="links-plants hidden items-center gap-6">{links_html(plant_links, desk_cls)}</span>'
        f'<span class="links-amphibians hidden items-center gap-6">{links_html(amphibian_links, desk_cls)}</span>'
        f'<span class="links-log hidden items-center gap-6">{links_html(log_links, desk_cls)}</span>')
    mob_links = (
        f'<div class="links-all flex flex-col gap-3">{links_html(all_links, mob_cls)}</div>'
        f'<div class="links-moths hidden flex-col gap-3">{links_html(moth_links, mob_cls)}</div>'
        f'<div class="links-butterflies hidden flex-col gap-3">{links_html(butterfly_links, mob_cls)}</div>'
        f'<div class="links-mammals hidden flex-col gap-3">{links_html(mammal_links, mob_cls)}</div>'
        f'<div class="links-plants hidden flex-col gap-3">{links_html(plant_links, mob_cls)}</div>'
        f'<div class="links-amphibians hidden flex-col gap-3">{links_html(amphibian_links, mob_cls)}</div>'
        f'<div class="links-log hidden flex-col gap-3">{links_html(log_links, mob_cls)}</div>')
    toggle = (
        '<div class="mode-toggle flex flex-wrap items-center justify-end rounded-2xl '
        'p-0.5 gap-0.5 bg-white/10 border border-white/15" role="group" aria-label="Switch view">'
        f'{mode_buttons()}</div>')
    return f"""
<a href="#whats-new" class="sr-only focus:not-sr-only focus:absolute focus:z-[60] focus:top-2 focus:left-2 focus:bg-white focus:text-stone-900 focus:px-3 focus:py-1 focus:rounded">Skip to content</a>
<nav id="navbar" class="nav-transparent fixed top-0 inset-x-0 z-50 transition-all duration-300">
  <div class="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
    <a href="{SITE}" class="flex items-center gap-2.5 shrink-0">{LOGO}
      <span id="nav-brand" class="font-serif text-white text-xl font-semibold tracking-wide transition-colors">Kingfisher Hollow</span></a>
    <div class="hidden md:flex items-center gap-4">
      {toggle}
      <a href="{SITE}" class="text-white/60 hover:text-white text-sm font-medium transition-colors whitespace-nowrap">← Main site</a>
    </div>
    <button onclick="document.getElementById('mob').classList.toggle('hidden')" class="md:hidden text-white p-1" aria-label="Menu">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg></button>
  </div>
  <div id="section-bar" class="hidden md:block">
    <div class="max-w-6xl mx-auto px-6 py-1.5 flex items-center gap-6">
      {desktop_links}
    </div>
  </div>
  <div id="mob" class="hidden md:hidden bg-hollow-950/95 px-6 py-4 flex flex-col gap-4 border-t border-white/10">
    <div class="mode-toggle flex flex-wrap gap-2" role="group" aria-label="Switch view">{mode_buttons()}</div>
    <div class="h-px bg-white/10"></div>
    {mob_links}
    <a href="{SITE}" class="text-hollow-300 text-sm py-1">← Main site</a>
  </div>
</nav>"""


_EASTERN = __import__("zoneinfo").ZoneInfo("America/New_York")


def _fmt_dt(dt):
    """Format a datetime as 'Jun 17 · 8:13am ET' — Eastern time, no leading zeros."""
    et = dt.astimezone(_EASTERN)
    h = et.hour % 12 or 12
    ampm = "am" if et.hour < 12 else "pm"
    return f"{et.strftime('%b')} {et.day} · {h}:{et.strftime('%M')}{ampm}"


def _code_updated():
    """Last commit to report.py or src/ that isn't a nightly CI chore or agent-copy commit."""
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent),
             "log", "--format=%cI\t%s", "--", "report.py", "src/"],
            capture_output=True, text=True, timeout=10)
        for line in (out.stdout or "").splitlines():
            iso, _, subject = line.partition("\t")
            if not iso.strip():
                continue
            if "[skip ci]" in subject or "Co-Authored-By" in subject:
                continue
            return _fmt_dt(datetime.fromisoformat(iso.strip()).astimezone())
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    return _fmt_dt(datetime.fromtimestamp(Path(__file__).stat().st_mtime).astimezone())


def _insights_updated():
    """Last commit where an AI agent wrote or refreshed content (Co-Authored-By: Claude)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent),
             "log", "-1", "--format=%cI", "--grep=Co-Authored-By: Claude"],
            capture_output=True, text=True, timeout=10)
        iso = (out.stdout or "").strip()
        if iso:
            return _fmt_dt(datetime.fromisoformat(iso).astimezone())
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    return "—"


def data_updated_date():
    """When the iNat data was last synced."""
    try:
        with connect() as conn:
            row = conn.execute("SELECT MAX(synced_at) AS t FROM sync_log").fetchone()
        if row and row["t"]:
            return _fmt_dt(datetime.fromisoformat(row["t"].replace(" ", "T")).astimezone())
    except Exception:
        pass
    return _fmt_dt(datetime.now(timezone.utc).astimezone())


def footer(code_updated, insights_updated, data_updated):
    def ts(label, value):
        return (f'<span class="flex flex-col items-center gap-0.5">'
                f'<span class="text-white/25 text-[0.6rem] uppercase tracking-[0.15em]">{label}</span>'
                f'<strong class="text-white/60 font-medium">{value}</strong>'
                f'</span>')
    return f"""
<footer class="bg-hollow-950 py-12 px-6">
  <div class="max-w-6xl mx-auto">
    <div class="flex flex-col md:flex-row items-center justify-between gap-6 mb-8 pb-8 border-b border-white/10">
      <div class="flex items-center gap-3">{LOGO}
        <div><div class="font-serif text-white text-lg font-semibold">Kingfisher Hollow</div>
        <div class="text-white/30 text-xs">Biodiversity Survey</div></div></div>
      <nav class="flex flex-wrap justify-center gap-x-7 gap-y-2 text-white/45 text-sm">
        <a href="{SITE}" class="hover:text-white/75 transition-colors">Main site</a>
        <a href="{PROJECT_URL}" target="_blank" rel="noopener" class="hover:text-white/75 transition-colors">iNaturalist project ↗</a>
      </nav>
    </div>
    <div class="flex flex-wrap items-start justify-center gap-x-8 gap-y-3 text-xs tracking-wide mb-4">
      {ts("Data synced", data_updated)}
      <span class="hidden sm:inline text-white/15 self-center">·</span>
      {ts("Insights updated", insights_updated)}
      <span class="hidden sm:inline text-white/15 self-center">·</span>
      {ts("Code updated", code_updated)}
    </div>
    <p class="text-center text-white/25 text-xs tracking-wide">Data from iNaturalist · Photos © their respective observers · Survey ongoing June 2025–2026</p>
  </div>
</footer>"""


SCRIPTS = """
<script>
  const navbar=document.getElementById('navbar'),brand=document.getElementById('nav-brand'),
        navLinks=navbar.querySelectorAll('.nav-link');
  function updateNav(){const p=window.scrollY>60;navbar.classList.toggle('nav-transparent',!p);
    navbar.classList.toggle('nav-solid',p);brand.style.color=p?'#1c1917':'#fff';
    navLinks.forEach(a=>a.style.color=p?'#44403c':'');}
  window.addEventListener('scroll',updateNav,{passive:true});updateNav();
  document.querySelectorAll('#mob a').forEach(a=>a.addEventListener('click',()=>document.getElementById('mob').classList.add('hidden')));

  // Life-list filter + search (pinned pills + a dropdown for the long tail)
  (function(){
    const rows=[...document.querySelectorAll('.ll-row')],search=document.getElementById('ll-search'),
          count=document.getElementById('ll-count'),sel=document.getElementById('ll-select');let group='all';
    function apply(){const q=(search.value||'').toLowerCase();let n=0;
      rows.forEach(r=>{const okG=group==='all'||r.dataset.group===group,
        okQ=!q||r.dataset.name.includes(q);const show=okG&&okQ;
        r.style.display=show?'':'none';if(show)n++;});
      count.textContent=n+' species shown';}
    function activate(g,fromSelect){group=g;
      document.querySelectorAll('.ll-filter').forEach(x=>{const on=(x.dataset.group===g);
        x.classList.toggle('ll-active',on);x.setAttribute('aria-pressed',on?'true':'false');});
      if(sel&&!fromSelect)sel.value='';apply();}
    document.querySelectorAll('.ll-filter').forEach(b=>b.addEventListener('click',()=>activate(b.dataset.group)));
    if(sel)sel.addEventListener('change',()=>{if(sel.value){
      document.querySelectorAll('.ll-filter').forEach(x=>{x.classList.remove('ll-active');x.setAttribute('aria-pressed','false');});
      activate(sel.value,true);}});
    if(search)search.addEventListener('input',apply);apply();
  })();

  // Scroll reveal
  const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}}),{threshold:0.08});
  document.querySelectorAll('.reveal').forEach(el=>io.observe(el));

  // Mode toggle: All life / Moths / Mammals / Plants / Log — one page, five views.
  (function(){
    const MODES=['all','moths','butterflies','mammals','plants','amphibians','log'];
    const views=Object.fromEntries(MODES.map(m=>[m,document.getElementById('view-'+m)]));
    function setMode(mode,force){
      if(!MODES.includes(mode)) mode='all';
      document.body.dataset.mode=mode;
      MODES.forEach(m=>views[m]&&views[m].classList.toggle('hidden',m!==mode));
      // Swap nav link set to match active view.
      MODES.forEach(m=>{
        document.querySelectorAll('.links-'+m).forEach(e=>{
          const on=mode===m;e.classList.toggle('hidden',!on);e.classList.toggle('flex',on);});});
      document.querySelectorAll('.mode-btn').forEach(b=>{const on=b.dataset.mode===mode;
        b.classList.toggle('mode-active',on);b.setAttribute('aria-pressed',on?'true':'false');});
      const hashes={moths:'#moths',butterflies:'#butterflies',mammals:'#mammals',plants:'#plants',amphibians:'#amphibians',log:'#log'};
      history.replaceState(null,'',hashes[mode]||location.pathname);
      updateNav&&updateNav();
      if(force){
        document.querySelectorAll('#view-'+mode+' .reveal').forEach(el=>el.classList.add('in'));
        window.dispatchEvent(new Event('resize'));
      }
    }
    document.querySelectorAll('.mode-btn').forEach(b=>b.addEventListener('click',()=>{
      setMode(b.dataset.mode,true);window.scrollTo({top:0,behavior:'smooth'});
      document.getElementById('mob').classList.add('hidden');}));
    const h=location.hash;
    const fromHash={['#moths']:'moths',['#butterflies']:'butterflies',['#mammals']:'mammals',['#plants']:'plants',['#amphibians']:'amphibians',['#log']:'log'};
    setMode(fromHash[h]||'all', h in fromHash);
  })();
</script></body></html>"""


def moth_view(df, stats):
    """The dark, moth-only report: stats, completeness, flight seasons, the
    county gap list, diversity, and a showcase. Returns concatenated sections."""
    moths = analyze.load_moths()
    if moths.empty:
        return section("moths", "After Dark", "The Moths",
                       '<p class="text-center text-white/60">Moth roster not synced '
                       'yet.</p>', dark=True)
    msum = analyze.moth_summary(df, moths)
    comp = analyze.moth_completeness(df, moths)
    import datetime as _dt
    _today = _dt.date.today()
    _window_end = _today + _dt.timedelta(days=14)
    target_months = sorted({_today.month, _window_end.month})
    gap = analyze.moth_county_gap(moths, n=50, target_months=target_months)
    div = analyze.moth_diversity(df, moths)
    eff = analyze.moth_effort(df, moths)
    moth_sub = analyze.moth_obs(df, moths)

    out = []
    out.append(section(
        'moth-why-here', 'Riparian Context', 'Why <em class="text-hollow-300">Here</em>',
        property_profile_body(),
        intro='Michigan Creek explains the moth numbers. Here is why.',
        dark=True))
    out.append(section(
        "moths", "After Dark", 'The <em class="text-hollow-300">Moths</em>',
        moth_stats(msum, comp),
        intro="576 moth species on 30 riparian acres, and 228 of them are first iNaturalist records for "
              "Tioga County. That says two things at once: the county has been thinly sampled, and this stretch "
              "of Michigan Creek is a real moth engine. The regional comparison is shaped by heavy Tompkins "
              "County effort, especially on micromoths, so the gap list is a target list rather than a verdict. "
              "The strongest KH signal is ecological: humid creek nights, oak-hickory and northern-hardwood "
              "canopy, wetland edges, and 253 recorded plant species supporting many host-linked guilds.",
        dark=True))
    out.append(section(
        "moth-gallery", "In Pictures",
        'Recent <em class="text-hollow-300">Moths</em>',
        gallery_body(analyze.photo_highlights(moth_sub)),
        intro="Recent moth photographs from the property.",
        dark=True))

    _import_calendar = __import__('calendar')
    _month_names = [_import_calendar.month_name[m] for m in target_months]
    _months_label = " and ".join(_month_names)
    out.append(section(
        "moth-gap", "Yet to Find",
        'The <em class="text-hollow-300">Gap List</em>',
        moth_gap_body(gap)
        + takeaway(
            f"Filtered to species with county records in {_months_label} — the flight window covering the next two weeks. "
            "Tioga County's moth records are thin, and many nearby records come from well-worked Tompkins County, "
            "so this list draws from the ~50-mile regional pool with that bias in mind. Species at the top are "
            "seen repeatedly nearby in these same weeks; their absence here is usually a survey-method gap, not "
            "evidence that the property lacks the habitat. "
            "Catocala underwings come poorly to UV but readily to sugar bait on warm August nights. "
            "Different gaps need different methods.", dark=True),
        intro=f"Moth species recorded within ~50 miles but not yet found on the property, ranked by how often they appear in {_months_label} county records. Tompkins County effort inflates some regional frequencies, especially for micros, so treat this as a practical field queue.",
        dark=True))
    out.append(section(
        "moth-families", "By Family",
        'Where the <em class="text-hollow-300">Gaps</em> Are',
        chart_card(viz.family_breakdown(analyze.moth_family_breakdown(moths)),
                   note="Solid bar: species recorded here. Faint bar: species known within ~50 miles. Numbers at bar ends show the recorded-to-regional ratio. Sorted by recorded species count.",
                   dark=True)
        + takeaway(
            "The large, conspicuous families — Noctuidae (owlet moths), Geometridae (geometers), Erebidae "
            "(tiger moths and kin) — are well represented because they're big enough to identify at the sheet. "
            "The micro-moth families tell a different story. Tortricidae, Gelechiidae, Coleophoridae, and "
            "Nepticulidae hold a large share of temperate moth diversity, but many records require leaf-mine "
            "work, host association, expert review, or collection-level evidence. KH should prioritize the "
            "photo-workable and host-informative micros, not chase every dissection-only species. Tortricidae "
            "has now reached 71 species here, so the leaf-roller gap is starting to close; the remaining "
            "undetected fauna is concentrated in methods the standard UV sheet barely samples.", dark=True),
        intro="The moth fauna isn't evenly sampled. Some families are nearly fully inventoried by the current approach; others are mostly visible only through host-plant work, bait, canopy sampling, or expert micro review.",
        dark=True))
    out.append(section(
        "moth-standouts", "Standouts",
        'Rare &amp; <em class="text-hollow-300">Notable</em>',
        moth_showcase(analyze.moth_highlights(moths, stats, df=df)),
        intro="Moths from Kingfisher Hollow with few iNaturalist records in New York. Some are truly notable; others are under-documented micros or hard IDs that need context from MPG, BAMONA, BugGuide, GBIF, and collections before anyone calls them rare.",
        dark=True))

    # Headline diagnostic: species detected on only one or two nights.
    once_band = (
        '<div class="flex flex-wrap items-start justify-center gap-8 md:gap-12 mb-8">'
        + _dark_divider().join([
            _dark_stat(f"{comp['q1']}", "On one night only"),
            _dark_stat(f"{comp['q2']}", "On just two nights"),
            _dark_stat(f"{comp['nights']}", "Survey nights"),
        ]) + '</div>')
    out.append(section(
        "moth-completeness", "How Complete?",
        'The Inventory, <em class="text-hollow-300">Estimated</em>',
        once_band
        + chart_card(viz.completeness_curve(eff, comp),
                     note=f"Chao2 uses the ratio of species seen on exactly one night (Q1) vs. exactly two nights (Q2) across {comp['nights']} survey sessions to project undetected species. Shaded band: 95% CI. The curve hasn't flattened yet.",
                     dark=True)
        + takeaway(
            f"Of the <strong>{comp['observed']}</strong> moth species confirmed here, "
            f"<strong>{comp['q1']}</strong> have appeared on exactly one night — seen once and not since. "
            f"That single-night rate drives the Chao2 estimate: roughly "
            f"<strong>{comp['estimated']}</strong> species total (95% CI: {comp['low']}–{comp['high']}), "
            f"putting the survey about <strong>{comp['pct_complete']}%</strong> complete. The regional pool is "
            f"larger, and many records in it come from better-sampled Tompkins County or from habitats this property doesn't have. "
            f"The ~780 ceiling is a realistic figure for this specific place — and Chao2 is a lower bound, so "
            f"it may be conservative. The roughly {comp['remaining']} undetected "
            f"species aren't evenly distributed; they're concentrated in cold-season moths, bait-feeders, canopy "
            f"species, and micro-moth families that a UV sheet samples poorly. Targeted work on the photo-workable "
            f"Tortricidae and host-linked micros would close the most useful part of the gap.", dark=True),
        intro="576 species confirmed. Statistical modeling puts the true total around 780. Here's the evidence for that gap — and how fast it's closing.",
        dark=True))
    out.append(section(
        "moth-diversity", "Diversity",
        'A <em class="text-hollow-300">Balanced</em> Community',
        moth_diversity_body(div)
        + chart_card(viz.rank_abundance(div.get("rank_abundance", [])),
                     note="Species ranked by total records, log scale. A steep initial drop followed by a long flat tail indicates high evenness — no species dominates. Terracotta: species recorded only once or twice.",
                     dark=True)
        + takeaway(
            "A rank-abundance curve for a degraded habitat drops steeply: one or two species dominate, the "
            "rest are noise. This one doesn't. It slopes gently across hundreds of species — no single "
            "species has crowded out the rest. Ecologists call that high evenness, and it's a reliable "
            "indicator of structurally complex habitat. The gentle slope across 576 species is what you'd "
            "predict from a site with 253 plant species on 30 acres, each supporting distinct moth guilds, "
            "with the three-province ecotone adding guild diversity on top. "
            "The long flat tail on the right — all the once-or-twice-seen species — is the frontier of "
            "what's still being found.", dark=True),
        intro="Is the moth community dominated by a handful of species, or is it broadly distributed? The diversity metrics give an unusually clear answer.",
        dark=True))

    # Combined calendar section: Month by Month + On the Wing + Phenology
    msum_monthly = analyze.monthly_survey_summary(df, moths)
    season_months = [r for r in msum_monthly if r['survey_season'] and r['nights_surveyed'] > 0]
    best_roi = max(season_months, key=lambda r: r['new_species_count'] / r['nights_surveyed']) if season_months else None
    best_roi_text = (
        f"<strong>{best_roi['month_name']}</strong> has produced the most new species per survey night "
        f"({best_roi['new_species_count']} firsts across {best_roi['nights_surveyed']} nights). "
        "Months with a tall terracotta bar but a short green one are where additional effort would pay off. "
        "The core season runs late June through August; nights below 55°F or near a full moon are mostly quiet."
    ) if best_roi else ''
    out.append(section(
        "moth-calendar", "The Calendar",
        'Flight <em class="text-hollow-300">Seasons</em>',
        chart_card(viz.monthly_survey_bar(msum_monthly),
                   note='Green: species recorded that month. Terracotta: species recorded for the first time ever. '
                        'Faded months are outside the May–September core flight season. Hover for survey-night counts.',
                   dark=True)
        + takeaway(best_roi_text, dark=True)
        + chart_card(viz.seasonal_cascade(analyze.moth_seasonal(df, moths), dark=True),
                     note="Faint line: full observed date range. Thick bar: middle 50% of records (core flight window). Dot: median date. Species with fewer than 3 records omitted. Sorted by median flight date.",
                     dark=True)
        + takeaway(
            "Each row is one species. The thick bar is its core flight window — the middle 50% of records. "
            "The faint line reaches its earliest and latest confirmed dates. Read all 576 rows together and "
            "you get the season's shape: sparse in April, a sharp peak in June, a gap in July where the "
            "lights weren't running, a full second plateau through August, fading through September and "
            "October. After one field season these windows are first drafts; they'll sharpen as more nights "
            "accumulate.", dark=True)
        + chart_card(viz.phenology(analyze.phenology(moth_sub), dark=True, normalize=True),
                     note="Each row is normalized to its own peak, so a species seen 4 times reads as vividly as one seen 400 times. Hover any cell for raw observation counts.",
                     dark=True)
        + takeaway(
            "Scan a row: that species' season, bright at its peak, dark where it disappears. Scan a column: "
            "the active community for that month. The sparse winter columns are partly real — few moths fly "
            "in January and February — and partly a survey gap, since few people run lights in the cold. "
            "Both things are true, and more data will eventually separate them.", dark=True),
        intro="Month-by-month totals and first records, individual flight windows for every species, and the full phenology matrix — the complete calendar of Kingfisher Hollow's moth season.",
        dark=True))
    out.append(section(
        "moth-methods", "Find More",
        'How to Find <em class="text-hollow-300">More</em>',
        survey_methods_body(MOTH_METHODS),
        intro="576 species came almost entirely from a UV sheet, which selects for large, photo-positive "
              "moths. These are the methods that reach the rest: bait-feeders, day and dusk fliers, canopy "
              "species, cold-season moths, and the host-linked micros worth documenting without turning the "
              "survey into a collection project.",
        dark=True))
    return "".join(out)


def mammals_view(df, stats):
    """Dark mammals view: stats band + found grid + regional gap list."""
    import datetime as _dt
    mammals = analyze.load_mammals()
    _today = _dt.date.today()
    target_months = sorted({_today.month, (_today + _dt.timedelta(days=14)).month})
    gap = analyze.mammal_gap(mammals, n=30, target_months=target_months)
    found = analyze.mammal_found(df, mammals) if not mammals.empty else mammals
    msum = analyze.mammal_summary(df, mammals) if not mammals.empty else {"species": 0, "records": 0, "top_month": ""}
    stats_band = (
        '<div class="flex flex-wrap items-start justify-center gap-8 md:gap-12 mb-8">'
        + _dark_divider().join([
            _dark_stat(str(msum["species"]), "mammal species"),
            _dark_stat(str(msum["records"]), "total records"),
            _dark_stat(msum.get("top_month") or "—", "peak month"),
        ]) + '</div>')
    out = []
    out.append(section(
        "mammals", "Warm-blooded",
        'The <em class="text-hollow-300">Mammals</em>',
        stats_band
        + takeaway(
            "What stands out in 22 species is the carnivore set: ten carnivores on 30 acres, including all "
            "four native mustelids (fisher, mink, long-tailed weasel, and ermine), both foxes, and the full "
            "black bear, coyote, and bobcat trio. That density on a parcel this small is the mark of the "
            "Michigan Creek corridor working as a travel route, with the stream-tied fisher and mink the "
            "most-documented of them. Eastern cottontail is the newest first record, logged this June. The "
            "rarest holding stays the eastern woodland jumping mouse, a riparian-forest indicator with only "
            "two records in all of Tioga County.", dark=True)
        + mammal_found_body(found),
        intro="The mammal list is detection-limited. Trail cameras and incidental tracks show the mid-sized corridor users well, but bats, shrews, voles, mice, moles, and semi-aquatic mammals need their own methods. Michigan Creek is the reason a 30-acre property can carry this much carnivore traffic.",
        dark=True))
    out.append(section(
        "mammal-gap", "Who's Missing?",
        'Mammal <em class="text-hollow-300">Gap List</em>',
        mammal_gap_body(gap),
        intro="Mammals confirmed within ~50 miles but not yet recorded at Kingfisher Hollow. The useful targets are not the most photographed regional mammals; they're the ones that fit the creek corridor, wet margins, forest floor, and night sky.",
        dark=True))
    out.append(section(
        "mammal-methods", "Find More",
        'How to Find <em class="text-hollow-300">More</em>',
        survey_methods_body(MAMMAL_METHODS),
        intro="22 species, and not one bat. These methods target the guilds a trail camera misses: acoustic "
              "fliers over the creek, small mammals in leaf litter, and semi-aquatic mammals moving through "
              "culverts, riffles, and log crossings.",
        dark=True))
    return "".join(out)


def plants_view(df, stats):
    """Dark plants view: stats band + found grid + regional gap list."""
    import datetime as _dt
    plants = analyze.load_plants()
    _today = _dt.date.today()
    target_months = sorted({_today.month, (_today + _dt.timedelta(days=14)).month})
    gap = analyze.plant_gap(plants, n=50, target_months=target_months)
    found = analyze.plant_found(df, plants) if not plants.empty else plants
    psum = analyze.plant_summary(df, plants) if not plants.empty else {"species": 0, "records": 0, "top_month": ""}
    # Per-group counts for the secondary band
    grp_counts = {}
    if not plants.empty and "plant_group" in plants.columns:
        grp_counts = plants["plant_group"].value_counts().to_dict()
    stats_band = (
        '<div class="flex flex-wrap items-start justify-center gap-8 md:gap-12 mb-4">'
        + _dark_divider().join([
            _dark_stat(str(psum["species"]), "plant species"),
            _dark_stat(str(psum["records"]), "total records"),
            _dark_stat(psum.get("top_month") or "—", "peak month"),
        ]) + '</div>'
        + '<div class="flex flex-wrap items-start justify-center gap-6 md:gap-10 mb-8 '
        + 'border-t border-white/10 pt-4">'
        + _dark_divider().join([
            _dark_stat(str(grp_counts.get("Angiosperm", 0)),        "angiosperms",        "flowering plants"),
            _dark_stat(str(grp_counts.get("Seedless Vascular", 0)), "seedless vascular",  "ferns &amp; allies"),
            _dark_stat(str(grp_counts.get("Gymnosperm", 0)),        "gymnosperms",        "conifers"),
            _dark_stat(str(grp_counts.get("Bryophyte", 0)),         "bryophytes",         "mosses &amp; allies"),
        ]) + '</div>')
    out = []
    out.append(section(
        "plants", "Green World",
        'The <em class="text-hollow-300">Plants</em>',
        stats_band
        + takeaway(
            "The plant list now reads like a compact Tioga County cross-section: oak-hickory upland, "
            "northern-hardwood slope, hemlock shade, wet meadow, pond edge, and creek corridor all packed into "
            "30 acres. The oak-and-hickory backbone explains much of the caterpillar richness, while alder, "
            "willow, dogwoods, viburnum, grape, goldenrods, asters, sedges, and wetland forbs point to the next "
            "wave of insect records. Two high-value groups are still thin: Salix is down to one species "
            "(shining willow) against a large regional pool, and Carex stands at two. Those are survey gaps, "
            "not ecological absences.", dark=True)
        + plant_found_body(found),
        intro="253 plant species on 30 acres, with a transition-zone signature: Appalachian ravine plants, "
              "northern hardwoods, wetland/riparian flora, old-field edge, and southern-edge woody possibilities "
              "all close together. Each native genus recorded here is potential structure, food, or larval host "
              "for the rest of the survey.",
        dark=True))
    out.append(section(
        "plant-gap", "What's Unrecorded?",
        'Plant <em class="text-hollow-300">Gap List</em>',
        plant_gap_body(gap),
        intro="Plants confirmed within ~50 miles but not yet documented at Kingfisher Hollow. Treat this as a field checklist filtered by habitat: spring rich woods, seep and pond edge, acidic upland, creek corridor, and sunny old-field margins.",
        dark=True))
    out.append(section(
        "plant-methods", "Find More",
        'How to Find <em class="text-hollow-300">More</em>',
        survey_methods_body(PLANT_METHODS),
        intro="253 species, with spring ephemerals, sedges, willows, grasses, aquatics, and cryptogams still "
              "under-sampled. These passes target the gaps when each group is actually identifiable.",
        dark=True))
    return "".join(out)


def amphibians_view(df, stats):
    """Dark herps view: amphibians + reptiles found + combined gap list."""
    amphibians = analyze.load_amphibians()
    reptiles = analyze.load_reptiles()
    amp_gap = analyze.amphibian_gap(amphibians, n=25)
    rep_gap = analyze.reptile_gap(reptiles, n=25)
    amp_found = analyze.amphibian_found(df, amphibians) if not amphibians.empty else amphibians
    rep_found = analyze.reptile_found(df, reptiles) if not reptiles.empty else reptiles
    asum = (analyze.amphibian_summary(df, amphibians) if not amphibians.empty
            else {"species": 0, "records": 0, "top_month": ""})
    rsum = (analyze.reptile_summary(df, reptiles) if not reptiles.empty
            else {"species": 0, "records": 0, "top_month": ""})
    stats_band = (
        '<div class="flex flex-wrap items-start justify-center gap-8 md:gap-12 mb-8">'
        + _dark_divider().join([
            _dark_stat(str(asum["species"]), "amphibian species"),
            _dark_stat(str(rsum["species"]), "reptile species"),
            _dark_stat(str(asum["records"] + rsum["records"]), "total records"),
        ]) + '</div>')
    out = []
    out.append(section(
        "amphibians", "At the Water's Edge",
        'The <em class="text-hollow-300">Amphibians</em>',
        takeaway(
            "Ten amphibian species is a strong incidental list, but the habitat says there is more to find. "
            "The confirmed set includes spring peeper, American toad, gray treefrog, pickerel frog, eastern "
            "newt, red-backed salamander, northern slimy salamander, and spotted salamander, so the forest, "
            "pond, seep, and vernal-pool signals are all present. The obvious hole is stream salamanders: "
            "riffles and seepage zones should be checked for two-lined, dusky, and spring salamanders before "
            "the site is treated as well sampled.", dark=True)
        + amphibian_found_body(amp_found),
        intro="Frogs and salamanders are method- and season-dependent. The current list already points to "
              "clean water, wet forest floor, and breeding wetlands, but it is still mostly incidental. Rainy "
              "nights, spring egg-mass checks, and careful creek rock surveys are the missing effort.",
        dark=True))
    out.append(section(
        "reptiles-found", "Sun & Scale",
        'The <em class="text-hollow-300">Reptiles</em>',
        stats_band + reptile_found_body(rep_found),
        intro="Seven reptile species are confirmed, including watersnake, snapping turtle, painted turtle, "
              "milksnake, DeKay's brownsnake, and gray ratsnake. Most records are incidental. Slow basking "
              "checks, cover-board work, and creek-edge walks should add the small secretive snakes and clarify "
              "how turtles use the pond and Michigan Creek.",
        dark=True))
    out.append(section(
        "amphibian-gap", "Yet to Find",
        'Herp <em class="text-hollow-300">Gap List</em>',
        '<h3 class="text-sm font-semibold tracking-widest uppercase text-white/40 mb-3">Amphibians</h3>'
        + amphibian_gap_body(amp_gap)
        + '<h3 class="text-sm font-semibold tracking-widest uppercase text-white/40 mt-8 mb-3">Reptiles</h3>'
        + reptile_gap_body(rep_gap),
        intro="Species recorded within ~50 miles but not yet documented here. For herps, regional frequency matters less than timing: rainy migration nights, spring chorus windows, cover objects, basking logs, and stream-rock checks decide what appears.",
        dark=True))
    out.append(section(
        "amphibian-methods", "Find More",
        'How to Find <em class="text-hollow-300">More</em>',
        survey_methods_body(AMPHIBIAN_METHODS),
        intro="Most herp records here are incidental. Targeted audio, egg-mass, stream, cover-object, and "
              "basking surveys are how the list grows. Replace cover exactly as found and treat sensitive "
              "locations carefully.",
        dark=True))
    return "".join(out)


def butterflies_view(df, stats):
    """Dark butterflies view: what's been found + the regional gap list."""
    butterflies = analyze.load_butterflies()
    gap = analyze.butterfly_gap(butterflies, n=30)
    found = (analyze.butterfly_found(df, butterflies) if not butterflies.empty
             else butterflies)
    bsum = (analyze.butterfly_summary(df, butterflies) if not butterflies.empty
            else {"species": 0, "records": 0, "top_month": ""})
    stats_band = (
        '<div class="flex flex-wrap items-start justify-center gap-8 md:gap-12 mb-8">'
        + _dark_divider().join([
            _dark_stat(str(bsum["species"]), "butterfly species"),
            _dark_stat(str(bsum["records"]), "total records"),
            _dark_stat(bsum.get("top_month") or "—", "peak month"),
        ]) + '</div>')
    out = []
    out.append(section(
        "butterflies", "By Day",
        'The <em class="text-hollow-300">Butterflies</em>',
        stats_band + butterfly_found_body(found),
        intro="Butterflies are the daytime half of the property's Lepidoptera, and this list is still "
              "effort-limited. Eighteen species against 576 moths says more about survey timing than habitat. "
              "The plants are already here for many missing species: violets, nettles, willows, oaks, hickories, "
              "cherries, sedges, turtlehead, milkweeds, asters, and goldenrods.",
        dark=True))
    out.append(section(
        "butterfly-gap", "Yet to Find",
        'Butterfly <em class="text-hollow-300">Gap List</em>',
        butterfly_gap_body(gap),
        intro="Butterflies recorded within ~50 miles but not yet found here. The first wins are daytime method "
              "gaps: skippers in grass and wet edges, hairstreaks around oak-hickory canopy and shrub edges, "
              "and conspicuous brushfoots that need repeated sunny walks.",
        dark=True))
    out.append(section(
        "butterfly-methods", "Find More",
        'How to Find <em class="text-hollow-300">More</em>',
        survey_methods_body(BUTTERFLY_METHODS),
        intro="Eighteen species is a barely-started list. Repeated sunny transects, dorsal and ventral photos, "
              "fruit bait, puddling checks, and host-plant searches across spring, midsummer, and fall would "
              "multiply it quickly.",
        dark=True))
    return "".join(out)


def survey_methods_body(methods):
    """Field-method cards — how to expand a taxon's list: where, when, what it adds.
    Responsive grid (1 col on phones, up to 3 on desktop)."""
    cards = []
    for m in methods:
        rows = ""
        for label, val in (("Where", m.get("where")), ("When", m.get("when")),
                           ("Adds", m.get("targets"))):
            if not val:
                continue
            rows += (
                '<div class="mt-3">'
                f'<span class="text-hollow-300 text-[0.6rem] font-semibold tracking-[0.18em] uppercase">{label}</span>'
                f'<p class="text-white/70 text-[0.9rem] leading-snug mt-1">{esc(val)}</p>'
                '</div>')
        cards.append(
            '<div class="bg-white/[0.04] border border-white/10 rounded-2xl p-5 md:p-6">'
            f'<h4 class="font-serif text-xl text-white font-semibold leading-tight">{esc(m["method"])}</h4>'
            f'{rows}</div>')
    return ('<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">'
            + "".join(cards) + '</div>')


# ── Field methods to expand each list — sourced from the taxa expert agents ───
MOTH_METHODS = [
    {"method": "Sugar baiting",
     "where": "Rum-molasses-overripe-banana ferment painted in vertical streaks on mature oak, maple, and shagbark hickory trunks along the mesic slope edge and the floodplain terrace, 50–100 m from the creek where humidity holds.",
     "when": "Warm, humid August nights, 64–75°F, no moon, light wind; bait at dusk and check by headlamp every 45–60 min until 1 AM. Repeat on warm September nights.",
     "targets": "Catocala underwings (come poorly to UV) and bait-positive Noctuidae — Eupsilia, Lithophane, Sunira, Amphipyra, Scoliopteryx — that the light sheet misses."},
    {"method": "Larval beating",
     "where": "Beating sheet under low streamside Salix and Alnus, plus Carya, Quercus, Acer and Betula on the mesic slope; tap branches and rear what drops.",
     "when": "June–July daytime for peak Tortricidae and Gelechiidae larvae; a second pass in September. Rear larvae on host foliage to confirm species on emergence.",
     "targets": "Micro-moths that never reach UV: Tortricidae, Gelechiidae, Coleophoridae case-bearers, Nepticulidae leaf-miners — the bulk of the undetected species."},
    {"method": "Canopy light sheet",
     "where": "A second sheet hoisted 10–15 m on a rope-and-pulley over a canopy gap in the mesic slope forest, well above the standard ground sheet.",
     "when": "Calm June–July nights, 60–72°F, humidity above 60%, no moon; run from 30 min before dark to 2 AM alongside the ground sheet.",
     "targets": "The Eupithecia complex (20+ species likely) and canopy-flying micro-geometrids and Tortricidae that rarely descend to a ground sheet."},
    {"method": "Dual light comparison",
     "where": "A 160W mercury-vapor bulb and a 15W actinic on separate sheets ~30 m apart at the floodplain-creek ecotone, the property's richest edge.",
     "when": "Peak June and July nights, 60–72°F, no moon, light wind; full dark to 2 AM, swapping observers between stations hourly.",
     "targets": "Species one light type filters out — MV pulls large Sphingidae, Saturniidae (watch for Hyalophora cecropia) and Catocala; actinic adds small Geometridae and microleps."},
    {"method": "Shoulder-season runs",
     "where": "The standard ground sheet at the sheltered creek bank, where the humidity buffer keeps moths flying on cold nights.",
     "when": "Seasons the survey neglects: warm late-September and October nights, November dusk runs at 38–50°F for Operophtera, and late-March/April nights above 45°F.",
     "targets": "Cold-season specialists absent from the June/August-heavy record: Operophtera, Sunira, late Noctuidae, and the early-spring Orthosia quaker complex."},
]

BUTTERFLY_METHODS = [
    {"method": "Transect netting",
     "where": "A fixed walk along the sunlit upland edge and the mowed floodplain openings, hitting nectar patches (milkweed, dogbane, joe-pye, asters) and damp creek-bank mud.",
     "when": "Warm sunny days late April–September, 10 AM–3 PM, above 65°F with little wind; weekly visits to catch successive flights.",
     "targets": "Most of the missing 40+ resident butterflies — whites and sulphurs, fritillaries and admirals, and the grass-skippers no one has netted."},
    {"method": "Creek mud-puddling",
     "where": "Wet gravel bars, seep margins, and damp sandy mud along Michigan Creek and at spring seeps where minerals concentrate.",
     "when": "Hot sunny mid-summer afternoons, 75–90°F, low wind, especially the day after rain when fresh mud is exposed.",
     "targets": "Puddling swallowtails, sulphurs, and the blues and hairstreaks (Celastrina, Satyrium, Cupido) drawn to mineral seeps."},
    {"method": "Host-plant larval search",
     "where": "Known larval hosts on site: violets on the mesic slope, Salix and Populus on the floodplain, spicebush and Prunus along edges, grasses and sedges in openings.",
     "when": "May–August daytime; search leaf damage, rolled leaves, and frass, and rear larvae to adult.",
     "targets": "Breeding residents missed by adult counts — fritillaries, viceroy and admirals, spicebush swallowtail, and cryptic satyrs."},
    {"method": "Fermented-fruit traps",
     "where": "Van Someren-Rydon hanging traps baited with fermented banana, 3–5 m up at the mesic slope forest edge and along shaded floodplain woodland.",
     "when": "Mid-June through September; set in the morning and check daily, best on warm humid stretches.",
     "targets": "Sap- and fruit-feeding woodland Nymphalidae that ignore flowers: hackberry and tawny emperors, mourning cloak and anglewings."},
    {"method": "Early-spring edge watch",
     "where": "South-facing upland edge and sun-warmed forest openings where overwintered adults and first broods bask.",
     "when": "The first warm sunny days of March–April, above 55°F, late morning — the season the record barely covers.",
     "targets": "Overwintering and early fliers: mourning cloak, commas and question mark, spring azure, and the elfins."},
    {"method": "Dusk skipper survey",
     "where": "Grassy and sedge-dominated floodplain openings and the damp creek-edge meadow.",
     "when": "June–July, late afternoon into early evening when grass-skippers perch low; sunny, calm conditions.",
     "targets": "Cryptic skippers (Poanes, Polites, Wallengrenia, Euphyes) tied to the floodplain graminoids."},
]

PLANT_METHODS = [
    {"method": "Spring ephemeral walk",
     "where": "Mesic slope forest above the creek, especially rich toe-of-slope benches and seep margins with deep, moist leaf litter.",
     "when": "Late March–late April, mid-morning, before the maple-beech canopy leafs out; time it to the first Sanguinaria and Erythronium bloom.",
     "targets": "Trillium, Claytonia, Dicentra cucullaria, Cardamine, Anemone, and several Viola — photograph leaf and flower together."},
    {"method": "Sedge survey",
     "where": "Active floodplain and gravel bars along the creek, plus wet seeps and the shrub-wetland transition; revisit drier upland edges.",
     "when": "Mid-June through July when perigynia are mature, any time of day.",
     "targets": "Streamside Carex (lurida, crinita, stipata, vulpinoidea) and upland sedges; also Scirpus, Glyceria, Sparganium. Two Carex confirmed against 108 in the regional pool — still the property's biggest botanical gap."},
    {"method": "Willow inventory",
     "where": "Creek banks, point bars, and the riparian shrub fringe alongside Alnus and Cornus.",
     "when": "April for catkins (sex and bloom timing), then June–July for mature leaves; midday for good underside lighting.",
     "targets": "Salix — one species confirmed (shining willow) against ~26 in the pool; likely eriocephala, sericea, nigra, discolor still unrecorded. Note leaf shape, underside, stipules, catkin timing."},
    {"method": "Late-composite pass",
     "where": "Sunny upland edges, the old-field/shrub transition, and the open floodplain margin.",
     "when": "Late August into September at peak bloom, midday — Solidago and aster ID needs open flower heads.",
     "targets": "Additional Solidago and asters beyond those recorded, plus Eutrochium variants. Photograph basal and stem leaves separately."},
    {"method": "Lichen & bryophyte transect",
     "where": "Shaded streamside boulders, splash-zone bedrock, decaying floodplain logs, and the bases of mature slope-forest trees.",
     "when": "Late autumn through early spring, or any damp overcast day when thalli are hydrated; low-angle light.",
     "targets": "Crustose and foliose lichens and additional bryophytes and liverworts — a near-blank group with only a few mosses recorded."},
    {"method": "Vine & bramble pass",
     "where": "Forest edges, fence lines, blowdown gaps, and the shrub-wetland transition where light reaches the understory.",
     "when": "July for Rubus fruit and Vitis leaves; September for ripe vine fruit and seed.",
     "targets": "Celastrus (native vs. invasive), more Vitis and Parthenocissus, Toxicodendron, Menispermum, and unrecorded Rubus by armature and leaflet."},
]

MAMMAL_METHODS = [
    {"method": "Acoustic bat survey",
     "where": "Over the open creek channel in a canopy gap where bats funnel and forage; an AudioMoth or Echo Meter on a tripod 1–2 m above the bank, mic down the channel.",
     "when": "Late May–early September, warm (>50°F) calm nights; record from 30 min before sunset through midnight, peak in the first two hours after dusk.",
     "targets": "The property's first bats: Big Brown, Eastern Red, Little Brown, Tri-colored, Silver-haired, Hoary; possibly Northern Long-eared near big snags."},
    {"method": "Sherman live trapping",
     "where": "A transect of 8–12 baited traps along the creek bank and wetland-edge transition, set at runways under root tangles, logs, and the slope base.",
     "when": "May–October; set at dusk, check at dawn, run 2–3 consecutive nights. Add bedding on cold nights.",
     "targets": "Small-mammal gaps: meadow, red-backed and woodland voles, meadow jumping mouse, and additional Peromyscus."},
    {"method": "Pitfall array",
     "where": "Wet riparian margin and seep edges between wetland and slope forest; buried cups along a low drift-fence through saturated leaf litter.",
     "when": "May–October, run continuously 3–5 nights with daily morning checks; most productive in damp spells.",
     "targets": "Shrews and moles that evade Sherman traps: masked, smoky and pygmy shrews, star-nosed and hairy-tailed moles."},
    {"method": "Water-crossing camera",
     "where": "A narrow ford, culvert, or log spanning the creek, plus any latrine boulder or muddy bank slide; camera mounted low, aimed at the crossing.",
     "when": "Year-round, left 4–8 weeks. Winter adds snow-track confirmation; otter and mink work ice edges and open leads.",
     "targets": "River Otter and Muskrat at slow-water sections; also documents mink and beaver activity."},
    {"method": "Cavity-tree night camera",
     "where": "Large-diameter snags and cavity trees on the mesic slope; camera or nest box facing a suet station or cavity entrance 2–4 m up.",
     "when": "Year-round, peak autumn–winter; cameras run on motion through the night, 1–2 hours after full dark.",
     "targets": "Southern (and possibly Northern) Flying Squirrel; also Northern Long-eared Bat roost emergence and porcupine."},
    {"method": "Travel-corridor cameras",
     "where": "Stone walls, brush piles, and the forested corridor connecting to nearby Tioga State Forest; pinch points and slope-base game trails.",
     "when": "Year-round; winter snow improves track confirmation for weasels and skunk; 6–8 weeks per station.",
     "targets": "Striped Skunk, Porcupine, Eastern Cottontail, possible Least Weasel and additional carnivore corridor records."},
]

AMPHIBIAN_METHODS = [
    {"method": "Stream rock-flip",
     "where": "Riffle and run sections of Michigan Creek; turn flat partly-submerged rocks and cobble at the wetted edge, plus rocks in the seepage zones feeding the creek.",
     "when": "April–June on cool days, water 45–60°F; daytime is fine since salamanders shelter under rocks. Replace every rock exactly as found.",
     "targets": "Northern Two-lined, Dusky and Allegheny Mountain Dusky salamanders — the single largest gap on the property."},
    {"method": "Cold seep search",
     "where": "Cold, clean spring runs and seeps on the mesic slope where groundwater emerges; flip flat rocks and probe gravel in the spring head.",
     "when": "April–June daytime when seep water is cold (under ~55°F); also active on warm rainy nights.",
     "targets": "Spring Salamander — a water-quality indicator and a notable find — plus larval Eurycea."},
    {"method": "Vernal-pool night walk",
     "where": "Floodplain depressions and woodland vernal pools off the creek; headlamp the pool edges and the forest-floor migration approach.",
     "when": "The first warm rainy nights of spring, March into early April, air above 45°F, 9 PM–midnight.",
     "targets": "Jefferson's and Blue-spotted salamander complex — breeding adults migrating to the pools."},
    {"method": "Egg-mass search",
     "where": "The same fishless vernal and floodplain pools; inspect submerged sticks and vegetation for attached masses.",
     "when": "Mid-March to mid-April daytime, shortly after the salamander migration nights.",
     "targets": "Confirms the Jefferson/Blue-spotted complex by jelly color and attachment, distinct from the recorded Spotted Salamander."},
    {"method": "Night chorus survey",
     "where": "The creek margin, floodplain wet areas, and any standing water or seeps; stop and listen at several stations.",
     "when": "Warm wet evenings, 9–11 PM; American Toad trills late April–May, leopard frog snore-calls in early-spring meltwater.",
     "targets": "Northern Leopard Frog and any unrecorded breeding choruses in the floodplain pools."},
    {"method": "Pool rock-flip / snorkel",
     "where": "Deeper, slow pools of the creek; lift large submerged flat rocks and woody debris, or snorkel the pool bottoms.",
     "when": "Night work in spring and fall when the water is cold; mudpuppies are nocturnal and active in cool water.",
     "targets": "Mudpuppy — fully aquatic, found only by working large rocks in the deeper pools."},
]


def build():
    init_db()
    df = analyze.load_property()
    stats = analyze.load_stats()
    if df.empty:
        print("No property observations yet — run sync.py --property first.")
        return None

    # Keep uniqueness stats species-level too (they're cached per-taxon and may
    # include coarser IDs cached before this filter existed).
    if not stats.empty:
        stats = stats[stats["taxon_id"].isin(set(df["taxon_id"].dropna()))]

    s = analyze.summary(df)
    life = analyze.life_list(df)
    firsts = analyze.firsts_timeline(df)
    county_firsts = int((stats["is_county_first"] == 1).sum()) if not stats.empty else 0

    parts = [head(s, county_firsts), nav(), hero(s, county_firsts)]

    # ── All-life view (light) ────────────────────────────────────────────────
    parts.append('<div id="view-all">')
    parts.append(section(
        "whats-new", "Latest", 'What\'s <em class="text-hollow-600">New</em>',
        whats_new_body(analyze.whats_new(df, stats)),
        intro="Species recorded at Kingfisher Hollow for the first time. Some are also first iNaturalist records for Tioga County, which makes them important additions to the public record even when the species is probably present elsewhere nearby.",
        tint="bg-stone-100"))
    parts.append(section(
        "discovery", "The Story So Far",
        'A Growing <em class="text-hollow-600">Life List</em>',
        chart_card(viz.discovery_curve(firsts),
                   note="Each step marks a species' first record at Kingfisher Hollow. A curve still rising steeply after 4,500+ observations indicates a long way still to go.")
        + takeaway(
            "The line is still climbing almost as steeply as it did on day one. Most well-studied reserves "
            "show a curve that flattens within the first season; this one hasn't. The steepest runs coincide "
            "with nights at the mothing lights, but the same pattern shows up in plants, herps, and mammals "
            "when the right method is used. Each plant genus documented on the property opens potential host "
            "links for insects, and each new survey method reaches a different slice of the site."),
        intro=f"{s['species']:,} steps, each the moment a species was recorded at Kingfisher Hollow for the first time. The curve hasn't levelled off."))

    # ── Rarity arc: emotional hook (county firsts) → the analytical payoff ────
    parts.append(section(
        "unique", "How Unique",
        'County <em class="text-hollow-300">Firsts</em>',
        showcase_body(analyze.county_first_showcase(df, stats))
        + takeaway(
            f"{county_firsts:,} county-first iNaturalist records means Kingfisher Hollow has added {county_firsts:,} species "
            "to Tioga County's public, photo-vouchered baseline. That is not the same as proving each species "
            "was absent from the county before. Tioga is under-sampled, while nearby Tompkins County has heavy "
            "naturalist and entomology effort. The right reading is still powerful: KH is turning private "
            "regional likelihood into documented county evidence, especially for moths and plants tied to "
            "Michigan Creek's transition-zone habitats.", dark=True),
        intro="For each of these species, Kingfisher Hollow currently holds the first iNaturalist record in Tioga County. That strengthens the county baseline and flags records worth checking against other sources when they look unusual.",
        dark=True))
    rarity_body = (
        chart_card(viz.uniqueness_scatter(stats),
                   note="Each dot is one species. X-axis: NY public-record scarcity (further left = fewer statewide records). Y-axis: frequency at Kingfisher Hollow. Terracotta: first iNaturalist record for Tioga County.")
        + takeaway(
            "Upper-left is the territory to investigate: few public New York records, but repeated records here. "
            "Some dots may be genuinely notable; others are under-documented groups, hard IDs, or observer-bias "
            "artifacts. The expert move is to check evidence quality, host plant, habitat, and outside sources "
            "before turning a low iNaturalist count into a rarity claim.")
        + '<h3 class="font-serif text-2xl font-bold text-stone-900 text-center mt-14 mb-6">'
          'The rarest of them</h3>'
        + rarest_body(analyze.rarest_finds(df, stats)))
    parts.append(section(
        "uniqueness", "The Big Picture",
        'Common Here, <em class="text-hollow-600">Rare There</em>',
        rarity_body,
        intro="Each dot is a species, plotted by public New York record scarcity against frequency here. The upper-left corner is where the site may be saying something real, but it needs expert context before it becomes a rarity claim.",
        tint="bg-stone-100"))

    parts.append(section(
        "life-list", "The Full Roll",
        'The <em class="text-hollow-600">Life List</em>',
        life_list_body(life),
        intro="Every species confirmed at Kingfisher Hollow — insects, plants, fungi, mammals, and more. Search by name or filter by group. Birds are tracked on eBird."))
    two_up = (
        '<div class="grid lg:grid-cols-2 gap-6">'
        + chart_card(viz.per_day(analyze.obs_per_day(df)))
        + chart_card(viz.taxa_bar(life))
        + '</div>')
    parts.append(section(
        "activity", "Effort & Breadth",
        'Activity &amp; <em class="text-hollow-600">Taxa</em>',
        two_up
        + takeaway(
            "The tall spikes are nights at the mothing lights; a well-run session can generate 50 to 100 "
            "observations before dawn. That effort reveals a real insect-heavy fauna, but it also exposes the "
            "survey's bias. Plants need seasonal ID passes, butterflies need sunny transects, mammals need "
            "cameras and acoustics, and herps need wet-night and stream methods. The site is rich, and the "
            "method mix still decides what becomes visible.",),
        intro="Daily observation totals and a taxonomic breakdown — how the effort is distributed and what it's actually finding.",
        tint="bg-stone-100"))
    parts.append(section(
        "phenology", "Phenology",
        'When Things <em class="text-hollow-600">Appear</em>',
        chart_card(viz.phenology(analyze.phenology(df, top=24), normalize=True),
                   note="Each row is normalized to its own peak, so a species seen 5 times reads as vividly as one seen 500 times — rare species' patterns show up alongside common ones. Hover for raw counts.")
        + takeaway(
            "Read across any row: one species' warm-up, peak, and fade. Read down any column: the community "
            "active in that month. The bright diagonal moving from spring to autumn is the year itself, "
            "written in species. Sparse months are both biology and effort: some taxa are truly seasonal, "
            "and some simply have not been searched for at the right time."),
        intro="The 24 most-recorded species across the calendar year — each one's seasonal rhythm in a single row."))
    parts.append(section(
        "observers", "Credit Where Due",
        'The <em class="text-hollow-600">Observers</em>',
        chart_card(viz.leaderboard(analyze.observer_leaderboard(df)))
        + takeaway(
            "Every record is attributed. Hover any bar to see how many observations a person submitted — and "
            "how many species only they have found here. Some of those species wouldn't be on the list without "
            "that one person."),
        intro="The survey exists because people showed up and submitted what they found. Each bar is one person's contribution; hover to see how many species only they have found here.",
        tint="bg-stone-100"))
    parts.append(section(
        "gallery", "In Pictures",
        'Recent <em class="text-hollow-600">Sightings</em>',
        gallery_body(analyze.photo_highlights(df)),
        intro="Recent research-grade photographs from iNaturalist — the visual evidence behind the species count."))
    parts.append(section(
        "map", "Where", 'On the <em class="text-hollow-600">Land</em>',
        chart_card(viz.obs_map(df))
        + takeaway(
            "The heaviest clusters follow the stream corridor and the mothing-light stations. The sparser "
            "areas aren't empty; they're under-walked or need different methods. Upland edge transects, wetland "
            "plant passes, creek rock surveys, and camera or acoustic stations would all move records into "
            "currently blank-looking parts of the map. iNaturalist automatically obscures coordinates for rare "
            "or sensitive species."),
        intro="Every GPS-tagged observation on the 30 acres. The clusters show where effort has been concentrated; the gaps show what's still unwalked."))
    parts.append('</div>')  # /view-all

    # ── Moths view (dark) ────────────────────────────────────────────────────
    parts.append('<div id="view-moths" class="hidden">')
    parts.append(moth_view(df, stats))
    parts.append('</div>')  # /view-moths

    # ── Butterflies view (dark) ──────────────────────────────────────────────
    parts.append('<div id="view-butterflies" class="hidden">')
    parts.append(butterflies_view(df, stats))
    parts.append('</div>')  # /view-butterflies

    # ── Mammals view (dark) ──────────────────────────────────────────────────
    parts.append('<div id="view-mammals" class="hidden">')
    parts.append(mammals_view(df, stats))
    parts.append('</div>')  # /view-mammals

    # ── Plants view (dark) ───────────────────────────────────────────────────
    parts.append('<div id="view-plants" class="hidden">')
    parts.append(plants_view(df, stats))
    parts.append('</div>')  # /view-plants

    # ── Amphibians view (dark) ───────────────────────────────────────────────
    parts.append('<div id="view-amphibians" class="hidden">')
    parts.append(amphibians_view(df, stats))
    parts.append('</div>')  # /view-amphibians

    # ── Log view (light, journal) ────────────────────────────────────────────
    parts.append('<div id="view-log" class="hidden">')
    log_entries = analyze.activity_log(df, stats)
    weather_cache = weather.load_weather()
    id_changes = inat_api.fetch_id_changes(PROPERTY_PROJECT_ID, MY_USERNAME)
    parts.append(section(
        "log-journal", "Field Journal",
        'The <em class="text-hollow-600">Daily Log</em>',
        activity_log_body(log_entries, weather_cache)
        + id_changes_body(id_changes),
        intro="A night-by-night record of every session: weather, observers, and every species appearing for the first time on the property."))
    parts.append('</div>')  # /view-log

    parts.append(footer(_code_updated(), _insights_updated(), data_updated_date()))
    parts.append(SCRIPTS)

    html = "".join(parts)

    out = PUBLIC_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size // 1024} KB)")
    return out


if __name__ == "__main__":
    build()
