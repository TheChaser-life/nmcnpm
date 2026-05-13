"""
SageMaker Training Script — XGBoost Exchange Rate Forecaster

Đọc CSV training data từ SageMaker input channel, huấn luyện một XGBoost regressor
riêng cho từng currency_code, đánh giá bằng RMSE và MAE trên validation split 20%,
và lưu model artifacts + evaluation metrics theo SageMaker convention.

Algorithm choice: XGBoost với lag features
  - Dataset_Maker đã tạo sẵn các time-based features (hour, day_of_week, day_of_month)
    → tabular regression là lựa chọn tự nhiên, không cần sequence model.
  - XGBoost xử lý tabular data tốt hơn LSTM/DeepAR với dataset nhỏ-vừa.
  - Không yêu cầu JSON Lines format như DeepAR — đọc thẳng CSV.
  - Dễ containerize, debug, và interpret feature importance.
  - Lag features (previous N days of rates) được tạo tự động từ time series data.

SageMaker paths (set bởi SageMaker runtime):
  - Input data  : SM_CHANNEL_TRAINING  → /opt/ml/input/data/training/
  - Model output: SM_MODEL_DIR         → /opt/ml/model/
  - Eval output : SM_OUTPUT_DATA_DIR   → /opt/ml/output/data/
  - Hyperparams : /opt/ml/input/config/hyperparameters.json

Exit codes:
  - 0 : Training hoàn thành thành công
  - 1 : Lỗi không thể phục hồi (SageMaker sẽ đánh dấu job là Failed)
"""

import glob
import json
import math
import os
import sys
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout (CloudWatch Logs)."""
    entry = {
        "level": level,
        "message": message,
        "service": "forecast-training",
        **kwargs,
    }
    print(json.dumps(entry, default=str), flush=True)


# ── SageMaker Paths ───────────────────────────────────────────────────────────

SM_CHANNEL_TRAINING: str = os.environ.get(
    "SM_CHANNEL_TRAINING", "/opt/ml/input/data/training"
)
SM_MODEL_DIR: str = os.environ.get("SM_MODEL_DIR", "/opt/ml/model")
SM_OUTPUT_DATA_DIR: str = os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data")
SM_OUTPUT_FAILURE: str = "/opt/ml/output/failure"
HYPERPARAMS_PATH: str = "/opt/ml/input/config/hyperparameters.json"

# Base feature columns from Dataset_Maker CSV schema
BASE_FEATURE_COLUMNS: List[str] = [
    "rate_normalized",
    "transaction_volume",
    "transaction_count",
    "hour",
    "day_of_week",
    "day_of_month",
]

# Target variable
TARGET_COLUMN: str = "rate_to_vnd"

# Validation split ratio
VALIDATION_SPLIT: float = 0.2

# Minimum number of rows required to train a model for a currency.
# Lowered for demo/bootstrap training while the dataset has only a few snapshots.
MIN_ROWS_PER_CURRENCY: int = 2

# Default number of lag days for feature engineering
DEFAULT_LAG_DAYS: int = 7


# ── Hyperparameter Loading ────────────────────────────────────────────────────

def load_hyperparameters() -> Dict:
    """
    Load hyperparameters from SageMaker hyperparameters.json.

    SageMaker passes all hyperparameter values as strings — we cast them
    to the appropriate Python types here.

    Returns:
        Dict of hyperparameters with correct types.
    """
    defaults = {
        "n_estimators": 100,
        "max_depth": 6,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "objective": "reg:squarederror",
        "lag_days": DEFAULT_LAG_DAYS,
        "forecast_horizon": 1,
    }

    if not os.path.exists(HYPERPARAMS_PATH):
        _log(
            "WARN",
            "hyperparameters.json not found, using defaults",
            path=HYPERPARAMS_PATH,
            defaults=defaults,
        )
        return defaults

    try:
        with open(HYPERPARAMS_PATH, "r") as f:
            raw: Dict = json.load(f)

        # SageMaker serialises all values as strings — cast to correct types
        params = {
            "n_estimators": int(raw.get("n_estimators", defaults["n_estimators"])),
            "max_depth": int(raw.get("max_depth", defaults["max_depth"])),
            "learning_rate": float(raw.get("learning_rate", defaults["learning_rate"])),
            "subsample": float(raw.get("subsample", defaults["subsample"])),
            "colsample_bytree": float(
                raw.get("colsample_bytree", defaults["colsample_bytree"])
            ),
            "objective": str(raw.get("objective", defaults["objective"])),
            "lag_days": int(raw.get("lag_days", defaults["lag_days"])),
            "forecast_horizon": int(raw.get("forecast_horizon", defaults["forecast_horizon"])),
        }

        _log("INFO", "Hyperparameters loaded", params=params)
        return params

    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        _log(
            "WARN",
            "Failed to parse hyperparameters.json, using defaults",
            error=str(exc),
            defaults=defaults,
        )
        return defaults


# ── Data Loading ──────────────────────────────────────────────────────────────

def load_training_data(training_dir: str) -> pd.DataFrame:
    """
    Read all CSV files from the SageMaker training channel directory.

    SageMaker copies all files from the S3 input channel to this local
    directory before the training script starts.

    Args:
        training_dir: Path to the SageMaker training channel directory.

    Returns:
        Concatenated DataFrame from all CSV files.

    Raises:
        FileNotFoundError: If no CSV files are found.
        ValueError: If required columns are missing.
    """
    csv_pattern = os.path.join(training_dir, "**", "*.csv")
    csv_files = glob.glob(csv_pattern, recursive=True)

    # Also check top-level directory (SageMaker may place files directly)
    csv_files += glob.glob(os.path.join(training_dir, "*.csv"))
    csv_files = list(set(csv_files))  # deduplicate

    if not csv_files:
        raise FileNotFoundError(
            f"No CSV files found in training directory: {training_dir}"
        )

    _log("INFO", "Found CSV files", count=len(csv_files), files=csv_files[:10])

    dfs: List[pd.DataFrame] = []
    for csv_path in sorted(csv_files):
        try:
            df = pd.read_csv(csv_path)
            dfs.append(df)
            _log(
                "INFO",
                "Loaded CSV file",
                path=csv_path,
                rows=len(df),
                columns=list(df.columns),
            )
        except Exception as exc:
            _log("WARN", "Failed to read CSV file, skipping", path=csv_path, error=str(exc))

    if not dfs:
        raise ValueError("All CSV files failed to load")

    combined = pd.concat(dfs, ignore_index=True)
    _log("INFO", "Combined training data", total_rows=len(combined))

    # Validate required columns
    required_columns = BASE_FEATURE_COLUMNS + [TARGET_COLUMN, "currency_code"]
    missing = [col for col in required_columns if col not in combined.columns]
    if missing:
        raise ValueError(f"Missing required columns in training data: {missing}")

    return combined


# ── Data Preprocessing ────────────────────────────────────────────────────────

def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and preprocess the training DataFrame.

    Steps:
      1. Drop rows with NaN in feature or target columns.
      2. Ensure numeric types for feature and target columns.
      3. Remove rows where rate_to_vnd <= 0 (invalid rates).
      4. Parse timestamp column if present.

    Args:
        df: Raw DataFrame from load_training_data().

    Returns:
        Cleaned DataFrame.
    """
    initial_rows = len(df)

    # Drop rows with NaN in required columns
    required = BASE_FEATURE_COLUMNS + [TARGET_COLUMN, "currency_code"]
    df = df.dropna(subset=required)

    # Cast numeric columns
    for col in BASE_FEATURE_COLUMNS + [TARGET_COLUMN]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows where coercion produced NaN
    df = df.dropna(subset=BASE_FEATURE_COLUMNS + [TARGET_COLUMN])

    # Remove invalid rates
    df = df[df[TARGET_COLUMN] > 0]

    # Parse timestamp if present
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)

    dropped = initial_rows - len(df)
    if dropped > 0:
        _log("WARN", "Dropped invalid rows during preprocessing", dropped=dropped)

    _log("INFO", "Preprocessing complete", rows_remaining=len(df))
    return df.reset_index(drop=True)


# ── Lag Feature Engineering ───────────────────────────────────────────────────

def create_lag_features(
    df_currency: pd.DataFrame,
    lag_days: int,
    forecast_horizon: int,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Create lag features for time-series forecasting with XGBoost.

    For each lag day i (1..lag_days), creates:
      - rate_lag_{i}: rate_to_vnd shifted by i periods
      - rate_normalized_lag_{i}: rate_normalized shifted by i periods

    Also shifts the target by forecast_horizon to predict future rates.

    Args:
        df_currency: DataFrame for a single currency, sorted by timestamp.
        lag_days: Number of lag periods to create.
        forecast_horizon: Number of steps ahead to predict (default: 1).

    Returns:
        Tuple of (DataFrame with lag features, list of all feature column names).
    """
    df = df_currency.copy()

    # Sort by timestamp if available
    if "timestamp" in df.columns and pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df = df.sort_values("timestamp").reset_index(drop=True)

    lag_feature_names: List[str] = []

    # Create lag features for rate_to_vnd
    for i in range(1, lag_days + 1):
        col_name = f"rate_lag_{i}"
        df[col_name] = df[TARGET_COLUMN].shift(i)
        lag_feature_names.append(col_name)

    # Create lag features for rate_normalized
    for i in range(1, lag_days + 1):
        col_name = f"rate_normalized_lag_{i}"
        df[col_name] = df["rate_normalized"].shift(i)
        lag_feature_names.append(col_name)

    # Shift target forward by forecast_horizon (predict future rate)
    if forecast_horizon > 1:
        df[TARGET_COLUMN] = df[TARGET_COLUMN].shift(-forecast_horizon)

    # Drop rows with NaN introduced by shifting
    df = df.dropna(subset=lag_feature_names + [TARGET_COLUMN])

    all_feature_columns = BASE_FEATURE_COLUMNS + lag_feature_names

    return df.reset_index(drop=True), all_feature_columns


# ── Model Training ────────────────────────────────────────────────────────────

def train_currency_model(
    currency_code: str,
    df_currency: pd.DataFrame,
    hyperparams: Dict,
) -> Tuple[Optional[xgb.XGBRegressor], float, float, List[str]]:
    """
    Train an XGBoost regressor for a single currency.

    Uses an 80/20 train/validation split (time-ordered: first 80% for training,
    last 20% for validation — preserves temporal ordering).

    Creates lag features from the time series before training.

    Args:
        currency_code: ISO 4217 currency code (for logging).
        df_currency: DataFrame filtered to this currency only.
        hyperparams: Hyperparameter dict from load_hyperparameters().

    Returns:
        Tuple of (trained XGBRegressor, RMSE, MAE, feature_columns).
        Returns (None, inf, inf, []) if training is skipped due to insufficient data.
    """
    n_rows = len(df_currency)

    if n_rows < MIN_ROWS_PER_CURRENCY:
        _log(
            "WARN",
            "Skipping currency: insufficient data",
            currency_code=currency_code,
            rows=n_rows,
            min_required=MIN_ROWS_PER_CURRENCY,
        )
        return None, float("inf"), float("inf"), []

    lag_days = hyperparams.get("lag_days", DEFAULT_LAG_DAYS)
    forecast_horizon = hyperparams.get("forecast_horizon", 1)

    # Create lag features
    df_with_lags, feature_columns = create_lag_features(
        df_currency, lag_days, forecast_horizon
    )

    if len(df_with_lags) < MIN_ROWS_PER_CURRENCY:
        _log(
            "WARN",
            "Skipping currency: insufficient data after lag feature creation",
            currency_code=currency_code,
            rows=len(df_with_lags),
            min_required=MIN_ROWS_PER_CURRENCY,
        )
        return None, float("inf"), float("inf"), []

    X = df_with_lags[feature_columns].values
    y = df_with_lags[TARGET_COLUMN].values

    # Time-ordered split: first 80% → train, last 20% → validation
    split_idx = int(len(X) * (1 - VALIDATION_SPLIT))
    if split_idx < 1 or split_idx >= len(X):
        # Fallback to random split if time split produces empty sets
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=VALIDATION_SPLIT, random_state=42
        )
    else:
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

    _log(
        "INFO",
        "Training model for currency",
        currency_code=currency_code,
        train_rows=len(X_train),
        val_rows=len(X_val),
        feature_count=len(feature_columns),
        lag_days=lag_days,
        forecast_horizon=forecast_horizon,
    )

    model = xgb.XGBRegressor(
        n_estimators=hyperparams["n_estimators"],
        max_depth=hyperparams["max_depth"],
        learning_rate=hyperparams["learning_rate"],
        subsample=hyperparams["subsample"],
        colsample_bytree=hyperparams["colsample_bytree"],
        objective=hyperparams["objective"],
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    # Evaluate on validation set
    y_pred = model.predict(X_val)
    rmse = math.sqrt(mean_squared_error(y_val, y_pred))
    mae = float(mean_absolute_error(y_val, y_pred))

    _log(
        "INFO",
        "Model trained",
        currency_code=currency_code,
        rmse=rmse,
        mae=mae,
        n_estimators=hyperparams["n_estimators"],
    )

    return model, rmse, mae, feature_columns


# ── Model Saving ──────────────────────────────────────────────────────────────

def save_model(
    model: xgb.XGBRegressor,
    currency_code: str,
    model_dir: str,
    feature_columns: List[str],
    hyperparams: Dict,
) -> str:
    """
    Save a trained XGBoost model and its metadata to the SageMaker model directory.

    Uses XGBoost's native JSON format (not pickle) for portability and
    compatibility with the inference script.

    Also saves a metadata JSON file with feature columns and hyperparameters
    so the inference script can reconstruct the correct feature vector.

    Args:
        model: Trained XGBRegressor instance.
        currency_code: ISO 4217 currency code (used as filename prefix).
        model_dir: SageMaker model output directory.
        feature_columns: List of feature column names used during training.
        hyperparams: Hyperparameters used for training.

    Returns:
        Full path to the saved model file.
    """
    os.makedirs(model_dir, exist_ok=True)

    # Save XGBoost model in native JSON format
    model_path = os.path.join(model_dir, f"{currency_code}_model.json")
    model.save_model(model_path)

    # Save metadata (feature columns, hyperparams) for inference
    metadata = {
        "currency_code": currency_code,
        "feature_columns": feature_columns,
        "lag_days": hyperparams.get("lag_days", DEFAULT_LAG_DAYS),
        "forecast_horizon": hyperparams.get("forecast_horizon", 1),
        "model_version": "1.0",
    }
    metadata_path = os.path.join(model_dir, f"{currency_code}_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    _log(
        "INFO",
        "Model saved",
        currency_code=currency_code,
        model_path=model_path,
        metadata_path=metadata_path,
        feature_count=len(feature_columns),
    )
    return model_path


# ── Evaluation Metrics ────────────────────────────────────────────────────────

def save_evaluation_metrics(
    rmse_by_currency: Dict[str, float],
    mae_by_currency: Dict[str, float],
    output_data_dir: str,
) -> None:
    """
    Save evaluation metrics to metrics.json in the SageMaker output directory.

    The Model Registry Lambda (task 5.3.1) reads this file to compare the new
    model's performance against the currently deployed model.

    Format:
        {
            "rmse_by_currency": {"USD": 0.0000012, "EUR": 0.0000018, ...},
            "mae_by_currency": {"USD": 0.0000010, "EUR": 0.0000015, ...},
            "mean_rmse": 0.0000015,
            "mean_mae": 0.0000012
        }

    Args:
        rmse_by_currency: Dict mapping currency_code → RMSE value.
        mae_by_currency: Dict mapping currency_code → MAE value.
        output_data_dir: SageMaker output data directory.
    """
    os.makedirs(output_data_dir, exist_ok=True)

    # Exclude currencies that were skipped (metric = inf or nan)
    valid_rmse = {
        code: rmse
        for code, rmse in rmse_by_currency.items()
        if rmse != float("inf") and not math.isnan(rmse)
    }
    valid_mae = {
        code: mae
        for code, mae in mae_by_currency.items()
        if mae != float("inf") and not math.isnan(mae)
    }

    mean_rmse = float(np.mean(list(valid_rmse.values()))) if valid_rmse else float("inf")
    mean_mae = float(np.mean(list(valid_mae.values()))) if valid_mae else float("inf")

    metrics = {
        "rmse_by_currency": valid_rmse,
        "mae_by_currency": valid_mae,
        "mean_rmse": mean_rmse,
        "mean_mae": mean_mae,
    }

    # Write to metrics.json (primary output for SageMaker Model Registry)
    metrics_path = os.path.join(output_data_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    # Also write evaluation.json for backward compatibility
    eval_path = os.path.join(output_data_dir, "evaluation.json")
    with open(eval_path, "w") as f:
        json.dump(metrics, f, indent=2)

    _log(
        "INFO",
        "Evaluation metrics saved",
        metrics_path=metrics_path,
        mean_rmse=mean_rmse,
        mean_mae=mean_mae,
        currencies_trained=list(valid_rmse.keys()),
    )


# ── Failure Handling ──────────────────────────────────────────────────────────

def write_failure(error_message: str) -> None:
    """
    Write failure message to /opt/ml/output/failure as required by SageMaker.

    SageMaker reads this file when the training container exits with a non-zero
    exit code and includes its content in the Training Job failure reason.

    Args:
        error_message: Human-readable error description.
    """
    failure_dir = os.path.dirname(SM_OUTPUT_FAILURE)
    os.makedirs(failure_dir, exist_ok=True)
    try:
        with open(SM_OUTPUT_FAILURE, "w") as f:
            f.write(error_message)
        _log("INFO", "Failure message written", path=SM_OUTPUT_FAILURE)
    except Exception as exc:
        _log("WARN", "Could not write failure file", error=str(exc))


# ── Main Training Orchestrator ────────────────────────────────────────────────

def main() -> int:
    """
    Main training entry point.

    Orchestrates the full training pipeline:
      1. Load hyperparameters
      2. Load and preprocess training data
      3. Train one XGBoost model per currency_code (with lag features)
      4. Save model artifacts to SM_MODEL_DIR
      5. Save evaluation metrics to SM_OUTPUT_DATA_DIR/metrics.json

    Returns:
        Exit code: 0 = success, 1 = failure.
    """
    _log("INFO", "SageMaker training job started", algorithm="XGBoost")
    _log(
        "INFO",
        "SageMaker paths",
        training_dir=SM_CHANNEL_TRAINING,
        model_dir=SM_MODEL_DIR,
        output_data_dir=SM_OUTPUT_DATA_DIR,
    )

    try:
        # ── Step 1: Load hyperparameters ──────────────────────────────────────
        _log("INFO", "Step 1/5: Loading hyperparameters")
        hyperparams = load_hyperparameters()

        # ── Step 2: Load training data ────────────────────────────────────────
        _log("INFO", "Step 2/5: Loading training data", training_dir=SM_CHANNEL_TRAINING)
        try:
            df = load_training_data(SM_CHANNEL_TRAINING)
        except (FileNotFoundError, ValueError) as exc:
            error_msg = f"Failed to load training data: {exc}"
            _log("ERROR", error_msg)
            write_failure(error_msg)
            return 1

        # ── Step 3: Preprocess ────────────────────────────────────────────────
        _log("INFO", "Step 3/5: Preprocessing data")
        try:
            df = preprocess_data(df)
        except Exception as exc:
            error_msg = f"Preprocessing failed: {exc}"
            _log("ERROR", error_msg)
            write_failure(error_msg)
            return 1

        if df.empty:
            error_msg = "No valid training data after preprocessing"
            _log("ERROR", error_msg)
            write_failure(error_msg)
            return 1

        # ── Step 4: Train one model per currency ──────────────────────────────
        _log("INFO", "Step 4/5: Training models per currency")
        currencies = df["currency_code"].unique().tolist()
        _log("INFO", "Currencies found in training data", currencies=currencies)

        rmse_by_currency: Dict[str, float] = {}
        mae_by_currency: Dict[str, float] = {}
        models_trained = 0

        for currency_code in sorted(currencies):
            df_currency = df[df["currency_code"] == currency_code].copy()

            model, rmse, mae, feature_columns = train_currency_model(
                currency_code, df_currency, hyperparams
            )

            rmse_by_currency[currency_code] = rmse
            mae_by_currency[currency_code] = mae

            if model is not None:
                save_model(model, currency_code, SM_MODEL_DIR, feature_columns, hyperparams)
                models_trained += 1

        if models_trained == 0:
            error_msg = (
                f"No models were trained — all currencies had insufficient data "
                f"(min_rows_required={MIN_ROWS_PER_CURRENCY})"
            )
            _log("ERROR", error_msg, min_rows_required=MIN_ROWS_PER_CURRENCY)
            write_failure(error_msg)
            return 1

        _log(
            "INFO",
            "All models trained",
            models_trained=models_trained,
            total_currencies=len(currencies),
        )

        # ── Step 5: Save evaluation metrics ──────────────────────────────────
        _log("INFO", "Step 5/5: Saving evaluation metrics")
        try:
            save_evaluation_metrics(rmse_by_currency, mae_by_currency, SM_OUTPUT_DATA_DIR)
        except Exception as exc:
            error_msg = f"Failed to save evaluation metrics: {exc}"
            _log("ERROR", error_msg)
            write_failure(error_msg)
            return 1

        _log(
            "INFO",
            "SageMaker training job completed successfully",
            models_trained=models_trained,
            rmse_by_currency={
                k: v for k, v in rmse_by_currency.items() if v != float("inf")
            },
            mae_by_currency={
                k: v for k, v in mae_by_currency.items() if v != float("inf")
            },
        )
        return 0

    except Exception as exc:
        error_msg = f"Unexpected error during training: {exc}\n{traceback.format_exc()}"
        _log("ERROR", "Unexpected training failure", error=str(exc))
        write_failure(error_msg)
        return 1


if __name__ == "__main__":
    sys.exit(main())
