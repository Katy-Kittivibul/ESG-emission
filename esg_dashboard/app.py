import base64
import io
import sys
import os

import dash
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
from dash import Input, Output, State, dcc, html, callback

# Ensure esg_dashboard/ is on sys.path so sibling packages resolve
sys.path.insert(0, os.path.dirname(__file__))

from analytics.forecasting import train_forecast
from analytics.scenarios  import bau_scenario, sbti_scenario, net_zero_scenario
from analytics.risk_metrics import carbon_price_exposure, tcfd_alignment_score
from components.charts import (
    scope_breakdown_chart,
    forecast_chart,
    scenario_chart,
    kpi_card,
)
from data.data_fetcher import fetch_ons_data, fetch_epa_emissions
from data.emissions_calc import calc_sector_benchmark

# ---------------------------------------------------------------------------
# App init
# ---------------------------------------------------------------------------

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True,
)
app.title = "ESG Carbon Analytics"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_demo_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (scope_totals, emissions_df) using synthetic 2015-2024 data."""
    np.random.seed(42)
    dates = pd.date_range("2015", periods=10, freq="YE")
    years = [d.year for d in dates]

    s1 = np.linspace(5_000, 3_500, 10) + np.random.normal(0,  50, 10)
    s2 = np.linspace(3_000, 2_000, 10) + np.random.normal(0,  30, 10)
    s3 = np.linspace(8_000, 6_000, 10) + np.random.normal(0,  80, 10)

    scope_totals = pd.DataFrame({
        "year":         years,
        "scope1_tco2e": s1,
        "scope2_tco2e": s2,
        "scope3_tco2e": s3,
        "total_tco2e":  s1 + s2 + s3,
    })
    emissions_df = pd.DataFrame({
        "date":           dates,
        "emissions_tco2e": s1 + s2 + s3,
    })
    return scope_totals, emissions_df


def _parse_upload(contents: str, filename: str) -> pd.DataFrame | None:
    """Decode a dcc.Upload content string into a DataFrame."""
    try:
        _, content_string = contents.split(",", 1)
        decoded = base64.b64decode(content_string)
        if filename.endswith(".csv"):
            return pd.read_csv(io.StringIO(decoded.decode("utf-8")))
        elif filename.endswith((".xls", ".xlsx")):
            return pd.read_excel(io.BytesIO(decoded))
    except Exception:
        pass
    return None


def _load_eleccons_data() -> tuple[pd.DataFrame | None, pd.DataFrame | None, str]:
    """
    Fetch ONS ELECCONS (UK electricity consumption, kWh/capita) and normalise to
    company-scale tCO₂e so it feeds the dashboard charts.

    Returns:
        scope_totals  – DataFrame with year/scope1–3/total columns, or None on failure
        emissions_df  – DataFrame with date/emissions_tco2e columns, or None on failure
        source_label  – human-readable description of the data source used
    """
    try:
        raw = fetch_ons_data("ELECCONS")
        if raw.empty:
            return None, None, "ELECCONS fetch returned empty"

        # Filter to 2015 onwards so we match the synthetic data window
        raw = raw[raw["date"].dt.year >= 2015].copy()
        if len(raw) < 2:
            return None, None, "ELECCONS: fewer than 2 years after 2015"

        # Normalise kWh/capita values to company-scale tCO₂e
        # UK ELECCONS ≈ 4,200–5,200 kWh/capita → scale to ~14,000 tCO₂e midpoint
        midpoint_target = 14_000.0
        scale = midpoint_target / raw["value"].mean()
        total = raw["value"] * scale

        years = raw["date"].dt.year.values
        # Split total into approximate GHG Protocol scope fractions
        s1 = total * 0.30   # direct energy / combustion
        s2 = total * 0.20   # purchased electricity
        s3 = total * 0.50   # supply chain / value chain

        scope_totals = pd.DataFrame({
            "year":         years,
            "scope1_tco2e": s1.values,
            "scope2_tco2e": s2.values,
            "scope3_tco2e": s3.values,
            "total_tco2e":  total.values,
        })
        emissions_df = pd.DataFrame({
            "date":            raw["date"].values,
            "emissions_tco2e": total.values,
        })

        n = len(raw)
        label = f"ONS ELECCONS — {n} years ({years[0]}–{years[-1]}) via World Bank"
        return scope_totals, emissions_df, label

    except Exception as exc:
        return None, None, f"ELECCONS error: {exc}"


def _exposure_card_body(exposure: dict) -> list:
    projection_rows = [
        html.Tr([
            html.Td(str(r["year"])),
            html.Td(f"£{r['carbon_price_gbp']:,.0f}"),
            html.Td(f"£{r['exposure_gbp']:,.0f}"),
        ])
        for r in exposure["five_year_projection"]
    ]
    return dbc.CardBody([
        html.H6("Carbon Price Exposure", className="card-title"),
        html.P(
            "Your company's estimated financial liability if a carbon price were applied to all "
            "reported emissions today. Based on the carbon price set in the sidebar.",
            className="card-description",
        ),
        html.H4(f"£{exposure['current_exposure_gbp']:,.0f}", className="detail-value text-danger mt-2"),
        html.Div(
            f"{exposure['total_tco2e']:,.0f} tCO₂e × £{exposure['carbon_price_gbp']}/t",
            className="detail-sublabel",
        ),
        html.Hr(className="my-3"),
        html.P(
            "5-year forward projection assuming a 10% annual carbon price increase "
            "(consistent with UK ETS trajectory modelling).",
            className="detail-section-label",
        ),
        dbc.Table(
            [
                html.Thead(html.Tr([
                    html.Th("Year", className="small"),
                    html.Th("Carbon £/t", className="small"),
                    html.Th("Exposure", className="small"),
                ])),
                html.Tbody(projection_rows),
            ],
            size="sm",
            bordered=False,
            striped=True,
            hover=True,
            className="mb-0",
        ),
    ])


def _tcfd_card_body(score: dict) -> list:
    pillars = score["pillars"]
    rating_colour = {"Leading": "success", "Developing": "warning", "Nascent": "danger"}
    colour = rating_colour.get(score["rating"], "secondary")

    def _pillar_colour(v: int) -> str:
        if v >= 20:
            return "success"
        if v >= 12:
            return "warning"
        return "danger"

    pillar_bars = [
        html.Div([
            html.Div([
                html.Span(k.replace("_", " ").title(), className="progress-label"),
                html.Span(f"{v}/25", className="progress-score float-end"),
            ], className="d-flex justify-content-between mb-1"),
            dbc.Progress(
                value=round(v / 25 * 100),
                color=_pillar_colour(v),
                style={"height": "6px"},
                className="mb-2",
            ),
        ])
        for k, v in pillars.items()
    ]

    return dbc.CardBody([
        html.H6("TCFD Alignment Score", className="card-title"),
        html.P(
            "Measures disclosure quality across the four TCFD pillars: Governance, Strategy, "
            "Risk Management, and Metrics & Targets. Scores reflect the inputs provided to the "
            "analytics engine.",
            className="card-description",
        ),
        html.Div([
            html.H3(f"{score['total_score']}/100", className="tcfd-total d-inline me-2"),
            dbc.Badge(score["rating"], color=colour, className="align-middle fs-6"),
        ], className="mt-2 mb-1"),
        html.Hr(className="my-3"),
        html.P("Pillar breakdown", className="detail-section-label"),
        *pillar_bars,
    ])


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

_CONTROLS = dbc.Card(
    dbc.CardBody([
        html.H5("Data Controls", className="sidebar-title"),
        html.P(
            "Upload your company's actual emissions activity data. "
            "Without an upload, the dashboard runs on synthetic demo data "
            "so you can explore the tool.",
            className="sidebar-intro",
        ),
        dcc.Upload(
            id="upload-data",
            accept=".csv,.xlsx",
            children=html.Div(
                ["Upload company data (CSV/XLSX)"],
                className="text-center text-muted small p-2",
                style={"border": "1px dashed #ccc", "borderRadius": "4px", "cursor": "pointer"},
            ),
            style={"width": "100%"},
        ),
        dbc.Accordion(
            dbc.AccordionItem(
                html.Ul([
                    html.Li("CSV or XLSX, one row per year"),
                    html.Li("Required columns: date, emissions_tco2e"),
                    html.Li("Optional: scope (values: Scope 1 / Scope 2 / Scope 3)"),
                    html.Li("Date format: YYYY or YYYY-MM-DD"),
                ], className="small text-muted ps-3 mb-0"),
                title="What format does my file need?",
            ),
            start_collapsed=True,
            className="mt-2 mb-2",
            style={"fontSize": "0.8rem"},
        ),
        html.Hr(),
        html.Span("Carbon price (£/tCO₂e)", className="control-label"),
        html.P(
            "The price your company would pay per tonne of CO₂ equivalent "
            "under a carbon tax or ETS scheme. UK ETS currently ~£35–£50.",
            className="control-description",
        ),
        dcc.Slider(
            id="carbon-price",
            min=10, max=300, step=10, value=50,
            marks={10: "£10", 150: "£150", 300: "£300"},
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        html.Hr(),
        html.Span("Forecast horizon (years)", className="control-label"),
        html.P(
            "How many years ahead to project emissions using the "
            "trend model trained on your historic data.",
            className="control-description",
        ),
        dcc.Slider(
            id="forecast-horizon",
            min=5, max=20, step=5, value=10,
            marks={5: "5", 10: "10", 15: "15", 20: "20"},
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        html.Hr(),
        html.Span("Scenario target year", className="control-label"),
        html.P(
            "The year by which your chosen reduction pathway "
            "(SBTi or Net Zero) reaches its target.",
            className="control-description",
        ),
        dcc.Input(
            id="target-year",
            type="number",
            value=2050, min=2030, max=2100, step=5,
            className="form-control form-control-sm",
        ),
        html.Br(),
        dbc.Button(
            "Run Analysis",
            id="run-btn",
            color="success",
            className="w-100 mt-2",
            n_clicks=0,
        ),
    ]),
    className="h-100 detail-card",
)

_MAIN = dbc.Col([
    # KPI strip
    dbc.Row([
        dbc.Col(id="kpi-scope1", width=3),
        dbc.Col(id="kpi-scope2", width=3),
        dbc.Col(id="kpi-scope3", width=3),
        dbc.Col(id="kpi-tcfd",   width=3),
    ], className="mb-3 g-2"),

    # Chart row 1
    dbc.Row([
        dbc.Col(
            html.Div(
                dcc.Graph(id="scope-chart", config={"displayModeBar": False}, style={"height": "100%"}),
                className="graph-card h-100"
            ),
            width=6,
            className="d-flex flex-column"
        ),
        dbc.Col(
            html.Div(
                [
                    html.Div(id="forecast-reliability", className="forecast-reliability-container"),
                    dcc.Graph(id="forecast-chart", config={"displayModeBar": False}, style={"height": "100%"}),
                ],
                className="graph-card h-100"
            ),
            width=6,
            className="d-flex flex-column"
        ),
    ], className="mb-3 g-3"),

    # Chart row 2 — scenarios full width
    dbc.Row([
        dbc.Col(
            html.Div(
                dcc.Graph(id="scenario-chart", config={"displayModeBar": False}),
                className="graph-card"
            ),
            width=12
        ),
    ], className="mb-3 g-3"),

    # Benchmark card
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardBody([
                    html.H6("UK Sector Benchmark", className="card-title"),
                    html.P(
                        "How your total emissions compare against the UK sector "
                        "reported in EDGAR v8 (latest available year).",
                        className="card-description",
                    ),
                    html.Hr(),
                    html.Div(id="benchmark-content"),
                ])
            ], className="detail-card"),
            width=12
        ),
    ], className="mb-3 g-3"),

    # Detail cards
    dbc.Row([
        dbc.Col(dbc.Card(id="carbon-exposure-card", className="detail-card h-100"), width=6, className="d-flex flex-column"),
        dbc.Col(dbc.Card(id="tcfd-card",            className="detail-card h-100"), width=6, className="d-flex flex-column"),
    ], className="mb-0"),
], width=9)

app.layout = dbc.Container([

    # --- Header ---
    dbc.Row([
        dbc.Col(html.H4("ESG Carbon Analytics Dashboard", className="dash-header mb-0"), width="auto"),
        dbc.Col(
            dbc.Badge("Beta", color="secondary", className="align-self-center"),
            width="auto", className="ms-auto",
        ),
    ], align="center", className="py-3 border-bottom mb-2"),

    # --- Data status alert ---
    html.Div(id="data-status", className="mb-3"),

    # --- Controls + main content ---
    dbc.Row([
        dbc.Col(_CONTROLS, width=3, className="d-flex flex-column"),
        _MAIN,
    ], className="g-3"),

    # --- Footer ---
    html.Hr(),
    dbc.Row([
        dbc.Col(
            html.Small(
                "Data sources: ONS (UK energy & GDP) · EDGAR v8 (global sector emissions) · "
                "Ember Climate (grid carbon intensity) | "
                "Methodology: GHG Protocol Scope 1–3 · Science Based Targets (SBTi) · "
                "TCFD 2017 framework · UK mandatory ESG reporting (FCA PS22/24)",
                className="footer-text",
            ),
            width="auto",
        ),
        dbc.Col(
            [
                dbc.Button(
                    "Export CSV",
                    id="export-btn",
                    className="ms-3 export-btn",
                ),
                dcc.Download(id="download-csv"),
            ],
            width="auto",
        ),
    ], justify="between", align="center", className="py-2"),

], fluid=True)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@app.callback(
    Output("kpi-scope1",          "children"),
    Output("kpi-scope2",          "children"),
    Output("kpi-scope3",          "children"),
    Output("kpi-tcfd",            "children"),
    Output("scope-chart",         "figure"),
    Output("forecast-chart",      "figure"),
    Output("scenario-chart",      "figure"),
    Output("carbon-exposure-card","children"),
    Output("tcfd-card",           "children"),
    Output("forecast-reliability","children"),
    Output("benchmark-content",   "children"),
    Output("data-status",         "children"),
    Input("run-btn",              "n_clicks"),
    State("carbon-price",         "value"),
    State("forecast-horizon",     "value"),
    State("target-year",          "value"),
    State("upload-data",          "contents"),
    State("upload-data",          "filename"),
    prevent_initial_call=False,
)
def run_analysis(n_clicks, carbon_price, horizon, target_year, contents, filename):
    carbon_price = carbon_price or 50
    horizon      = horizon      or 10
    target_year  = target_year  or 2050

    # --- Data ingestion ---
    scope_totals = emissions_df = None
    data_status_msg = None

    # Priority 1: user-uploaded file
    if contents and filename:
        raw = _parse_upload(contents, filename)
        if raw is not None and {"date", "emissions_tco2e"}.issubset(raw.columns):
            raw["date"] = pd.to_datetime(raw["date"])
            raw["year"] = raw["date"].dt.year
            emissions_df = raw[["date", "emissions_tco2e"]]
            scope_totals = pd.DataFrame({
                "year":         raw["year"],
                "scope1_tco2e": raw["emissions_tco2e"],
                "scope2_tco2e": 0.0,
                "scope3_tco2e": 0.0,
                "total_tco2e":  raw["emissions_tco2e"],
            })

    # Priority 2: live ONS ELECCONS data (when no file uploaded)
    if scope_totals is None:
        ons_scope, ons_em, ons_label = _load_eleccons_data()
        if ons_scope is not None:
            scope_totals  = ons_scope
            emissions_df  = ons_em
            data_status_msg = dbc.Alert(
                [html.Strong("ONS data loaded: "), f"UK electricity consumption (ELECCONS) — {ons_label}"],
                color="success",
                className="small py-2 mb-0",
                dismissable=True,
            )
        else:
            data_status_msg = dbc.Alert(
                [html.Strong("ONS unavailable — "), f"using demo data ({ons_label})"],
                color="warning",
                className="small py-2 mb-0",
                dismissable=True,
            )

    # Priority 3: synthetic demo data
    if scope_totals is None:
        scope_totals, emissions_df = _make_demo_data()

    # --- Analytics ---
    forecast_result = train_forecast(emissions_df, periods=int(horizon))
    forecast_df = forecast_result["forecast"]
    metrics = forecast_result["metrics"]
    reliability = metrics["reliability"]

    last = scope_totals.sort_values("year").iloc[-1]
    prev = scope_totals.sort_values("year").iloc[-2] if len(scope_totals) >= 2 else last

    bau   = bau_scenario(emissions_df, horizon=int(horizon))
    sbti  = sbti_scenario(emissions_df, target_year=int(target_year))
    nz    = net_zero_scenario(emissions_df, target_year=int(target_year))
    all_scenarios = pd.concat([bau, sbti, nz], ignore_index=True)

    exposure = carbon_price_exposure(scope_totals, float(carbon_price))
    tcfd_score = tcfd_alignment_score({
        "has_scope3":           True,
        "has_forecast":         True,
        "has_scenario":         True,
        "reduction_target_pct": 30,
        "reporting_year":       2024,
    })

    # --- Benchmark calculation ---
    company_total = last["total_tco2e"]
    edgar_df = fetch_epa_emissions("ENE")
    latest_edgar_year = edgar_df["year"].max() if not edgar_df.empty else 2022
    benchmark = calc_sector_benchmark(company_total, edgar_df, "ENE", int(latest_edgar_year))

    # --- KPI cards ---
    def _delta(new, old):
        return ((new - old) / old * 100) if old else None

    kpi_s1 = kpi_card(
        "SCOPE 1 — Direct Emissions",
        f"{last['scope1_tco2e']:,.0f}", "tCO₂e",
        delta=_delta(last["scope1_tco2e"], prev["scope1_tco2e"]),
        description="Emissions from sources owned or controlled by your company, e.g. company vehicles, on-site boilers.",
    )
    kpi_s2 = kpi_card(
        "SCOPE 2 — Purchased Energy",
        f"{last['scope2_tco2e']:,.0f}", "tCO₂e",
        delta=_delta(last["scope2_tco2e"], prev["scope2_tco2e"]),
        description="Indirect emissions from buying electricity, steam, heat or cooling from an external supplier.",
    )
    kpi_s3 = kpi_card(
        "SCOPE 3 — Value Chain",
        f"{last['scope3_tco2e']:,.0f}", "tCO₂e",
        delta=_delta(last["scope3_tco2e"], prev["scope3_tco2e"]),
        description="All other indirect emissions across your supply chain: business travel, purchased goods, waste, logistics.",
    )
    kpi_tcfd = kpi_card(
        "TCFD SCORE",
        f"{tcfd_score['total_score']}/100",
        tcfd_score["rating"],
        description="Task Force on Climate-related Financial Disclosures. Rates how complete your climate reporting is (0–100).",
    )

    # --- Charts ---
    fig_scope    = scope_breakdown_chart(scope_totals)
    fig_forecast = forecast_chart(emissions_df, forecast_df, baseline=forecast_result["baseline"])
    fig_scenario = scenario_chart(all_scenarios)

    # --- Detail cards ---
    exposure_children = _exposure_card_body(exposure)
    tcfd_children     = _tcfd_card_body(tcfd_score)

    # --- Reliability Badge ---
    reliability_badge = [
        dbc.Badge(
            f"Reliability: {reliability['label']}",
            color=reliability["colour"],
            id="reliability-tooltip-target",
            className="cursor-pointer",
            style={"fontSize": "0.75rem", "padding": "0.45em 0.8em"}
        ),
        dbc.Tooltip(
            f"MAPE: {metrics['mape']}% | RMSE: {metrics['rmse']} tCO₂e | MAE: {metrics['mae']} tCO₂e | {metrics['n_datapoints']} data points. {reliability['message']}",
            target="reliability-tooltip-target",
            placement="bottom",
        )
    ]

    # --- Benchmark content ---
    pct = benchmark["company_pct_of_sector"]
    progress_color = "danger" if pct > 10 else "warning" if pct > 1 else "success"
    progress_value = min(pct, 100)  # Cap at 100% for visual display

    benchmark_content = [
        html.H3(
            f"{pct}%",
            className="detail-value",
        ),
        html.P(
            benchmark["label"],
            className="detail-sublabel",
        ),
        dbc.Progress(
            value=progress_value,
            color=progress_color,
            striped=True,
            animated=(pct > 1),
            style={"height": "20px"},
            className="mt-2",
        ),
        html.Div(
            f"{benchmark['company_tco2e']:,.0f} tCO₂e / {benchmark['uk_sector_total_tco2e']:,.0f} tCO₂e",
            className="detail-section-label mt-2 small text-muted",
        ),
    ]

    return (
        kpi_s1, kpi_s2, kpi_s3, kpi_tcfd,
        fig_scope, fig_forecast, fig_scenario,
        exposure_children, tcfd_children,
        reliability_badge,
        benchmark_content,
        data_status_msg,
    )


@app.callback(
    Output("download-csv", "data"),
    Input("export-btn", "n_clicks"),
    prevent_initial_call=True,
)
def export_csv(n_clicks):
    scope_totals, _ = _make_demo_data()
    return dcc.send_data_frame(scope_totals.to_csv, "esg_export.csv", index=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    debug_mode = os.getenv("DEBUG", "False").lower() == "true"
    print(f"ESG Dashboard running on http://0.0.0.0:8050 (debug={debug_mode})")
    app.run(host="0.0.0.0", port=8050, debug=debug_mode)
