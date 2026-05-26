# ESG Carbon Analytics Dashboard

## Project
Dash app for Scope 1/2/3 emissions forecasting and scenario modelling.
Target user: ESG analyst. UK-focused (ONS, EDGAR, Ember data).

## Stack
Python 3.11, Dash 2.17, Plotly, Prophet, Pandas, PyArrow, scikit-learn

## Structure
data/          — fetchers, cleaner, emissions calculator
analytics/     — forecasting, scenarios, risk metrics
components/    — reusable Dash chart components
assets/        — style.css
cache/         — Parquet cache files (gitignored)

## Conventions
- All emissions in tCO₂e
- Dates as datetime, year-end (Dec 31)
- Cache TTL: 24h
- Logging: module-level logger, no print() in lib code
- Empty df returns must include correct columns

## Steps completed
- [x] Step 1: scaffold, requirements.txt, venv, stubs
- [x] Step 2: data_fetcher.py (ONS, EDGAR, Ember)
- [x] Step 3: data_cleaner.py + emissions_calc.py
- [x] Step 4: forecasting.py + scenarios.py + risk_metrics.py
- [x] Step 5: app.py + components/charts.py
- [x] Step 6: UX pass 1 — descriptions, chart titles, TCFD/exposure card copy added.
- [x] Step 7: UX pass 2 — CSS hierarchy, consistent font scale, KPI values dominant.
- [x] Step 4 fix: Prophet + linear baseline, MAPE/RMSE/MAE, CV evaluation, BAU uncertainty bounds, reliability rating.
- [x] Step 8: Real data wiring v1 — ONS ELECCONS live (ONS website → World Bank fallback). data-status alert in app.py.
- [x] Phase A: EDGAR v8 UK sector emissions fetch + caching. Benchmark calculator. Benchmark panel wired to dashboard.
- [x] Phase B: pytest suite — 71 tests, 36% coverage. conftest.py fixtures. test_emissions_calc.py (19), test_data_fetcher.py (14), test_forecasting.py (16), test_scenarios.py (22), test_integration.py (4).
- [x] Phase C: Dockerised. Dockerfile (python:3.11-slim, build-essential, libgomp1). docker-compose.yml with healthcheck + volume persistence. App runs on host=0.0.0.0:8050, debug=False. Ready for Render.
- [x] Phase D: CI/CD Pipeline. GitHub Actions (.github/workflows/ci.yml): test → build → deploy to Render on main push. render.yaml configured. README.md comprehensive rewrite with badges, features, architecture, methodology, deployment steps.
