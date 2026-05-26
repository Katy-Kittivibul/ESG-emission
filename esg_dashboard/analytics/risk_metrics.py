"""Computes carbon price exposure and TCFD alignment scoring."""

import logging
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)


def carbon_price_exposure(
    scope_totals: pd.DataFrame,
    carbon_price_gbp: float = 50.0,
) -> dict:
    """
    Estimate current and 5-year projected financial exposure to carbon pricing.

    scope_totals  : output of emissions_calc.total_emissions()
                    cols: year, scope1_tco2e, scope2_tco2e, scope3_tco2e, total_tco2e.
    carbon_price_gbp : current carbon price in £/tCO₂e.

    Returns:
        {
            "current_exposure_gbp": float,
            "five_year_projection": [{"year": int, "carbon_price_gbp": float,
                                       "exposure_gbp": float}, ...],
            "total_tco2e": float,
            "carbon_price_gbp": float,
        }
    """
    if scope_totals.empty or "total_tco2e" not in scope_totals.columns:
        logger.warning("carbon_price_exposure: scope_totals empty or missing total_tco2e")
        return {
            "current_exposure_gbp": 0.0,
            "five_year_projection": [],
            "total_tco2e": 0.0,
            "carbon_price_gbp": carbon_price_gbp,
        }

    latest = scope_totals.sort_values("year").iloc[-1]
    total_tco2e = float(latest["total_tco2e"])
    current_exposure = total_tco2e * carbon_price_gbp

    current_year = date.today().year
    projection = []
    price = carbon_price_gbp
    for i in range(5):
        yr = current_year + i
        projection.append(
            {
                "year": yr,
                "carbon_price_gbp": round(price, 2),
                "exposure_gbp": round(total_tco2e * price, 2),
            }
        )
        price *= 1.10  # 10 % annual increase

    return {
        "current_exposure_gbp": round(current_exposure, 2),
        "five_year_projection": projection,
        "total_tco2e": round(total_tco2e, 4),
        "carbon_price_gbp": carbon_price_gbp,
    }


def tcfd_alignment_score(data: dict) -> dict:
    """
    Score ESG disclosure quality against the four TCFD pillars (0–100).

    Expected data keys:
        has_scope3 (bool)         — Scope 3 emissions reported
        has_forecast (bool)       — Emissions forecast published
        has_scenario (bool)       — Climate scenario analysis conducted
        reduction_target_pct (float) — Absolute reduction target (0–100)
        reporting_year (int)      — Year of the most recent disclosure

    Pillar scoring (each 0–25):
        Governance  : has_scope3 → +10, has_forecast → +15
        Strategy    : has_scenario → +25
        Risk Mgmt   : reduction_target_pct capped at 25
        Metrics     : reporting_year == current year → +25, else +10

    Returns:
        {
            "total_score": int (0–100),
            "rating": "Leading" | "Developing" | "Nascent",
            "pillars": {
                "governance": int,
                "strategy": int,
                "risk_management": int,
                "metrics": int,
            },
        }
    """
    current_year = date.today().year

    governance = (10 if data.get("has_scope3") else 0) + (
        15 if data.get("has_forecast") else 0
    )

    strategy = 25 if data.get("has_scenario") else 0

    target_pct = float(data.get("reduction_target_pct", 0))
    risk_management = int(min(max(target_pct, 0), 25))

    metrics = 25 if data.get("reporting_year") == current_year else 10

    total = governance + strategy + risk_management + metrics

    if total >= 80:
        rating = "Leading"
    elif total >= 50:
        rating = "Developing"
    else:
        rating = "Nascent"

    return {
        "total_score": total,
        "rating": rating,
        "pillars": {
            "governance":      governance,
            "strategy":        strategy,
            "risk_management": risk_management,
            "metrics":         metrics,
        },
    }
