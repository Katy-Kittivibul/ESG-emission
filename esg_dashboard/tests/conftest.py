"""Shared pytest fixtures for the ESG dashboard test suite."""

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_emissions_df():
    """
    Create sample emissions time series: 2015-2024, linear decline 10000 → 7000 tCO₂e.
    """
    np.random.seed(42)
    dates = pd.date_range("2015", periods=10, freq="YE")
    emissions = np.linspace(10_000, 7_000, 10)
    df = pd.DataFrame({
        "date": dates,
        "emissions_tco2e": emissions,
    })
    return df


@pytest.fixture
def sample_scope_totals():
    """
    Create sample scope totals table: 10 years of scope1/2/3/total columns.
    Mimics the output shape of total_emissions().
    """
    np.random.seed(42)
    years = list(range(2015, 2025))
    s1 = np.linspace(3_000, 2_500, 10)
    s2 = np.linspace(2_000, 1_500, 10)
    s3 = np.linspace(5_000, 3_000, 10)

    df = pd.DataFrame({
        "year": years,
        "scope1_tco2e": s1,
        "scope2_tco2e": s2,
        "scope3_tco2e": s3,
        "total_tco2e": s1 + s2 + s3,
    })
    return df


@pytest.fixture
def sample_edgar_df():
    """
    Create minimal EDGAR-format DataFrame: 3 rows (ENE, IND, TRA for 2022).
    """
    df = pd.DataFrame({
        "year": [2022, 2022, 2022],
        "sector": ["ENE", "IND", "TRA"],
        "emissions_mt": [100.0, 50.0, 120.0],
    })
    return df


@pytest.fixture
def mock_ons_response():
    """
    Create mock ONS API JSON response shape with 10 years of data.
    """
    years_data = [
        {"date": str(year), "value": str(100 + year - 2015)}
        for year in range(2015, 2025)
    ]
    return {
        "years": years_data,
    }


@pytest.fixture
def sample_scope1_data():
    """Sample Scope 1 activity data."""
    return pd.DataFrame({
        "date": ["2023-01-01", "2023-06-01"],
        "activity_type": ["natural_gas", "diesel"],
        "quantity": [10_000.0, 5_000.0],
        "unit": ["kWh", "litres"],
    })


@pytest.fixture
def sample_scope1_factors():
    """Sample Scope 1 emission factors."""
    return pd.DataFrame({
        "activity_type": ["natural_gas", "diesel"],
        "factor_kgco2e_per_unit": [0.18290, 2.6820],
    })


@pytest.fixture
def sample_scope2_energy():
    """Sample Scope 2 energy consumption data."""
    return pd.DataFrame({
        "date": pd.date_range("2022-01-01", periods=3, freq="QE"),
        "kwh": [500_000.0, 480_000.0, 510_000.0],
    })


@pytest.fixture
def sample_scope2_intensity():
    """Sample grid carbon intensity data."""
    return pd.DataFrame({
        "year": [2022],
        "intensity_gco2_kwh": [233.0],
    })


@pytest.fixture
def sample_scope3_supply():
    """Sample Scope 3 supply chain data."""
    return pd.DataFrame({
        "date": ["2023-01-01", "2023-01-01", "2023-01-01"],
        "category": ["IT equipment", "business travel", "packaging"],
        "spend_gbp": [50_000.0, 20_000.0, 10_000.0],
    })


@pytest.fixture
def sample_scope3_factors():
    """Sample Scope 3 spend-based emission factors."""
    return pd.DataFrame({
        "category": ["IT equipment", "business travel", "packaging"],
        "factor_kgco2e_per_gbp": [0.47, 0.29, 0.15],
    })
