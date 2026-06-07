"""Plotly figures rendered to standalone HTML fragments. plotly.js is loaded
once (via CDN) by report.py, so every fragment here uses include_plotlyjs=False."""

import plotly.express as px
import plotly.graph_objects as go

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _html(fig):
    return fig.to_html(full_html=False, include_plotlyjs=False)


def accumulation(acc):
    fig = px.line(
        acc, x="observed_on", y="cumulative_species",
        title="Species accumulation curve",
        labels={"observed_on": "Date", "cumulative_species": "Cumulative species"},
    )
    fig.update_traces(line_shape="hv")
    return _html(fig)


def per_day(daily):
    fig = go.Figure()
    fig.add_bar(x=daily["observed_on"], y=daily["observations"],
                name="Observations", marker_color="#7cb342")
    fig.add_scatter(x=daily["observed_on"], y=daily["rolling_30d"],
                    name="30-day average", line=dict(color="#1b5e20", width=2))
    fig.update_layout(title="Observations per day",
                      xaxis_title="Date", yaxis_title="Observations")
    return _html(fig)


def taxa_breakdown(df):
    sub = df.dropna(subset=["iconic_taxon"]).copy()
    sub["count"] = 1
    fig = px.sunburst(
        sub, path=["iconic_taxon", "quality_grade"], values="count",
        title="Observations by taxon group and quality grade",
    )
    return _html(fig)


def phenology(matrix, title="Phenology (observations by month)"):
    if matrix.empty:
        return "<p><em>No phenology data.</em></p>"
    fig = go.Figure(go.Heatmap(
        z=matrix.values,
        x=MONTHS,
        y=matrix.index.tolist(),
        colorscale="YlGn",
        colorbar=dict(title="Obs"),
    ))
    fig.update_layout(title=title, height=max(400, 18 * len(matrix)),
                      yaxis=dict(autorange="reversed"))
    return _html(fig)


def uniqueness_scatter(stats):
    if stats.empty:
        return "<p><em>No uniqueness stats yet.</em></p>"
    s = stats.copy()
    s["label"] = s["common_name"].fillna(s["taxon_name"])
    s["County first"] = s["is_county_first"].map({1: "Yes", 0: "No"})
    fig = px.scatter(
        s, x="state_obs_count", y="property_obs_count",
        color="County first", hover_name="label",
        hover_data={"county_obs_count": True, "state_obs_count": True},
        log_x=True,
        color_discrete_map={"Yes": "#d81b60", "No": "#90a4ae"},
        title="Contribution uniqueness — rarer in NY is further left",
        labels={"state_obs_count": "Observations in NY (log)",
                "property_obs_count": "Your observations on the property"},
    )
    return _html(fig)


def leaderboard(board):
    fig = px.bar(
        board.head(20), x="observations", y="user_login", orientation="h",
        hover_data=["species", "unique_species", "display_name"],
        title="Observer leaderboard",
        labels={"observations": "Observations", "user_login": "Observer"},
    )
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return _html(fig)


def obs_map(df):
    pts = df.dropna(subset=["latitude", "longitude"])
    if pts.empty:
        return "<p><em>No mappable (un-obscured) observations.</em></p>"
    fig = px.scatter_map(
        pts, lat="latitude", lon="longitude", color="iconic_taxon",
        hover_name="common_name",
        hover_data={"taxon_name": True, "observed_on": True,
                    "latitude": False, "longitude": False},
        zoom=13, height=600, title="Property observations",
    )
    fig.update_layout(map_style="open-street-map",
                      margin=dict(l=0, r=0, t=40, b=0))
    return _html(fig)
