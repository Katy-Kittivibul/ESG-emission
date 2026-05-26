"""Normalises units, fills time-series gaps, and aligns reporting periods."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def normalise_units(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Rename and scale value columns to a documented standard per source.

    source="ons"   : multiply ``value`` by 1000 (ktoe → toe), rename to ``value_toe``.
    source="edgar" : values already in MtCO₂e; add constant column ``unit="MtCO2e"``.
    source="ember" : rename ``intensity_gco2_kwh`` to itself (asserts column present).
    Unknown source : log a warning and return df unchanged.
    """
    df = df.copy()

    if source == "ons":
        if "value" not in df.columns:
            logger.warning("normalise_units(ons): 'value' column missing")
            return df
        df["value"] = df["value"] * 1000
        df = df.rename(columns={"value": "value_toe"})

    elif source == "edgar":
        df["unit"] = "MtCO2e"

    elif source == "ember":
        if "intensity_gco2_kwh" not in df.columns:
            logger.warning("normalise_units(ember): 'intensity_gco2_kwh' column missing")
        # column already correctly named; nothing to rename

    else:
        logger.warning("normalise_units: unknown source '%s', returning df unchanged", source)

    return df


def fill_gaps(df: pd.DataFrame, method: str = "linear") -> pd.DataFrame:
    """
    Fill missing values in a time-indexed DataFrame by resampling to year-end frequency.

    Supported methods: ``"linear"`` (interpolation), ``"ffill"``, ``"bfill"``.
    Logs the number of filled gaps at DEBUG level.
    """
    df = df.copy()

    # Ensure a DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("fill_gaps expects a DataFrame with a DatetimeIndex")

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    before_nulls = df[numeric_cols].isna().sum().sum()

    resampled = df.resample("YE").mean()

    if method == "linear":
        filled = resampled.interpolate(method="linear")
    elif method == "ffill":
        filled = resampled.ffill()
    elif method == "bfill":
        filled = resampled.bfill()
    else:
        logger.warning("fill_gaps: unsupported method '%s', using linear", method)
        filled = resampled.interpolate(method="linear")

    after_nulls = filled[numeric_cols].isna().sum().sum()
    gaps_filled = int(before_nulls - after_nulls)
    logger.debug("fill_gaps: filled %d gap(s) using method='%s'", gaps_filled, method)

    return filled


def align_periods(dfs: list[pd.DataFrame], freq: str = "Y") -> pd.DataFrame:
    """
    Resample each DataFrame in *dfs* to *freq* and inner-merge on the date index.

    Finds the common date range (max of mins, min of maxes) across all DataFrames,
    trims each to that range, resamples, then merges.

    Raises ``ValueError`` if no overlapping period exists.
    """
    if not dfs:
        raise ValueError("align_periods: received an empty list of DataFrames")

    date_series = []
    for i, df in enumerate(dfs):
        if not isinstance(df.index, pd.DatetimeIndex):
            raise TypeError(f"align_periods: DataFrame at index {i} does not have a DatetimeIndex")
        if df.empty:
            raise ValueError(f"align_periods: DataFrame at index {i} is empty")
        date_series.append(df.index)

    common_start = max(idx.min() for idx in date_series)
    common_end   = min(idx.max() for idx in date_series)

    if common_start > common_end:
        raise ValueError(
            f"align_periods: no overlapping period between {common_start.date()} "
            f"and {common_end.date()}"
        )

    resampled = []
    for df in dfs:
        trimmed = df.loc[common_start:common_end]
        resampled.append(trimmed.resample(freq).mean())

    merged = resampled[0]
    for right in resampled[1:]:
        merged = merged.join(right, how="inner", rsuffix="_r")

    return merged


# ---------------------------------------------------------------------------
# Smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
    errors: list[str] = []

    # --- normalise_units ---
    ons_df = pd.DataFrame({"date": pd.date_range("2010", periods=3, freq="YE"), "value": [1.0, 2.0, 3.0]})
    result = normalise_units(ons_df, "ons")
    assert "value_toe" in result.columns, "ons: expected value_toe column"
    assert result["value_toe"].iloc[0] == 1000.0, "ons: scaling failed"

    edgar_df = pd.DataFrame({"year": [2020, 2021], "emissions_mt": [50.0, 48.0]})
    result = normalise_units(edgar_df, "edgar")
    assert "unit" in result.columns, "edgar: expected unit column"
    assert result["unit"].iloc[0] == "MtCO2e", "edgar: wrong unit value"

    ember_df = pd.DataFrame({"year": [2020], "intensity_gco2_kwh": [350.0]})
    result = normalise_units(ember_df, "ember")
    assert "intensity_gco2_kwh" in result.columns, "ember: column missing"

    normalise_units(edgar_df, "unknown_source")  # should log warning, not raise

    # --- fill_gaps ---
    idx = pd.date_range("2010", periods=5, freq="YE")
    gapped = pd.DataFrame({"value": [1.0, None, None, 4.0, 5.0]}, index=idx)
    filled = fill_gaps(gapped, method="linear")
    assert filled["value"].isna().sum() == 0, "fill_gaps linear: NaNs remain"

    filled_ff = fill_gaps(gapped, method="ffill")
    assert filled_ff["value"].isna().sum() == 0, "fill_gaps ffill: NaNs remain"

    # --- align_periods ---
    idx_a = pd.date_range("2012", periods=5, freq="YE")
    idx_b = pd.date_range("2014", periods=5, freq="YE")
    df_a = pd.DataFrame({"a": range(5)}, index=idx_a)
    df_b = pd.DataFrame({"b": range(5)}, index=idx_b)
    aligned = align_periods([df_a, df_b], freq="YE")
    assert not aligned.empty, "align_periods: result is empty"
    assert "a" in aligned.columns and "b" in aligned.columns, "align_periods: columns missing"

    try:
        # non-overlapping should raise
        df_c = pd.DataFrame({"c": [1]}, index=pd.date_range("2030", periods=1, freq="YE"))
        align_periods([df_a, df_c])
        errors.append("align_periods: should have raised ValueError for non-overlapping ranges")
    except ValueError:
        pass

    if errors:
        for e in errors:
            print("FAIL:", e)
        sys.exit(1)

    print("data_cleaner.py OK")
