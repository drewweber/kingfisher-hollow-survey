#!/usr/bin/env python3
"""Build the Kingfisher Hollow biodiversity report as a single branded page
(public/index.html), styled to match kingfisher-hollow.com and composed like an
editorial infographic. Charts come from viz.py; this module owns the page shell,
typography, and the photo/table/showcase sections."""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import analyze  # noqa: E402
import viz  # noqa: E402
import weather  # noqa: E402
from config import PUBLIC_DIR  # noqa: E402
from db import connect, init_db  # noqa: E402

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"
SITE = "https://www.kingfisher-hollow.com"
PROJECT_URL = "https://www.inaturalist.org/projects/kingfisher-hollow-biodiversity-survey"
TAXON_URL = "https://www.inaturalist.org/taxa/"   # + taxon_id → species page
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
    return (f'<div class="mt-6 max-w-2xl mx-auto border-l-2 {border} {bg} rounded-r-lg px-5 py-4">'
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
  <div class="relative z-10 text-center px-6 max-w-4xl mx-auto pt-24">
    <p class="fade-up text-hollow-300 font-medium tracking-[0.35em] uppercase text-xs md:text-sm mb-5">Biodiversity Survey · {esc(rng)}</p>
    <h1 class="fade-up delay-1 font-serif text-5xl md:text-7xl text-white font-bold leading-[1.05] mb-6">
      Life at <em class="font-normal text-hollow-200" style="font-style:italic;">the Hollow</em>
    </h1>
    <p class="fade-up delay-2 text-white/70 text-lg md:text-xl max-w-xl mx-auto leading-relaxed mb-12">
      Every species recorded on 30 acres along Michigan Creek — counted, mapped, and measured against all of New York.
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
    for _, r in new_species.head(6).iterrows():
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
        img = (f'<img src="{esc(photo)}" class="w-full h-40 object-cover" alt="{name}">'
               if photo == photo and photo else
               '<div class="w-full h-40 bg-hollow-100 flex items-center justify-center text-hollow-400 text-3xl">🪶</div>')
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
            f'<strong class="text-stone-700">{len(recent)}</strong> observations added recently · '
            f'<strong class="text-hollow-600">{len(new_species)}</strong> new for the property</p>')
    if not cards:
        return lead + ('<p class="text-center text-stone-400">No brand-new '
                       'species in this batch — but the count keeps climbing.</p>')
    return lead + ('<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">'
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


def moth_stats(msum, comp):
    """Headline stat band for the moth view."""
    tiles = [_dark_stat(f"{msum['species']:,}", "Moth species"),
             _dark_stat(f"{msum['records']:,}", "Records")]
    if comp:
        ci = (f"Chao2 estimate; 95% CI {comp['low']}–{comp['high']}"
              if comp.get("high", 0) > comp.get("low", 0) else "Chao2 estimate")
        tiles.append(_dark_stat(f"{comp['pct_complete']}%", "Est. complete",
                                "of the likely total, found so far"))
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
        tid = sval(r.get("taxon_id"))
        href = f"{TAXON_URL}{int(tid)}" if tid not in ("", None) and tid == tid else "#"
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


def moth_gap_body(gap):
    """Regional moths not yet found here — ranked by how common they are nearby."""
    if not gap or gap.get("missing_count", 0) == 0:
        return '<p class="text-center text-white/50">No gap data yet.</p>'
    radius = gap.get("region_radius_km", 80)
    miles = round(radius / 1.609)
    region_total = gap.get("region_total", 0)
    county_line = ""
    if gap.get("county_total"):
        county_line = (f' For context, that\'s '
                       f'<strong class="text-hollow-300">{gap["county_pct"]}%</strong> of the '
                       f'{gap["county_total"]} moths recorded in Tioga County itself — but the '
                       f'county is thinly surveyed, so the wider region is the truer yardstick.')
    lead = (f'<p class="text-center text-white/60 max-w-2xl mx-auto mb-8">You\'ve recorded '
            f'<strong class="text-hollow-300">{gap["have"]}</strong> of the '
            f'<strong class="text-hollow-300">{region_total}</strong> moth species logged within '
            f'~{miles} miles (<strong class="text-hollow-300">{gap["pct"]}%</strong>).{county_line} '
            f'The <strong class="text-hollow-300">{gap["missing_count"]}</strong> below are recorded '
            f'nearby but not yet here — the likeliest next finds.</p>')
    gmax = max(int(r["ref_count"]) for _, r in gap["missing"].iterrows()) or 1
    rows = []
    for _, r in gap["missing"].iterrows():
        cc = int(r["ref_count"])
        pct = max(4, round(100 * cc / gmax))   # commoner nearby = longer bar
        link = taxon_link(r.get("taxon_id"), r["label"],
                          cls="font-medium text-white hover:text-hollow-300")
        rows.append(f"""
        <div class="flex items-center justify-between gap-4 py-2.5 border-b border-white/10 last:border-0">
          <div class="min-w-0 flex-1"><div class="truncate">{link}</div>
            <div class="text-white/40 text-sm italic truncate">{esc(r.get('taxon_name'))}</div>
            <div class="mt-1.5 h-1 rounded-full bg-white/10"><div class="h-1 rounded-full" style="width:{pct}%;background:#8ec8b1"></div></div></div>
          <div class="text-right whitespace-nowrap"><span class="font-serif text-lg font-bold text-hollow-300">{cc}</span>
            <span class="text-white/40 text-[0.7rem] uppercase tracking-wider ml-1">nearby records</span></div>
        </div>""")
    return (lead + '<div class="max-w-2xl mx-auto bg-white/[0.04] border border-white/10 '
            'rounded-2xl p-6 md:p-8">' + "".join(rows) + "</div>")


def moth_diversity_body(div):
    simp_pct = round(float(div["simpson"]) * 100, 1)
    tiles = [
        _dark_stat(div["shannon"], "Shannon H′", "higher = more varied"),
        _dark_stat(div["simpson"], "Simpson",
                   f"two random records are different species {simp_pct}% of the time"),
        _dark_stat(div["evenness"], "Evenness", "0 = one dominates · 1 = perfectly even"),
    ]
    return ('<div class="flex flex-wrap items-start justify-center gap-8 md:gap-12 mb-10">'
            + _dark_divider().join(tiles) + "</div>")


# ── field journal / activity log ────────────────────────────────────────────
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
    """Compact weather summary string for a journal entry."""
    if not w:
        return ""
    parts = []
    if w.get("temp_f_hi") is not None:
        parts.append(f"{w['temp_f_hi']}°F")
    if w.get("humidity_pct") is not None:
        parts.append(f"{w['humidity_pct']}% humidity")
    wd = w.get("wind_desc")
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

        date_label = f"{month_names[d.month]} {d.day}"
        w = weather_cache.get(str(d))
        weather_str = _weather_line(w)
        weather_html = (
            f'<p class="text-stone-400 text-sm mt-1">{esc(weather_str)}</p>'
            if weather_str else ""
        )

        # Separate moths from everything else.
        moths = [sp for sp in entry["new_species"] if sp["is_moth"]]
        others = [sp for sp in entry["new_species"] if not sp["is_moth"]]

        def _sp_html(sp):
            badge = _rarity_badge(sp)
            name_html = taxon_link(sp["taxon_id"], sp["label"])
            if badge:
                return (f'{name_html} <span class="text-hollow-600 text-xs font-medium '
                        f'whitespace-nowrap">({badge})</span>')
            return name_html

        species_parts = []
        if moths:
            moth_items = ", ".join(_sp_html(sp) for sp in moths)
            species_parts.append(
                f'<span class="font-medium text-stone-700">Moths:</span> {moth_items}'
            )
        if others:
            # Group non-moths by group name.
            groups_seen = {}
            for sp in others:
                grp = sp["group"] or "Other"
                groups_seen.setdefault(grp, []).append(sp)
            # If there's only one group besides moths, label it; otherwise
            # flatten under "Other species".
            if len(groups_seen) == 1:
                grp_name, grp_sps = next(iter(groups_seen.items()))
                items = ", ".join(_sp_html(sp) for sp in grp_sps)
                species_parts.append(
                    f'<span class="font-medium text-stone-700">{esc(grp_name)}:</span> {items}'
                )
            else:
                other_items = ", ".join(_sp_html(sp) for sp in others)
                label = "Other species" if moths else "Species"
                species_parts.append(
                    f'<span class="font-medium text-stone-700">{label}:</span> {other_items}'
                )

        species_html = (
            '<p class="text-stone-700 leading-relaxed mt-2 text-[0.95rem]">'
            + " &nbsp;·&nbsp; ".join(species_parts)
            + '</p>'
        ) if species_parts else ""

        new_count = len(entry["new_species"])
        count_badge = (
            f'<span class="inline-flex items-center justify-center w-6 h-6 '
            f'rounded-full bg-hollow-100 text-hollow-700 text-xs font-bold '
            f'flex-shrink-0 mt-0.5">{new_count}</span>'
        )

        html_parts.append(f"""
<div class="grid grid-cols-[8rem_1fr] gap-x-6 py-5 border-b border-stone-100 group">
  <div class="text-right pt-0.5">
    <span class="font-serif text-lg font-bold text-stone-900 leading-snug">{date_label}</span>
  </div>
  <div>
    <div class="flex items-start gap-2">
      {count_badge}
      <div class="flex-1 min-w-0">
        {weather_html}
        {species_html}
      </div>
    </div>
  </div>
</div>""")

    html_parts.append("</div>")
    return "".join(html_parts)


# ── head / nav / footer ──────────────────────────────────────────────────────
def head():
    desc = ("A living biodiversity survey of Kingfisher Hollow — every species "
            "recorded on 30 acres along Michigan Creek in Tioga County, NY, "
            "measured against the county and all of New York, with a deep dive "
            "into the property's moths.")
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
  .log-rarity {{ color:#2e735c; font-size:.78rem; font-weight:500; }}
  .log-moth-label {{ color:#57534e; font-size:.8rem; font-weight:600; letter-spacing:.04em; text-transform:uppercase; }}
</style></head>
<body class="font-sans text-stone-800 antialiased" data-mode="all">"""


def nav():
    all_links = [("#whats-new", "What's New"), ("#discovery", "Discovery"),
                 ("#unique", "Unique Finds"), ("#life-list", "Life List"),
                 ("#gallery", "Gallery")]
    moth_links = [("#moth-completeness", "Completeness"), ("#moth-families", "Families"),
                  ("#moth-seasons", "Flight Seasons"), ("#moth-gap", "Gap List"),
                  ("#moth-diversity", "Diversity"), ("#moth-standouts", "Standouts")]
    log_links = [("#log-journal", "Field Journal")]

    def links_html(links, item_cls):
        return "".join(f'<a href="{h}" class="{item_cls}">{t}</a>' for h, t in links)
    desk_cls = "nav-link text-white/80 hover:text-white text-sm font-medium transition-colors"
    mob_cls = "text-white/80 hover:text-white text-sm py-1"
    # All three sets render; setMode() shows the one matching the active view.
    desktop_links = (f'<span class="links-all flex items-center gap-6">{links_html(all_links, desk_cls)}</span>'
                     f'<span class="links-moths hidden items-center gap-6">{links_html(moth_links, desk_cls)}</span>'
                     f'<span class="links-log hidden items-center gap-6">{links_html(log_links, desk_cls)}</span>')
    mob_links = (f'<div class="links-all flex flex-col gap-3">{links_html(all_links, mob_cls)}</div>'
                 f'<div class="links-moths hidden flex-col gap-3">{links_html(moth_links, mob_cls)}</div>'
                 f'<div class="links-log hidden flex-col gap-3">{links_html(log_links, mob_cls)}</div>')
    toggle = """
      <div class="mode-toggle flex items-center rounded-full p-0.5 bg-white/10 border border-white/15" role="group" aria-label="Switch view">
        <button class="mode-btn mode-active" data-mode="all" aria-pressed="true">All life</button>
        <button class="mode-btn" data-mode="moths" aria-pressed="false">Moths</button>
        <button class="mode-btn" data-mode="log" aria-pressed="false">Log</button>
      </div>"""
    return f"""
<a href="#whats-new" class="sr-only focus:not-sr-only focus:absolute focus:z-[60] focus:top-2 focus:left-2 focus:bg-white focus:text-stone-900 focus:px-3 focus:py-1 focus:rounded">Skip to content</a>
<nav id="navbar" class="nav-transparent fixed top-0 inset-x-0 z-50 transition-all duration-300">
  <div class="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
    <a href="{SITE}" class="flex items-center gap-2.5">{LOGO}
      <span id="nav-brand" class="font-serif text-white text-xl font-semibold tracking-wide transition-colors">Kingfisher Hollow</span></a>
    <div class="hidden md:flex items-center gap-6">{desktop_links}{toggle}
      <a href="{SITE}" class="text-white/70 hover:text-white text-sm font-medium transition-colors">← Main site</a>
    </div>
    <button onclick="document.getElementById('mob').classList.toggle('hidden')" class="md:hidden text-white p-1" aria-label="Menu">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg></button>
  </div>
  <div id="mob" class="hidden md:hidden bg-hollow-950/95 px-6 py-4 flex flex-col gap-3 border-t border-white/10">
    <div class="mode-toggle flex items-center rounded-full p-0.5 bg-white/10 border border-white/15 self-start" role="group" aria-label="Switch view">
      <button class="mode-btn mode-active" data-mode="all" aria-pressed="true">All life</button>
      <button class="mode-btn" data-mode="moths" aria-pressed="false">Moths</button>
      <button class="mode-btn" data-mode="log" aria-pressed="false">Log</button>
    </div>
    {mob_links}
    <a href="{SITE}" class="text-hollow-300 text-sm py-1">← Main site</a>
  </div>
</nav>"""


def _git_date():
    """Last commit date of the repo (when the code last changed), MM/DD/YYYY."""
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent), "log", "-1", "--format=%cI"],
            capture_output=True, text=True, timeout=10)
        iso = (out.stdout or "").strip()
        if iso:
            return datetime.fromisoformat(iso).strftime("%m/%d/%Y")
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    # Fallback: this file's modification time.
    return datetime.fromtimestamp(Path(__file__).stat().st_mtime).strftime("%m/%d/%Y")


def data_updated_date():
    """When the data was last refreshed — the most recent sync, MM/DD/YYYY UTC."""
    try:
        with connect() as conn:
            row = conn.execute("SELECT MAX(synced_at) AS t FROM sync_log").fetchone()
        if row and row["t"]:
            return datetime.fromisoformat(row["t"].replace(" ", "T")).strftime("%m/%d/%Y")
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%m/%d/%Y")


def footer(code_updated, data_updated):
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
    <div class="flex flex-col sm:flex-row items-center justify-center gap-x-6 gap-y-1 text-white/40 text-xs tracking-wide mb-2">
      <span>Data last updated <strong class="text-white/60">{data_updated}</strong></span>
      <span class="hidden sm:inline text-white/20">·</span>
      <span>Code last updated <strong class="text-white/60">{code_updated}</strong></span>
    </div>
    <p class="text-center text-white/25 text-xs tracking-wide">Data from iNaturalist · Photos © their respective observers</p>
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

  // Mode toggle: All life / Moths / Log — one page, three views.
  (function(){
    const vAll=document.getElementById('view-all'),vMoth=document.getElementById('view-moths'),
          vLog=document.getElementById('view-log');
    function setMode(mode,force){
      if(mode!=='moths'&&mode!=='log') mode='all';
      document.body.dataset.mode=mode;
      vAll.classList.toggle('hidden',mode!=='all');
      vMoth.classList.toggle('hidden',mode!=='moths');
      vLog.classList.toggle('hidden',mode!=='log');
      // Swap nav link set to match active view.
      [['links-all','all'],['links-moths','moths'],['links-log','log']].forEach(([cls,m])=>{
        document.querySelectorAll('.'+cls).forEach(e=>{
          const on=mode===m;e.classList.toggle('hidden',!on);e.classList.toggle('flex',on);});});
      document.querySelectorAll('.mode-btn').forEach(b=>{const on=b.dataset.mode===mode;
        b.classList.toggle('mode-active',on);b.setAttribute('aria-pressed',on?'true':'false');});
      const hash=mode==='moths'?'#moths':mode==='log'?'#log':location.pathname;
      history.replaceState(null,'',hash);
      updateNav&&updateNav();
      if(force){
        const sel='#view-'+mode+' .reveal';
        document.querySelectorAll(sel).forEach(el=>el.classList.add('in'));
        window.dispatchEvent(new Event('resize'));
      }
    }
    document.querySelectorAll('.mode-btn').forEach(b=>b.addEventListener('click',()=>{
      setMode(b.dataset.mode,true);window.scrollTo({top:0,behavior:'smooth'});
      document.getElementById('mob').classList.add('hidden');}));
    const h=location.hash;
    setMode(h==='#moths'?'moths':h==='#log'?'log':'all', h==='#moths'||h==='#log');
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
    gap = analyze.moth_county_gap(moths)
    div = analyze.moth_diversity(df, moths)
    eff = analyze.moth_effort(df, moths)
    moth_sub = analyze.moth_obs(df, moths)

    out = []
    out.append(section(
        "moths", "After Dark", 'The <em class="text-hollow-300">Moths</em>',
        moth_stats(msum, comp),
        intro="Most of the survey’s life turns up on summer nights at the lights — "
              "a parade of moths, from giant silkmoths to the smallest leaf-miners. "
              "This is the moth survey in full.",
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
                     note=f"Chao2 (incidence-based) projects the true total from how many "
                          f"moths turned up on only one or two of the {comp['nights']} survey "
                          f"nights; the shaded band is the 95% confidence range.",
                     dark=True)
        + takeaway(
            f"We've recorded <strong>{comp['observed']}</strong> moth species. Because "
            f"<strong>{comp['q1']}</strong> of them have shown up on just a single night, "
            f"the statistics say many more are out there: Chao2 estimates roughly "
            f"<strong>{comp['estimated']}</strong> species live here (likely "
            f"{comp['low']}–{comp['high']}). So the inventory is about "
            f"<strong>{comp['pct_complete']}%</strong> complete — strong, but every new "
            f"night still turns up moths never seen before.", dark=True),
        intro="How many moth species really live here, and how close the survey is to "
              "finding them all.",
        dark=True))
    out.append(section(
        "moth-families", "By Family",
        'Where the <em class="text-hollow-300">Gaps</em> Are',
        chart_card(viz.family_breakdown(analyze.moth_family_breakdown(moths)),
                   note="Solid bar: species recorded here. Faint bar: species known within "
                        "~50 miles. Bar labels show recorded / regional.",
                   dark=True)
        + takeaway(
            "Completeness is far from even across the moths. The big, showy macro-moths — "
            "owlets, geometers, tigers — are well represented, but the tiny, hard-to-identify "
            "micro-moth families trail far behind the regional pool. That's where most of the "
            "undiscovered species are hiding, and where extra trapping and dissection would "
            "pay off most.", dark=True),
        intro="Completeness isn't even across the moths — some families are well covered, "
              "others wide open.",
        dark=True))
    out.append(section(
        "moth-seasons", "Flight Seasons",
        'On the <em class="text-hollow-300">Wing</em>',
        chart_card(viz.seasonal_cascade(analyze.moth_seasonal(df, moths), dark=True),
                   note="Faint line: full span seen · bar: middle 50% of records · "
                        "dot: typical date. Only species with several records are drawn.",
                   dark=True)
        + takeaway(
            "Each row is a moth species, stacked by when in the year it flies — so the "
            "chart reads top-to-bottom as the season unfolding, from early-spring species "
            "down to late-summer and fall fliers. The bar marks its core flight window; "
            "the faint line shows the full range of dates it's been seen. With one season "
            "of data these are first sketches that will sharpen each year.", dark=True),
        intro="When each moth species flies, ordered as a wave from early-season to late.",
        dark=True))
    out.append(section(
        "moth-phenology", "By Month",
        'Moth <em class="text-hollow-300">Phenology</em>',
        chart_card(viz.phenology(analyze.phenology(moth_sub), dark=True, normalize=True),
                   note="Each row is normalized to its own peak month, so a rare moth's "
                        "timing is as visible as a common one's. Hover for raw counts.",
                   dark=True)
        + takeaway(
            "Reading across a row shows a single species' season; reading down a column "
            "shows which moths share a month. Brighter cells are that species' peak. "
            "Sparse winter columns reflect cold nights with little flying — and little "
            "surveying — rather than a true moth-free season.", dark=True),
        intro="Each species' seasonal signature, month by month.",
        dark=True))
    out.append(section(
        "moth-gap", "Yet to Find",
        'The <em class="text-hollow-300">Gap List</em>',
        moth_gap_body(gap)
        + takeaway(
            "Because Tioga County is lightly surveyed, this list is built from the much "
            "better-sampled ~50-mile region (which reaches into the Ithaca area and across "
            "into Pennsylvania) — a truer picture of what could occur here. Species are "
            "ranked by how often they're recorded nearby, so the top of the list is where "
            "to point the light next.", dark=True),
        intro="Moths recorded within ~50 miles but not yet on the property — the truest "
              "measure of what's still out there.",
        dark=True))
    out.append(section(
        "moth-diversity", "Diversity",
        'A <em class="text-hollow-300">Balanced</em> Community',
        moth_diversity_body(div)
        + chart_card(viz.rank_abundance(div.get("rank_abundance", [])),
                     note="Each species ranked by how often it's recorded (log scale). "
                          "The terracotta tail is species seen only once or twice.",
                     dark=True)
        + takeaway(
            "A steep drop would mean a few moths dominate; this gentle slope means the "
            "community is remarkably even — no single species swamps the rest, which is "
            "the hallmark of a rich, intact habitat. The long flat tail of once-or-twice "
            "seen moths is the frontier of the inventory.", dark=True),
        intro="How even the moth community is — diversity and dominance at a glance.",
        dark=True))
    out.append(section(
        "moth-standouts", "Standouts",
        'Rare &amp; <em class="text-hollow-300">Remarkable</em>',
        moth_showcase(analyze.moth_highlights(moths, stats)),
        intro="The rarest-in-New-York moths recorded here, with their statewide tallies.",
        dark=True))
    out.append(section(
        "moth-gallery", "In Pictures",
        'Recent <em class="text-hollow-300">Moths</em>',
        gallery_body(analyze.photo_highlights(moth_sub)),
        intro="The latest moth photographs from the property.",
        dark=True))
    return "".join(out)


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

    parts = [head(), nav(), hero(s, county_firsts)]

    # ── All-life view (light) ────────────────────────────────────────────────
    parts.append('<div id="view-all">')
    parts.append(section(
        "whats-new", "Latest", 'What\'s <em class="text-hollow-600">New</em>',
        whats_new_body(analyze.whats_new(df, stats)),
        intro="The most recent arrivals to the survey, fresh from the field.",
        tint="bg-stone-100"))
    parts.append(section(
        "discovery", "The Story So Far",
        'A Growing <em class="text-hollow-600">Life List</em>',
        chart_card(viz.discovery_curve(firsts),
                   note="Each step marks the first time a species was recorded on the property.")
        + takeaway(
            "Every step up is a species recorded here for the first time. The line is "
            "still climbing steeply, not levelling off — a sign the survey is young and "
            "the property keeps yielding species nobody had logged here before."),
        intro="Every species, the day it was first found here — a cumulative portrait of the survey."))

    # ── Rarity arc: emotional hook (county firsts) → the analytical payoff ────
    parts.append(section(
        "unique", "How Unique",
        'County <em class="text-hollow-300">Firsts</em>',
        showcase_body(analyze.county_first_showcase(df, stats))
        + takeaway(
            "For each of these species, the earliest record anywhere in Tioga County "
            "is the one made here — the property isn't just cataloguing local life, "
            "it's adding to what the county knows it has.", dark=True),
        intro="Species for which Kingfisher Hollow holds the earliest record in all of Tioga County.",
        dark=True))
    rarity_body = (
        chart_card(viz.uniqueness_scatter(stats),
                   note="Each point is a species: left = rarer in New York, higher = more "
                        "often found here. Terracotta = a county-first record.")
        + takeaway(
            "Species drifting to the upper-left are the property's signature: scarce across "
            "New York yet reliably found here. Those are the records that matter most to "
            "the wider picture — and the ranked list below pulls out the very rarest.")
        + '<h3 class="font-serif text-2xl font-bold text-stone-900 text-center mt-14 mb-6">'
          'The rarest of them</h3>'
        + rarest_body(analyze.rarest_finds(df, stats)))
    parts.append(section(
        "uniqueness", "The Big Picture",
        'Common Here, <em class="text-hollow-600">Rare There</em>',
        rarity_body,
        intro="How the property's species sit against the whole state — and which are the "
              "genuine rarities.",
        tint="bg-stone-100"))

    parts.append(section(
        "life-list", "The Full Roll",
        'The <em class="text-hollow-600">Life List</em>',
        life_list_body(life),
        intro="Every species recorded on the property. Search or filter by group. "
              "(Birds are tracked on eBird, not here.)"))
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
            "Left: how much looking happens day to day — the tall spikes are big survey "
            "days and warm summer nights. Right: the sheer breadth of life found, across "
            "the tree of life. It's an unusually diverse single property, though insects "
            "— moths above all — dominate both the effort and the count.",),
        intro="Observation effort over time, and the breadth of life recorded across taxonomic groups.",
        tint="bg-stone-100"))
    parts.append(section(
        "phenology", "Phenology",
        'When Things <em class="text-hollow-600">Appear</em>',
        chart_card(viz.phenology(analyze.phenology(df, top=24), normalize=True),
                   note="Each row is normalized to its own peak month, so a rare species' "
                        "timing reads as clearly as a common one's. Hover for raw counts.")
        + takeaway(
            "Each row is one of the 24 most-recorded species; brighter cells are the months "
            "it shows up most. Read across for a species' season, or down a column to see "
            "what's active in a given month — the green wave sweeping left-to-right is the "
            "year turning over."),
        intro="The most-recorded species and the months they show up."))
    parts.append(section(
        "observers", "Credit Where Due",
        'The <em class="text-hollow-600">Observers</em>',
        chart_card(viz.leaderboard(analyze.observer_leaderboard(df)))
        + takeaway(
            "Every record is credited. Bars show each person's observations; hover for their "
            "species total and the species only they have found here — a survey built by many eyes."),
        intro="Everyone who has contributed observations to the survey.",
        tint="bg-stone-100"))
    parts.append(section(
        "gallery", "In Pictures",
        'Recent <em class="text-hollow-600">Sightings</em>',
        gallery_body(analyze.photo_highlights(df)),
        intro="The latest research-grade photographs from the property."))
    parts.append(section(
        "map", "Where", 'On the <em class="text-hollow-600">Land</em>',
        chart_card(viz.obs_map(df))
        + takeaway(
            "Where life turns up on the 30 acres. Clusters trace the trails, the pond, and "
            "the spots where lights are run on summer nights. Locations for sensitive species "
            "are deliberately blurred by iNaturalist."),
        intro="Every mapped observation. Coordinates for sensitive species are obscured by iNaturalist."))
    parts.append('</div>')  # /view-all

    # ── Moths view (dark) ────────────────────────────────────────────────────
    parts.append('<div id="view-moths" class="hidden">')
    parts.append(moth_view(df, stats))
    parts.append('</div>')  # /view-moths

    # ── Log view (light, journal) ────────────────────────────────────────────
    parts.append('<div id="view-log" class="hidden">')
    log_entries = analyze.activity_log(df, stats)
    weather_cache = weather.load_weather()
    parts.append(section(
        "log-journal", "Field Journal",
        'The <em class="text-hollow-600">Daily Log</em>',
        activity_log_body(log_entries, weather_cache),
        intro="Every day a new species was recorded on the property — conditions, moths first, then everything else."))
    parts.append('</div>')  # /view-log

    parts.append(footer(_git_date(), data_updated_date()))
    parts.append(SCRIPTS)

    html = "".join(parts)

    out = PUBLIC_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size // 1024} KB)")
    return out


if __name__ == "__main__":
    build()
