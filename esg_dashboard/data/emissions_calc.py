"""Calculates Scope 1, 2, and 3 emissions in tCO₂e."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

_SCOPE1_COLS = ["date", "activity_type", "emissions_tco2e"]
_SCOPE2_COLS = ["date", "kwh", "intensity_gco2_kwh", "emissions_tco2e"]
_SCOPE3_COLS = ["date", "category", "spend_gbp", "emissions_tco2e"]
_TOTAL_COLS  = ["year", "scope1_tco2e", "scope2_tco2e", "scope3_tco2e", "total_tco2e"]


def calc_scope1(
    activity_data: pd.DataFrame,
    emission_factors: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute Scope 1 emissions from direct combustion / process activity data.

    activity_data  cols : date, activity_type, quantity, unit
    emission_factors cols: activity_type, factor_kgco2e_per_unit
    formula              : emissions_tco2e = quantity * factor_kgco2e_per_unit / 1000

    Returns columns: date, activity_type, emissions_tco2e.
    """
    if activity_data.empty or emission_factors.empty:
        logger.warning("calc_scope1: one or both inputs are empty")
        return pd.DataFrame(columns=_SCOPE1_COLS)

    merged = activity_data.merge(emission_factors, on="activity_type", how="left")
    missing = merged["factor_kgco2e_per_unit"].isna().sum()
    if missing:
        logger.warning("calc_scope1: %d row(s) have no matching emission factor", missing)

    merged["emissions_tco2e"] = merged["quantity"] * merged["factor_kgco2e_per_unit"] / 1000
    return merged[_SCOPE1_COLS].copy()


def calc_scope2(
    energy_kwh: pd.DataFrame,
    grid_intensity: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute location-based Scope 2 emissions from purchased electricity.

    energy_kwh    cols : date, kwh
    grid_intensity cols: year, intensity_gco2_kwh
    formula            : emissions_tco2e = kwh * intensity_gco2_kwh / 1_000_000

    Returns columns: date, kwh, intensity_gco2_kwh, emissions_tco2e.
    """
    if energy_kwh.empty or grid_intensity.empty:
        logger.warning("calc_scope2: one or both inputs are empty")
        return pd.DataFrame(columns=_SCOPE2_COLS)

    df = energy_kwh.copy()
    df["year"] = pd.to_datetime(df["date"]).dt.year
    merged = df.merge(grid_intensity[["year", "intensity_gco2_kwh"]], on="year", how="left")

    missing = merged["intensity_gco2_kwh"].isna().sum()
    if missing:
        logger.warning("calc_scope2: %d row(s) have no matching grid intensity", missing)

    merged["emissions_tco2e"] = merged["kwh"] * merged["intensity_gco2_kwh"] / 1_000_000
    return merged[_SCOPE2_COLS].copy()


def calc_scope3(
    supply_chain_data: pd.DataFrame,
    spend_factors: pd.DataFrame,
) -> pd.DataFrame:
    """
    Estimate Scope 3 upstream/downstream emissions using spend-based factors.

    supply_chain_data cols: date, category, spend_gbp
    spend_factors cols     : category, factor_kgco2e_per_gbp
    formula                : emissions_tco2e = spend_gbp * factor_kgco2e_per_gbp / 1000

    Returns columns: date, category, spend_gbp, emissions_tco2e.
    """
    if supply_chain_data.empty or spend_factors.empty:
        logger.warning("calc_scope3: one or both inputs are empty")
        return pd.DataFrame(columns=_SCOPE3_COLS)

    merged = supply_chain_data.merge(spend_factors, on="category", how="left")
    missing = merged["factor_kgco2e_per_gbp"].isna().sum()
    if missing:
        logger.warning("calc_scope3: %d row(s) have no matching spend factor", missing)

    merged["emissions_tco2e"] = merged["spend_gbp"] * merged["factor_kgco2e_per_gbp"] / 1000
    return merged[_SCOPE3_COLS].copy()


def calc_sector_benchmark(
    company_total_tco2e: float,
    edgar_df: pd.DataFrame,
    sector: str,
    year: int,
) -> dict:
    """
    Compare company emissions against UK sector totals from EDGAR v8.

    company_total_tco2e – company's total annual emissions (tCO₂e)
    edgar_df            – EDGAR DataFrame with columns: year, sector, emissions_mt
    sector              – sector code: "ENE", "IND", or "TRA"
    year                – year to benchmark against

    Returns dict:
      sector            – sector code
      year              – benchmark year
      company_tco2e     – company emissions (tCO₂e)
      uk_sector_total_tco2e – UK sector total (tCO₂e)
      company_pct_of_sector – company % of sector (2 decimal places)
      label             – human-readable comparison string
    """
    if edgar_df.empty:
        logger.warning("calc_sector_benchmark: EDGAR df is empty")
        return {
            "sector": sector,
            "year": year,
            "company_tco2e": company_total_tco2e,
            "uk_sector_total_tco2e": 0.0,
            "company_pct_of_sector": 0.0,
            "label": "Benchmark data unavailable",
        }

    try:
        # Filter to sector and year
        mask = (edgar_df["sector"] == sector) & (edgar_df["year"] == year)
        sector_data = edgar_df[mask]

        if sector_data.empty:
            # Try to use latest available year
            sector_only = edgar_df[edgar_df["sector"] == sector]
            if sector_only.empty:
                logger.warning("calc_sector_benchmark: no data for sector=%s", sector)
                return {
                    "sector": sector,
                    "year": year,
                    "company_tco2e": company_total_tco2e,
                    "uk_sector_total_tco2e": 0.0,
                    "company_pct_of_sector": 0.0,
                    "label": f"No {sector} sector data for {year}",
                }
            # Use latest year available
            latest_year = sector_only["year"].max()
            sector_data = edgar_df[(edgar_df["sector"] == sector) & (edgar_df["year"] == latest_year)]
            year = latest_year

        # Convert MtCO₂e to tCO₂e
        emissions_mt = sector_data["emissions_mt"].sum()
        uk_sector_total_tco2e = emissions_mt * 1_000_000  # Mt → t

        # Calculate company % of sector
        if uk_sector_total_tco2e > 0:
            company_pct = (company_total_tco2e / uk_sector_total_tco2e) * 100
            company_pct = round(company_pct, 2)
        else:
            company_pct = 0.0

        # Human-readable label
        label = (
            f"Your emissions are {company_pct}% of the UK {sector} sector "
            f"(EDGAR v8, {year})"
        )

        return {
            "sector": sector,
            "year": year,
            "company_tco2e": company_total_tco2e,
            "uk_sector_total_tco2e": uk_sector_total_tco2e,
            "company_pct_of_sector": company_pct,
            "label": label,
        }

    except Exception as exc:
        logger.warning("calc_sector_benchmark processing error: %s", exc)
        return {
            "sector": sector,
            "year": year,
            "company_tco2e": company_total_tco2e,
            "uk_sector_total_tco2e": 0.0,
            "company_pct_of_sector": 0.0,
            "label": "Benchmark calculation failed",
        }


def total_emissions(
    s1: pd.DataFrame,
    s2: pd.DataFrame,
    s3: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate Scope 1, 2, and 3 outputs into an annual totals table.

    Accepts the DataFrames returned by calc_scope1 / calc_scope2 / calc_scope3.
    Returns columns: year, scope1_tco2e, scope2_tco2e, scope3_tco2e, total_tco2e.
    """
    def _annual(df: pd.DataFrame, col_name: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["year", col_name])
        d = df.copy()
        d["year"] = pd.to_datetime(d["date"]).dt.year
        return d.groupby("year", as_index=False)["emissions_tco2e"].sum().rename(
            columns={"emissions_tco2e": col_name}
        )

    a1 = _annual(s1, "scope1_tco2e")
    a2 = _annual(s2, "scope2_tco2e")
    a3 = _annual(s3, "scope3_tco2e")

    # Outer-merge so years present in only one scope are still included
    merged = a1.merge(a2, on="year", how="outer").merge(a3, on="year", how="outer")
    merged = merged.fillna(0.0).sort_values("year").reset_index(drop=True)
    merged["total_tco2e"] = (
        merged["scope1_tco2e"] + merged["scope2_tco2e"] + merged["scope3_tco2e"]
    )
    return merged[_TOTAL_COLS]


# ---------------------------------------------------------------------------
# Smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from data_fetcher import fetch_epa_emissions

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    errors: list[str] = []

    # --- calc_sector_benchmark ---
    edgar_df = fetch_epa_emissions("ENE")
    if not edgar_df.empty:
        result = calc_sector_benchmark(
            company_total_tco2e=10_000,
            edgar_df=edgar_df,
            sector="ENE",
            year=2022,
        )
        assert result["sector"] == "ENE", f"sector mismatch: {result['sector']}"
        assert result["company_pct_of_sector"] >= 0, "negative percentage"
        logger.info("calc_sector_benchmark: %s", result["label"])
        print(f"\nBenchmark test: company is {result['company_pct_of_sector']}% of UK ENE sector")
    else:
        logger.warning("Skipping calc_sector_benchmark test (no EDGAR data)")

    # --- calc_scope1 ---
    activity = pd.DataFrame({
        "date":          ["2023-01-01", "2023-06-01"],
        "activity_type": ["natural_gas", "diesel"],
        "quantity":      [10_000.0, 5_000.0],
        "unit":          ["kWh", "litres"],
    })
    factors = pd.DataFrame({
        "activity_type":          ["natural_gas", "diesel"],
        "factor_kgco2e_per_unit": [0.18290, 2.6820],
    })
    s1 = calc_scope1(activity, factors)
    assert list(s1.columns) == _SCOPE1_COLS, f"scope1 columns wrong: {list(s1.columns)}"
    assert s1["emissions_tco2e"].isna().sum() == 0, "scope1: NaNs in emissions"
    assert abs(s1["emissions_tco2e"].iloc[0] - 10_000 * 0.18290 / 1000) < 1e-9, "scope1: value mismatch"

    # --- calc_scope2 ---
    energy = pd.DataFrame({
        "date": pd.date_range("2022-01-01", periods=3, freq="QE"),
        "kwh":  [500_000.0, 480_000.0, 510_000.0],
    })
    intensity = pd.DataFrame({
        "year":               [2022],
        "intensity_gco2_kwh": [233.0],
    })
    s2 = calc_scope2(energy, intensity)
    assert list(s2.columns) == _SCOPE2_COLS, f"scope2 columns wrong: {list(s2.columns)}"
    assert s2["emissions_tco2e"].isna().sum() == 0, "scope2: NaNs in emissions"
    expected_s2_first = 500_000 * 233.0 / 1_000_000
    assert abs(s2["emissions_tco2e"].iloc[0] - expected_s2_first) < 1e-9, "scope2: value mismatch"

    # --- calc_scope3 ---
    supply = pd.DataFrame({
        "date":      ["2023-01-01", "2023-01-01", "2023-01-01"],
        "category":  ["IT equipment", "business travel", "packaging"],
        "spend_gbp": [50_000.0, 20_000.0, 10_000.0],
    })
    spend_f = pd.DataFrame({
        "category":              ["IT equipment", "business travel", "packaging"],
        "factor_kgco2e_per_gbp": [0.47, 0.29, 0.15],
    })
    s3 = calc_scope3(supply, spend_f)
    assert list(s3.columns) == _SCOPE3_COLS, f"scope3 columns wrong: {list(s3.columns)}"
    assert s3["emissions_tco2e"].isna().sum() == 0, "scope3: NaNs in emissions"

    # --- total_emissions ---
    total = total_emissions(s1, s2, s3)
    assert list(total.columns) == _TOTAL_COLS, f"total columns wrong: {list(total.columns)}"
    assert total["total_tco2e"].isna().sum() == 0, "total: NaNs in total_tco2e"
    assert (total["total_tco2e"] >= 0).all(), "total: negative totals"

    if errors:
        for e in errors:
            print("FAIL:", e)
        sys.exit(1)

    print("emissions_calc.py OK")
