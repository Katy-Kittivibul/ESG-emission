"""Generates BAU, SBTi, and Net Zero reduction pathways for scenario modelling."""

import logging
from datetime import date

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_SCENARIO_COLS = ["year", "emissions_tco2e", "scenario"]


def _historic_actuals(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
    """Return the historic portion of *df* tagged with *scenario*."""
    hist = df[["date", "emissions_tco2e"]].copy()
    hist["year"] = pd.to_datetime(hist["date"]).dt.year
    hist = (
        hist.groupby("year", as_index=False)["emissions_tco2e"]
        .mean()
        .sort_values("year")
        .reset_index(drop=True)
    )
    hist["scenario"] = scenario
    return hist[_SCENARIO_COLS]


def _last_value_and_year(df: pd.DataFrame) -> tuple[float, int]:
    """Return the most recent (emissions_tco2e, year) pair from *df*."""
    last = df.sort_values("date").iloc[-1]
    return float(last["emissions_tco2e"]), int(pd.to_datetime(last["date"]).year)


def bau_scenario(df: pd.DataFrame, horizon: int = 10) -> pd.DataFrame:
    """
    Project a business-as-usual trajectory using the CAGR of the last 5 years.

    Input df cols  : date (datetime64), emissions_tco2e (float).
    Returns cols   : year (int), emissions_tco2e (float), bau_lower (float), bau_upper (float), scenario="BAU", data_warning (bool).
    """
    if df.empty:
        return pd.DataFrame(columns=_SCENARIO_COLS + ["bau_lower", "bau_upper", "data_warning"])

    sorted_df = df.sort_values("date").reset_index(drop=True)
    last_val, last_year = _last_value_and_year(sorted_df)

    # CAGR from 5 years ago
    cutoff = sorted_df[
        pd.to_datetime(sorted_df["date"]).dt.year <= last_year - 5
    ]
    if cutoff.empty:
        val_5yrs_ago = float(sorted_df.iloc[0]["emissions_tco2e"])
        n_years = last_year - int(pd.to_datetime(sorted_df.iloc[0]["date"]).year)
    else:
        val_5yrs_ago = float(cutoff.iloc[-1]["emissions_tco2e"])
        n_years = 5

    if val_5yrs_ago <= 0 or n_years <= 0:
        cagr = 0.0
    else:
        cagr = (last_val / val_5yrs_ago) ** (1.0 / n_years) - 1.0

    future_years = range(last_year + 1, last_year + horizon + 1)
    projected = pd.DataFrame(
        {
            "year": list(future_years),
            "emissions_tco2e": [
                last_val * ((1 + cagr) ** i) for i in range(1, horizon + 1)
            ],
            "scenario": "BAU",
        }
    )

    # Compute uncertainty band from standard deviation of year-on-year changes
    yoy_changes = sorted_df["emissions_tco2e"].pct_change().dropna()
    std_change = yoy_changes.std()
    if pd.isna(std_change):
        std_change = 0.0

    proj_lower = []
    proj_upper = []
    for i, val in enumerate(projected["emissions_tco2e"], start=1):
        proj_lower.append(val * (1 - std_change * np.sqrt(i)))
        proj_upper.append(val * (1 + std_change * np.sqrt(i)))
    
    projected["bau_lower"] = proj_lower
    projected["bau_upper"] = proj_upper

    hist = _historic_actuals(sorted_df, "BAU")
    hist["bau_lower"] = hist["emissions_tco2e"]
    hist["bau_upper"] = hist["emissions_tco2e"]

    warning_flag = len(df) < 8
    if warning_flag:
        logger.warning(
            "BAU scenario based on < 8 data points — "
            "uncertainty bounds will be wide."
        )
    hist["data_warning"] = warning_flag
    projected["data_warning"] = warning_flag

    return pd.concat([hist, projected], ignore_index=True)

def sbti_scenario(df: pd.DataFrame, target_year: int = 2030) -> pd.DataFrame:
    """
    Apply a 4.2 % absolute annual reduction (SBTi 1.5 °C pathway).

    Reduction applies until *target_year*; emissions are held flat thereafter.
    Input df cols : date (datetime64), emissions_tco2e (float).
    Returns cols  : year (int), emissions_tco2e (float), scenario="SBTi".
    """
    if df.empty:
        return pd.DataFrame(columns=_SCENARIO_COLS)

    sorted_df = df.sort_values("date").reset_index(drop=True)
    last_val, last_year = _last_value_and_year(sorted_df)

    current_year = date.today().year
    end_year = max(target_year, last_year + 1)
    future_years = range(last_year + 1, end_year + 1)

    rows = []
    val = last_val
    for yr in future_years:
        if yr <= target_year:
            val = val * (1 - 0.042)
        rows.append({"year": yr, "emissions_tco2e": max(val, 0.0), "scenario": "SBTi"})

    projected = pd.DataFrame(rows)
    hist = _historic_actuals(sorted_df, "SBTi")
    return pd.concat([hist, projected], ignore_index=True)


def net_zero_scenario(df: pd.DataFrame, target_year: int = 2050) -> pd.DataFrame:
    """
    Linear decline from the last actual value to zero by *target_year*.

    Uses np.linspace to distribute the reduction evenly across years.
    Input df cols : date (datetime64), emissions_tco2e (float).
    Returns cols  : year (int), emissions_tco2e (float), scenario="Net Zero".
    """
    if df.empty:
        return pd.DataFrame(columns=_SCENARIO_COLS)

    sorted_df = df.sort_values("date").reset_index(drop=True)
    last_val, last_year = _last_value_and_year(sorted_df)

    if target_year <= last_year:
        logger.warning(
            "net_zero_scenario: target_year %d is not in the future (last data: %d)",
            target_year,
            last_year,
        )
        target_year = last_year + 1

    n_years = target_year - last_year + 1  # inclusive of last_year value
    emissions_path = np.linspace(last_val, 0.0, n_years)

    # Drop the first element (= last historic year, already in actuals)
    future_years = range(last_year + 1, target_year + 1)
    projected = pd.DataFrame(
        {
            "year": list(future_years),
            "emissions_tco2e": emissions_path[1:],
            "scenario": "Net Zero",
        }
    )

    hist = _historic_actuals(sorted_df, "Net Zero")
    return pd.concat([hist, projected], ignore_index=True)
