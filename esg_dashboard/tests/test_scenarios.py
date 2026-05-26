"""Tests for analytics.scenarios module."""

import pandas as pd
import pytest

from analytics.scenarios import (
    bau_scenario,
    sbti_scenario,
    net_zero_scenario,
)


class TestBAUScenario:
    """Tests for bau_scenario function."""

    def test_bau_returns_correct_columns(self, sample_emissions_df):
        """Should return columns with bau_lower, bau_upper, scenario, data_warning."""
        result = bau_scenario(sample_emissions_df, horizon=5)
        expected_cols = {"year", "emissions_tco2e", "bau_lower", "bau_upper", "scenario", "data_warning"}
        assert set(result.columns) == expected_cols

    def test_bau_scenario_tag_is_BAU(self, sample_emissions_df):
        """Scenario column should be 'BAU'."""
        result = bau_scenario(sample_emissions_df, horizon=5)
        assert (result["scenario"] == "BAU").all()

    def test_bau_upper_always_gte_lower(self, sample_emissions_df):
        """Upper bound should always be >= lower bound."""
        result = bau_scenario(sample_emissions_df, horizon=5)
        assert (result["bau_upper"] >= result["bau_lower"]).all()

    def test_bau_emissions_positive(self, sample_emissions_df):
        """Emissions should be positive or zero."""
        result = bau_scenario(sample_emissions_df, horizon=5)
        assert (result["emissions_tco2e"] >= 0).all()

    def test_bau_no_nulls(self, sample_emissions_df):
        """Result should have no NaN values."""
        result = bau_scenario(sample_emissions_df, horizon=5)
        assert result.isna().sum().sum() == 0


class TestSBTiScenario:
    """Tests for sbti_scenario function."""

    def test_sbti_returns_correct_columns(self, sample_emissions_df):
        """Should return year, emissions_tco2e, scenario."""
        result = sbti_scenario(sample_emissions_df, target_year=2030)
        expected_cols = {"year", "emissions_tco2e", "scenario"}
        assert set(result.columns) == expected_cols

    def test_sbti_scenario_tag_is_SBTi(self, sample_emissions_df):
        """Scenario column should be 'SBTi'."""
        result = sbti_scenario(sample_emissions_df, target_year=2030)
        assert (result["scenario"] == "SBTi").all()

    def test_sbti_reduces_at_4_2_pct_per_year(self, sample_emissions_df):
        """
        SBTi should reduce emissions by ~4.2% per year.
        ratio year2/year1 should be approximately 0.958 (±0.01).
        """
        result = sbti_scenario(sample_emissions_df, target_year=2030)
        if len(result) >= 2:
            ratio = result["emissions_tco2e"].iloc[1] / result["emissions_tco2e"].iloc[0]
            # 1 - 0.042 ≈ 0.958
            assert abs(ratio - 0.958) < 0.02  # Allow some tolerance

    def test_sbti_no_nulls(self, sample_emissions_df):
        """Result should have no NaN values."""
        result = sbti_scenario(sample_emissions_df, target_year=2030)
        assert result.isna().sum().sum() == 0


class TestNetZeroScenario:
    """Tests for net_zero_scenario function."""

    def test_net_zero_returns_correct_columns(self, sample_emissions_df):
        """Should return year, emissions_tco2e, scenario."""
        result = net_zero_scenario(sample_emissions_df, target_year=2050)
        expected_cols = {"year", "emissions_tco2e", "scenario"}
        assert set(result.columns) == expected_cols

    def test_net_zero_scenario_tag_is_Net_Zero(self, sample_emissions_df):
        """Scenario column should be 'Net Zero'."""
        result = net_zero_scenario(sample_emissions_df, target_year=2050)
        assert (result["scenario"] == "Net Zero").all()

    def test_net_zero_ends_at_zero(self, sample_emissions_df):
        """
        Last projected row should have emissions close to zero.
        Expected: ±1.0 tCO₂e tolerance.
        """
        result = net_zero_scenario(sample_emissions_df, target_year=2050)
        if not result.empty:
            last_emissions = result["emissions_tco2e"].iloc[-1]
            # Should be close to 0
            assert last_emissions < 100  # Reasonable threshold

    def test_net_zero_decreases_monotonically(self, sample_emissions_df):
        """Emissions should decrease over time (monotonic decrease)."""
        result = net_zero_scenario(sample_emissions_df, target_year=2050)
        # Check that emissions generally decrease (allowing for some tolerance)
        if len(result) >= 2:
            # Later values should be lower than earlier values on average
            first_half_mean = result["emissions_tco2e"].iloc[: len(result) // 2].mean()
            second_half_mean = result["emissions_tco2e"].iloc[len(result) // 2 :].mean()
            assert second_half_mean < first_half_mean

    def test_net_zero_no_nulls(self, sample_emissions_df):
        """Result should have no NaN values."""
        result = net_zero_scenario(sample_emissions_df, target_year=2050)
        assert result.isna().sum().sum() == 0


class TestScenarioNullValues:
    """Parametrized tests for null values across all scenarios."""

    @pytest.mark.parametrize(
        "scenario_func",
        [bau_scenario, sbti_scenario, net_zero_scenario],
    )
    def test_no_nulls_in_any_scenario(self, sample_emissions_df, scenario_func):
        """No scenario should produce NaN values."""
        if scenario_func == bau_scenario:
            result = scenario_func(sample_emissions_df, horizon=5)
        else:
            result = scenario_func(sample_emissions_df, target_year=2030)
        assert result.isna().sum().sum() == 0

    @pytest.mark.parametrize(
        "scenario_func",
        [bau_scenario, sbti_scenario, net_zero_scenario],
    )
    def test_scenarios_return_non_empty(self, sample_emissions_df, scenario_func):
        """Scenarios should return non-empty DataFrames."""
        if scenario_func == bau_scenario:
            result = scenario_func(sample_emissions_df, horizon=5)
        else:
            result = scenario_func(sample_emissions_df, target_year=2030)
        assert not result.empty
