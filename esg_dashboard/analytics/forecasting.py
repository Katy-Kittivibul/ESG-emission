"""
Time-series forecasting for emissions using Prophet and LinearRegression.
"""

from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
import logging

logger = logging.getLogger(__name__)

MIN_DATAPOINTS = 6      # minimum rows to attempt forecast
MIN_CV_DATAPOINTS = 10  # minimum rows for cross-validation

def _reliability_rating(mape: float, n: int) -> dict:
    """Private helper to rate forecast reliability."""
    if n < MIN_DATAPOINTS:
        return {
            "label": "Insufficient data",
            "colour": "danger",
            "message": f"Need >= {MIN_DATAPOINTS} data points."
        }
    elif mape < 5 and n >= MIN_CV_DATAPOINTS:
        return {
            "label": "High",
            "colour": "success",
            "message": "MAPE < 5%. Forecast is well-fitted to historic trend."
        }
    elif mape < 15:
        return {
            "label": "Moderate",
            "colour": "warning",
            "message": "MAPE 5–15%. Treat projections as indicative, not precise."
        }
    else:
        return {
            "label": "Low",
            "colour": "danger",
            "message": f"MAPE {mape:.1f}%. High variance — extend historic data for better accuracy."
        }

def train_forecast(df: pd.DataFrame, periods: int = 10) -> dict:
    """
    Fit a trend model on historic annual emissions and return a forecast dict.
    
    Input df cols : date (datetime64), emissions_tco2e (float).
    Returns dict  : {forecast: df, baseline: df, model: Prophet, metrics: dict}
    """
    # a) Validate input
    if len(df) < MIN_DATAPOINTS:
        raise ValueError(f"Need >= {MIN_DATAPOINTS} annual data points, got {len(df)}")
    
    df = df.sort_values("date").copy()
    prophet_df = df.rename(columns={"date": "ds", "emissions_tco2e": "y"})
    
    # Try Prophet first
    prophet_success = False
    model = None
    prophet_result = None
    
    try:
        # Suppress Prophet stdout
        logging.getLogger("prophet").setLevel(logging.WARNING)
        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
        
        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=False,
            daily_seasonality=False,
            interval_width=0.90,
            changepoint_prior_scale=0.05,  # conservative, less overfit
            seasonality_mode="additive"
        )
        model.fit(prophet_df)
        
        future = model.make_future_dataframe(periods=periods, freq="YE")
        forecast = model.predict(future)
        forecast = forecast.rename(columns={"ds": "date"})
        
        prophet_result = forecast[["date", "yhat", "yhat_lower", "yhat_upper", "trend"]].copy()
        prophet_success = True
    except Exception as exc:
        logger.warning(f"Prophet fit failed, falling back to sklearn linear regression: {exc}")
        model = None
        prophet_result = None

    # c) Fit baseline linear regression (for comparison or fallback)
    X = np.arange(len(df)).reshape(-1, 1)
    y = df["emissions_tco2e"].values
    lr = LinearRegression().fit(X, y)
    
    X_future = np.arange(len(df) + periods).reshape(-1, 1)
    lr_preds = lr.predict(X_future)
    
    if prophet_success:
        future_dates = prophet_result["date"].values
    else:
        # Generate year-end dates for historical and future periods manually
        last_date = df["date"].max()
        future_dates_raw = pd.date_range(start=last_date, periods=periods + 1, freq="YE")
        hist_dates = df["date"].values
        future_dates = np.concatenate([hist_dates, future_dates_raw[1:]])
        
    lr_result = pd.DataFrame({
        "date": future_dates,
        "yhat_lr": lr_preds
    })

    # d) In-sample residuals for quick metrics
    if prophet_success:
        final_forecast = prophet_result
        y_true = prophet_df["y"].values
        y_pred = forecast["yhat"].values[:len(df)]
    else:
        # Standard fallback to Linear Regression with widening confidence bands
        resid = y - lr.predict(X)
        rmse_val = float(np.std(resid)) or 1.0
        n = len(df)
        h = np.maximum(np.arange(len(future_dates)) - n + 1, 0)
        _Z90 = 1.645
        sigma = rmse_val * np.sqrt(1.0 + h / n)
        
        final_forecast = pd.DataFrame({
            "date": future_dates,
            "yhat": lr_preds,
            "yhat_lower": lr_preds - _Z90 * sigma,
            "yhat_upper": lr_preds + _Z90 * sigma,
            "trend": lr_preds,
        })
        y_true = y
        y_pred = lr_preds[:len(df)]

    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mape = np.mean(np.abs((y_true - y_pred) / np.where(y_true == 0, 1, y_true))) * 100

    # Build reliability rating
    reliability = _reliability_rating(mape, len(df))
    if not prophet_success:
        reliability = {
            "label": f"{reliability['label']} (Baseline model)",
            "colour": "warning" if reliability["colour"] == "success" else reliability["colour"],
            "message": f"Prophet model failed to load. Using linear trend fallback. {reliability['message']}"
        }

    # e) Return dict
    return {
        "forecast": final_forecast,
        "baseline": lr_result,
        "model": model,
        "metrics": {
            "mae": round(float(mae), 1),
            "rmse": round(float(rmse), 1),
            "mape": round(float(mape), 2),
            "n_datapoints": len(df),
            "cv_performed": False,
            "reliability": reliability
        }
    }

def evaluate_forecast(df: pd.DataFrame, periods: int = 10) -> dict:
    """Runs Prophet cross-validation if enough data."""
    if len(df) < MIN_CV_DATAPOINTS:
        logger.warning(
            f"CV skipped: need {MIN_CV_DATAPOINTS} points, got {len(df)}"
        )
        return {
            "cv_performed": False,
            "reason": f"Need >= {MIN_CV_DATAPOINTS} annual data points for cross-validation (have {len(df)}).",
            "metrics": None
        }

    result = train_forecast(df, periods)
    model = result["model"]
    
    if model is None:
        logger.warning("CV skipped: Prophet model failed to compile or fit.")
        return {
            "cv_performed": False,
            "reason": "Prophet model failed to fit (Stan backend issue). Cross-validation skipped.",
            "metrics": result["metrics"]
        }

    # CV: initial=60% of data, period=1yr, horizon=3yr
    n_years = len(df)
    initial_days = str(int(n_years * 0.6 * 365)) + " days"
    period_days  = "365 days"
    horizon_days = "1095 days"  # 3 years

    try:
        df_cv = cross_validation(
            model,
            initial=initial_days,
            period=period_days,
            horizon=horizon_days,
            disable_tqdm=True
        )
        df_perf = performance_metrics(df_cv)
        cv_mape = round(float(df_perf["mape"].mean() * 100), 2)
        cv_rmse = round(float(df_perf["rmse"].mean()), 1)
        cv_mae  = round(float(df_perf["mae"].mean()), 1)
        return {
            "cv_performed": True,
            "metrics": {
                "cv_mape": cv_mape,
                "cv_rmse": cv_rmse,
                "cv_mae": cv_mae,
                "in_sample_mape": result["metrics"]["mape"],
                "n_datapoints": len(df),
                "reliability": _reliability_rating(cv_mape, len(df))
            }
        }
    except Exception as e:
        logger.warning(f"CV failed: {e}")
        return {
            "cv_performed": False,
            "reason": str(e),
            "metrics": result["metrics"]
        }

def get_confidence_intervals(forecast_dict: dict) -> dict:
    """Update to accept new dict return format."""
    forecast = forecast_dict["forecast"]
    return {
        "lower":   forecast[["date", "yhat_lower"]].to_dict("records"),
        "upper":   forecast[["date", "yhat_upper"]].to_dict("records"),
        "central": forecast[["date", "yhat"]].to_dict("records")
    }

if __name__ == "__main__":
    import sys
    import os
    
    # Add project root to path so sibling packages resolve
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    
    from analytics.scenarios import bau_scenario

    # Build synthetic df: 2010-2024 (15 points),
    # emissions 12000->8000 linear + np.random.seed(42) noise
    np.random.seed(42)
    years = np.arange(2010, 2025)
    dates = pd.to_datetime([f"{y}-12-31" for y in years])
    trend = np.linspace(12000, 8000, len(years))
    noise = np.random.normal(0, 150, len(years))
    df = pd.DataFrame({
        "date": dates,
        "emissions_tco2e": trend + noise
    })

    result = train_forecast(df, periods=10)
    assert "forecast" in result
    assert "metrics" in result
    assert result["metrics"]["mape"] is not None
    print(f'Prophet MAPE (in-sample): {result["metrics"]["mape"]}%')
    print(f'Reliability: {result["metrics"]["reliability"]["label"]}')

    ev = evaluate_forecast(df, periods=10)
    if ev["cv_performed"]:
        print(f'CV MAPE: {ev["metrics"]["cv_mape"]}%')
        print(f'CV RMSE: {ev["metrics"]["cv_rmse"]} tCO2e')
    else:
        print(f'CV skipped: {ev["reason"]}')

    bau = bau_scenario(df)
    assert "bau_lower" in bau.columns
    assert "bau_upper" in bau.columns
    print(f'BAU rows: {len(bau)}, data_warning: {bau["data_warning"].iloc[0]}')

    print("Step 4 fix complete.")
