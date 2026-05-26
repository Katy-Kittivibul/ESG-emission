# ESG Carbon Analytics Dashboard

<!-- Badges -->
[![CI/CD](https://github.com/YOUR_USERNAME/esg-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/esg-dashboard/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/YOUR_USERNAME/esg-dashboard/branch/main/graph/badge.svg)](https://codecov.io/gh/YOUR_USERNAME/esg-dashboard)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-enabled-blue.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/tests-71%20passing-brightgreen.svg)]()
[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen.svg)](https://esg-carbon-dashboard.onrender.com)

---

## Overview

Open-source Scope 1–3 emissions forecasting and scenario modelling tool for ESG analysts. Built on UK open data (ONS, EDGAR v8, Ember Climate) with interactive dashboards, TCFD alignment scoring, and sector benchmarking.

## Why This Exists

UK mandatory ESG reporting ([FCA PS22/24](https://www.fca.org.uk/news/news-stories/fca-confirms-timeline-mandatory-climate-related-disclosures)) requires companies to forecast emissions and align with climate targets. This dashboard makes that accessible to organisations without expensive consultancy, powered by real UK data and peer benchmarking.

---

## Features

- **Scope 1/2/3 Emissions Calculator** — Manual data entry or CSV upload
- **Forecasting** — Prophet (Meta) with 90% confidence intervals and MAPE evaluation
- **Scenario Modelling** — BAU, Science Based Targets (SBTi), and Net Zero pathways
- **TCFD Alignment** — 4-pillar scoring (Governance, Strategy, Risk, Metrics)
- **Carbon Price Exposure** — Financial liability under carbon tax/ETS scenarios
- **Sector Benchmarking** — Compare against UK sector totals (EDGAR v8)
- **Real UK Data** — Live ONS energy consumption, grid carbon intensity
- **Data Caching** — 24h Parquet cache for instant reload

---

## Architecture

```
Data Sources (ONS · EDGAR v8 · Ember Climate)
       ↓
ETL Layer (data_fetcher → data_cleaner → emissions_calc)
       ↓
Analytics Engines (forecasting · scenarios · risk_metrics)
       ↓
Interactive Dashboard (Dash + Plotly)
```

## Quick Start

### Prerequisites
- Python 3.11+
- Docker (optional)

### Local Installation

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/esg-dashboard.git
cd esg-dashboard

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r esg_dashboard/requirements.txt

# Run tests
pytest esg_dashboard/tests/ --cov=esg_dashboard/data --cov=esg_dashboard/analytics

# Start dashboard
cd esg_dashboard
python app.py
# → Visit http://localhost:8050
```

### Docker

```bash
# Build image
docker build -t esg-dashboard .

# Run container
docker run -p 8050:8050 esg-dashboard

# With docker-compose (includes volume persistence)
docker-compose up --build
docker-compose down
```

---

## Upload Format

### CSV / XLSX Requirements

Your emissions data file must have these columns:

| Column | Type | Notes |
|--------|------|-------|
| `date` | Date (YYYY-MM-DD or YYYY) | Year-end preferred (Dec 31) |
| `emissions_tco2e` | Float | Tonnes CO₂ equivalent |
| `scope` | Text (optional) | "Scope 1", "Scope 2", or "Scope 3" |

**Example:**
```
date,emissions_tco2e,scope
2020-12-31,5000.0,Scope 1
2021-12-31,4800.0,Scope 1
2022-12-31,4600.0,Scope 2
2023-12-31,4500.0,Scope 3
```

---

## Data Sources

| Source | What It Provides | Update Frequency | URL |
|--------|-----------------|------------------|-----|
| **ONS QWEC** | UK energy consumption (kWh/capita) | Quarterly | [Link](https://www.ons.gov.uk) |
| **ONS ELECCONS** | UK electricity consumption | Quarterly | [Link](https://www.ons.gov.uk) |
| **EDGAR v8** | UK sector GHG emissions (ENE/IND/TRA) | Annual | [Link](https://edgar.jrc.ec.europa.eu) |
| **Ember Climate** | UK grid carbon intensity (gCO₂/kWh) | Annual | [Link](https://ember-climate.org) |

---

## Methodology

### Forecasting
- **Model**: Prophet (Meta) with linear fallback
- **Evaluation**: MAPE, RMSE, MAE on 6+ data points
- **Confidence Interval**: 90% (upper/lower bounds)
- **Data requirement**: ≥6 annual data points

### Scenarios

| Scenario | Reduction Rate | Use Case |
|----------|---|----------|
| **BAU** (Business As Usual) | 0% (inertia) | Baseline: what happens if nothing changes? |
| **SBTi** (Science Based) | 4.2% per year | Science-based target (1.5°C alignment) |
| **Net Zero** (2050) | Linear to zero | UK legislative target (Climate Change Act 2008) |

### TCFD Scoring
- **Governance**: Board oversight, climate committee, targets
- **Strategy**: Scenario analysis, transition plan, financial impact
- **Risk Management**: Identification, assessment, monitoring
- **Metrics & Targets**: Emissions, intensity, SBT progress

---

## Testing

```bash
# Run all tests (71 tests)
pytest tests/ -v

# With coverage report
pytest tests/ --cov=data --cov=analytics --cov-report=html
```

**Status**: 71 tests passing, 36% coverage (Scenarios 88%, Emissions 51%, Forecasting 54%)

---

## Deployment to Render

### Step 1: Fork Repository
```bash
git clone https://github.com/YOUR_USERNAME/esg-dashboard.git
cd esg-dashboard
git push -u origin main
```

### Step 2: Create Render Service
1. Visit [render.com](https://render.com)
2. Create Web Service → Connect GitHub
3. Select this repository
4. **Configure**:
   - **Name**: `esg-carbon-dashboard`
   - **Runtime**: Docker
   - **Start Command**: `python app.py`

### Step 3: Set Secrets (for CI/CD auto-deploy)
In GitHub repository settings → **Secrets and variables**:
- `RENDER_SERVICE_ID`
- `RENDER_API_KEY`

### Step 4: Deploy
```bash
git push origin main
# → GitHub Actions triggers → Tests → Docker build → Render deploys
```

---

## Tech Stack

| Category | Technology |
|----------|-----------|
| **Language** | Python 3.11 |
| **Web Framework** | Dash 2.17 (React) |
| **Visualizations** | Plotly |
| **Data** | Pandas, PyArrow, Parquet |
| **Forecasting** | Prophet (Meta), scikit-learn |
| **Containerization** | Docker, docker-compose |
| **CI/CD** | GitHub Actions |
| **Deployment** | Render |
| **Testing** | pytest, coverage |

---

## License

MIT License — see [LICENSE](LICENSE) file for details.

---

## References

- [GHG Protocol Scope 1–3](https://ghgprotocol.org)
- [Science Based Targets Initiative](https://sciencebasedtargets.org)
- [TCFD Framework](https://www.tcfdhub.org)
- [UK FCA Mandatory Climate Disclosure (PS22/24)](https://www.fca.org.uk)
- [EDGAR v8 Dataset](https://edgar.jrc.ec.europa.eu)
- [ONS Open Data](https://www.ons.gov.uk)

---

**Built with ❤️ for ESG analysts | Production Ready**
