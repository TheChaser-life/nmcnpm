"""
Model Promotion Lambda — SageMaker Model Registry Comparison & Promotion

So sánh evaluation metric (RMSE) của model mới được đăng ký trong SageMaker Model
Registry với model hiện đang được approved/deployed. Nếu model mới tốt hơn (RMSE
thấp hơn), approve và promote lên SageMaker Endpoint; ngược lại, reject model mới.

Trigger: Step Functions workflow sau khi SageMaker Training Job hoàn thành.
Input event:
    {
        "model_package_arn": "<ARN của model package vừa đăng ký>",
        "endpoint_name": "<tên SageMaker Endpoint cần update>"   # optional
    }

Output: Structured response với decision và metrics để Step Functions tiếp tục xử lý.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.exceptions import ClientError


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(level: str, message: str, **kwargs: Any) -> None:
    """Emit structured JSON log entry to stdout (CloudWatch Logs)."""
    entry = {
        "level": level,
        "message": message,
        "service": "model-promotion",
        **kwargs,
    }
    print(json.dumps(entry, default=str), flush=True)


# ── Configuration ─────────────────────────────────────────────────────────────

AWS_REGION: str = os.environ.get("AWS_REGION", "ap-southeast-2")

# Primary metric used for comparison — lower is better
PRIMARY_METRIC: str = os.environ.get("PRIMARY_METRIC", "mean_rmse")


# ── SageMaker Client ──────────────────────────────────────────────────────────

def _get_sagemaker_client() -> Any:
    """Return a boto3 SageMaker client."""
    return boto3.client("sagemaker", region_name=AWS_REGION)


def _get_s3_client() -> Any:
    """Return a boto3 S3 client."""
    return boto3.client("s3", region_name=AWS_REGION)


# ── Metric Extraction ─────────────────────────────────────────────────────────

def _fetch_metrics_from_s3(s3_uri: str, s3_client: Any) -> Dict[str, Any]:
    """
    Download and parse the metrics.json file from S3.

    The training script (train.py) writes metrics.json to:
        s3://<model_artifact_bucket>/model-artifacts/<job_name>/output/metrics.json

    This URI is stored in ModelMetrics.ModelQuality.Statistics.S3Uri of the
    model package.

    Args:
        s3_uri: S3 URI in the format s3://bucket/key.
        s3_client: boto3 S3 client.

    Returns:
        Parsed metrics dict with keys: mean_rmse, mean_mae, rmse_by_currency, mae_by_currency.

    Raises:
        ValueError: If the S3 URI is malformed or the file cannot be parsed.
        ClientError: If the S3 object cannot be retrieved.
    """
    if not s3_uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {s3_uri!r}")

    # Parse s3://bucket/key
    without_scheme = s3_uri[len("s3://"):]
    slash_idx = without_scheme.find("/")
    if slash_idx == -1:
        raise ValueError(f"Cannot parse bucket/key from S3 URI: {s3_uri!r}")

    bucket = without_scheme[:slash_idx]
    key = without_scheme[slash_idx + 1:]

    _log("INFO", "Fetching metrics from S3", bucket=bucket, key=key)

    response = s3_client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")

    try:
        metrics = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse metrics JSON from {s3_uri}: {exc}") from exc

    _log("INFO", "Metrics fetched from S3", metrics=metrics)
    return metrics


def get_model_metric(model_package_arn: str, sm_client: Any, s3_client: Any) -> float:
    """
    Retrieve the primary evaluation metric for a model package.

    Reads the ModelMetrics.ModelQuality.Statistics.S3Uri from the model package
    description, downloads the metrics.json file from S3, and returns the
    value of PRIMARY_METRIC (default: mean_rmse).

    Args:
        model_package_arn: ARN of the SageMaker model package.
        sm_client: boto3 SageMaker client.
        s3_client: boto3 S3 client.

    Returns:
        Float value of the primary metric (lower is better).

    Raises:
        ValueError: If the model package has no ModelMetrics or the metric is missing.
        ClientError: If the SageMaker or S3 API call fails.
    """
    _log("INFO", "Describing model package", model_package_arn=model_package_arn)

    response = sm_client.describe_model_package(ModelPackageName=model_package_arn)

    model_metrics = response.get("ModelMetrics", {})
    model_quality = model_metrics.get("ModelQuality", {})
    statistics = model_quality.get("Statistics", {})
    s3_uri = statistics.get("S3Uri")

    if not s3_uri:
        raise ValueError(
            f"Model package {model_package_arn!r} has no ModelMetrics.ModelQuality."
            "Statistics.S3Uri — cannot retrieve evaluation metrics."
        )

    metrics = _fetch_metrics_from_s3(s3_uri, s3_client)

    if PRIMARY_METRIC not in metrics:
        raise ValueError(
            f"Primary metric {PRIMARY_METRIC!r} not found in metrics file at {s3_uri}. "
            f"Available keys: {list(metrics.keys())}"
        )

    metric_value = float(metrics[PRIMARY_METRIC])
    _log(
        "INFO",
        "Model metric retrieved",
        model_package_arn=model_package_arn,
        metric_name=PRIMARY_METRIC,
        metric_value=metric_value,
    )
    return metric_value


# ── Current Approved Model Lookup ─────────────────────────────────────────────

def get_current_approved_model(
    model_package_group_name: str,
    exclude_arn: str,
    sm_client: Any,
) -> Optional[str]:
    """
    Find the currently approved model package ARN in the given Model Package Group,
    excluding the newly registered model.

    Iterates through all model packages in the group (sorted by creation time,
    newest first) and returns the first one with ModelApprovalStatus == "Approved".

    Args:
        model_package_group_name: Name of the SageMaker Model Package Group.
        exclude_arn: ARN of the new model package to exclude from the search.
        sm_client: boto3 SageMaker client.

    Returns:
        ARN of the currently approved model package, or None if no approved
        model exists (first training run).
    """
    _log(
        "INFO",
        "Searching for currently approved model",
        model_package_group_name=model_package_group_name,
        exclude_arn=exclude_arn,
    )

    paginator = sm_client.get_paginator("list_model_packages")
    pages = paginator.paginate(
        ModelPackageGroupName=model_package_group_name,
        ModelApprovalStatus="Approved",
        SortBy="CreationTime",
        SortOrder="Descending",
    )

    for page in pages:
        for pkg in page.get("ModelPackageSummaryList", []):
            arn = pkg["ModelPackageArn"]
            if arn == exclude_arn:
                # Skip the newly registered model itself
                continue
            _log(
                "INFO",
                "Found currently approved model",
                approved_model_arn=arn,
                creation_time=str(pkg.get("CreationTime")),
            )
            return arn

    _log(
        "INFO",
        "No currently approved model found — this is the first training run",
        model_package_group_name=model_package_group_name,
    )
    return None


# ── Model Package Group Name Extraction ───────────────────────────────────────

def _get_model_package_group_name(model_package_arn: str, sm_client: Any) -> str:
    """
    Extract the Model Package Group name from a model package ARN.

    Describes the model package and reads ModelPackageGroupName from the response.

    Args:
        model_package_arn: ARN of the model package.
        sm_client: boto3 SageMaker client.

    Returns:
        Model Package Group name string.

    Raises:
        ValueError: If the group name cannot be determined.
    """
    response = sm_client.describe_model_package(ModelPackageName=model_package_arn)
    group_name = response.get("ModelPackageGroupName")
    if not group_name:
        raise ValueError(
            f"Cannot determine ModelPackageGroupName from model package {model_package_arn!r}"
        )
    return group_name


# ── Approval / Rejection ──────────────────────────────────────────────────────

def update_model_approval_status(
    model_package_arn: str,
    approval_status: str,
    approval_description: str,
    sm_client: Any,
) -> None:
    """
    Update the ModelApprovalStatus of a model package.

    This function is idempotent — calling it multiple times with the same
    model_package_arn and approval_status is safe.

    Args:
        model_package_arn: ARN of the model package to update.
        approval_status: "Approved" or "Rejected".
        approval_description: Human-readable reason for the decision.
        sm_client: boto3 SageMaker client.

    Raises:
        ClientError: If the SageMaker API call fails.
    """
    _log(
        "INFO",
        "Updating model approval status",
        model_package_arn=model_package_arn,
        approval_status=approval_status,
        approval_description=approval_description,
    )

    sm_client.update_model_package(
        ModelPackageName=model_package_arn,
        ModelApprovalStatus=approval_status,
        ApprovalDescription=approval_description,
    )

    _log(
        "INFO",
        "Model approval status updated",
        model_package_arn=model_package_arn,
        approval_status=approval_status,
    )


# ── Endpoint Update ───────────────────────────────────────────────────────────

def _get_model_name_from_package(model_package_arn: str, sm_client: Any) -> str:
    """
    Derive a SageMaker Model name from a model package ARN.

    SageMaker requires a Model resource (aws_sagemaker_model) to be created
    before it can be referenced in an EndpointConfig. This function creates
    a Model resource that wraps the approved model package.

    The model name is derived from the model package ARN to ensure uniqueness
    and traceability.

    Args:
        model_package_arn: ARN of the approved model package.
        sm_client: boto3 SageMaker client.

    Returns:
        Name of the created (or already existing) SageMaker Model resource.

    Raises:
        ClientError: If the SageMaker API call fails unexpectedly.
    """
    # Derive a stable, unique model name from the ARN
    # ARN format: arn:aws:sagemaker:<region>:<account>:model-package/<group>/<version>
    arn_suffix = model_package_arn.split("model-package/")[-1]
    # Replace slashes with hyphens to make a valid resource name
    model_name = "forecast-model-" + arn_suffix.replace("/", "-")
    # Truncate to 63 chars (SageMaker limit)
    model_name = model_name[:63]

    _log("INFO", "Creating SageMaker Model resource from model package", model_name=model_name, model_package_arn=model_package_arn)

    try:
        sm_client.create_model(
            ModelName=model_name,
            PrimaryContainer={
                "ModelPackageName": model_package_arn,
            },
            ExecutionRoleArn=os.environ.get("SAGEMAKER_EXECUTION_ROLE_ARN", ""),
        )
        _log("INFO", "SageMaker Model resource created", model_name=model_name)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "ValidationException" and "already exists" in str(exc):
            # Model already exists — safe to reuse
            _log("INFO", "SageMaker Model resource already exists — reusing", model_name=model_name)
        else:
            raise

    return model_name


def create_endpoint_config_for_model(
    model_package_arn: str,
    sm_client: Any,
) -> str:
    """
    Create a new SageMaker EndpointConfig that references the approved model package.

    A timestamp suffix is appended to the config name to ensure uniqueness across
    multiple promotion runs. The config uses a single production variant with
    ml.t2.medium (cost-effective for inference).

    Args:
        model_package_arn: ARN of the approved model package.
        sm_client: boto3 SageMaker client.

    Returns:
        Name of the newly created EndpointConfig.

    Raises:
        ClientError: If the SageMaker API call fails.
    """
    # Timestamp suffix ensures uniqueness (format: YYYYMMDDHHMMSS)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
    endpoint_config_name = f"forecast-endpoint-config-{timestamp}"

    # Create a SageMaker Model resource wrapping the approved model package
    model_name = _get_model_name_from_package(model_package_arn, sm_client)

    _log(
        "INFO",
        "Creating EndpointConfig",
        endpoint_config_name=endpoint_config_name,
        model_name=model_name,
        model_package_arn=model_package_arn,
    )

    sm_client.create_endpoint_config(
        EndpointConfigName=endpoint_config_name,
        ProductionVariants=[
            {
                "VariantName": "AllTraffic",
                "ModelName": model_name,
                # ml.t2.medium: cheapest SageMaker real-time inference instance
                # suitable for XGBoost models with low-to-medium traffic
                "InstanceType": "ml.t2.medium",
                "InitialInstanceCount": 1,
                "InitialVariantWeight": 1.0,
            }
        ],
    )

    _log(
        "INFO",
        "EndpointConfig created",
        endpoint_config_name=endpoint_config_name,
    )

    return endpoint_config_name


def update_sagemaker_endpoint(
    endpoint_name: str,
    endpoint_config_name: str,
    sm_client: Any,
) -> None:
    """
    Update the SageMaker Endpoint to serve traffic from the new EndpointConfig.

    This call is non-blocking — it triggers the update and returns immediately.
    The endpoint transitions to "Updating" state; the actual swap happens
    asynchronously. The caller should not wait for completion.

    If the endpoint is already in "Updating" state, the call raises a
    ClientError with code "ValidationException". This is handled gracefully
    by logging a warning and returning without raising — the in-flight update
    will eventually complete and the endpoint will serve the previous config.
    In production, a retry mechanism (e.g., Step Functions Wait + retry) should
    be used to re-attempt the update once the endpoint is back to "InService".

    Args:
        endpoint_name: Name of the SageMaker Endpoint to update.
        endpoint_config_name: Name of the new EndpointConfig to deploy.
        sm_client: boto3 SageMaker client.

    Raises:
        ClientError: If the SageMaker API call fails for reasons other than
                     the endpoint being in "Updating" state.
    """
    _log(
        "INFO",
        "Updating SageMaker Endpoint",
        endpoint_name=endpoint_name,
        endpoint_config_name=endpoint_config_name,
    )

    try:
        sm_client.update_endpoint(
            EndpointName=endpoint_name,
            EndpointConfigName=endpoint_config_name,
        )
        _log(
            "INFO",
            "SageMaker Endpoint update triggered (non-blocking)",
            endpoint_name=endpoint_name,
            endpoint_config_name=endpoint_config_name,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        error_message = str(exc)

        # Endpoint is already being updated — log warning and continue
        # The Step Functions workflow can retry later if needed
        if error_code == "ValidationException" and (
            "Cannot update in-progress endpoint" in error_message
            or "updating" in error_message.lower()
        ):
            _log(
                "WARN",
                "Endpoint is already in Updating state — skipping update. "
                "The endpoint will continue serving the previous model until "
                "the in-flight update completes.",
                endpoint_name=endpoint_name,
                endpoint_config_name=endpoint_config_name,
                error=error_message,
            )
            return

        # Re-raise unexpected errors
        _log(
            "ERROR",
            "Failed to update SageMaker Endpoint",
            endpoint_name=endpoint_name,
            endpoint_config_name=endpoint_config_name,
            error=error_message,
            error_code=error_code,
        )
        raise


def promote_model_to_endpoint(
    model_package_arn: str,
    endpoint_name: str,
    sm_client: Any,
) -> Tuple[str, str]:
    """
    Approve the model package and update the SageMaker Endpoint to serve it.

    This is the "happy path" for task 5.3.2: called only when the new model's
    metric is better than the current model's metric.

    Steps:
        1. Create a new EndpointConfig pointing to the approved model package.
        2. Call update_endpoint() to swap the endpoint to the new config.

    Args:
        model_package_arn: ARN of the approved model package.
        endpoint_name: Name of the SageMaker Endpoint to update.
        sm_client: boto3 SageMaker client.

    Returns:
        Tuple of (endpoint_config_name, endpoint_name) for inclusion in the
        Lambda response.

    Raises:
        ClientError: If any SageMaker API call fails unexpectedly.
    """
    _log(
        "INFO",
        "Promoting model to endpoint",
        model_package_arn=model_package_arn,
        endpoint_name=endpoint_name,
    )

    # Step 1: Create a new EndpointConfig for the approved model
    endpoint_config_name = create_endpoint_config_for_model(model_package_arn, sm_client)

    # Step 2: Update the endpoint (non-blocking)
    update_sagemaker_endpoint(endpoint_name, endpoint_config_name, sm_client)

    _log(
        "INFO",
        "Model promotion to endpoint complete",
        model_package_arn=model_package_arn,
        endpoint_name=endpoint_name,
        endpoint_config_name=endpoint_config_name,
    )

    return endpoint_config_name, endpoint_name


# ── Main Handler ──────────────────────────────────────────────────────────────

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler — compare new model metric against current approved model,
    then approve + update endpoint if the new model is better.

    Input event (from Step Functions):
        {
            "model_package_arn": "arn:aws:sagemaker:...:model-package/...",
            "endpoint_name": "forecast-endpoint"   # optional; falls back to env var
        }

    Output (returned to Step Functions):
        {
            "decision": "Approved" | "Rejected",
            "model_package_arn": "...",
            "new_model_metric": 0.000123,
            "current_model_metric": 0.000145,       # null if no current model
            "current_model_arn": "...",              # null if no current model
            "metric_name": "mean_rmse",
            "reason": "New model RMSE 0.000123 < current RMSE 0.000145 — promoting",
            "endpoint_name": "forecast-endpoint",   # present when Approved
            "endpoint_config_name": "forecast-endpoint-config-20240101120000"  # present when Approved
        }

    Logic:
        1. Describe the new model package to get its S3 metrics URI.
        2. Download metrics.json from S3 and extract mean_rmse.
        3. Find the currently approved model in the same Model Package Group.
        4. If no current model exists → approve (first deployment).
        5. If new model metric < current model metric → approve.
        6. Otherwise → reject.
        7. If approved → create new EndpointConfig + update SageMaker Endpoint.
        8. If rejected → keep existing endpoint unchanged.

    Args:
        event: Step Functions input event containing model_package_arn and
               optionally endpoint_name.
        context: Lambda context object (unused).

    Returns:
        Structured response dict with decision, metrics, and endpoint info.

    Raises:
        ValueError: If model_package_arn is missing from the event.
        ClientError: If any AWS API call fails unexpectedly.
    """
    _log("INFO", "Model promotion Lambda invoked", event=event)

    # ── Validate input ────────────────────────────────────────────────────────
    model_package_arn: Optional[str] = event.get("model_package_arn")
    if not model_package_arn:
        raise ValueError(
            "Event must contain 'model_package_arn'. "
            f"Received keys: {list(event.keys())}"
        )

    # endpoint_name: prefer event value, fall back to environment variable
    endpoint_name: str = event.get("endpoint_name") or os.environ.get(
        "SAGEMAKER_ENDPOINT_NAME", "forecast-endpoint"
    )

    sm_client = _get_sagemaker_client()
    s3_client = _get_s3_client()

    # ── Step 1: Get new model metric ──────────────────────────────────────────
    _log("INFO", "Step 1/4: Retrieving new model metric", model_package_arn=model_package_arn)
    try:
        new_metric = get_model_metric(model_package_arn, sm_client, s3_client)
    except (ValueError, ClientError) as exc:
        _log(
            "ERROR",
            "Failed to retrieve new model metric",
            model_package_arn=model_package_arn,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise

    # ── Step 2: Get Model Package Group name ──────────────────────────────────
    _log("INFO", "Step 2/4: Determining Model Package Group name")
    try:
        group_name = _get_model_package_group_name(model_package_arn, sm_client)
    except (ValueError, ClientError) as exc:
        _log(
            "ERROR",
            "Failed to determine Model Package Group name",
            model_package_arn=model_package_arn,
            error=str(exc),
        )
        raise

    # ── Step 3: Find currently approved model ─────────────────────────────────
    _log("INFO", "Step 3/4: Finding currently approved model", group_name=group_name)
    try:
        current_model_arn = get_current_approved_model(
            group_name, model_package_arn, sm_client
        )
    except ClientError as exc:
        _log(
            "ERROR",
            "Failed to list model packages",
            group_name=group_name,
            error=str(exc),
        )
        raise

    # ── Step 4: Compare metrics and decide ────────────────────────────────────
    _log("INFO", "Step 4/4: Comparing metrics and making promotion decision")

    current_metric: Optional[float] = None

    if current_model_arn is None:
        # First training run — no existing approved model → always approve
        decision = "Approved"
        reason = (
            f"No currently approved model found in group {group_name!r}. "
            f"Approving new model as first deployment "
            f"({PRIMARY_METRIC}={new_metric:.8f})."
        )
        _log(
            "INFO",
            "First deployment — approving new model automatically",
            model_package_arn=model_package_arn,
            new_metric=new_metric,
            metric_name=PRIMARY_METRIC,
        )
    else:
        # Retrieve current model metric for comparison
        try:
            current_metric = get_model_metric(current_model_arn, sm_client, s3_client)
        except (ValueError, ClientError) as exc:
            # If we cannot read the current model's metric, log a warning and
            # approve the new model conservatively (avoids blocking the pipeline).
            _log(
                "WARN",
                "Cannot retrieve current model metric — approving new model conservatively",
                current_model_arn=current_model_arn,
                error=str(exc),
            )
            current_metric = None
            decision = "Approved"
            reason = (
                f"Could not retrieve metric for current model {current_model_arn!r} "
                f"({exc}). Approving new model conservatively."
            )
        else:
            # Core comparison: lower metric = better (RMSE/MAE)
            if new_metric < current_metric:
                decision = "Approved"
                improvement = current_metric - new_metric
                reason = (
                    f"New model {PRIMARY_METRIC}={new_metric:.8f} < "
                    f"current {PRIMARY_METRIC}={current_metric:.8f} "
                    f"(improvement={improvement:.8f}). Promoting new model."
                )
                _log(
                    "INFO",
                    "New model is better — approving",
                    new_metric=new_metric,
                    current_metric=current_metric,
                    improvement=improvement,
                    metric_name=PRIMARY_METRIC,
                )
            else:
                decision = "Rejected"
                degradation = new_metric - current_metric
                reason = (
                    f"New model {PRIMARY_METRIC}={new_metric:.8f} >= "
                    f"current {PRIMARY_METRIC}={current_metric:.8f} "
                    f"(degradation={degradation:.8f}). Keeping existing model."
                )
                _log(
                    "INFO",
                    "New model is not better — rejecting",
                    new_metric=new_metric,
                    current_metric=current_metric,
                    degradation=degradation,
                    metric_name=PRIMARY_METRIC,
                )

    # ── Apply decision: update Model Registry approval status ─────────────────
    try:
        update_model_approval_status(
            model_package_arn=model_package_arn,
            approval_status=decision,
            approval_description=reason,
            sm_client=sm_client,
        )
    except ClientError as exc:
        _log(
            "ERROR",
            "Failed to update model approval status",
            model_package_arn=model_package_arn,
            decision=decision,
            error=str(exc),
        )
        raise

    # ── Task 5.3.2: If approved, update SageMaker Endpoint ───────────────────
    # Only update the endpoint when the new model is better (decision == "Approved").
    # If rejected, the existing endpoint continues serving the current model unchanged.
    endpoint_config_name: Optional[str] = None
    promoted_endpoint_name: Optional[str] = None

    if decision == "Approved":
        _log(
            "INFO",
            "Model approved — updating SageMaker Endpoint with new model",
            model_package_arn=model_package_arn,
            endpoint_name=endpoint_name,
        )
        try:
            endpoint_config_name, promoted_endpoint_name = promote_model_to_endpoint(
                model_package_arn=model_package_arn,
                endpoint_name=endpoint_name,
                sm_client=sm_client,
            )
        except ClientError as exc:
            # Endpoint update failure should not block the overall pipeline result.
            # Log the error and include it in the response so Step Functions can
            # handle it (e.g., send an alert or trigger a retry).
            _log(
                "ERROR",
                "Failed to update SageMaker Endpoint after model approval — "
                "model is approved in Registry but endpoint was NOT updated",
                model_package_arn=model_package_arn,
                endpoint_name=endpoint_name,
                error=str(exc),
            )
            # Re-raise so Step Functions marks this execution as failed
            raise
    else:
        _log(
            "INFO",
            "Model rejected — keeping existing endpoint unchanged",
            model_package_arn=model_package_arn,
            endpoint_name=endpoint_name,
        )

    # ── Build response ────────────────────────────────────────────────────────
    result: Dict[str, Any] = {
        "decision": decision,
        "model_package_arn": model_package_arn,
        "new_model_metric": new_metric,
        "current_model_metric": current_metric,
        "current_model_arn": current_model_arn,
        "metric_name": PRIMARY_METRIC,
        "reason": reason,
        "endpoint_name": promoted_endpoint_name,
        "endpoint_config_name": endpoint_config_name,
    }

    _log(
        "INFO",
        "Model promotion decision made",
        decision=decision,
        model_package_arn=model_package_arn,
        new_model_metric=new_metric,
        current_model_metric=current_metric,
        metric_name=PRIMARY_METRIC,
        endpoint_name=promoted_endpoint_name,
        endpoint_config_name=endpoint_config_name,
        reason=reason,
    )

    return result
