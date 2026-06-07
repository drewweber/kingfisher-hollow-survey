#!/usr/bin/env python3
"""Build a self-contained reports/report.html from the local database."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import analyze  # noqa: E402
import viz  # noqa: E402
from config import PUBLIC_DIR  # noqa: E402
from db import init_db  # noqa: E402

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"


def _esc(x):
    return ("" if x is None else str(x)).replace("&", "&amp;").replace(
        "<", "&lt;").replace(">", "&gt;")


def whats_new_html(recent):
    if recent.empty:
        return "<p>No new observations in the last couple of days.</p>"
    new_species = recent[recent["is_new_for_property"]]
    parts = [f"<p><strong>{len(recent)}</strong> observations added recently, "
             f"including <strong>{len(new_species)}</strong> new for the "
             f"property.</p>"]
    parts.append("<table><thead><tr><th>Species</th><th>Observer</th>"
                 "<th>Date</th><th>New?</th><th>NY records</th>"
                 "<th>County records</th><th>Flag</th></tr></thead><tbody>")
    for _, r in recent.head(50).iterrows():
        name = r.get("common_name") or r.get("taxon_name") or "Unidentified"
        flags = []
        if r.get("is_county_first") == 1:
            flags.append("🏅 county first")
        state_n = r.get("state_obs_count")
        if state_n is not None and state_n == state_n and state_n <= 10:
            flags.append(f"💎 only {int(state_n)} in NY")
        new_badge = "🆕" if r["is_new_for_property"] else ""
        url = r.get("url") or "#"
        parts.append(
            f"<tr><td><a href='{_esc(url)}' target='_blank'>{_esc(name)}</a></td>"
            f"<td>{_esc(r.get('user_name') or r.get('user_login'))}</td>"
            f"<td>{_esc(str(r.get('observed_on'))[:10])}</td>"
            f"<td>{new_badge}</td>"
            f"<td>{_esc('' if state_n != state_n else state_n)}</td>"
            f"<td>{_esc('' if r.get('county_obs_count') != r.get('county_obs_count') else r.get('county_obs_count'))}</td>"
            f"<td>{_esc(', '.join(flags))}</td></tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def uniqueness_html(table):
    if table.empty:
        return "<p>No uniqueness stats yet — run <code>sync.py --stats</code>.</p>"
    rows = ["<table><thead><tr><th>Species</th><th>Yours</th>"
            "<th>County</th><th>NY</th><th>County first?</th></tr></thead><tbody>"]
    for _, r in table.head(60).iterrows():
        first = "🏅" if r.get("is_county_first") == 1 else ""
        rows.append(
            f"<tr><td>{_esc(r['label'])}</td>"
            f"<td>{_esc(r['property_obs_count'])}</td>"
            f"<td>{_esc(r['county_obs_count'])}</td>"
            f"<td>{_esc(r['state_obs_count'])}</td>"
            f"<td>{first}</td></tr>"
        )
    rows.append("</tbody></table>")
    return "".join(rows)


def summary_cards(s):
    def card(label, value):
        return (f"<div class='card'><div class='num'>{_esc(value)}</div>"
                f"<div class='lbl'>{_esc(label)}</div></div>")
    return ("<div class='cards'>"
            + card("Species", s["species"])
            + card("Observations", s["observations"])
            + card("Observers", s["observers"])
            + card("Research grade", s["research_grade"])
            + "</div>")


TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Kingfisher Hollow — iNaturalist Report</title>
<script src="{cdn}"></script>
<style>
  body {{ font-family: -apple-system, Helvetica, Arial, sans-serif;
         margin: 0 auto; max-width: 1100px; padding: 24px; color: #1b2a1b; }}
  h1 {{ color: #1b5e20; }} h2 {{ color: #2e7d32; border-bottom: 2px solid #c8e6c9;
         padding-bottom: 4px; margin-top: 40px; }}
  .meta {{ color: #678; font-size: 0.9em; }}
  .cards {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .card {{ background: #f1f8e9; border-radius: 10px; padding: 16px 24px; flex: 1;
          min-width: 120px; text-align: center; }}
  .card .num {{ font-size: 2em; font-weight: 700; color: #1b5e20; }}
  .card .lbl {{ color: #557; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.9em; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #e0e0e0; }}
  th {{ background: #f1f8e9; }}
  .whatsnew {{ background: #fffde7; border: 1px solid #fff59d; border-radius: 10px;
              padding: 16px 20px; }}
</style></head><body>
<h1>🐦 Kingfisher Hollow Biodiversity Survey</h1>
<p class="meta">Generated {generated} · <a href="https://www.inaturalist.org/projects/kingfisher-hollow-biodiversity-survey" target="_blank">project on iNaturalist</a></p>

<h2>🆕 What's new</h2>
<div class="whatsnew">{whatsnew}</div>

<h2>Summary</h2>
{summary}

<h2>Species accumulation</h2>
{accumulation}

<h2>Observations per day</h2>
{per_day}

<h2>Contribution uniqueness</h2>
{uniqueness_scatter}
{uniqueness_table}

<h2>Phenology</h2>
{phenology}

<h2>Taxa breakdown</h2>
{taxa}

<h2>Observers</h2>
{leaderboard}

<h2>Map</h2>
{obs_map}
</body></html>
"""


def build():
    init_db()
    df = analyze.load_property()
    stats_df = analyze.load_stats()
    if df.empty:
        print("No property observations yet — run sync.py --property first.")
        return None

    s = analyze.summary(df)
    html = TEMPLATE.format(
        cdn=PLOTLY_CDN,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        whatsnew=whats_new_html(analyze.whats_new(df, stats_df)),
        summary=summary_cards(s),
        accumulation=viz.accumulation(analyze.species_accumulation(df)),
        per_day=viz.per_day(analyze.obs_per_day(df)),
        uniqueness_scatter=viz.uniqueness_scatter(stats_df),
        uniqueness_table=uniqueness_html(analyze.uniqueness_table(df, stats_df)),
        phenology=viz.phenology(analyze.phenology(df)),
        taxa=viz.taxa_breakdown(df),
        leaderboard=viz.leaderboard(analyze.observer_leaderboard(df)),
        obs_map=viz.obs_map(df),
    )
    # Written as index.html so the directory is a valid Cloudflare Pages site;
    # also fine to open locally by double-clicking.
    out = PUBLIC_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")
    return out


if __name__ == "__main__":
    build()
