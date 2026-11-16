"""Editorial Plotly figures themed to the Kingfisher Hollow palette.

The look aims for printed-infographic restraint: light horizontal rules instead
of full grids, transparent backgrounds so charts sit on the page, a green family
with a single terracotta accent for "look here" moments, and labels on the chart
rather than in legends. plotly.js loads once from the page, so every fragment
uses include_plotlyjs=False.
"""

from html import escape
import hashlib
import json
import math
import textwrap

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- palette (mirrors the site's `hollow` Tailwind scale) -------------------
HOLLOW = ["#2e735c", "#5eab8d", "#8ec8b1", "#265d4b", "#bbdfd0", "#1d3d33"]
ACCENT = "#c2703d"          # terracotta — highlights (county firsts, rarities)
INK = "#1d3d33"             # hollow-900, primary text
MUTED = "#57685e"           # secondary text, including on pale chart fills
ACCENT_TEXT = "#98552c"     # darker terracotta for small labels on light cards
GRID = "rgba(29,61,51,0.08)"
GREEN_SCALE = [[0.0, "#f0f7f4"], [0.5, "#5eab8d"], [1.0, "#1d3d33"]]

FONT = "Inter, system-ui, sans-serif"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_STARTS = pd.date_range("2000-01-01", periods=12, freq="MS").day_of_year.tolist()

# Dark-mode equivalents for the moth view (charts sit on bg-hollow-950).
DARK_INK = "#e8f0ec"
DARK_MUTED = "#9bb3a8"
DARK_ACCENT_TEXT = "#e5a575"
DARK_GRID = "rgba(255,255,255,0.10)"
# On dark, line/marker colors need to be light tints to read.
DARK_LINE = "#8ec8b1"       # hollow-300
DARK_LINE2 = "#5eab8d"      # hollow-400
DARK_GREEN_SCALE = [[0.0, "#13322a"], [0.5, "#3d8f72"], [1.0, "#bbdfd0"]]


def _palette(dark):
    """Text / grid / line colors for the active theme."""
    if dark:
        return dict(ink=DARK_INK, muted=DARK_MUTED, grid=DARK_GRID,
                    accent_text=DARK_ACCENT_TEXT,
                    line=DARK_LINE, line2=DARK_LINE2,
                    hover_bg="#214a3d", hover_fg="#f0f7f4", hover_border="#5eab8d",
                    green_scale=DARK_GREEN_SCALE)
    return dict(ink=INK, muted=MUTED, grid=GRID,
                accent_text=ACCENT_TEXT,
                line=HOLLOW[0], line2=HOLLOW[3],
                hover_bg="white", hover_fg=INK, hover_border=GRID,
                green_scale=GREEN_SCALE)


def _style(fig, height=420, showlegend=False, dark=False):
    """Apply the shared editorial treatment to a figure (light or dark)."""
    c = _palette(dark)
    fig.update_layout(
        height=height,
        showlegend=showlegend,
        font=dict(family=FONT, size=13, color=c["ink"]),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=12, r=18, t=14, b=12),
        hoverlabel=dict(font=dict(family=FONT, size=12, color=c["hover_fg"]),
                        bgcolor=c["hover_bg"], bordercolor=c["hover_border"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    x=0, font=dict(size=12, color=c["ink"]),
                    bgcolor="rgba(0,0,0,0)"),
        title=None,
    )
    fig.update_xaxes(showgrid=False, zeroline=False,
                     linecolor=c["grid"], ticks="outside", tickcolor=c["grid"],
                     tickfont=dict(color=c["muted"], size=11))
    fig.update_yaxes(showgrid=True, gridcolor=c["grid"], zeroline=False,
                     tickfont=dict(color=c["muted"], size=11))
    return fig


def _html(fig, **cfg):
    config = {"displayModeBar": False, "responsive": True, **cfg}
    # Queue chart creation until its card approaches the viewport. This keeps
    # Plotly's large runtime and the hidden taxonomy views off the initial path.
    return (fig.to_html(full_html=False, include_plotlyjs=False, config=config)
            .replace('class="plotly-graph-div"',
                     'class="plotly-graph-div" data-plotly-chart')
            .replace("Plotly.newPlot(", "window.__plotlyRender("))


def _with_data(plot_html, title, summary, headers, rows, dark=False):
    """Pair a plot with source-derived HTML that needs no chart runtime.

    Keep alternatives outside the Plotly host: rendering or replacing that host
    must never remove the summary or table. Native details supports touch and
    keyboard activation even when scripts are unavailable.
    """
    rows = list(rows)
    fingerprint = hashlib.sha256(json.dumps([title, summary, headers, rows], default=str).encode()).hexdigest()[:16]
    caption_id = f"chart-data-{fingerprint}"
    summary_id = f"{caption_id}-summary"
    text = "text-secondary-inverse" if dark else "text-secondary"
    surface = "bg-hollow-950" if dark else "bg-white"
    border = "border-white/10" if dark else "border-stone-200"

    def cell(value):
        return escape("Not available" if pd.isna(value) else str(value))

    table_rows = []
    for row in rows:
        cells = [
            f'<th scope="row" class="sticky left-0 {surface} py-2 pr-4 text-left font-normal">{cell(row[0])}</th>'
        ]
        cells.extend(f'<td class="px-3 py-2 text-right tabular-nums">{cell(value)}</td>'
                     for value in row[1:])
        table_rows.append(f'<tr class="border-t {border}">{"".join(cells)}</tr>')
    columns = "".join(
        f'<th scope="col" class="px-3 py-2 text-left font-medium">{escape(header)}</th>'
        for header in headers
    )
    return (
        f'<div data-chart-figure data-chart-title="{escape(title, quote=True)}" class="min-w-0 {text}">'
        f'<figure aria-labelledby="{summary_id}">'
        f'<figcaption id="{summary_id}" class="mb-4 text-sm leading-relaxed text-pretty">{escape(summary)}</figcaption>'
        f'{plot_html}</figure>'
        f'<details data-chart-table data-chart-description="{escape(summary, quote=True)}" class="mt-4 border-t {border}">'
        '<summary class="cursor-pointer py-3 text-sm font-medium">'
        f'View {escape(title.lower())} data ({len(rows):,} rows)</summary>'
        '<p class="mb-2 text-xs">Scroll the table to read all columns and rows.</p>'
        f'<div tabindex="0" role="region" aria-labelledby="{caption_id}" '
        'class="max-h-80 max-w-full overflow-auto">'
        '<table class="w-full text-sm border-separate border-spacing-0">'
        f'<caption id="{caption_id}" class="pb-3 text-left font-medium">{escape(title)}</caption>'
        f'<thead class="sticky top-0 z-10 {surface}"><tr>{columns}</tr></thead>'
        f'<tbody>{"".join(table_rows)}</tbody></table></div></details></div>'
    )


def _date(value):
    return pd.Timestamp(value).strftime("%Y-%m-%d") if pd.notna(value) else None


def _number(value):
    """Keep integer counts compact without rounding fractional source values."""
    return f"{value:g}" if pd.notna(value) else None


# --- cumulative discovery (species accumulation, annotated) -----------------
def discovery_curve(firsts):
    """Combined inventory chronology, with source evidence and dated coverage."""
    undated = int(firsts.attrs.get("undated_species", 0))
    inventory_total = int(firsts.attrs.get("inventory_species", len(firsts)))
    coverage = (
        f"{inventory_total:,} species in the combined inventory; "
        f"{undated:,} species without a usable date remain in the inventory but are not plotted. "
    )
    inventory_link = (
        '<p class="mt-4 border-t border-stone-200 text-sm">'
        '<a data-chart-link href="/life-list/" class="inline-block py-3 underline">'
        'Browse the Life List</a> for species names and available record dates.</p>'
    )
    if firsts.empty:
        return f"<p class='chart-empty'>No dated records to plot. {coverage}</p>" + inventory_link
    fig = go.Figure()
    fig.add_scatter(
        x=firsts["observed_on"], y=firsts["cumulative"],
        mode="lines", line=dict(color=HOLLOW[0], width=2.5, shape="hv"),
        fill="tozeroy", fillcolor="rgba(94,171,141,0.16)",
        hovertemplate="%{x|%b %e, %Y}<br><b>%{y}</b> species<extra></extra>",
        name="Species",
    )
    total = int(firsts["cumulative"].max())
    milestones = [m for m in (100, 250, 500, 750, 1000, 1500) if m <= total]
    for m in milestones:
        row = firsts[firsts["cumulative"] >= m].iloc[0]
        fig.add_annotation(
            x=row["observed_on"], y=m, text=f"{m}th",
            showarrow=True, arrowhead=0, arrowcolor=MUTED, arrowwidth=1,
            ax=0, ay=-26, font=dict(size=10, color=MUTED),
        )
    # Label the latest total directly on the line's end.
    last = firsts.iloc[-1]
    fig.add_annotation(
        x=last["observed_on"], y=total, text=f"<b>{total}</b> species",
        showarrow=False, xanchor="right", yanchor="bottom",
        font=dict(size=14, color=HOLLOW[0]),
    )
    summary = (
        f"The curve reaches {total:,} species with dated records by {_date(last['observed_on'])}. "
        + coverage
        + "Each species is counted once, using its earliest available inventory record: "
        "eBird life-list dates for birds and iNaturalist dates for other groups. "
        "These dates do not establish arrival or repeat frequency; identification revisions can change this history."
    )
    summary_id = "discovery-" + hashlib.sha256(summary.encode()).hexdigest()[:16]
    # The Life List is the full inventory alternative; do not publish a second
    # species table here. Keep this link and summary outside the Plotly host.
    return (
        '<div data-chart-figure data-chart-title="Cumulative species records · iNaturalist + eBird" '
        'class="min-w-0 text-secondary">'
        f'<figure aria-labelledby="{summary_id}">'
        f'<figcaption id="{summary_id}" class="mb-4 text-sm leading-relaxed text-pretty">{escape(summary)}</figcaption>'
        f'{_html(_style(fig, height=440))}</figure>{inventory_link}</div>'
    )


# --- observations per day ---------------------------------------------------
def per_day(daily):
    """Compare reporting seasons on a fixed calendar, retaining real dates.

    Rolling averages are calculated on the continuous record in analyze, before
    splitting into years. A leap reference year aligns month/day across years
    without shifting March onward or inventing a February 29 in non-leap years.
    """
    if daily.empty:
        return "<p class='chart-empty'>No data yet.</p>"
    daily = daily.sort_values("observed_on")
    fig = go.Figure()
    spans = []
    styles = [(HOLLOW[0], "solid"), (ACCENT_TEXT, "dash"),
              (MUTED, "dot"), (HOLLOW[3], "dashdot")]
    years = list(daily.groupby(daily["observed_on"].dt.year))
    for index, (year, records) in enumerate(years):
        start, end = records["observed_on"].iloc[[0, -1]]
        partial = start > pd.Timestamp(year=year, month=1, day=1) or end < pd.Timestamp(year=year, month=12, day=31)
        label = f"{year}" + (" (partial)" if partial else "")
        spans.append(f"{label}: {start:%b %d}–{end:%b %d}")
        color, dash = styles[(len(years) - 1 - index) % len(styles)]
        fig.add_scatter(
            x=[date.replace(year=2000).day_of_year for date in records["observed_on"]],
            y=records["rolling_30d"],
            mode="lines" if len(records) > 1 else "markers",
            line=dict(color=color, width=2.5, dash=dash),
            marker=dict(color=color, size=7),
            connectgaps=False,
            customdata=[[_date(r.observed_on), int(r.observations)]
                        for r in records.itertuples()],
            hovertemplate=("%{customdata[0]}<br>%{customdata[1]} records that day"
                           "<br>%{y:.1f} records/day, trailing average<extra>%{fullData.name}</extra>"),
            name=label,
        )
    _style(fig, height=360, showlegend=True)
    fig.update_xaxes(range=[1, 366], fixedrange=True, tickmode="array",
                     tickvals=MONTH_STARTS, ticktext=MONTHS)
    fig.update_yaxes(title_text="Records / day", rangemode="tozero", fixedrange=True)
    fig.update_layout(dragmode=False, legend=dict(itemclick=False, itemdoubleclick=False))
    return _with_data(
        _html(fig), "Daily observation reports by year",
        f"{int(daily['observations'].sum()):,} observations across {len(daily):,} calendar days. "
        "Lines compare the trailing 30-day average of submitted records by observation date on a January–December calendar. "
        + "; ".join(spans) + ". "
        "Dates outside the available record span are left blank. Within that span, zero means no submitted records, "
        "not confirmed absence or survey effort. Averages include preceding December days when available; "
        "the first 29 days of the record use the available days only. Daily counts are in the data table.",
        ["Date", "Observations", "Trailing daily average (up to 30 days)"],
        ((_date(r.observed_on), int(r.observations), f"{r.rolling_30d:.1f}")
         for r in daily.itertuples()),
    )


# --- species by taxonomic group (clean horizontal bars) ---------------------
def taxa_bar(life):
    if life.empty:
        return "<p class='chart-empty'>No data yet.</p>"
    counts = (life.groupby("iconic_taxon")["taxon_id"].nunique()
              .sort_values(ascending=True))
    # Accent the single largest group so the chart has a focal point.
    top_group = counts.index[-1] if len(counts) else None
    colors = [ACCENT if g == top_group else HOLLOW[1] for g in counts.index]
    fig = go.Figure(go.Bar(
        x=counts.values, y=counts.index, orientation="h",
        marker_color=colors,
        text=counts.values, textposition="outside",
        textfont=dict(color=INK, size=12),
        hovertemplate="%{y}: %{x} species<extra></extra>",
    ))
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(showgrid=False)
    return _with_data(
        _html(_style(fig, height=max(260, 30 * len(counts)))), "Species by taxonomic group",
        f"{int(counts.sum()):,} species across {len(counts)} taxonomic groups. "
        "Each bar counts distinct species recorded in that group.",
        ["Taxonomic group", "Species"], ((label, int(count)) for label, count in counts.items()),
    )


# --- phenology heatmap ------------------------------------------------------
def phenology(matrix, dark=False, normalize=False):
    """Species × month heatmap. With normalize=True each row is scaled to its own
    peak month, so a rare species' timing reads as clearly as a common one's
    (raw counts stay in the hover)."""
    if matrix.empty:
        return "<p class='chart-empty'>No phenology data.</p>"
    raw = matrix.values
    hover_counts = matrix.fillna(0).astype(int).astype(str).values.tolist()
    if normalize:
        row_max = matrix.max(axis=1).replace(0, 1)
        z = matrix.div(row_max, axis=0).values
        cbar_title = "relative to<br>peak reporting month"
    else:
        z = raw
        cbar_title = ""
    fig = go.Figure(go.Heatmap(
        z=z, x=MONTHS, y=matrix.index.tolist(),
        text=hover_counts,
        colorscale=_palette(dark)["green_scale"], showscale=True,
        colorbar=dict(title=dict(text=cbar_title, font=dict(size=10)),
                      thickness=10, len=0.6, outlinewidth=0),
        hovertemplate="%{y}<br>%{x}: %{text} observations recorded<extra></extra>",
        xgap=2, ygap=2,
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(side="top")
    return _with_data(
        _html(_style(fig, height=max(420, 19 * len(matrix)), dark=dark)), "Monthly species reports",
        f"{int(matrix.fillna(0).to_numpy().sum()):,} observations for the {len(matrix)} species shown, grouped by calendar month across years. "
        + ("Colors are scaled to each species' peak reporting month; the table gives raw observation counts. " if normalize else "The table gives raw observation counts. ")
        + "A zero means no submitted record in that month, not confirmed absence.",
        ["Species", *MONTHS],
        ((label, *(int(value) if pd.notna(value) else None for value in row))
         for label, row in matrix.iterrows()), dark=dark,
    )


# --- seasonal cascade (when each species appears) ---------------------------
def seasonal_cascade(agg, group_label="Birds", dark=False):
    """Horizontal range plot: faint first→last line, q1–q3 bar, median dot —
    species ordered by median appearance so it reads as a seasonal wave."""
    if agg.empty:
        return "<p class='chart-empty'>Not enough data for a seasonal view.</p>"
    c = _palette(dark)
    span = ("rgba(142,200,177,0.30)" if dark else "rgba(94,171,141,0.35)")
    dot = "#bbdfd0" if dark else HOLLOW[3]
    fig = go.Figure()
    y = agg["label"].tolist()
    # full span (faint)
    for _, r in agg.iterrows():
        fig.add_scatter(
            x=[r["first_doy"], r["last_doy"]], y=[r["label"], r["label"]],
            mode="lines", line=dict(color=span, width=2),
            hoverinfo="skip", showlegend=False,
        )
    # interquartile band
    for _, r in agg.iterrows():
        fig.add_scatter(
            x=[r["q1"], r["q3"]], y=[r["label"], r["label"]],
            mode="lines", line=dict(color=c["line2"], width=7),
            hoverinfo="skip", showlegend=False,
        )
    # median marker
    fig.add_scatter(
        x=agg["median_doy"], y=y, mode="markers",
        marker=dict(color=dot, size=9,
                    line=dict(color=c["hover_bg"], width=1.5)),
        customdata=agg["n"],
        hovertemplate=(
            "<b>%{y}</b><br>Median observation day of year: %{x:.0f}<br>"
            "%{customdata} dated records<extra></extra>"
        ),
        showlegend=False,
    )
    fig.update_xaxes(tickvals=MONTH_STARTS, ticktext=MONTHS,
                     range=[1, 366], showgrid=True, gridcolor=c["grid"])
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return _with_data(
        _html(_style(fig, height=max(360, 22 * len(agg)), dark=dark)), "Seasonal reporting ranges",
        f"Reporting dates for {len(agg)} species: earliest to latest record, middle half of records, and median. "
        "Days use a shared leap-year calendar and describe submitted records, not the full flight or activity season.",
        ["Species", "First day of year", "25th percentile day", "Median day", "75th percentile day", "Last day of year", "Dated records"],
        ((r.label, *(_number(getattr(r, name)) for name in
                    ("first_doy", "q1", "median_doy", "q3", "last_doy", "n")))
         for r in agg.itertuples()), dark=dark,
    )


# --- uniqueness scatter -----------------------------------------------------
def uniqueness_scatter(stats):
    if stats.empty:
        return "<p class='chart-empty'>No uniqueness stats yet.</p>"
    s = stats.copy()
    s["label"] = s["common_name"].fillna(s["taxon_name"])
    fig = go.Figure()
    common = s[s["is_county_first"] != 1]
    firsts = s[s["is_county_first"] == 1]
    fig.add_scatter(
        x=common["state_obs_count"], y=common["property_obs_count"],
        mode="markers", marker=dict(color="rgba(94,171,141,0.55)", size=8),
        text=common["label"], name="Recorded elsewhere too",
        hovertemplate="<b>%{text}</b><br>%{x} in NY · %{y} here<extra></extra>",
    )
    fig.add_scatter(
        x=firsts["state_obs_count"], y=firsts["property_obs_count"],
        mode="markers", marker=dict(color=ACCENT, size=11,
                                    line=dict(color="white", width=1)),
        text=firsts["label"], name="County-first record",
        hovertemplate="<b>%{text}</b> · county first<br>%{x} in NY<extra></extra>",
    )
    # Mark the "rare in NY" zone (matches the ≤25 badge threshold) and label the
    # standout species there directly — hover is dead on mobile / static export.
    ymax = s["property_obs_count"].max() if not s.empty else 1
    fig.add_shape(type="rect", x0=0.5, x1=25, y0=0, y1=ymax * 1.08,
                  fillcolor="rgba(194,112,61,0.07)", line=dict(width=0), layer="below")
    fig.add_vline(x=25, line=dict(color=ACCENT, width=1, dash="dot"))
    fig.add_annotation(x=25, y=ymax * 1.08, text="← rarer in New York",
                       showarrow=False, xanchor="left", yanchor="top",
                       font=dict(size=11, color=ACCENT_TEXT))
    standouts = (s[s["state_obs_count"] <= 25]
                 .sort_values("property_obs_count", ascending=False).head(4))
    if not standouts.empty:
        fig.add_scatter(
            x=standouts["state_obs_count"], y=standouts["property_obs_count"],
            mode="text", text=standouts["label"], textposition="middle right",
            textfont=dict(size=10, color=INK), hoverinfo="skip", showlegend=False)
    fig.update_xaxes(type="log", range=[0, 6], title=dict(
        text="Observations in New York (log scale) →", font=dict(size=11, color=MUTED)))
    fig.update_yaxes(title=dict(
        text="Your observations here", font=dict(size=11, color=MUTED)))
    return _with_data(
        _html(_style(fig, height=460, showlegend=True)), "Property and New York records",
        f"Record counts for {len(s)} species compare this property with New York. "
        f"{int((s['state_obs_count'] <= 25).sum())} have at most 25 New York records in the available comparison. "
        "The horizontal axis is logarithmic. These are reporting counts, not population estimates.",
        ["Species", "New York observations", "Property observations", "County-first flag"],
        ((r.label, _number(r.state_obs_count), _number(r.property_obs_count),
          "Yes" if r.is_county_first == 1 else ("No" if r.is_county_first == 0 else None))
         for r in s.itertuples()),
    )


# --- observer leaderboard ---------------------------------------------------
def leaderboard(board):
    """Give every contributor equal space while comparing two skewed totals.

    Mark position, never bar length, encodes a logarithmic count. Zero has no
    logarithm: retain it in the exact labels/table without inventing a position.
    """
    if board.empty:
        return "<p class='chart-empty'>No observers yet.</p>"
    b = board.copy()
    b["label"] = b["display_name"].fillna("").astype(str).str.strip()
    b["label"] = b["label"].where(b["label"].ne(""), b["user_login"])
    b = b.sort_values(["label", "user_login"], key=lambda values: values.str.casefold())
    labels = []
    for row in b.itertuples():
        name = "<br>".join(escape(line) for line in textwrap.wrap(row.label, width=18))
        labels.append(f"<b>{name}</b><br>{int(row.observations):,} observations"
                      f"<br>{int(row.species):,} species")
    positions = list(range(len(b)))
    fig = go.Figure()
    for metric, title, color, symbol, offset in [
        ("species", "Total species", HOLLOW[0], "circle", 0.14),
        ("observations", "Observations", ACCENT_TEXT, "diamond", -0.14),
    ]:
        fig.add_scatter(
            x=[int(value) if value > 0 else None for value in b[metric]],
            y=[position + offset for position in positions], mode="markers",
            marker=dict(color=color, symbol=symbol, size=9), name=title,
            customdata=[[escape(row.label), int(getattr(row, metric))]
                        for row in b.itertuples()],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]:,} "
                          + title.lower() + "<extra></extra>",
        )
    # Reserve enough height for wrapped names and exact counts at phone widths.
    row_height = max(76, max(label.count("<br>") + 1 for label in labels) * 16 + 20)
    _style(fig, height=100 + row_height * len(b), showlegend=True)
    maximum = max(1, int(b[["observations", "species"]].max().max()))
    exponent = max(1, math.ceil(math.log10(maximum)))
    step = max(1, math.ceil(exponent / 4))
    ticks = [10 ** power for power in range(0, exponent + 1, step)]
    fig.update_xaxes(type="log", range=[-0.12, exponent + 0.12],
                     tickmode="array", tickvals=ticks, tickformat="~s",
                     title_text="Count · logarithmic scale", showgrid=True,
                     gridcolor=GRID, fixedrange=True)
    fig.update_yaxes(tickmode="array", tickvals=positions, ticktext=labels,
                     range=[len(b) - 0.5, -0.5], showgrid=False, fixedrange=True,
                     tickfont=dict(color=INK, size=11), automargin=True)
    fig.update_layout(dragmode=False, margin=dict(l=132, r=18, t=50, b=55),
                      legend=dict(y=1, itemclick=False, itemdoubleclick=False))
    zero_note = (" Zero counts are labeled but not plotted on the logarithmic axis."
                 if (b[["observations", "species"]] == 0).any().any() else "")
    return _with_data(
        _html(fig), "Observer contributions",
        f"All {len(b)} observers, in alphabetical order. Circles show total distinct species; "
        "diamonds show observations. The logarithmic count axis keeps small contributions visible: "
        "each tenfold increase spans the same distance. Counts cover species-level, non-bird "
        "iNaturalist records in this survey; eBird contributions are not included. "
        "Species totals include shared species and overlap between observers."
        + zero_note,
        ["Observer", "Observations", "Total species", "Species recorded only by this observer"],
        ((r.label, int(r.observations), int(r.species), int(r.unique_species))
         for r in b.itertuples()),
    )


# --- map --------------------------------------------------------------------
# Map color roles: quiet Carto tiles provide neutral context; these botanical /
# earth hues identify categories, not magnitude, rarity, or selection. Each pair
# is (light basemap, dark basemap), keeping the same hue family in either theme.
# Key by taxon so absent groups and input order cannot reassign a category.
# Unknown groups are neutral; legend labels and species/taxon hover text remain
# essential for distinguishing categories in grayscale or color-deficient views.
MAP_TAXON_COLORS = {
    "Plantae":        ("#39724b", "#80b88b"),  # leaf
    "Insecta":        ("#b36b12", "#e7ac56"),  # ochre
    "Fungi":          ("#98547c", "#d593b9"),  # heather
    "Arachnida":      ("#7456a6", "#b49bdc"),  # violet
    "Reptilia":       ("#817226", "#c4b45f"),  # olive
    "Amphibia":       ("#187d83", "#66bfc4"),  # pond teal
    "Mammalia":       ("#91604b", "#c99b82"),  # chestnut
    "Animalia":       ("#566275", "#9daec5"),  # slate
    "Actinopterygii": ("#316d9e", "#79b2df"),  # river blue
    "Mollusca":       ("#b55341", "#e59079"),  # clay
    "Aves":           ("#a74f68", "#df8fa4"),  # rose
    "Chromista":      ("#58519a", "#a39cdb"),  # indigo
    "Protozoa":       ("#557b22", "#a0be6a"),  # moss
    "Other":          ("#737373", "#b0b0b0"),  # neutral fallback
}


def obs_map(df, dark=False):
    pts = df.dropna(subset=["latitude", "longitude"])
    if pts.empty:
        return "<p class='chart-empty'>No mappable (un-obscured) observations.</p>"
    groups = pts["iconic_taxon"].fillna("Other").unique()
    palette = {g: MAP_TAXON_COLORS.get(g, MAP_TAXON_COLORS["Other"])[bool(dark)]
               for g in groups}
    fig = go.Figure()
    for g in groups:
        sub = pts[pts["iconic_taxon"].fillna("Other") == g]
        fig.add_scattermap(
            lat=sub["latitude"], lon=sub["longitude"], mode="markers",
            marker=dict(size=7, color=palette[g]), name=g,
            text=sub["common_name"].fillna(sub["taxon_name"]),
            hovertemplate="<b>%{text}</b><extra>" + g + "</extra>",
        )
    legend_bg = "rgba(13,34,28,0.85)" if dark else "rgba(255,255,255,0.85)"
    fig.update_layout(
        map=dict(style="carto-darkmatter" if dark else "carto-positron",
                 center=dict(lat=pts["latitude"].mean(),
                             lon=pts["longitude"].mean()),
                 zoom=15),
        height=560, margin=dict(l=0, r=0, t=0, b=0),
        showlegend=True,
        font=dict(family=FONT, color=DARK_INK if dark else INK),
        legend=dict(bgcolor=legend_bg, x=0.01, y=0.99,
                    bordercolor=DARK_GRID if dark else GRID, borderwidth=1),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return _html(fig)


# === moth-view charts (dark by default) =====================================
def completeness_curve(effort, comp, dark=True):
    """Cumulative species vs. observations, with the Chao2 asymptote drawn as a
    horizontal target line — visualizes how close the moth inventory is to done."""
    if effort.empty:
        return "<p class='chart-empty'>Not enough data.</p>"
    c = _palette(dark)
    est = comp["estimated"]
    low, high = comp.get("low", est), comp.get("high", est)
    xmax = effort["cum_obs"].max()
    fig = go.Figure()
    # Chao2 95% CI as a shaded band — the estimate is a range, not a point.
    if high > low:
        fig.add_shape(type="rect", x0=0, x1=xmax, y0=low, y1=high,
                      fillcolor="rgba(194,112,61,0.14)", line=dict(width=0),
                      layer="below")
    fig.add_scatter(
        x=effort["cum_obs"], y=effort["cum_species"], mode="lines",
        line=dict(color=c["line"], width=3), fill="tozeroy",
        fillcolor="rgba(142,200,177,0.12)",
        hovertemplate="%{x} obs → %{y} species<extra></extra>", name="Recorded",
    )
    fig.add_hline(y=est, line=dict(color=ACCENT, width=1.5, dash="dot"))
    band = f" (likely {low}–{high})" if high > low else ""
    fig.add_annotation(
        x=xmax, y=high if high > low else est, xanchor="right", yanchor="bottom",
        text=f"Chao2 estimate ≈ <b>{est}</b>{band}", showarrow=False,
        font=dict(size=12, color=c["accent_text"]))
    fig.update_xaxes(title=dict(text="Cumulative moth observations →",
                                font=dict(size=11, color=c["muted"])))
    fig.update_yaxes(title=dict(text="Moth species",
                                font=dict(size=11, color=c["muted"])))
    return _with_data(
        _html(_style(fig, height=400, dark=dark)), "Moth inventory accumulation",
        f"The recorded curve reaches {int(effort['cum_species'].max()):,} species over {int(xmax):,} observations. "
        f"The Chao2 estimate is {est}" + (f", with a plotted 95% interval of {low}–{high}. " if high > low else ". ")
        + "The table gives the recorded curve; the estimate is a model result, not an observed total.",
        ["Cumulative observations", "Cumulative species"],
        ((int(r.cum_obs), int(r.cum_species)) for r in effort.itertuples()), dark=dark,
    )


def family_breakdown(fam, dark=True):
    """Per-family progress: a faint full bar = species known from the county, a
    solid bar = species recorded here. Shows which moth families are near-complete
    and which (the micros) are barely sampled."""
    if fam.empty:
        return "<p class='chart-empty'>Not enough family data yet.</p>"
    c = _palette(dark)
    f = fam.iloc[::-1]   # largest family on top
    labels = [f"{lbl} ({r}/{t})" for lbl, r, t in
              zip(f["label"], f["recorded"], f["region_total"])]
    fig = go.Figure()
    fig.add_bar(y=labels, x=f["region_total"], orientation="h",
                marker_color="rgba(142,200,177,0.20)", name="Known within 50 mi",
                hovertemplate="%{y}<br>%{x} regional species<extra></extra>")
    fig.add_bar(y=labels, x=f["recorded"], orientation="h",
                marker_color=c["line2"], name="Recorded here",
                hovertemplate="%{y}<br>%{x} recorded here<extra></extra>")
    fig.update_layout(barmode="overlay", bargap=0.35)
    fig.update_xaxes(title=dict(text="Species →", font=dict(size=11, color=c["muted"])))
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11, color=c["ink"]))
    return _with_data(
        _html(_style(fig, height=max(380, 32 * len(f)), showlegend=True, dark=dark)), "Moth family comparison",
        f"{len(fam)} moth families compared: species recorded here and species known within 50 miles. "
        "Regional records do not establish that every species occurs on this property.",
        ["Family", "Species recorded here", "Species known within 50 miles"],
        ((r.label, int(r.recorded), int(r.region_total)) for r in fam.itertuples()), dark=dark,
    )


def rank_abundance(counts, dark=True):
    """Species ranked by observation count, highlighting one or two records."""
    if not counts:
        return "<p class='chart-empty'>Not enough data.</p>"
    c = _palette(dark)
    singletons = sum(1 for v in counts if v == 1)
    doubletons = sum(1 for v in counts if v == 2)
    n = len(counts)
    x = list(range(1, n + 1))
    body = [v if v > 2 else None for v in counts]
    tail = [v if v <= 2 else None for v in counts]
    fig = go.Figure()
    fig.add_scatter(x=x, y=body, mode="lines+markers",
                    line=dict(color=c["line"], width=2),
                    marker=dict(color=c["line2"], size=4),
                    hovertemplate="rank %{x}: %{y} observations<extra></extra>",
                    name="3+ records")
    fig.add_scatter(x=x, y=tail, mode="markers",
                    marker=dict(color=ACCENT, size=5),
                    hovertemplate="rank %{x}: %{y} observation(s)<extra></extra>",
                    name="1–2 records")
    fig.add_hline(y=1, line=dict(color=c["grid"], width=1))
    if singletons:
        fig.add_annotation(
            x=n, y=1, xanchor="right", yanchor="bottom",
            text=f"<b>{singletons}</b> recorded once · <b>{doubletons}</b> twice",
            showarrow=False, font=dict(size=11, color=c["accent_text"]))
    fig.update_yaxes(type="log", title=dict(text="Observations (log) →",
                     font=dict(size=11, color=c["muted"])))
    fig.update_xaxes(title=dict(text="Species rank (most → least recorded)",
                     font=dict(size=11, color=c["muted"])))
    return _with_data(
        _html(_style(fig, height=360, dark=dark)), "Species observation ranks",
        f"{n} species ranked by observation count; {singletons} have one record and {doubletons} have two. "
        "The vertical axis is logarithmic. Ranks describe reporting frequency, not population abundance.",
        ["Species rank", "Observations"], enumerate(counts, start=1), dark=dark,
    )


def monthly_survey_bar(summary, dark=True):
    """Horizontal grouped bar chart of monthly moth reports and discoveries.

    Each month is a row. The primary (wider) bar shows species_count in
    hollow-green. A thinner overlay bar shows new_species_count in terracotta.
    October–April render at 30% opacity. Hover shows species counts and the
    number of dates with reports. Months use the overnight session date.

    `summary` is the list of 12 dicts returned by analyze.monthly_survey_summary().
    Returns an HTML fragment (include_plotlyjs=False, displayModeBar=False).
    """
    if not summary:
        return "<p class='chart-empty'>No survey data yet.</p>"
    c = _palette(dark)

    labels = [r["month_name"] for r in summary]
    species_counts = [r["species_count"] for r in summary]
    new_counts = [r["new_species_count"] for r in summary]
    nights = [r["nights_surveyed"] for r in summary]
    in_season = [r["survey_season"] for r in summary]

    # Species bar: solid green for survey months, 30% opacity for off-season.
    species_colors = [
        (c["line2"] if s else f"rgba(94,171,141,0.30)") for s in in_season
    ]
    # New-species overlay: terracotta at full opacity in season, 30% off-season.
    new_colors = [
        (ACCENT if s else "rgba(194,112,61,0.30)") for s in in_season
    ]

    fig = go.Figure()

    # Primary bar: species recorded that month.
    fig.add_bar(
        y=labels,
        x=species_counts,
        orientation="h",
        name="Species recorded",
        marker_color=species_colors,
        customdata=list(zip(species_counts, new_counts, nights)),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "%{customdata[0]} species recorded · %{customdata[1]} first records<br>"
            "%{customdata[2]} dates with moth reports<extra></extra>"
        ),
    )

    # Overlay bar: species first recorded on the property that month (thinner).
    fig.add_bar(
        y=labels,
        x=new_counts,
        orientation="h",
        name="New to property",
        marker_color=new_colors,
        width=0.35,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "%{x} species first recorded here<extra></extra>"
        ),
    )

    fig.update_layout(barmode="overlay", bargap=0.25)
    fig.update_xaxes(
        title=dict(text="Species →", font=dict(size=11, color=c["muted"]))
    )
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12, color=c["ink"]))
    return _with_data(
        _html(_style(fig, height=420, showlegend=True, dark=dark)), "Monthly moth reports",
        f"{sum(new_counts):,} first records across the {len(summary)} months shown. "
        "Each row gives species recorded, species first recorded here, and dates with reports. "
        "Species can appear in multiple months; dates use the overnight session date.",
        ["Month", "Species recorded", "Species first recorded here", "Dates with moth reports"],
        zip(labels, species_counts, new_counts, nights), dark=dark,
    )


def nightly_species_calendar(nightly, dark=True):
    """Calendar heatmap of distinct moth species reported per session date.

    Each year is a Monday–Sunday calendar row. Dates without moth reports stay
    blank rather than appearing as zeroes. Exact counts are printed in active
    cells and repeated in an expandable HTML table for small screens and
    assistive technology.
    """
    if nightly is None or nightly.empty:
        return (
            "<p class='chart-empty text-pretty'>No nightly moth reports yet. "
            "Add observations to populate the calendar.</p>"
        )

    data = nightly.copy()
    data["night"] = pd.to_datetime(data["night"], errors="coerce").dt.normalize()
    data = data.dropna(subset=["night"]).sort_values("night")
    if data.empty:
        return (
            "<p class='chart-empty text-pretty'>No dated moth reports yet. "
            "Add dated observations to populate the calendar.</p>"
        )

    c = _palette(dark)
    years = sorted(data["night"].dt.year.unique())
    max_species = max(int(data["species_count"].max()), 1)
    scale_max = max(max_species, 2)
    vertical_spacing = min(0.12, 0.5 / max(len(years), 1))
    fig = make_subplots(
        rows=len(years),
        cols=1,
        vertical_spacing=vertical_spacing,
    )
    active_scale = [
        [0.0, "#265d4b"],
        [0.55, "#3d8f72"],
        [1.0, "#bbdfd0"],
    ]
    annotations = []

    for row_num, year in enumerate(years, start=1):
        axis_suffix = "" if row_num == 1 else str(row_num)
        axis_refs = {"xref": f"x{axis_suffix}", "yref": f"y{axis_suffix}"}
        year_start = pd.Timestamp(year=int(year), month=1, day=1)
        year_end = pd.Timestamp(year=int(year), month=12, day=31)
        grid_start = year_start - pd.Timedelta(days=year_start.weekday())
        week_count = int((year_end - grid_start).days // 7) + 1

        background = [[None] * week_count for _ in range(7)]
        values = [[None] * week_count for _ in range(7)]
        hover = [[None] * week_count for _ in range(7)]

        for date in pd.date_range(year_start, year_end, freq="D"):
            week = int((date - grid_start).days // 7)
            background[date.weekday()][week] = 1

        year_data = data[data["night"].dt.year == year]
        for record in year_data.itertuples(index=False):
            date = pd.Timestamp(record.night)
            week = int((date - grid_start).days // 7)
            weekday = date.weekday()
            species_count = int(record.species_count)
            observation_count = int(record.observation_count)
            values[weekday][week] = species_count
            hover[weekday][week] = [
                f"{date:%A, %B} {date.day}, {date.year}",
                species_count,
                observation_count,
            ]

        fig.add_trace(
            go.Heatmap(
                z=background,
                x=list(range(week_count)),
                y=list(range(7)),
                colorscale=[
                    [0.0, "rgba(255,255,255,0.045)"],
                    [1.0, "rgba(255,255,255,0.045)"],
                ],
                zmin=0,
                zmax=1,
                xgap=2,
                ygap=2,
                showscale=False,
                hoverinfo="skip",
            ),
            row=row_num,
            col=1,
        )
        fig.add_trace(
            go.Heatmap(
                z=values,
                customdata=hover,
                x=list(range(week_count)),
                y=list(range(7)),
                colorscale=active_scale,
                zmin=1,
                zmax=scale_max,
                xgap=2,
                ygap=2,
                showscale=row_num == 1,
                hoverongaps=False,
                hovertemplate=(
                    "<b>Reporting date: %{customdata[0]}</b><br>"
                    "%{customdata[1]} species reported<br>"
                    "%{customdata[2]} observations<extra></extra>"
                ),
                colorbar=dict(
                    title=dict(
                        text="Species",
                        side="right",
                        font=dict(size=10, color=c["muted"]),
                    ),
                    thickness=10,
                    len=min(0.82, 0.28 * len(years) + 0.28),
                    tickfont=dict(size=10, color=c["muted"]),
                    outlinewidth=0,
                ),
            ),
            row=row_num,
            col=1,
        )

        for record in year_data.itertuples(index=False):
            date = pd.Timestamp(record.night)
            week = int((date - grid_start).days // 7)
            species_count = int(record.species_count)
            text_color = (
                "#0d221c"
                if species_count / scale_max >= 0.62
                else "#f7fbf9"
            )
            annotations.append(dict(
                x=week,
                y=date.weekday(),
                text=f"<b>{species_count}</b>",
                showarrow=False,
                font=dict(
                    family=FONT,
                    size=8 if species_count >= 100 else 9,
                    color=text_color,
                ),
                **axis_refs,
            ))

        month_starts = [
            pd.Timestamp(year=int(year), month=month, day=1)
            for month in range(1, 13)
        ]
        month_weeks = [
            int((date - grid_start).days // 7) for date in month_starts
        ]
        fig.update_xaxes(
            tickmode="array",
            tickvals=month_weeks,
            ticktext=MONTHS,
            side="top",
            ticks="",
            showline=False,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            range=[-3.6, week_count - 0.5],
            tickfont=dict(size=10, color=c["muted"]),
            row=row_num,
            col=1,
        )
        fig.update_yaxes(
            tickmode="array",
            tickvals=[0, 2, 4, 6],
            ticktext=["Mon", "Wed", "Fri", "Sun"],
            autorange="reversed",
            ticks="",
            showline=False,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            tickfont=dict(size=9, color=c["muted"]),
            row=row_num,
            col=1,
        )
        annotations.append(dict(
            x=-2.0,
            y=3,
            text=f"<b>{year}</b>",
            showarrow=False,
            font=dict(family=FONT, size=11, color=c["ink"]),
            **axis_refs,
        ))

    fig.update_layout(
        annotations=annotations,
        height=155 * len(years) + 70,
        showlegend=False,
        font=dict(family=FONT, size=12, color=c["ink"]),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=4, r=58, t=22, b=6),
        hoverlabel=dict(
            font=dict(family=FONT, size=12, color=c["hover_fg"]),
            bgcolor=c["hover_bg"],
            bordercolor=c["hover_border"],
        ),
    )

    peak = data.loc[data["species_count"].idxmax()]
    peak_date = pd.Timestamp(peak["night"])
    date_range = (
        f"{data.iloc[0]['night']:%B} {data.iloc[0]['night'].day}, "
        f"{data.iloc[0]['night'].year} through "
        f"{data.iloc[-1]['night']:%B} {data.iloc[-1]['night'].day}, "
        f"{data.iloc[-1]['night'].year}"
    )
    accessible_summary = (
        f"Calendar heatmap of {len(data)} Kingfisher Hollow moth-reporting "
        f"nights from {date_range}. The highest nightly total is "
        f"{int(peak['species_count'])} species on {peak_date:%B} "
        f"{peak_date.day}, {peak_date.year}. Blank dates have no moth report "
        "and do not mean zero species."
    )

    table_rows = []
    for record in data.sort_values("night", ascending=False).itertuples(index=False):
        date = pd.Timestamp(record.night)
        table_rows.append(
            "<tr class='border-t border-white/10'>"
            f"<th scope='row' class='py-2 pr-5 text-left font-normal text-white/70'>"
            f"{date:%b} {date.day}, {date.year}</th>"
            f"<td class='py-2 px-4 text-right text-white tabular-nums'>"
            f"{int(record.species_count)}</td>"
            f"<td class='py-2 pl-4 text-right text-white/70 tabular-nums'>"
            f"{int(record.observation_count)}</td>"
            "</tr>"
        )

    plot_html = _html(fig)
    return (
        "<figure aria-labelledby='moth-night-calendar-summary'>"
        f"<figcaption id='moth-night-calendar-summary' class='sr-only'>"
        f"{accessible_summary}</figcaption>"
        "<p class='mb-2 text-right text-xs text-white/40 md:hidden'>"
        "Swipe sideways for the full year →</p>"
        "<div class='overflow-x-auto pb-2'>"
        f"<div class='min-w-[52rem]'>{plot_html}</div>"
        "</div>"
        "</figure>"
        "<details class='mt-4 border-t border-white/10 pt-4'>"
        "<summary class='cursor-pointer text-sm font-medium text-hollow-300 "
        "focus-visible:outline-none focus-visible:ring-2 "
        "focus-visible:ring-hollow-300 focus-visible:ring-offset-2 "
        "focus-visible:ring-offset-hollow-950'>"
        f"Night-by-night data ({len(data)} reporting nights)</summary>"
        "<p class='mt-3 text-pretty text-xs leading-5 text-white/50'>"
        "Counts are distinct moth species assigned to the evening session; "
        "records before noon count toward the previous night. A missing date "
        "means no moth report, not a zero-species survey.</p>"
        "<div class='mt-3 max-h-80 overflow-auto'>"
        "<table class='w-full text-sm'>"
        "<thead class='text-white/40'>"
        "<tr><th scope='col' class='pb-2 pr-5 text-left font-medium'>Night</th>"
        "<th scope='col' class='pb-2 px-4 text-right font-medium'>Species</th>"
        "<th scope='col' class='pb-2 pl-4 text-right font-medium'>Observations</th>"
        "</tr></thead>"
        f"<tbody>{''.join(table_rows)}</tbody>"
        "</table></div></details>"
    )
