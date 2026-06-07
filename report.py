#!/usr/bin/env python3
"""Build the Kingfisher Hollow biodiversity report as a single branded page
(public/index.html), styled to match kingfisher-hollow.com and composed like an
editorial infographic. Charts come from viz.py; this module owns the page shell,
typography, and the photo/table/showcase sections."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import analyze  # noqa: E402
import viz  # noqa: E402
from config import PUBLIC_DIR  # noqa: E402
from db import init_db  # noqa: E402

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"
SITE = "https://www.kingfisher-hollow.com"
PROJECT_URL = "https://www.inaturalist.org/projects/kingfisher-hollow-biodiversity-survey"
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


def chart_card(html, note=""):
    note_html = (f'<p class="text-stone-400 text-xs mt-4 italic">{note}</p>'
                 if note else "")
    return (f'<div class="bg-white border border-stone-100 rounded-2xl '
            f'p-5 md:p-7 shadow-sm">{html}{note_html}</div>')


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
        cards.append(f"""
        <div class="photo-card relative rounded-2xl overflow-hidden" style="height:300px;">
          <div class="absolute inset-0 overflow-hidden">{img}</div>
          <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/15 to-transparent"></div>
          <div class="absolute top-3 left-3"><span class="badge badge-accent">County first</span></div>
          <div class="absolute bottom-0 inset-x-0 p-5">
            <div class="font-serif text-xl font-bold text-white leading-snug">{name}</div>
            <div class="text-white/70 text-sm italic">{sci}</div>
            <div class="text-hollow-300 text-xs mt-1.5 font-medium">{ny}</div>
          </div>
        </div>""")
    return ('<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">'
            + "".join(cards) + "</div>")


# ── rarest finds ─────────────────────────────────────────────────────────────
def rarest_body(rare):
    if rare.empty:
        return '<p class="text-center text-stone-500">Stats still caching.</p>'
    rows = []
    for i, (_, r) in enumerate(rare.iterrows(), 1):
        name = esc(r["label"])
        sci = esc(r.get("taxon_name") or "")
        ny = int(r["state_obs_count"])
        county = _num(r.get("county_obs_count"))
        rows.append(f"""
        <div class="flex items-center gap-4 py-3.5 border-b border-stone-100 last:border-0">
          <div class="font-serif text-2xl font-bold text-hollow-300 w-8 text-right">{i}</div>
          <div class="flex-1 min-w-0">
            <div class="font-medium text-stone-900 truncate">{name}</div>
            <div class="text-stone-400 text-sm italic truncate">{sci}</div>
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
    groups = sorted(life["iconic_taxon"].dropna().unique())
    btns = ['<button class="ll-filter ll-active" data-group="all">All</button>']
    btns += [f'<button class="ll-filter" data-group="{esc(g)}">{esc(g)}</button>'
             for g in groups]
    rows = []
    for _, r in life.iterrows():
        name = esc(r["label"])
        sci = esc(r.get("taxon_name") or "")
        grp = esc(r.get("iconic_taxon") or "Other")
        rows.append(f"""
      <tr class="ll-row border-b border-stone-100" data-group="{grp}" data-name="{name.lower()} {sci.lower()}">
        <td class="py-2.5 pr-4"><span class="font-medium text-stone-800">{name}</span>
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
        <div class="flex flex-wrap gap-2 justify-center">{''.join(btns)}</div>
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


# ── head / nav / footer ──────────────────────────────────────────────────────
def head():
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kingfisher Hollow · Biodiversity Survey</title>
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
  .chart-empty {{ text-align:center; color:#a8a29e; padding:2rem; font-style:italic; }}
  .reveal {{ opacity:0; transform: translateY(24px); transition: opacity .7s ease, transform .7s ease; }}
  .reveal.in {{ opacity:1; transform:none; }}
</style></head>
<body class="font-sans text-stone-800 antialiased">"""


def nav():
    links = [("#whats-new", "What's New"), ("#discovery", "Discovery"),
             ("#unique", "Unique Finds"), ("#life-list", "Life List"),
             ("#seasons", "Seasons"), ("#gallery", "Gallery")]
    link_html = "".join(
        f'<a href="{h}" class="nav-link text-white/80 hover:text-white text-sm font-medium transition-colors">{t}</a>'
        for h, t in links)
    return f"""
<nav id="navbar" class="nav-transparent fixed top-0 inset-x-0 z-50 transition-all duration-300">
  <div class="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
    <a href="{SITE}" class="flex items-center gap-2.5">{LOGO}
      <span id="nav-brand" class="font-serif text-white text-xl font-semibold tracking-wide transition-colors">Kingfisher Hollow</span></a>
    <div class="hidden md:flex items-center gap-7">{link_html}
      <a href="{SITE}" class="bg-hollow-500 hover:bg-hollow-400 text-white text-sm font-medium px-5 py-2 rounded-full transition-colors shadow-sm">← Main site</a>
    </div>
    <button onclick="document.getElementById('mob').classList.toggle('hidden')" class="md:hidden text-white p-1">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg></button>
  </div>
  <div id="mob" class="hidden md:hidden bg-hollow-950/95 px-6 py-4 flex flex-col gap-3 border-t border-white/10">
    {''.join(f'<a href="{h}" class="text-white/80 hover:text-white text-sm py-1">{t}</a>' for h,t in links)}
    <a href="{SITE}" class="text-hollow-300 text-sm py-1">← Main site</a>
  </div>
</nav>"""


def footer(generated):
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
    <p class="text-center text-white/25 text-xs tracking-wide">Data from iNaturalist · Updated {generated} · Photos © their respective observers</p>
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

  // Life-list filter + search
  (function(){
    const rows=[...document.querySelectorAll('.ll-row')],search=document.getElementById('ll-search'),
          count=document.getElementById('ll-count');let group='all';
    function apply(){const q=(search.value||'').toLowerCase();let n=0;
      rows.forEach(r=>{const okG=group==='all'||r.dataset.group===group,
        okQ=!q||r.dataset.name.includes(q);const show=okG&&okQ;
        r.style.display=show?'':'none';if(show)n++;});
      count.textContent=n+' species shown';}
    document.querySelectorAll('.ll-filter').forEach(b=>b.addEventListener('click',()=>{
      document.querySelectorAll('.ll-filter').forEach(x=>x.classList.remove('ll-active'));
      b.classList.add('ll-active');group=b.dataset.group;apply();}));
    if(search)search.addEventListener('input',apply);apply();
  })();

  // Scroll reveal
  const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}}),{threshold:0.08});
  document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
</script></body></html>"""


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
    generated = datetime.now(timezone.utc).strftime("%B %-d, %Y")

    parts = [head(), nav(), hero(s, county_firsts)]

    parts.append(section(
        "whats-new", "Latest", 'What\'s <em class="text-hollow-600">New</em>',
        whats_new_body(analyze.whats_new(df, stats)),
        intro="The most recent arrivals to the survey, fresh from the field.",
        tint="bg-stone-100"))

    parts.append(section(
        "discovery", "The Story So Far",
        'A Growing <em class="text-hollow-600">Life List</em>',
        chart_card(viz.discovery_curve(firsts),
                   note="Each step marks the first time a species was recorded on the property."),
        intro="Every species, the day it was first found here — a cumulative portrait of the survey."))

    parts.append(section(
        "unique", "How Unique",
        'County <em class="text-hollow-300">Firsts</em>',
        showcase_body(analyze.county_first_showcase(df, stats)),
        intro="Species for which Kingfisher Hollow holds the earliest record in all of Tioga County.",
        dark=True))

    parts.append(section(
        "rarest", "Rarities",
        'Rarest in <em class="text-hollow-600">New York</em>',
        rarest_body(analyze.rarest_finds(df, stats)),
        intro="Your finds ranked by how few times they’ve been recorded anywhere in the state."))

    parts.append(section(
        "life-list", "The Full Roll",
        'The <em class="text-hollow-600">Life List</em>',
        life_list_body(life),
        intro="Every species recorded on the property. Search or filter by group.",
        tint="bg-stone-100"))

    parts.append(section(
        "seasons", "Through the Year",
        'A Seasonal <em class="text-hollow-600">Cascade</em>',
        chart_card(viz.seasonal_cascade(analyze.seasonal_timing(df, "Insecta")),
                   note="Faint line: full span observed. Bar: middle 50% of records. Dot: typical date. Insects only."),
        intro="When each insect species tends to be on the wing, ordered as a wave from early-season to late."))

    two_up = (
        '<div class="grid lg:grid-cols-2 gap-6">'
        + chart_card(viz.per_day(analyze.obs_per_day(df)))
        + chart_card(viz.taxa_bar(life))
        + '</div>')
    parts.append(section(
        "activity", "Effort & Breadth",
        'Activity &amp; <em class="text-hollow-600">Taxa</em>', two_up,
        intro="Observation effort over time, and the breadth of life recorded across taxonomic groups."))

    parts.append(section(
        "phenology", "Phenology",
        'When Things <em class="text-hollow-600">Appear</em>',
        chart_card(viz.phenology(analyze.phenology(df))),
        intro="The 40 most-recorded species and the months they show up."))

    parts.append(section(
        "uniqueness", "The Big Picture",
        'Common Here, <em class="text-hollow-600">Rare There</em>',
        chart_card(viz.uniqueness_scatter(stats),
                   note="Each point is a species. Further left = rarer in New York. Terracotta = county-first record."),
        tint="bg-stone-100"))

    parts.append(section(
        "observers", "Credit Where Due",
        'The <em class="text-hollow-600">Observers</em>',
        chart_card(viz.leaderboard(analyze.observer_leaderboard(df))),
        intro="Everyone who has contributed observations to the survey."))

    parts.append(section(
        "gallery", "In Pictures",
        'Recent <em class="text-hollow-600">Sightings</em>',
        gallery_body(analyze.photo_highlights(df)),
        intro="The latest research-grade photographs from the property."))

    parts.append(section(
        "map", "Where", 'On the <em class="text-hollow-600">Land</em>',
        chart_card(viz.obs_map(df)),
        intro="Every mapped observation. Coordinates for sensitive species are obscured by iNaturalist."))

    parts.append(footer(generated))
    parts.append(SCRIPTS)

    html = "".join(parts)

    out = PUBLIC_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size // 1024} KB)")
    return out


if __name__ == "__main__":
    build()
