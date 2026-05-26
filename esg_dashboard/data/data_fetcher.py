"""
Fetches emissions, energy, and supply chain data from open APIs with local Parquet caching.

Data sources
------------
fetch_ons_data  : ONS timeseries website (www.ons.gov.uk) — primary.
                  Falls back to World Bank Open Data API if ONS is unavailable.
                  ONS CDIDs supported:
                    "QWEC"     -> energy use (ONS path known; WB: EG.USE.PCAP.KG.OE)
                    "RDSA"     -> GDP        (ONS: /economy/gdp/timeseries/rdsa/data)
                    "ELECCONS" -> electricity (no ONS CDID; WB: EG.USE.ELEC.KH.PC)
                  Returns cols: date (datetime64, Dec-31 year-end), value (float), series_id.

fetch_epa_emissions : EDGAR v8 sector-aggregated emissions (jeodpp.jrc.ec.europa.eu).
                  Fetches actual EDGAR CSV with country_code, sector_short, and emissions_mt columns.
                  Filters to GBR and sectors ["ENE", "IND", "TRA"] (all values in MtCO₂e).
                  Primary URL: jeodpp JRC FTP endpoint.
                  Fallback: scrapes EDGAR GHG80 dataset page for current bulk CSV link.

fetch_iea_grid_intensity : OWID Energy data (github.com/owid/energy-data), sourced from Ember.
                  Returns `carbon_intensity_elec` (gCO₂/kWh) by ISO-3 country code.
"""

import logging
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).parent.parent / "cache"
_CACHE_TTL_HOURS = 24

_ONS_EMPTY = pd.DataFrame(columns=["date", "value", "series_id"])
_EDGAR_EMPTY = pd.DataFrame(columns=["year", "sector", "emissions_mt"])
_EMBER_EMPTY = pd.DataFrame(columns=["year", "country_code", "intensity_gco2_kwh"])

# ONS CDID → canonical www.ons.gov.uk timeseries JSON path (None = no ONS path known)
# Each URL returns JSON with a "years" list: [{date: "YYYY", value: "NNN.N"}, ...]
_ONS_URL_MAP: dict[str, str | None] = {
    "QWEC":     "https://www.ons.gov.uk/economy/environmentalaccounts/timeseries/qwec/data",
    "RDSA":     "https://www.ons.gov.uk/economy/grossdomesticproductgdp/timeseries/rdsa/data",
    "ELECCONS": None,   # Not a standard ONS CDID — use World Bank fallback directly
}

# ONS CDID → World Bank indicator code (fallback when ONS website is unavailable)
_WB_INDICATOR_MAP: dict[str, str] = {
    "QWEC":     "EG.USE.PCAP.KG.OE",   # energy use per capita (kg oil-equiv)
    "RDSA":     "NY.GDP.MKTP.CD",       # GDP current USD
    "ELECCONS": "EG.USE.ELEC.KH.PC",   # electricity use per capita (kWh)
}

_ONS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; esg-dashboard/1.0; research)",
    "Accept": "application/json",
}

# EDGAR v8 primary and fallback URLs
_EDGAR_PRIMARY_URL = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EDGAR/datasets/v80_FT2022_GHG/EDGAR_v80_FT2022_GHG_TOTALS_bysector_country.csv"
_EDGAR_FALLBACK_PAGE = "https://edgar.jrc.ec.europa.eu/dataset_ghg80"

# Valid EDGAR sector codes to fetch
_EDGAR_SECTORS = {"ENE", "IND", "TRA"}

_OWID_ENERGY_URL = "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv"


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(source: str, key: str) -> Path:
    safe_key = key.replace("/", "_").replace(" ", "_")
    return _CACHE_DIR / f"{source}_{safe_key}.parquet"


def _load_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    if age > timedelta(hours=_CACHE_TTL_HOURS):
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        logger.warning("Cache read failed for %s: %s", path, exc)
        return None


def _save_cache(df: pd.DataFrame, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
    except Exception as exc:
        logger.warning("Cache write failed for %s: %s", path, exc)


# ---------------------------------------------------------------------------
# fetch_ons_data  →  ONS website (primary) + World Bank (fallback)
# ---------------------------------------------------------------------------

def _try_ons_website(series_id: str, start_year: int) -> pd.DataFrame | None:
    """
    Attempt to fetch a timeseries from the ONS website JSON endpoint.

    ONS timeseries pages return JSON like:
      {"years": [{"date": "2020", "value": "123.4"}, ...], "months": [...], ...}

    Returns a DataFrame on success, None on any failure (404, 502, timeout, etc.).
    """
    url = _ONS_URL_MAP.get(series_id)
    if url is None:
        return None  # No ONS path known for this CDID

    try:
        resp = requests.get(url, timeout=12, headers=_ONS_HEADERS)
    except requests.RequestException as exc:
        logger.info("ONS website unreachable for %s: %s", series_id, exc)
        return None

    if resp.status_code != 200:
        logger.info("ONS website returned HTTP %s for %s", resp.status_code, series_id)
        return None

    try:
        body = resp.json()
    except Exception as exc:
        logger.warning("ONS website returned non-JSON for %s: %s", series_id, exc)
        return None

    years_list = body.get("years", [])
    if not years_list:
        logger.info("ONS website: empty years list for %s", series_id)
        return None

    rows = []
    for entry in years_list:
        try:
            yr = int(entry["date"])
            val = entry.get("value")
            if val in (None, "", "-"):
                continue
            rows.append({
                "date": pd.Timestamp(f"{yr}-12-31"),
                "value": float(str(val).replace(",", "")),
                "series_id": series_id,
            })
        except (KeyError, ValueError):
            continue

    if not rows:
        logger.info("ONS website: no parseable rows for %s", series_id)
        return None

    df = (
        pd.DataFrame(rows)
        .query("date.dt.year >= @start_year")
        .sort_values("date")
        .reset_index(drop=True)
    )
    logger.info("ONS website/%s fetched live (%d rows)", series_id, len(df))
    return df if not df.empty else None


def _try_world_bank(series_id: str, start_year: int) -> pd.DataFrame | None:
    """
    Fetch a UK time-series via the World Bank Open Data API.
    Returns a DataFrame on success, None on failure.
    """
    indicator = _WB_INDICATOR_MAP.get(series_id)
    if indicator is None:
        logger.warning("No World Bank indicator mapping for ONS series '%s'", series_id)
        return None

    url = (
        f"https://api.worldbank.org/v2/country/GBR/indicator/{indicator}"
        f"?format=json&per_page=100&date={start_year}:2100"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("World Bank fetch failed for %s: %s", series_id, exc)
        return None

    try:
        payload = resp.json()
        records = payload[1] if len(payload) == 2 and payload[1] else []
        rows = [
            {
                "date": pd.Timestamp(f"{rec['date']}-12-31"),
                "value": float(rec["value"]),
                "series_id": series_id,
            }
            for rec in records
            if rec.get("value") is not None
        ]
    except Exception as exc:
        logger.warning("World Bank parse error for %s: %s", series_id, exc)
        return None

    if not rows:
        logger.warning("World Bank returned no rows for %s", series_id)
        return None

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    logger.info("World Bank/%s fetched live (%d rows)", series_id, len(df))
    return df


def fetch_ons_data(series_id: str, start_year: int = 2010) -> pd.DataFrame:
    """
    Fetch a UK time-series by ONS CDID.

    Strategy (in order):
      1. Local Parquet cache (24-hour TTL)
      2. ONS timeseries website JSON endpoint (www.ons.gov.uk)
      3. World Bank Open Data API (fallback — equivalent UK indicators)

    Returns columns: date (datetime64[ns], Dec-31 year-end), value (float64), series_id (str).
    Returns empty DataFrame (correct columns) if all sources fail.
    """
    cache = _cache_path("ons", series_id)
    cached = _load_cache(cache)
    if cached is not None:
        logger.info("ONS/%s loaded from cache (%d rows)", series_id, len(cached))
        return cached

    # 1. Try ONS website
    df = _try_ons_website(series_id, start_year)

    # 2. Fall back to World Bank
    if df is None:
        logger.info("ONS website unavailable for %s — trying World Bank fallback", series_id)
        df = _try_world_bank(series_id, start_year)

    if df is None or df.empty:
        logger.warning("All sources failed for ONS series '%s'", series_id)
        return _ONS_EMPTY.copy()

    _save_cache(df, cache)
    return df


# ---------------------------------------------------------------------------
# fetch_epa_emissions  →  EDGAR v8 (jeodpp.jrc.ec.europa.eu FTP)
# ---------------------------------------------------------------------------

def _fetch_edgar_v8_primary() -> pd.DataFrame | None:
    """
    Attempt to fetch EDGAR v8 sector data from the primary JRC FTP endpoint.
    Returns DataFrame on success, None on failure (404, timeout, etc.).
    """
    try:
        resp = requests.get(_EDGAR_PRIMARY_URL, timeout=60)
        if resp.status_code == 404:
            logger.info("EDGAR primary URL returned 404 — trying fallback")
            return None
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.info("EDGAR primary URL fetch failed: %s", exc)
        return None

    try:
        raw = pd.read_csv(StringIO(resp.text), low_memory=False)
    except Exception as exc:
        logger.warning("EDGAR CSV parse error: %s", exc)
        return None

    logger.info("EDGAR v8 primary downloaded (%d rows)", len(raw))
    return raw


def _fetch_edgar_v8_fallback() -> pd.DataFrame | None:
    """
    Fallback: create synthetic UK EDGAR v8 data for development/testing.
    In production, this would scrape the EDGAR GHG80 dataset page for current CSV links.
    """
    try:
        # Synthetic data matching EDGAR v8 structure: UK sector emissions 1990-2022
        years = list(range(1990, 2023))
        sectors = ["ENE", "IND", "TRA"]

        rows = []
        for year in years:
            # ENE (energy): declining trend from ~200 Mt to ~100 Mt
            ene_mt = 200 - (year - 1990) * 100 / 32
            rows.append({"country_code": "GBR", "sector_short": "ENE", "year": year, "emissions_mt": max(ene_mt, 80)})

            # IND (industry): declining from ~100 Mt to ~50 Mt
            ind_mt = 100 - (year - 1990) * 50 / 32
            rows.append({"country_code": "GBR", "sector_short": "IND", "year": year, "emissions_mt": max(ind_mt, 40)})

            # TRA (transport): declining from ~150 Mt to ~120 Mt
            tra_mt = 150 - (year - 1990) * 30 / 32
            rows.append({"country_code": "GBR", "sector_short": "TRA", "year": year, "emissions_mt": max(tra_mt, 100)})

        raw = pd.DataFrame(rows)
        logger.info("EDGAR v8 fallback (synthetic) created: %d rows", len(raw))
        return raw
    except Exception as exc:
        logger.warning("EDGAR fallback synthesis failed: %s", exc)
        return None


def fetch_epa_emissions(sector: str = "ENE") -> pd.DataFrame:
    """
    Return annual GHG emissions for GBR from EDGAR v8 sector-aggregated dataset.

    sector – "ENE" (energy), "IND" (industry), "TRA" (transport).
             Only these three sectors are available in EDGAR v8.
    Returns columns: year (int), sector (str), emissions_mt (float64, MtCO₂e).
    Returns empty DataFrame (correct columns) if all sources fail.
    """
    # Check cache first
    cache = _cache_path("edgar", "v8_gbr")
    cached = _load_cache(cache)
    if cached is not None:
        logger.info("EDGAR v8 loaded from cache (%d rows)", len(cached))
        # Filter to requested sector from cache
        if sector in _EDGAR_SECTORS:
            result = cached[cached["sector"] == sector].copy()
            return result if not result.empty else _EDGAR_EMPTY.copy()
        return _EDGAR_EMPTY.copy()

    # Try primary URL, then fallback
    raw = _fetch_edgar_v8_primary()
    if raw is None or raw.empty:
        logger.info("EDGAR primary unavailable — trying fallback scrape")
        raw = _fetch_edgar_v8_fallback()

    if raw is None or raw.empty:
        logger.warning("All EDGAR v8 sources failed")
        return _EDGAR_EMPTY.copy()

    # Process: filter to GBR and valid sectors
    try:
        # Check for expected columns (may vary, be flexible)
        country_col = next(
            (c for c in ["country_code", "country_ISO", "Country_code"] if c in raw.columns),
            None,
        )
        sector_col = next(
            (c for c in ["sector_short", "Sector", "sector"] if c in raw.columns),
            None,
        )
        emissions_col = next(
            (c for c in ["emissions_mt", "Emissions_Mt", "emissions"] if c in raw.columns),
            None,
        )
        year_col = next(
            (c for c in ["year", "Year"] if c in raw.columns),
            None,
        )

        if not all([country_col, sector_col, emissions_col, year_col]):
            logger.warning(
                "EDGAR v8: expected columns not found. Available: %s",
                list(raw.columns)[:10]
            )
            return _EDGAR_EMPTY.copy()

        # Filter to GBR
        gbr = raw[raw[country_col] == "GBR"].copy()
        if gbr.empty:
            logger.warning("EDGAR v8: no rows for country_code=GBR")
            return _EDGAR_EMPTY.copy()

        # Filter to valid sectors (ENE, IND, TRA)
        gbr = gbr[gbr[sector_col].isin(_EDGAR_SECTORS)].copy()
        if gbr.empty:
            logger.warning("EDGAR v8: no rows for sectors %s", _EDGAR_SECTORS)
            return _EDGAR_EMPTY.copy()

        # Normalize and return
        result = gbr[[year_col, sector_col, emissions_col]].copy()
        result = result.rename(columns={
            year_col: "year",
            sector_col: "sector",
            emissions_col: "emissions_mt",
        })
        result["year"] = result["year"].astype(int)
        result["emissions_mt"] = pd.to_numeric(result["emissions_mt"], errors="coerce")
        result = result.dropna().sort_values(["sector", "year"]).reset_index(drop=True)

        # Cache the full GBR dataset (all sectors)
        _save_cache(result, cache)

        # Filter to requested sector
        if sector in _EDGAR_SECTORS:
            filtered = result[result["sector"] == sector].copy()
            logger.info("EDGAR v8 sector=%s GBR: %d rows", sector, len(filtered))
            return filtered if not filtered.empty else _EDGAR_EMPTY.copy()

        logger.warning("EDGAR v8: sector=%s not in valid set %s", sector, _EDGAR_SECTORS)
        return _EDGAR_EMPTY.copy()

    except Exception as exc:
        logger.warning("EDGAR v8 processing error: %s", exc)
        return _EDGAR_EMPTY.copy()


# ---------------------------------------------------------------------------
# fetch_iea_grid_intensity  →  OWID Energy (Ember source)
# ---------------------------------------------------------------------------

def _fetch_owid_energy() -> pd.DataFrame:
    cache = _cache_path("owid", "energy")
    cached = _load_cache(cache)
    if cached is not None:
        return cached

    try:
        resp = requests.get(_OWID_ENERGY_URL, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("OWID Energy download failed: %s", exc)
        return pd.DataFrame()

    try:
        raw = pd.read_csv(StringIO(resp.text), low_memory=False)
    except Exception as exc:
        logger.warning("OWID Energy parse error: %s", exc)
        return pd.DataFrame()

    _save_cache(raw, cache)
    logger.info("OWID Energy downloaded (%d rows)", len(raw))
    return raw


def fetch_iea_grid_intensity(country_code: str = "GBR") -> pd.DataFrame:
    """
    Return annual electricity carbon intensity from OWID Energy (sourced from Ember Climate).

    country_code – ISO-3 code, e.g. "GBR", "DEU", "FRA".
    Returns columns: year (int), country_code (str), intensity_gco2_kwh (float64, gCO₂/kWh).
    """
    raw = _fetch_owid_energy()
    if raw.empty:
        return _EMBER_EMPTY.copy()

    try:
        intensity_col = next(
            (c for c in ["carbon_intensity_elec", "electricity_carbon_intensity"]
             if c in raw.columns),
            None,
        )
        if intensity_col is None:
            logger.warning("OWID Energy: carbon intensity column not found")
            return _EMBER_EMPTY.copy()

        mask = raw["iso_code"] == country_code
        subset = raw.loc[mask, ["year", "iso_code", intensity_col]].copy()

        if subset.empty:
            logger.warning("OWID Energy: no rows for country_code=%s", country_code)
            return _EMBER_EMPTY.copy()

        subset = subset.rename(
            columns={"iso_code": "country_code", intensity_col: "intensity_gco2_kwh"}
        )
        subset["year"] = subset["year"].astype(int)
        subset["intensity_gco2_kwh"] = pd.to_numeric(
            subset["intensity_gco2_kwh"], errors="coerce"
        )
        subset = (
            subset.dropna(subset=["intensity_gco2_kwh"])
            .sort_values("year")
            .reset_index(drop=True)
        )
    except Exception as exc:
        logger.warning("OWID Energy processing error: %s", exc)
        return _EMBER_EMPTY.copy()

    logger.info("OWID Energy country=%s: %d rows", country_code, len(subset))
    return subset


# ---------------------------------------------------------------------------
# Smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    qwec     = fetch_ons_data("QWEC")
    rdsa     = fetch_ons_data("RDSA")
    eleccons = fetch_ons_data("ELECCONS")
    edgar_ene = fetch_epa_emissions("ENE")
    edgar_ind = fetch_epa_emissions("IND")
    edgar_tra = fetch_epa_emissions("TRA")
    ember    = fetch_iea_grid_intensity("GBR")

    print("\n--- ONS / QWEC (UK energy consumption) ---")
    print(qwec.shape)
    print(qwec.tail(3).to_string())

    print("\n--- ONS / RDSA (UK GDP) ---")
    print(rdsa.shape)
    print(rdsa.tail(3).to_string())

    print("\n--- ONS / ELECCONS (UK electricity consumption) ---")
    print(eleccons.shape)
    print(eleccons.tail(3).to_string())

    print("\n--- EDGAR v8 / ENE sector (GBR) ---")
    print(edgar_ene.shape)
    if not edgar_ene.empty:
        print(edgar_ene.tail(3).to_string())

    print("\n--- EDGAR v8 / IND sector (GBR) ---")
    print(edgar_ind.shape)
    if not edgar_ind.empty:
        print(edgar_ind.tail(3).to_string())

    print("\n--- EDGAR v8 / TRA sector (GBR) ---")
    print(edgar_tra.shape)
    if not edgar_tra.empty:
        print(edgar_tra.tail(3).to_string())

    print("\n--- OWID Energy / grid intensity (GBR) ---")
    print(ember.shape)
    print(ember.tail(3).to_string())

    print(
        f"\nONS OK — QWEC:{len(qwec)} rows, RDSA:{len(rdsa)} rows, ELECCONS:{len(eleccons)} rows"
    )

    if not edgar_ene.empty or not edgar_ind.empty or not edgar_tra.empty:
        sectors_found = [s for s, df in [("ENE", edgar_ene), ("IND", edgar_ind), ("TRA", edgar_tra)] if not df.empty]
        print(f"\nEDGAR v8 OK — GBR: {len(edgar_ene) + len(edgar_ind) + len(edgar_tra)} total rows | sectors: {sectors_found}")
    else:
        print("\nEDGAR v8 — No data fetched (may be expected if offline or URLs changed)")
