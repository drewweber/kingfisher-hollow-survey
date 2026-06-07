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


def _style(fig, height=420, showlegend=False):
    """Apply the shared editorial treatment to a figure."""
    fig.update_layout(
        height=height,
        showlegend=showlegend,
        font=dict(family=FONT, size=13, color=INK),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=12, r=18, t=14, b=12),
        hoverlabel=dict(font=dict(family=FONT, size=12),
                        bgcolor="white", bordercolor=GRID),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    x=0, font=dict(size=12), bgcolor="rgba(0,0,0,0)"),
        title=None,
    )
    fig.update_xaxes(showgrid=False, zeroline=False,
                     linecolor=GRID, ticks="outside", tickcolor=GRID,
                     tickfont=dict(color=MUTED, size=11))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False,
                     tickfont=dict(color=MUTED, size=11))
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
def phenology(matrix):
    if matrix.empty:
        return "<p class='chart-empty'>No phenology data.</p>"
    fig = go.Figure(go.Heatmap(
        z=matrix.values, x=MONTHS, y=matrix.index.tolist(),
        colorscale=GREEN_SCALE, showscale=True,
        colorbar=dict(title="", thickness=10, len=0.6, outlinewidth=0),
        hovertemplate="%{y}<br>%{x}: %{z} obs<extra></extra>",
        xgap=2, ygap=2,
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(side="top")
    return _html(_style(fig, height=max(420, 19 * len(matrix))))


# --- seasonal cascade (when each species appears) ---------------------------
def seasonal_cascade(agg, group_label="Birds"):
    """Horizontal range plot: faint first→last line, q1–q3 bar, median dot —
    species ordered by median appearance so it reads as a seasonal wave."""
    if agg.empty:
        return "<p class='chart-empty'>Not enough data for a seasonal view.</p>"
    fig = go.Figure()
    y = agg["label"].tolist()
    # full span (faint)
    for _, r in agg.iterrows():
        fig.add_scatter(
            x=[r["first_doy"], r["last_doy"]], y=[r["label"], r["label"]],
            mode="lines", line=dict(color="rgba(94,171,141,0.35)", width=2),
            hoverinfo="skip", showlegend=False,
        )
    # interquartile band
    for _, r in agg.iterrows():
        fig.add_scatter(
            x=[r["q1"], r["q3"]], y=[r["label"], r["label"]],
            mode="lines", line=dict(color=HOLLOW[1], width=7),
            hoverinfo="skip", showlegend=False,
        )
    # median marker
    fig.add_scatter(
        x=agg["median_doy"], y=y, mode="markers",
        marker=dict(color=HOLLOW[3], size=9,
                    line=dict(color="white", width=1.5)),
        hovertemplate="<b>%{y}</b><br>typically around day %{x:.0f}<extra></extra>",
        showlegend=False,
    )
    fig.update_xaxes(tickvals=MONTH_STARTS, ticktext=MONTHS,
                     range=[1, 366], showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return _html(_style(fig, height=max(360, 22 * len(agg))))


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
def obs_map(df):
    pts = df.dropna(subset=["latitude", "longitude"])
    if pts.empty:
        return "<p class='chart-empty'>No mappable (un-obscured) observations.</p>"
    groups = pts["iconic_taxon"].fillna("Other").unique()
    palette = {g: (ACCENT if g == "Aves" else HOLLOW[i % len(HOLLOW)])
               for i, g in enumerate(groups)}
    fig = go.Figure()
    for g in groups:
        sub = pts[pts["iconic_taxon"].fillna("Other") == g]
        fig.add_scattermap(
            lat=sub["latitude"], lon=sub["longitude"], mode="markers",
            marker=dict(size=7, color=palette[g]), name=g,
            text=sub["common_name"].fillna(sub["taxon_name"]),
            hovertemplate="<b>%{text}</b><extra>" + g + "</extra>",
        )
    fig.update_layout(
        map=dict(style="carto-positron",
                 center=dict(lat=pts["latitude"].mean(),
                             lon=pts["longitude"].mean()),
                 zoom=13.5),
        height=560, margin=dict(l=0, r=0, t=0, b=0),
        showlegend=True, font=dict(family=FONT, color=INK),
        legend=dict(bgcolor="rgba(255,255,255,0.85)", x=0.01, y=0.99,
                    bordercolor=GRID, borderwidth=1),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return _html(fig)
