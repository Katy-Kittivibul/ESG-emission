"""Tests for data.emissions_calc module."""

import pandas as pd
import pytest

from data.emissions_calc import (
    calc_scope1,
    calc_scope2,
    calc_scope3,
    total_emissions,
    calc_sector_benchmark,
)


class TestCalcScope1:
    """Tests for calc_scope1 function."""

    def test_calc_scope1_returns_correct_columns(
        self, sample_scope1_data, sample_scope1_factors
    ):
        """Verify output has correct columns: date, activity_type, emissions_tco2e."""
        result = calc_scope1(sample_scope1_data, sample_scope1_factors)
        expected_cols = ["date", "activity_type", "emissions_tco2e"]
        assert list(result.columns) == expected_cols

    def test_calc_scope1_emissions_are_positive(
        self, sample_scope1_data, sample_scope1_factors
    ):
        """All emissions should be positive or zero."""
        result = calc_scope1(sample_scope1_data, sample_scope1_factors)
        assert (result["emissions_tco2e"] >= 0).all()

    def test_calc_scope1_returns_empty_on_empty_input(self):
        """Empty input should return empty DataFrame with correct columns."""
        empty_df = pd.DataFrame(columns=["date", "activity_type", "quantity", "unit"])
        factors = pd.DataFrame(
            columns=["activity_type", "factor_kgco2e_per_unit"]
        )
        result = calc_scope1(empty_df, factors)
        assert result.empty
        assert list(result.columns) == ["date", "activity_type", "emissions_tco2e"]


class TestCalcScope2:
    """Tests for calc_scope2 function."""

    def test_calc_scope2_matches_manual_calculation(
        self, sample_scope2_energy, sample_scope2_intensity
    ):
        """
        Verify calculation: kwh * intensity_gco2_kwh / 1_000_000.
        For 500_000 kwh * 233 gCO2/kwh / 1M = 0.1165 tCO2e.
        """
        result = calc_scope2(sample_scope2_energy, sample_scope2_intensity)
        expected_first = 500_000 * 233.0 / 1_000_000
        actual_first = result["emissions_tco2e"].iloc[0]
        assert abs(actual_first - expected_first) < 1e-9

    def test_calc_scope2_returns_correct_columns(
        self, sample_scope2_energy, sample_scope2_intensity
    ):
        """Output should have: date, kwh, intensity_gco2_kwh, emissions_tco2e."""
        result = calc_scope2(sample_scope2_energy, sample_scope2_intensity)
        expected_cols = ["date", "kwh", "intensity_gco2_kwh", "emissions_tco2e"]
        assert list(result.columns) == expected_cols

    def test_calc_scope2_emissions_are_positive(
        self, sample_scope2_energy, sample_scope2_intensity
    ):
        """All emissions should be positive or zero."""
        result = calc_scope2(sample_scope2_energy, sample_scope2_intensity)
        assert (result["emissions_tco2e"] >= 0).all()


class TestCalcScope3:
    """Tests for calc_scope3 function."""

    def test_calc_scope3_merges_on_category(
        self, sample_scope3_supply, sample_scope3_factors
    ):
        """Should merge supply data on category and produce output."""
        result = calc_scope3(sample_scope3_supply, sample_scope3_factors)
        assert not result.empty
        assert len(result) == 3

    def test_calc_scope3_returns_correct_columns(
        self, sample_scope3_supply, sample_scope3_factors
    ):
        """Output should have: date, category, spend_gbp, emissions_tco2e."""
        result = calc_scope3(sample_scope3_supply, sample_scope3_factors)
        expected_cols = ["date", "category", "spend_gbp", "emissions_tco2e"]
        assert list(result.columns) == expected_cols

    def test_calc_scope3_emissions_are_positive(
        self, sample_scope3_supply, sample_scope3_factors
    ):
        """All emissions should be positive or zero."""
        result = calc_scope3(sample_scope3_supply, sample_scope3_factors)
        assert (result["emissions_tco2e"] >= 0).all()


class TestTotalEmissions:
    """Tests for total_emissions aggregation function."""

    def test_total_emissions_sums_all_scopes(
        self,
        sample_scope1_data,
        sample_scope1_factors,
        sample_scope2_energy,
        sample_scope2_intensity,
        sample_scope3_supply,
        sample_scope3_factors,
    ):
        """total_tco2e should equal sum of scope1/2/3."""
        s1 = calc_scope1(sample_scope1_data, sample_scope1_factors)
        s2 = calc_scope2(sample_scope2_energy, sample_scope2_intensity)
        s3 = calc_scope3(sample_scope3_supply, sample_scope3_factors)

        result = total_emissions(s1, s2, s3)
        # For any year present, total should be sum of scopes
        for _, row in result.iterrows():
            expected_total = row["scope1_tco2e"] + row["scope2_tco2e"] + row["scope3_tco2e"]
            assert abs(row["total_tco2e"] - expected_total) < 1e-9

    def test_total_emissions_no_nulls(
        self,
        sample_scope1_data,
        sample_scope1_factors,
        sample_scope2_energy,
        sample_scope2_intensity,
        sample_scope3_supply,
        sample_scope3_factors,
    ):
        """Result should have no NaN values in totals."""
        s1 = calc_scope1(sample_scope1_data, sample_scope1_factors)
        s2 = calc_scope2(sample_scope2_energy, sample_scope2_intensity)
        s3 = calc_scope3(sample_scope3_supply, sample_scope3_factors)

        result = total_emissions(s1, s2, s3)
        assert result["total_tco2e"].isna().sum() == 0
        assert result["scope1_tco2e"].isna().sum() == 0

    def test_total_emissions_returns_correct_columns(
        self,
        sample_scope1_data,
        sample_scope1_factors,
        sample_scope2_energy,
        sample_scope2_intensity,
        sample_scope3_supply,
        sample_scope3_factors,
    ):
        """Output should have: year, scope1_tco2e, scope2_tco2e, scope3_tco2e, total_tco2e."""
        s1 = calc_scope1(sample_scope1_data, sample_scope1_factors)
        s2 = calc_scope2(sample_scope2_energy, sample_scope2_intensity)
        s3 = calc_scope3(sample_scope3_supply, sample_scope3_factors)

        result = total_emissions(s1, s2, s3)
        expected_cols = [
            "year",
            "scope1_tco2e",
            "scope2_tco2e",
            "scope3_tco2e",
            "total_tco2e",
        ]
        assert list(result.columns) == expected_cols


class TestSectorBenchmark:
    """Tests for calc_sector_benchmark function."""

    def test_sector_benchmark_returns_pct(self, sample_edgar_df):
        """Percentage should be between 0 and 100."""
        result = calc_sector_benchmark(
            company_total_tco2e=10_000,
            edgar_df=sample_edgar_df,
            sector="ENE",
            year=2022,
        )
        pct = result["company_pct_of_sector"]
        assert 0 <= pct <= 100

    def test_sector_benchmark_label_is_string(self, sample_edgar_df):
        """Label should be a readable string."""
        result = calc_sector_benchmark(
            company_total_tco2e=10_000,
            edgar_df=sample_edgar_df,
            sector="ENE",
            year=2022,
        )
        assert isinstance(result["label"], str)
        assert "%" in result["label"]
        assert "ENE" in result["label"]

    def test_sector_benchmark_correct_calculation(self, sample_edgar_df):
        """
        Test correct percentage calculation:
        Company: 10,000 tCO2e
        UK ENE: 100 MtCO2e = 100,000,000 tCO2e
        Expected: 10,000 / 100,000,000 * 100 = 0.01%
        """
        result = calc_sector_benchmark(
            company_total_tco2e=10_000,
            edgar_df=sample_edgar_df,
            sector="ENE",
            year=2022,
        )
        assert result["company_pct_of_sector"] == 0.01

    def test_sector_benchmark_empty_edgar(self):
        """Should handle empty EDGAR DataFrame gracefully."""
        empty_df = pd.DataFrame(columns=["year", "sector", "emissions_mt"])
        result = calc_sector_benchmark(
            company_total_tco2e=10_000,
            edgar_df=empty_df,
            sector="ENE",
            year=2022,
        )
        assert result["company_pct_of_sector"] == 0.0
        assert "unavailable" in result["label"].lower()

    def test_sector_benchmark_returns_all_keys(self, sample_edgar_df):
        """Result dict should have all required keys."""
        result = calc_sector_benchmark(
            company_total_tco2e=10_000,
            edgar_df=sample_edgar_df,
            sector="ENE",
            year=2022,
        )
        required_keys = [
            "sector",
            "year",
            "company_tco2e",
            "uk_sector_total_tco2e",
            "company_pct_of_sector",
            "label",
        ]
        for key in required_keys:
            assert key in result
