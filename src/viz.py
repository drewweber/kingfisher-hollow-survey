"""Editorial Plotly figures themed to the Kingfisher Hollow palette.

The look aims for printed-infographic restraint: light horizontal rules instead
of full grids, transparent backgrounds so charts sit on the page, a green family
with a single terracotta accent for "look here" moments, and labels on the chart
rather than in legends. plotly.js loads once from the page, so every fragment
uses include_plotlyjs=False.
"""

import plotly.graph_objects as go

# --- palette (mirrors the site's `hollow` Tailwind scale) -------------------
HOLLOW = ["#2e735c", "#5eab8d", "#8ec8b1", "#265d4b", "#bbdfd0", "#1d3d33"]
ACCENT = "#c2703d"          # terracotta — highlights (county firsts, rarities)
INK = "#1d3d33"             # hollow-900, primary text
MUTED = "#6b7d74"           # secondary text
GRID = "rgba(29,61,51,0.08)"
GREEN_SCALE = [[0.0, "#f0f7f4"], [0.5, "#5eab8d"], [1.0, "#1d3d33"]]

FONT = "Inter, system-ui, sans-serif"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]

# Dark-mode equivalents for the moth view (charts sit on bg-hollow-950).
DARK_INK = "#e8f0ec"
DARK_MUTED = "#9bb3a8"
DARK_GRID = "rgba(255,255,255,0.10)"
# On dark, line/marker colors need to be light tints to read.
DARK_LINE = "#8ec8b1"       # hollow-300
DARK_LINE2 = "#5eab8d"      # hollow-400
DARK_GREEN_SCALE = [[0.0, "#13322a"], [0.5, "#3d8f72"], [1.0, "#bbdfd0"]]


def _palette(dark):
    """Text / grid / line colors for the active theme."""
    if dark:
        return dict(ink=DARK_INK, muted=DARK_MUTED, grid=DARK_GRID,
                    line=DARK_LINE, line2=DARK_LINE2,
                    hover_bg="#214a3d", hover_fg="#f0f7f4", hover_border="#5eab8d",
                    green_scale=DARK_GREEN_SCALE)
    return dict(ink=INK, muted=MUTED, grid=GRID,
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
    return fig.to_html(full_html=False, include_plotlyjs=False, config=config)


# --- cumulative discovery (species accumulation, annotated) -----------------
def discovery_curve(firsts):
    """Cumulative species over time as a filled area, with milestone callouts —
    the property's discovery story. `firsts` has observed_on + cumulative."""
    if firsts.empty:
        return "<p class='chart-empty'>No data yet.</p>"
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
    return _html(_style(fig, height=440))


# --- observations per day ---------------------------------------------------
def per_day(daily):
    if daily.empty:
        return "<p class='chart-empty'>No data yet.</p>"
    fig = go.Figure()
    fig.add_bar(x=daily["observed_on"], y=daily["observations"],
                marker_color="rgba(94,171,141,0.45)",
                hovertemplate="%{x|%b %e, %Y}<br>%{y} obs<extra></extra>",
                name="Observations")
    fig.add_scatter(x=daily["observed_on"], y=daily["rolling_30d"],
                    mode="lines", line=dict(color=HOLLOW[3], width=2.5),
                    hoverinfo="skip", name="30-day average")
    return _html(_style(fig, height=340))


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
    return _html(_style(fig, height=max(260, 30 * len(counts))))


# --- phenology heatmap ------------------------------------------------------
def phenology(matrix, dark=False, normalize=False):
    """Species × month heatmap. With normalize=True each row is scaled to its own
    peak month, so a rare species' timing reads as clearly as a common one's
    (raw counts stay in the hover)."""
    if matrix.empty:
        return "<p class='chart-empty'>No phenology data.</p>"
    raw = matrix.values
    if normalize:
        row_max = matrix.max(axis=1).replace(0, 1)
        z = matrix.div(row_max, axis=0).values
        cbar_title = "share of<br>peak month"
    else:
        z = raw
        cbar_title = ""
    fig = go.Figure(go.Heatmap(
        z=z, x=MONTHS, y=matrix.index.tolist(),
        customdata=raw,
        colorscale=_palette(dark)["green_scale"], showscale=True,
        colorbar=dict(title=dict(text=cbar_title, font=dict(size=10)),
                      thickness=10, len=0.6, outlinewidth=0),
        hovertemplate="%{y}<br>%{x}: %{customdata} obs<extra></extra>",
        xgap=2, ygap=2,
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(side="top")
    return _html(_style(fig, height=max(420, 19 * len(matrix)), dark=dark))


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
        hovertemplate="<b>%{y}</b><br>typically around day %{x:.0f}<extra></extra>",
        showlegend=False,
    )
    fig.update_xaxes(tickvals=MONTH_STARTS, ticktext=MONTHS,
                     range=[1, 366], showgrid=True, gridcolor=c["grid"])
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return _html(_style(fig, height=max(360, 22 * len(agg)), dark=dark))


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
                       font=dict(size=11, color=ACCENT))
    standouts = (s[s["state_obs_count"] <= 25]
                 .sort_values("property_obs_count", ascending=False).head(4))
    if not standouts.empty:
        fig.add_scatter(
            x=standouts["state_obs_count"], y=standouts["property_obs_count"],
            mode="text", text=standouts["label"], textposition="middle right",
            textfont=dict(size=10, color=INK), hoverinfo="skip", showlegend=False)
    fig.update_xaxes(type="log", title=dict(
        text="Observations in New York (log scale) →", font=dict(size=11, color=MUTED)))
    fig.update_yaxes(title=dict(
        text="Your observations here", font=dict(size=11, color=MUTED)))
    return _html(_style(fig, height=460, showlegend=True))


# --- observer leaderboard ---------------------------------------------------
def leaderboard(board):
    if board.empty:
        return "<p class='chart-empty'>No observers yet.</p>"
    b = board.head(15).iloc[::-1]
    labels = b["display_name"].fillna(b["user_login"])
    fig = go.Figure(go.Bar(
        x=b["observations"], y=labels, orientation="h",
        marker_color=HOLLOW[1],
        text=b["observations"], textposition="outside",
        textfont=dict(color=INK, size=11),
        customdata=b[["species", "unique_species"]].values,
        hovertemplate="<b>%{y}</b><br>%{x} obs · %{customdata[0]} species"
                      "<br>%{customdata[1]} found only by them<extra></extra>",
    ))
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(showgrid=False)
    return _html(_style(fig, height=max(320, 26 * len(b))))


# --- map --------------------------------------------------------------------
def obs_map(df, dark=False):
    pts = df.dropna(subset=["latitude", "longitude"])
    if pts.empty:
        return "<p class='chart-empty'>No mappable (un-obscured) observations.</p>"
    groups = pts["iconic_taxon"].fillna("Other").unique()
    palette = {g: (ACCENT if g == "Aves" else HOLLOW[i % len(HOLLOW)])
               for i, g in enumerate(groups)}
    fig = go.Figure()
    for g in groups:
        sub = pts[pts["iconic_taxon"].fillna("Other") == g]
        # scattermapbox/mapbox (Plotly.js 2.x) — the page pins plotly 2.35.2,
        # which doesn't understand the newer scattermap/map (MapLibre) trace.
        fig.add_scattermapbox(
            lat=sub["latitude"], lon=sub["longitude"], mode="markers",
            marker=dict(size=7, color=palette[g]), name=g,
            text=sub["common_name"].fillna(sub["taxon_name"]),
            hovertemplate="<b>%{text}</b><extra>" + g + "</extra>",
        )
    legend_bg = "rgba(13,34,28,0.85)" if dark else "rgba(255,255,255,0.85)"
    fig.update_layout(
        mapbox=dict(style="carto-darkmatter" if dark else "carto-positron",
                    center=dict(lat=pts["latitude"].mean(),
                                lon=pts["longitude"].mean()),
                    zoom=13.5),
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
        font=dict(size=12, color=ACCENT))
    fig.update_xaxes(title=dict(text="Cumulative moth observations →",
                                font=dict(size=11, color=c["muted"])))
    fig.update_yaxes(title=dict(text="Moth species",
                                font=dict(size=11, color=c["muted"])))
    return _html(_style(fig, height=400, dark=dark))


def family_breakdown(fam, dark=True):
    """Per-family progress: a faint full bar = species known from the county, a
    solid bar = species recorded here. Shows which moth families are near-complete
    and which (the micros) are barely sampled."""
    if fam.empty:
        return "<p class='chart-empty'>Not enough family data yet.</p>"
    c = _palette(dark)
    f = fam.iloc[::-1]   # largest family on top
    labels = [f"{lbl} ({r}/{t})" for lbl, r, t in
              zip(f["label"], f["recorded"], f["county_total"])]
    fig = go.Figure()
    fig.add_bar(y=labels, x=f["county_total"], orientation="h",
                marker_color="rgba(142,200,177,0.20)", name="Known in county",
                hovertemplate="%{y}<br>%{x} county species<extra></extra>")
    fig.add_bar(y=labels, x=f["recorded"], orientation="h",
                marker_color=c["line2"], name="Recorded here",
                hovertemplate="%{y}<br>%{x} recorded here<extra></extra>")
    fig.update_layout(barmode="overlay", bargap=0.35)
    fig.update_xaxes(title=dict(text="Species →", font=dict(size=11, color=c["muted"])))
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11, color=c["ink"]))
    return _html(_style(fig, height=max(380, 32 * len(f)), showlegend=True, dark=dark))


def rank_abundance(counts, dark=True):
    """Whittaker rank-abundance: species ranked by observation count (log y).
    The once/twice-seen tail is highlighted — the long flat tail of barely-
    recorded species is the 'unfinished edge' of the inventory."""
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
                    name="seen 3+ times")
    fig.add_scatter(x=x, y=tail, mode="markers",
                    marker=dict(color=ACCENT, size=5),
                    hovertemplate="rank %{x}: %{y} observation(s)<extra></extra>",
                    name="seen once/twice")
    fig.add_hline(y=1, line=dict(color=c["grid"], width=1))
    if singletons:
        fig.add_annotation(
            x=n, y=1, xanchor="right", yanchor="bottom",
            text=f"<b>{singletons}</b> recorded once · <b>{doubletons}</b> twice",
            showarrow=False, font=dict(size=11, color=ACCENT))
    fig.update_yaxes(type="log", title=dict(text="Observations (log) →",
                     font=dict(size=11, color=c["muted"])))
    fig.update_xaxes(title=dict(text="Species rank (most → least recorded)",
                     font=dict(size=11, color=c["muted"])))
    return _html(_style(fig, height=360, dark=dark))
