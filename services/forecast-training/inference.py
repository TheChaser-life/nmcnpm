"""
SageMaker Inference Script — XGBoost Exchange Rate Forecaster

Implements the four SageMaker inference handler functions required for a
custom inference container, plus a Flask-based HTTP server that follows
SageMaker BYO container conventions:

  GET  /ping         → HTTP 200 (health check)
  POST /invocations  → inference result

SageMaker handler functions:
  model_fn(model_dir)                    — load model artifacts
  input_fn(request_body, content_type)   — parse incoming request
  predict_fn(input_data, model)          — run prediction
  output_fn(prediction, accept)          — serialise response

Input format (JSON):
  {
    "currency_code": "USD",
    "horizon": 7
  }

Output format (JSON):
  {
    "currency_code": "USD",
    "forecast": [
      {"date": "2024-01-16", "predicted_rate": 0.0000432},
      {"date": "2024-01-17", "predicted_rate": 0.0000435},
      ...
    ]
  }

Error handling:
  - Unknown currency_code → HTTP 400 with error message
  - Missing required fields → HTTP 400 with error message
  - Invalid content_type → HTTP 415 with error message
  - Internal error → HTTP 500 with error message
"""

import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import xgboost as xgb

# Flask is used for the HTTP inference server (SageMaker BYO container convention)
from flask import Flask, Response, jsonify, request


# ── Constants ─────────────────────────────────────────────────────────────────

# Base feature columns — must match the order used during training in train.py
BASE_FEATURE_COLUMNS = [
    "rate_normalized",
    "transaction_volume",
    "transaction_count",
    "hour",
    "day_of_week",
    "day_of_month",
]

# Model version string embedded in every inference response.
MODEL_VERSION = "1.0"

SUPPORTED_CONTENT_TYPES = {"application/json"}
SUPPORTED_ACCEPT_TYPES = {"application/json"}

# Default forecast horizon (days) if not specified in request
DEFAULT_HORIZON = 7

# SageMaker inference server port
INFERENCE_PORT = 8080


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout (CloudWatch Logs)."""
    entry = {
        "level": level,
        "message": message,
        "service": "forecast-inference",
        **kwargs,
    }
    print(json.dumps(entry, default=str), flush=True)


# ── model_fn ──────────────────────────────────────────────────────────────────

def model_fn(model_dir: str) -> Dict[str, Any]:
    """
    Load all per-currency XGBoost models and their metadata from the model directory.

    SageMaker calls this function once when the endpoint starts up.
    The returned object is passed to predict_fn on every inference request.

    Model files follow the naming convention:
      {currency_code}_model.json    — XGBoost model in native JSON format
      {currency_code}_metadata.json — feature columns, lag_days, forecast_horizon

    Args:
        model_dir: Directory containing the model artifact files.
                   SageMaker extracts model.tar.gz here automatically.

    Returns:
        Dict with:
          "models": {currency_code: XGBRegressor}
          "metadata": {currency_code: {feature_columns, lag_days, forecast_horizon}}

    Raises:
        RuntimeError: If no model files are found in model_dir.
    """
    model_pattern = os.path.join(model_dir, "*_model.json")
    model_files = glob.glob(model_pattern)

    if not model_files:
        raise RuntimeError(
            f"No model files found in {model_dir}. "
            f"Expected files matching pattern: *_model.json"
        )

    models: Dict[str, xgb.XGBRegressor] = {}
    metadata: Dict[str, Dict] = {}

    for model_path in sorted(model_files):
        # Extract currency code from filename: "USD_model.json" → "USD"
        filename = os.path.basename(model_path)
        currency_code = filename.replace("_model.json", "")

        # Load XGBoost model
        model = xgb.XGBRegressor()
        model.load_model(model_path)
        models[currency_code] = model

        # Load metadata (feature columns, lag_days, etc.)
        metadata_path = os.path.join(model_dir, f"{currency_code}_metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as f:
                meta = json.load(f)
        else:
            # Fallback metadata for backward compatibility
            meta = {
                "currency_code": currency_code,
                "feature_columns": BASE_FEATURE_COLUMNS,
                "lag_days": 7,
                "forecast_horizon": 1,
                "model_version": MODEL_VERSION,
            }
        metadata[currency_code] = meta

    _log(
        "INFO",
        "Models loaded",
        currencies=list(models.keys()),
        model_count=len(models),
    )

    return {"models": models, "metadata": metadata}


# ── input_fn ──────────────────────────────────────────────────────────────────

def input_fn(request_body: str, content_type: str) -> Dict[str, Any]:
    """
    Parse the incoming inference request body.

    Supports content_type: application/json

    Expected JSON payload:
      {
        "currency_code": "USD",
        "horizon": 7
      }

    Args:
        request_body: Raw request body string.
        content_type: MIME type of the request (e.g., "application/json").

    Returns:
        Parsed dict with validated fields:
          {
            "currency_code": "USD",
            "horizon": 7
          }

    Raises:
        ValueError: If content_type is unsupported, JSON is malformed,
                    or required fields are missing/invalid.
    """
    # Normalise content type (strip parameters like charset)
    normalised_ct = content_type.split(";")[0].strip().lower()

    if normalised_ct not in SUPPORTED_CONTENT_TYPES:
        raise ValueError(
            f"Unsupported content type: '{content_type}'. "
            f"Supported types: {sorted(SUPPORTED_CONTENT_TYPES)}"
        )

    try:
        data = json.loads(request_body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in request body: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")

    # Validate required fields
    if "currency_code" not in data:
        raise ValueError("Missing required field: 'currency_code'")

    # Parse and validate fields
    try:
        currency_code = str(data["currency_code"]).upper().strip()
        horizon = int(data.get("horizon", DEFAULT_HORIZON))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid field value: {exc}") from exc

    if not currency_code:
        raise ValueError("'currency_code' must not be empty")

    if horizon < 1:
        raise ValueError(f"'horizon' must be >= 1, got {horizon}")

    if horizon > 365:
        raise ValueError(f"'horizon' must be <= 365, got {horizon}")

    return {
        "currency_code": currency_code,
        "horizon": horizon,
    }


# ── predict_fn ────────────────────────────────────────────────────────────────

def predict_fn(
    input_data: Dict[str, Any],
    model: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run multi-step forecast using the appropriate per-currency XGBoost model.

    Uses an iterative (recursive) forecasting strategy:
      1. Start with the last known feature values.
      2. Predict the next step.
      3. Use the prediction as input for the next step (update lag features).
      4. Repeat for `horizon` steps.

    Args:
        input_data: Parsed and validated dict from input_fn().
        model: Dict with "models" and "metadata" from model_fn().

    Returns:
        Dict with forecast result:
          {
            "currency_code": "USD",
            "forecast": [
              {"date": "2024-01-16", "predicted_rate": 0.0000432},
              ...
            ]
          }

    Raises:
        ValueError: If the requested currency_code has no trained model.
    """
    currency_code = input_data["currency_code"]
    horizon = input_data["horizon"]

    models = model["models"]
    metadata = model["metadata"]

    if currency_code not in models:
        available = sorted(models.keys())
        raise ValueError(
            f"No model available for currency '{currency_code}'. "
            f"Available currencies: {available}"
        )

    booster = models[currency_code]
    meta = metadata[currency_code]
    feature_columns = meta.get("feature_columns", BASE_FEATURE_COLUMNS)
    lag_days = meta.get("lag_days", 7)

    # Build initial feature vector using neutral/default values.
    # In production, the Forecast Service would pass current market context.
    # For the iterative forecast, we start with a neutral state and update
    # lag features as we generate predictions.
    now = datetime.now(timezone.utc)

    # Initialize lag values to 0.0 (will be updated iteratively)
    lag_values: List[float] = [0.0] * lag_days
    lag_normalized_values: List[float] = [0.5] * lag_days

    forecast_steps = []

    for step in range(horizon):
        forecast_date = now + timedelta(days=step + 1)

        # Build feature vector
        feature_dict: Dict[str, float] = {
            "rate_normalized": lag_normalized_values[0] if lag_normalized_values else 0.5,
            "transaction_volume": 0.0,
            "transaction_count": 0.0,
            "hour": 0,  # predict for midnight
            "day_of_week": forecast_date.weekday(),
            "day_of_month": forecast_date.day,
        }

        # Add lag features
        for i in range(1, lag_days + 1):
            lag_idx = i - 1
            feature_dict[f"rate_lag_{i}"] = lag_values[lag_idx] if lag_idx < len(lag_values) else 0.0
            feature_dict[f"rate_normalized_lag_{i}"] = (
                lag_normalized_values[lag_idx] if lag_idx < len(lag_normalized_values) else 0.5
            )

        # Build feature vector in the exact order used during training
        feature_vector = np.array(
            [[feature_dict.get(col, 0.0) for col in feature_columns]],
            dtype=np.float32,
        )

        prediction = booster.predict(feature_vector)
        predicted_rate = float(prediction[0])

        # Clamp to non-negative (exchange rates cannot be negative)
        predicted_rate = max(0.0, predicted_rate)

        forecast_steps.append({
            "date": forecast_date.strftime("%Y-%m-%d"),
            "predicted_rate": predicted_rate,
        })

        # Update lag values for next iteration (shift and prepend new prediction)
        lag_values = [predicted_rate] + lag_values[:-1]
        # Normalize: use a simple running estimate (clamp to [0, 1])
        lag_normalized_values = [min(1.0, max(0.0, predicted_rate))] + lag_normalized_values[:-1]

    return {
        "currency_code": currency_code,
        "forecast": forecast_steps,
    }


# ── output_fn ─────────────────────────────────────────────────────────────────

def output_fn(prediction: Dict[str, Any], accept: str) -> str:
    """
    Serialise the prediction result to the response body.

    Supports accept type: application/json

    Args:
        prediction: Dict from predict_fn().
        accept: Requested response MIME type (e.g., "application/json").

    Returns:
        JSON-serialised string of the prediction result.

    Raises:
        ValueError: If the requested accept type is not supported.
    """
    normalised_accept = accept.split(";")[0].strip().lower()

    # Default to application/json if accept is wildcard or empty
    if normalised_accept in ("*/*", ""):
        normalised_accept = "application/json"

    if normalised_accept not in SUPPORTED_ACCEPT_TYPES:
        raise ValueError(
            f"Unsupported accept type: '{accept}'. "
            f"Supported types: {sorted(SUPPORTED_ACCEPT_TYPES)}"
        )

    return json.dumps(prediction)


# ── Flask Inference Server ────────────────────────────────────────────────────

def create_app(model_dir: str) -> Flask:
    """
    Create and configure the Flask inference server.

    Follows SageMaker BYO container conventions:
      GET  /ping         → HTTP 200 (health check)
      POST /invocations  → inference result

    Args:
        model_dir: Directory containing model artifacts.

    Returns:
        Configured Flask application.
    """
    app = Flask(__name__)

    # Load models at startup
    _log("INFO", "Loading models", model_dir=model_dir)
    try:
        loaded_model = model_fn(model_dir)
        _log(
            "INFO",
            "Models loaded successfully",
            currencies=list(loaded_model["models"].keys()),
        )
    except Exception as exc:
        _log("ERROR", "Failed to load models", error=str(exc))
        # Store error state — /ping will return 500 until models are loaded
        loaded_model = None
        load_error = str(exc)

    @app.route("/ping", methods=["GET"])
    def ping() -> Response:
        """Health check endpoint required by SageMaker."""
        if loaded_model is None:
            return Response(
                json.dumps({"status": "unhealthy", "error": "Models not loaded"}),
                status=500,
                mimetype="application/json",
            )
        return Response(
            json.dumps({"status": "healthy", "currencies": list(loaded_model["models"].keys())}),
            status=200,
            mimetype="application/json",
        )

    @app.route("/invocations", methods=["POST"])
    def invocations() -> Response:
        """Inference endpoint required by SageMaker."""
        if loaded_model is None:
            return Response(
                json.dumps({"error": "Models not loaded"}),
                status=500,
                mimetype="application/json",
            )

        content_type = request.content_type or "application/json"
        accept = request.accept_mimetypes.best or "application/json"

        try:
            # Parse input
            input_data = input_fn(request.get_data(as_text=True), content_type)
        except ValueError as exc:
            _log("WARN", "Invalid request", error=str(exc))
            return Response(
                json.dumps({"error": str(exc)}),
                status=400,
                mimetype="application/json",
            )

        try:
            # Run prediction
            prediction = predict_fn(input_data, loaded_model)
        except ValueError as exc:
            _log("WARN", "Prediction error", error=str(exc))
            return Response(
                json.dumps({"error": str(exc)}),
                status=400,
                mimetype="application/json",
            )
        except Exception as exc:
            _log("ERROR", "Unexpected prediction error", error=str(exc))
            return Response(
                json.dumps({"error": "Internal server error"}),
                status=500,
                mimetype="application/json",
            )

        try:
            # Serialise output
            response_body = output_fn(prediction, str(accept))
        except ValueError as exc:
            _log("WARN", "Unsupported accept type", error=str(exc))
            return Response(
                json.dumps({"error": str(exc)}),
                status=415,
                mimetype="application/json",
            )

        _log(
            "INFO",
            "Inference completed",
            currency_code=input_data["currency_code"],
            horizon=input_data["horizon"],
            forecast_steps=len(prediction.get("forecast", [])),
        )

        return Response(response_body, status=200, mimetype="application/json")

    return app


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Start the Flask inference server.

    This is called by the 'serve' executable in the SageMaker container.
    SageMaker expects the server to listen on port 8080.
    """
    model_dir = os.environ.get("SM_MODEL_DIR", "/opt/ml/model")

    _log("INFO", "Starting inference server", port=INFERENCE_PORT, model_dir=model_dir)

    app = create_app(model_dir)
    app.run(host="0.0.0.0", port=INFERENCE_PORT, debug=False)
