"""Reusable Plotly/Dash chart components."""

import pandas as pd
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html

# Brand colours
_C1 = "#10B981"   # Scope 1 / Emerald
_C2 = "#6366F1"   # Scope 2 / Indigo
_C3 = "#F97316"   # Scope 3 / Warm Orange
_C2_RGBA_15 = "rgba(99,102,241,0.15)"

_SCENARIO_COLOURS = {
    "BAU":      "#64748B",
    "SBTi":     "#10B981",
    "Net Zero": "#6366F1",
}

_LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Plus Jakarta Sans, Outfit, Inter, sans-serif", size=13),
    margin=dict(l=48, r=16, t=32, b=48),
    hovermode="x unified",
)


def scope_breakdown_chart(df: pd.DataFrame) -> go.Figure:
    """
    Stacked bar chart of Scope 1/2/3 emissions per year.

    Input df cols: year, scope1_tco2e, scope2_tco2e, scope3_tco2e.
    """
    fig = go.Figure()
    for name, col, colour in [
        ("Scope 1", "scope1_tco2e", _C1),
        ("Scope 2", "scope2_tco2e", _C2),
        ("Scope 3", "scope3_tco2e", _C3),
    ]:
        if col in df.columns:
            fig.add_trace(go.Bar(
                name=name,
                x=df["year"],
                y=df[col],
                marker_color=colour,
                hovertemplate=f"{name}: %{{y:,.0f}} tCO₂e<extra></extra>",
            ))

    fig.update_layout(
        barmode="stack",
        title=dict(
            text="Scope 1–3 Emissions Breakdown<br><sup>Annual greenhouse gas emissions by category (tCO₂e)</sup>",
            font=dict(family="Outfit, sans-serif", size=20, color="#0f172a"),
            pad=dict(b=4),
        ),
        yaxis_title="tCO₂e",
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)"),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=-0.32,
            xanchor="center", x=0.5,
        ),
        margin=dict(l=48, r=16, t=76, b=52),
        **{k: v for k, v in _LAYOUT_BASE.items() if k != "margin"},
    )
    return fig


def forecast_chart(
    historic: pd.DataFrame,
    forecast: pd.DataFrame,
    baseline: pd.DataFrame | None = None
) -> go.Figure:
    """
    Line chart: historic actuals (solid) + forecast yhat (dashed) + 90 % CI band + baseline.

    historic cols : date (datetime64), emissions_tco2e (float).
    forecast cols : date (datetime64), yhat, yhat_lower, yhat_upper (float).
    """
    fig = go.Figure()

    # Confidence band — drawn first so lines render on top
    fc_dates   = list(forecast["date"])
    fc_upper   = list(forecast["yhat_upper"])
    fc_lower   = list(forecast["yhat_lower"])
    x_band = fc_dates + fc_dates[::-1]
    y_band = fc_upper + fc_lower[::-1]

    fig.add_trace(go.Scatter(
        x=x_band, y=y_band,
        fill="toself",
        fillcolor=_C2_RGBA_15,
        line=dict(color="rgba(0,0,0,0)"),
        name="90% CI",
        showlegend=True,
        hoverinfo="skip",
    ))

    # Linear baseline
    if baseline is not None and not baseline.empty:
        fig.add_trace(go.Scatter(
            x=baseline["date"],
            y=baseline["yhat_lr"],
            mode="lines",
            name="Linear baseline",
            line=dict(color="#888780", width=1, dash="dot"),
            hovertemplate="Linear Baseline: %{y:,.0f} tCO₂e<extra></extra>",
        ))

    # Forecast yhat
    fig.add_trace(go.Scatter(
        x=forecast["date"],
        y=forecast["yhat"],
        mode="lines",
        name="Forecast",
        line=dict(color=_C2, width=2, dash="dash"),
        hovertemplate="Forecast: %{y:,.0f} tCO₂e<extra></extra>",
    ))

    # Historic actuals
    fig.add_trace(go.Scatter(
        x=historic["date"],
        y=historic["emissions_tco2e"],
        mode="lines+markers",
        name="Actuals",
        line=dict(color=_C1, width=2),
        marker=dict(size=5),
        hovertemplate="Actual: %{y:,.0f} tCO₂e<extra></extra>",
    ))

    # Vertical line at last historic date
    if not historic.empty:
        last_date = pd.to_datetime(historic["date"]).max()
        x_str = last_date.strftime("%Y-%m-%d")
        fig.add_shape(
            type="line",
            x0=x_str, x1=x_str,
            y0=0, y1=1, yref="paper",
            line=dict(dash="dash", color="rgba(0,0,0,0.25)", width=1),
        )
        fig.add_annotation(
            x=x_str, y=0.98, yref="paper",
            text="Forecast →",
            showarrow=False,
            font=dict(size=11, color="rgba(0,0,0,0.45)"),
            xanchor="left",
        )

    fig.update_layout(
        title=dict(
            text="Emissions Forecast<br><sup>Historic actuals + projection with 90% confidence interval</sup>",
            font=dict(family="Outfit, sans-serif", size=20, color="#0f172a"),
            pad=dict(b=4),
        ),
        yaxis_title="tCO₂e",
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.32, xanchor="center", x=0.5),
        margin=dict(l=48, r=16, t=76, b=52),
        **{k: v for k, v in _LAYOUT_BASE.items() if k != "margin"},
    )
    return fig


def scenario_chart(scenarios_df: pd.DataFrame) -> go.Figure:
    """
    Multi-line scenario comparison: BAU / SBTi / Net Zero.

    Input: pd.concat of scenario outputs, cols [year, emissions_tco2e, scenario].
    """
    fig = go.Figure()

    # Add BAU uncertainty band if columns exist
    if "bau_lower" in scenarios_df.columns and "bau_upper" in scenarios_df.columns:
        bau_df = scenarios_df[scenarios_df["scenario"] == "BAU"].sort_values("year")
        if not bau_df.empty:
            fig.add_trace(go.Scatter(
                x=bau_df["year"],
                y=bau_df["bau_upper"],
                fill=None,
                mode="lines",
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip"
            ))
            fig.add_trace(go.Scatter(
                x=bau_df["year"],
                y=bau_df["bau_lower"],
                fill="tonexty",
                mode="lines",
                line=dict(width=0),
                name="BAU uncertainty",
                fillcolor="rgba(136,135,128,0.15)",
                hoverinfo="skip"
            ))

    for scenario in scenarios_df["scenario"].unique():
        subset = scenarios_df[scenarios_df["scenario"] == scenario].sort_values("year")
        colour = _SCENARIO_COLOURS.get(scenario, "#888780")
        fig.add_trace(go.Scatter(
            x=subset["year"],
            y=subset["emissions_tco2e"],
            mode="lines+markers",
            name=scenario,
            line=dict(color=colour, width=2),
            marker=dict(size=5),
            hovertemplate=f"{scenario}: %{{y:,.0f}} tCO₂e<extra></extra>",
        ))

    fig.update_layout(
        title=dict(
            text=(
                "Reduction Pathway Scenarios<br>"
                "<sup>BAU = business as usual trend  ·  "
                "SBTi = Science Based Targets (–4.2%/yr)  ·  "
                "Net Zero = linear decline to zero</sup>"
            ),
            font=dict(family="Outfit, sans-serif", size=20, color="#0f172a"),
            pad=dict(b=4),
        ),
        yaxis_title="tCO₂e",
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)"),
        legend=dict(
            orientation="v",
            yanchor="middle", y=0.5,
            xanchor="left", x=1.02,
        ),
        margin=dict(l=48, r=16, t=76, b=52),
        **{k: v for k, v in _LAYOUT_BASE.items() if k != "margin"},
    )
    return fig


def kpi_card(
    title: str,
    value: str,
    unit: str,
    delta: float | None = None,
    description: str | None = None,
) -> dbc.Card:
    """
    Compact KPI card with optional percentage-change badge and description.

    delta > 0 renders a green badge; delta < 0 renders a red badge.
    description renders a muted helper paragraph below the value.
    """
    body: list = [
        html.P(title, className="kpi-label"),
        html.Div(
            [
                html.Span(value, className="kpi-value"),
                html.Span(unit,  className="kpi-unit"),
            ],
            className="my-1",
        ),
    ]
    if delta is not None:
        arrow = "▲" if delta > 0 else "▼"
        badge_colour = "danger" if delta > 0 else "success"
        body.append(
            dbc.Badge(
                f"{arrow} {abs(delta):.1f}%",
                color=badge_colour,
                className="mt-1",
            )
        )
    if description is not None:
        body.append(
            html.P(description, className="kpi-description")
        )
    return dbc.Card(dbc.CardBody(body, className="p-2"), className="kpi-card")
