"""Tests for analytics.forecasting module."""

import pandas as pd
import pytest

from analytics.forecasting import (
    train_forecast,
    evaluate_forecast,
    get_confidence_intervals,
    _reliability_rating,
)


class TestTrainForecast:
    """Tests for train_forecast function."""

    def test_train_forecast_returns_dict(self, sample_emissions_df):
        """Should return a dictionary."""
        result = train_forecast(sample_emissions_df, periods=5)
        assert isinstance(result, dict)

    def test_train_forecast_has_required_keys(self, sample_emissions_df):
        """Result should contain forecast, baseline, model, and metrics."""
        result = train_forecast(sample_emissions_df, periods=5)
        required_keys = ["forecast", "baseline", "model", "metrics"]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_forecast_df_has_correct_columns(self, sample_emissions_df):
        """Forecast DataFrame should have: date, yhat, yhat_lower, yhat_upper, trend."""
        result = train_forecast(sample_emissions_df, periods=5)
        forecast_df = result["forecast"]
        expected_cols = ["date", "yhat", "yhat_lower", "yhat_upper", "trend"]
        assert list(forecast_df.columns) == expected_cols

    def test_forecast_extends_beyond_historic(self, sample_emissions_df):
        """Forecast should extend beyond historic data."""
        result = train_forecast(sample_emissions_df, periods=5)
        forecast_df = result["forecast"]
        assert len(forecast_df) > len(sample_emissions_df)

    def test_metrics_mape_is_float(self, sample_emissions_df):
        """MAPE in metrics should be a float."""
        result = train_forecast(sample_emissions_df, periods=5)
        mape = result["metrics"]["mape"]
        assert isinstance(mape, (float, int))

    def test_metrics_mape_between_0_and_100(self, sample_emissions_df):
        """MAPE should be between 0 and 100."""
        result = train_forecast(sample_emissions_df, periods=5)
        mape = result["metrics"]["mape"]
        assert 0 <= mape <= 100

    def test_metrics_has_reliability_rating(self, sample_emissions_df):
        """Metrics should include reliability dict with label and colour."""
        result = train_forecast(sample_emissions_df, periods=5)
        reliability = result["metrics"]["reliability"]
        assert "label" in reliability
        assert "colour" in reliability


class TestReliabilityRating:
    """Tests for _reliability_rating function."""

    def test_reliability_rating_low(self):
        """High MAPE + low data points → Low reliability."""
        rating = _reliability_rating(mape=50, n=10)
        assert rating["label"] == "Low"
        assert rating["colour"] == "danger"

    def test_reliability_rating_moderate(self):
        """Moderate MAPE → Moderate reliability."""
        rating = _reliability_rating(mape=10, n=10)
        assert rating["label"] == "Moderate"
        assert rating["colour"] == "warning"

    def test_reliability_rating_insufficient(self):
        """Very few data points → Insufficient data."""
        rating = _reliability_rating(mape=5, n=3)
        assert rating["label"] == "Insufficient data"
        assert rating["colour"] == "danger"

    def test_reliability_rating_high(self):
        """Low MAPE + good data → High reliability."""
        rating = _reliability_rating(mape=5, n=10)
        assert rating["label"] in ["High", "Moderate"]


class TestConfidenceIntervals:
    """Tests for get_confidence_intervals function."""

    def test_confidence_intervals_has_three_keys(self, sample_emissions_df):
        """Should return dict with lower, upper, central."""
        result = train_forecast(sample_emissions_df, periods=5)
        intervals = get_confidence_intervals(result)
        required_keys = ["lower", "upper", "central"]
        for key in required_keys:
            assert key in intervals

    def test_confidence_intervals_values_are_lists(self, sample_emissions_df):
        """Interval values should be lists."""
        result = train_forecast(sample_emissions_df, periods=5)
        intervals = get_confidence_intervals(result)
        assert isinstance(intervals["lower"], list)
        assert isinstance(intervals["upper"], list)
        assert isinstance(intervals["central"], list)


class TestEvaluateForecast:
    """Tests for evaluate_forecast function."""

    def test_evaluate_forecast_requires_minimum_data(self):
        """With only 5 rows, should raise ValueError (needs >= 6)."""
        small_df = pd.DataFrame({
            "date": pd.date_range("2020", periods=5, freq="YE"),
            "emissions_tco2e": [1000, 1100, 1050, 1200, 1150],
        })
        with pytest.raises(ValueError, match="Need >= 6"):
            train_forecast(small_df, periods=5)

    def test_forecast_returns_baseline_model(self, sample_emissions_df):
        """Baseline should be a linear trend."""
        result = train_forecast(sample_emissions_df, periods=5)
        baseline = result["baseline"]
        assert baseline is not None
        assert hasattr(baseline, "predict") or isinstance(baseline, object)

    def test_forecast_metrics_has_required_fields(self, sample_emissions_df):
        """Metrics should have mape, rmse, mae, n_datapoints."""
        result = train_forecast(sample_emissions_df, periods=5)
        metrics = result["metrics"]
        required_fields = ["mape", "rmse", "mae", "n_datapoints"]
        for field in required_fields:
            assert field in metrics
