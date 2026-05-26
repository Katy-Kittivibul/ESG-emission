"""Integration tests for full pipeline using synthetic data."""

import pandas as pd
import pytest

from analytics.forecasting import train_forecast
from analytics.scenarios import bau_scenario, sbti_scenario, net_zero_scenario
from data.emissions_calc import (
    calc_scope1,
    calc_scope2,
    calc_scope3,
    total_emissions,
    calc_sector_benchmark,
)


class TestFullPipelineIntegration:
    """End-to-end integration test using only synthetic data."""

    def test_full_pipeline_synthetic(
        self,
        sample_emissions_df,
        sample_scope_totals,
        sample_edgar_df,
        sample_scope1_data,
        sample_scope1_factors,
        sample_scope2_energy,
        sample_scope2_intensity,
        sample_scope3_supply,
        sample_scope3_factors,
    ):
        """
        Full pipeline test:
        1. Forecast from emissions data
        2. Run all three scenarios
        3. Calculate scope emissions
        4. Benchmark against EDGAR
        """

        # Step 1: Forecast
        forecast_result = train_forecast(sample_emissions_df, periods=5)
        assert "forecast" in forecast_result
        assert "metrics" in forecast_result
        forecast_df = forecast_result["forecast"]
        assert len(forecast_df) > len(sample_emissions_df)
        print(f"✓ Forecast completed: {len(forecast_df)} rows")

        # Step 2: Scenarios
        bau = bau_scenario(sample_emissions_df, horizon=5)
        sbti = sbti_scenario(sample_emissions_df, target_year=2030)
        nz = net_zero_scenario(sample_emissions_df, target_year=2050)

        assert (bau["scenario"] == "BAU").all()
        assert (sbti["scenario"] == "SBTi").all()
        assert (nz["scenario"] == "Net Zero").all()
        print("✓ Scenarios completed")

        # Combine scenarios
        all_scenarios = pd.concat([bau, sbti, nz], ignore_index=True)
        unique_scenarios = all_scenarios["scenario"].unique()
        assert len(unique_scenarios) == 3
        print(f"✓ Scenarios combined: {list(unique_scenarios)}")

        # Step 3: Scope calculations
        s1 = calc_scope1(sample_scope1_data, sample_scope1_factors)
        s2 = calc_scope2(sample_scope2_energy, sample_scope2_intensity)
        s3 = calc_scope3(sample_scope3_supply, sample_scope3_factors)

        assert not s1.empty
        assert not s2.empty
        assert not s3.empty
        print("✓ Scope 1, 2, 3 calculations completed")

        # Total emissions
        totals = total_emissions(s1, s2, s3)
        assert "total_tco2e" in totals.columns
        assert (totals["total_tco2e"] >= 0).all()
        print(f"✓ Total emissions aggregated: {len(totals)} years")

        # Step 4: Benchmark
        company_total = sample_scope_totals["total_tco2e"].iloc[-1]
        benchmark = calc_sector_benchmark(
            company_total_tco2e=company_total,
            edgar_df=sample_edgar_df,
            sector="ENE",
            year=2022,
        )
        assert isinstance(benchmark["label"], str)
        assert benchmark["company_pct_of_sector"] >= 0
        print(f"✓ Benchmark calculated: {benchmark['label']}")

        print("\n✓✓✓ Integration test passed ✓✓✓")

    def test_pipeline_handles_empty_inputs_gracefully(self):
        """Pipeline should handle empty inputs without crashing."""
        empty_df = pd.DataFrame({"date": [], "emissions_tco2e": []})

        # Should not crash, may return empty results
        try:
            forecast_result = train_forecast(empty_df, periods=5)
            # May fail or return limited data, but shouldn't crash
        except Exception as e:
            # Expected behavior might be to raise an error
            assert isinstance(e, (ValueError, IndexError))

    def test_scenario_forecasts_reasonable_values(self, sample_emissions_df):
        """Scenarios should produce reasonable values."""
        bau = bau_scenario(sample_emissions_df, horizon=5)
        sbti = sbti_scenario(sample_emissions_df, target_year=2030)
        nz = net_zero_scenario(sample_emissions_df, target_year=2050)

        # All should be non-negative
        assert (bau["emissions_tco2e"] >= 0).all()
        assert (sbti["emissions_tco2e"] >= 0).all()
        assert (nz["emissions_tco2e"] >= 0).all()

        # Net Zero should end near zero
        nz_final = nz["emissions_tco2e"].iloc[-1]
        assert nz_final < 500  # Very low final value

        # All scenarios should have data
        assert len(bau) > 0
        assert len(sbti) > 0
        assert len(nz) > 0

        print("✓ Scenario reductions are reasonable")

    def test_scope_calculations_are_consistent(
        self,
        sample_scope1_data,
        sample_scope1_factors,
        sample_scope2_energy,
        sample_scope2_intensity,
        sample_scope3_supply,
        sample_scope3_factors,
    ):
        """Repeated scope calculations should produce identical results."""
        s1_first = calc_scope1(sample_scope1_data, sample_scope1_factors)
        s1_second = calc_scope1(sample_scope1_data, sample_scope1_factors)

        pd.testing.assert_frame_equal(s1_first, s1_second)

        s2_first = calc_scope2(sample_scope2_energy, sample_scope2_intensity)
        s2_second = calc_scope2(sample_scope2_energy, sample_scope2_intensity)

        pd.testing.assert_frame_equal(s2_first, s2_second)

        s3_first = calc_scope3(sample_scope3_supply, sample_scope3_factors)
        s3_second = calc_scope3(sample_scope3_supply, sample_scope3_factors)

        pd.testing.assert_frame_equal(s3_first, s3_second)

        print("✓ Scope calculations are deterministic")
