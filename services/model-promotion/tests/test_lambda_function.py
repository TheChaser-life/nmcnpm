"""
Unit tests for Model Promotion Lambda.

Tests cover:
- New model is better (lower RMSE) → decision "Approved"
- New model is not better (higher or equal RMSE) → decision "Rejected"
- No existing approved model (first deployment) → decision "Approved"
- Missing metrics in model package (no S3Uri) → raises ValueError
- Missing primary metric key in metrics JSON → raises ValueError
- Idempotency: calling lambda_handler twice with same ARN is safe
- Structured response contains all required keys
- Task 5.3.2: When approved, create_endpoint_config + update_endpoint are called
- Task 5.3.2: When rejected, endpoint is NOT updated
- Task 5.3.2: Endpoint already updating → graceful handling (no exception raised)
- Task 5.3.2: Endpoint update failure → exception propagated

All AWS API calls are mocked with unittest.mock — no real AWS calls are made.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

# Add parent directory to path so we can import lambda_function
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lambda_function


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_describe_model_package_response(
    group_name: str,
    s3_uri: str,
    approval_status: str = "PendingManualApproval",
) -> dict:
    """Build a minimal describe_model_package API response."""
    return {
        "ModelPackageGroupName": group_name,
        "ModelApprovalStatus": approval_status,
        "ModelMetrics": {
            "ModelQuality": {
                "Statistics": {
                    "ContentType": "application/json",
                    "S3Uri": s3_uri,
                }
            }
        },
    }


def _make_metrics_json(mean_rmse: float, mean_mae: float = None) -> str:
    """Build a metrics.json payload as a JSON string."""
    if mean_mae is None:
        mean_mae = mean_rmse * 0.8
    return json.dumps({
        "mean_rmse": mean_rmse,
        "mean_mae": mean_mae,
        "rmse_by_currency": {"USD": mean_rmse},
        "mae_by_currency": {"USD": mean_mae},
    })


def _make_s3_get_object_response(body_str: str) -> dict:
    """Build a minimal S3 get_object response with a streaming body."""
    mock_body = MagicMock()
    mock_body.read.return_value = body_str.encode("utf-8")
    return {"Body": mock_body}


# ── Tests: get_model_metric ───────────────────────────────────────────────────

class TestGetModelMetric(unittest.TestCase):
    """Tests for get_model_metric()."""

    def test_returns_mean_rmse_from_s3(self):
        """Should return the mean_rmse value from the metrics.json file in S3."""
        sm_client = MagicMock()
        s3_client = MagicMock()

        sm_client.describe_model_package.return_value = _make_describe_model_package_response(
            group_name="forecast_model_registry",
            s3_uri="s3://my-bucket/model-artifacts/job-1/output/metrics.json",
        )
        s3_client.get_object.return_value = _make_s3_get_object_response(
            _make_metrics_json(mean_rmse=0.000123)
        )

        result = lambda_function.get_model_metric(
            "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/1",
            sm_client,
            s3_client,
        )

        self.assertAlmostEqual(result, 0.000123)

    def test_raises_value_error_when_no_model_metrics(self):
        """Should raise ValueError when model package has no ModelMetrics."""
        sm_client = MagicMock()
        s3_client = MagicMock()

        sm_client.describe_model_package.return_value = {
            "ModelPackageGroupName": "forecast_model_registry",
            "ModelApprovalStatus": "PendingManualApproval",
            "ModelMetrics": {},  # empty — no ModelQuality
        }

        with self.assertRaises(ValueError) as ctx:
            lambda_function.get_model_metric(
                "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/1",
                sm_client,
                s3_client,
            )

        self.assertIn("S3Uri", str(ctx.exception))

    def test_raises_value_error_when_s3_uri_missing(self):
        """Should raise ValueError when Statistics has no S3Uri."""
        sm_client = MagicMock()
        s3_client = MagicMock()

        sm_client.describe_model_package.return_value = {
            "ModelPackageGroupName": "forecast_model_registry",
            "ModelApprovalStatus": "PendingManualApproval",
            "ModelMetrics": {
                "ModelQuality": {
                    "Statistics": {
                        "ContentType": "application/json",
                        # S3Uri intentionally missing
                    }
                }
            },
        }

        with self.assertRaises(ValueError) as ctx:
            lambda_function.get_model_metric(
                "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/1",
                sm_client,
                s3_client,
            )

        self.assertIn("S3Uri", str(ctx.exception))

    def test_raises_value_error_when_primary_metric_missing_from_json(self):
        """Should raise ValueError when metrics.json does not contain the primary metric key."""
        sm_client = MagicMock()
        s3_client = MagicMock()

        sm_client.describe_model_package.return_value = _make_describe_model_package_response(
            group_name="forecast_model_registry",
            s3_uri="s3://my-bucket/model-artifacts/job-1/output/metrics.json",
        )
        # metrics.json is missing mean_rmse
        s3_client.get_object.return_value = _make_s3_get_object_response(
            json.dumps({"mean_mae": 0.0001})
        )

        with self.assertRaises(ValueError) as ctx:
            lambda_function.get_model_metric(
                "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/1",
                sm_client,
                s3_client,
            )

        self.assertIn("mean_rmse", str(ctx.exception))

    def test_raises_value_error_for_invalid_s3_uri(self):
        """Should raise ValueError when S3Uri does not start with s3://."""
        sm_client = MagicMock()
        s3_client = MagicMock()

        sm_client.describe_model_package.return_value = _make_describe_model_package_response(
            group_name="forecast_model_registry",
            s3_uri="https://not-an-s3-uri/metrics.json",
        )

        with self.assertRaises(ValueError) as ctx:
            lambda_function.get_model_metric(
                "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/1",
                sm_client,
                s3_client,
            )

        self.assertIn("Invalid S3 URI", str(ctx.exception))


# ── Tests: get_current_approved_model ────────────────────────────────────────

class TestGetCurrentApprovedModel(unittest.TestCase):
    """Tests for get_current_approved_model()."""

    def test_returns_arn_of_approved_model(self):
        """Should return the ARN of the most recently approved model."""
        sm_client = MagicMock()

        approved_arn = "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/1"
        new_arn = "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/2"

        paginator = MagicMock()
        sm_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "ModelPackageSummaryList": [
                    {"ModelPackageArn": approved_arn, "CreationTime": "2024-01-01"},
                ]
            }
        ]

        result = lambda_function.get_current_approved_model(
            "forecast_model_registry", new_arn, sm_client
        )

        self.assertEqual(result, approved_arn)

    def test_returns_none_when_no_approved_model_exists(self):
        """Should return None when there are no approved models (first run)."""
        sm_client = MagicMock()

        paginator = MagicMock()
        sm_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{"ModelPackageSummaryList": []}]

        result = lambda_function.get_current_approved_model(
            "forecast_model_registry",
            "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/1",
            sm_client,
        )

        self.assertIsNone(result)

    def test_excludes_the_new_model_arn_from_results(self):
        """Should skip the new model's own ARN when searching for the current approved model."""
        sm_client = MagicMock()

        new_arn = "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/2"
        old_arn = "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/1"

        paginator = MagicMock()
        sm_client.get_paginator.return_value = paginator
        # List returns new_arn first (newest), then old_arn
        paginator.paginate.return_value = [
            {
                "ModelPackageSummaryList": [
                    {"ModelPackageArn": new_arn, "CreationTime": "2024-01-02"},
                    {"ModelPackageArn": old_arn, "CreationTime": "2024-01-01"},
                ]
            }
        ]

        result = lambda_function.get_current_approved_model(
            "forecast_model_registry", new_arn, sm_client
        )

        # Should skip new_arn and return old_arn
        self.assertEqual(result, old_arn)


# ── Tests: lambda_handler ─────────────────────────────────────────────────────

class TestLambdaHandler(unittest.TestCase):
    """Integration-style tests for lambda_handler() with all AWS calls mocked."""

    NEW_ARN = "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/2"
    OLD_ARN = "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/1"
    GROUP_NAME = "forecast_model_registry"
    NEW_METRICS_URI = "s3://my-bucket/model-artifacts/job-2/output/metrics.json"
    OLD_METRICS_URI = "s3://my-bucket/model-artifacts/job-1/output/metrics.json"

    def _setup_sm_client(
        self,
        new_rmse: float,
        current_rmse: float = None,
        has_current_model: bool = True,
    ):
        """
        Build a mock SageMaker client for lambda_handler tests.

        Returns (sm_client, s3_client) tuple.
        """
        sm_client = MagicMock()
        s3_client = MagicMock()

        # describe_model_package: first call = new model, second call = current model
        new_response = _make_describe_model_package_response(
            group_name=self.GROUP_NAME,
            s3_uri=self.NEW_METRICS_URI,
        )

        if has_current_model and current_rmse is not None:
            old_response = _make_describe_model_package_response(
                group_name=self.GROUP_NAME,
                s3_uri=self.OLD_METRICS_URI,
                approval_status="Approved",
            )
            sm_client.describe_model_package.side_effect = [new_response, new_response, old_response]
        else:
            sm_client.describe_model_package.return_value = new_response

        # list_model_packages paginator
        paginator = MagicMock()
        sm_client.get_paginator.return_value = paginator

        if has_current_model:
            paginator.paginate.return_value = [
                {
                    "ModelPackageSummaryList": [
                        {"ModelPackageArn": self.OLD_ARN, "CreationTime": "2024-01-01"},
                    ]
                }
            ]
        else:
            paginator.paginate.return_value = [{"ModelPackageSummaryList": []}]

        # S3 get_object: first call = new model metrics, second call = current model metrics
        new_s3_response = _make_s3_get_object_response(_make_metrics_json(new_rmse))
        if has_current_model and current_rmse is not None:
            old_s3_response = _make_s3_get_object_response(_make_metrics_json(current_rmse))
            s3_client.get_object.side_effect = [new_s3_response, old_s3_response]
        else:
            s3_client.get_object.return_value = new_s3_response

        return sm_client, s3_client

    def test_approves_when_new_model_is_better(self):
        """lambda_handler should return 'Approved' when new model RMSE < current RMSE."""
        sm_client, s3_client = self._setup_sm_client(
            new_rmse=0.000100,
            current_rmse=0.000150,
            has_current_model=True,
        )

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN}, None
            )

        self.assertEqual(result["decision"], "Approved")
        self.assertAlmostEqual(result["new_model_metric"], 0.000100)
        self.assertAlmostEqual(result["current_model_metric"], 0.000150)
        self.assertEqual(result["model_package_arn"], self.NEW_ARN)
        self.assertEqual(result["current_model_arn"], self.OLD_ARN)

        # Verify update_model_package was called with "Approved"
        sm_client.update_model_package.assert_called_once()
        call_kwargs = sm_client.update_model_package.call_args[1]
        self.assertEqual(call_kwargs["ModelApprovalStatus"], "Approved")

    def test_rejects_when_new_model_is_worse(self):
        """lambda_handler should return 'Rejected' when new model RMSE > current RMSE."""
        sm_client, s3_client = self._setup_sm_client(
            new_rmse=0.000200,
            current_rmse=0.000150,
            has_current_model=True,
        )

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN}, None
            )

        self.assertEqual(result["decision"], "Rejected")
        self.assertAlmostEqual(result["new_model_metric"], 0.000200)
        self.assertAlmostEqual(result["current_model_metric"], 0.000150)

        # Verify update_model_package was called with "Rejected"
        sm_client.update_model_package.assert_called_once()
        call_kwargs = sm_client.update_model_package.call_args[1]
        self.assertEqual(call_kwargs["ModelApprovalStatus"], "Rejected")

    def test_rejects_when_new_model_metric_equals_current(self):
        """lambda_handler should return 'Rejected' when new RMSE == current RMSE (not strictly better)."""
        sm_client, s3_client = self._setup_sm_client(
            new_rmse=0.000150,
            current_rmse=0.000150,
            has_current_model=True,
        )

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN}, None
            )

        self.assertEqual(result["decision"], "Rejected")

    def test_approves_when_no_current_model_exists(self):
        """lambda_handler should approve the new model when no approved model exists (first run)."""
        sm_client, s3_client = self._setup_sm_client(
            new_rmse=0.000123,
            has_current_model=False,
        )

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN}, None
            )

        self.assertEqual(result["decision"], "Approved")
        self.assertIsNone(result["current_model_metric"])
        self.assertIsNone(result["current_model_arn"])

        # Verify update_model_package was called with "Approved"
        sm_client.update_model_package.assert_called_once()
        call_kwargs = sm_client.update_model_package.call_args[1]
        self.assertEqual(call_kwargs["ModelApprovalStatus"], "Approved")

    def test_raises_value_error_when_model_package_arn_missing(self):
        """lambda_handler should raise ValueError when event has no model_package_arn."""
        with self.assertRaises(ValueError) as ctx:
            lambda_function.lambda_handler({}, None)

        self.assertIn("model_package_arn", str(ctx.exception))

    def test_raises_value_error_when_metrics_missing_from_model_package(self):
        """lambda_handler should raise ValueError when model package has no ModelMetrics."""
        sm_client = MagicMock()
        s3_client = MagicMock()

        # describe_model_package returns a response with no ModelMetrics
        sm_client.describe_model_package.return_value = {
            "ModelPackageGroupName": self.GROUP_NAME,
            "ModelApprovalStatus": "PendingManualApproval",
            "ModelMetrics": {},
        }

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            with self.assertRaises(ValueError):
                lambda_function.lambda_handler(
                    {"model_package_arn": self.NEW_ARN}, None
                )

    def test_response_contains_all_required_keys(self):
        """lambda_handler response must contain all required keys for Step Functions."""
        sm_client, s3_client = self._setup_sm_client(
            new_rmse=0.000100,
            current_rmse=0.000150,
            has_current_model=True,
        )

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN}, None
            )

        required_keys = {
            "decision",
            "model_package_arn",
            "new_model_metric",
            "current_model_metric",
            "current_model_arn",
            "metric_name",
            "reason",
            "endpoint_name",
            "endpoint_config_name",
        }
        self.assertEqual(required_keys, set(result.keys()))

    def test_idempotency_calling_twice_with_same_arn(self):
        """Calling lambda_handler twice with the same model_package_arn should be safe."""
        sm_client = MagicMock()
        s3_client = MagicMock()

        # Both calls return the same describe response
        describe_response = _make_describe_model_package_response(
            group_name=self.GROUP_NAME,
            s3_uri=self.NEW_METRICS_URI,
        )
        sm_client.describe_model_package.return_value = describe_response

        paginator = MagicMock()
        sm_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{"ModelPackageSummaryList": []}]

        s3_client.get_object.return_value = _make_s3_get_object_response(
            _make_metrics_json(0.000123)
        )

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result1 = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN}, None
            )
            result2 = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN}, None
            )

        # Both calls should produce the same decision
        self.assertEqual(result1["decision"], result2["decision"])
        self.assertEqual(result1["decision"], "Approved")

    def test_metric_name_in_response_matches_primary_metric(self):
        """The metric_name field in the response should match PRIMARY_METRIC."""
        sm_client, s3_client = self._setup_sm_client(
            new_rmse=0.000100,
            has_current_model=False,
        )

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN}, None
            )

        self.assertEqual(result["metric_name"], lambda_function.PRIMARY_METRIC)

    def test_reason_field_is_non_empty_string(self):
        """The reason field in the response should be a non-empty string."""
        sm_client, s3_client = self._setup_sm_client(
            new_rmse=0.000100,
            current_rmse=0.000150,
            has_current_model=True,
        )

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN}, None
            )

        self.assertIsInstance(result["reason"], str)
        self.assertGreater(len(result["reason"]), 0)


# ── Tests: _fetch_metrics_from_s3 ────────────────────────────────────────────

class TestFetchMetricsFromS3(unittest.TestCase):
    """Tests for _fetch_metrics_from_s3()."""

    def test_parses_valid_metrics_json(self):
        """Should parse and return the metrics dict from a valid S3 object."""
        s3_client = MagicMock()
        s3_client.get_object.return_value = _make_s3_get_object_response(
            _make_metrics_json(0.000123)
        )

        result = lambda_function._fetch_metrics_from_s3(
            "s3://my-bucket/path/to/metrics.json", s3_client
        )

        self.assertIn("mean_rmse", result)
        self.assertAlmostEqual(result["mean_rmse"], 0.000123)

    def test_raises_value_error_for_invalid_json(self):
        """Should raise ValueError when S3 object contains invalid JSON."""
        s3_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"not-valid-json{{{"
        s3_client.get_object.return_value = {"Body": mock_body}

        with self.assertRaises(ValueError) as ctx:
            lambda_function._fetch_metrics_from_s3(
                "s3://my-bucket/path/to/metrics.json", s3_client
            )

        self.assertIn("parse", str(ctx.exception).lower())

    def test_raises_value_error_for_non_s3_uri(self):
        """Should raise ValueError when URI does not start with s3://."""
        s3_client = MagicMock()

        with self.assertRaises(ValueError) as ctx:
            lambda_function._fetch_metrics_from_s3(
                "https://example.com/metrics.json", s3_client
            )

        self.assertIn("Invalid S3 URI", str(ctx.exception))

    def test_raises_value_error_for_uri_without_key(self):
        """Should raise ValueError when URI has no key path (only bucket)."""
        s3_client = MagicMock()

        with self.assertRaises(ValueError):
            lambda_function._fetch_metrics_from_s3("s3://bucket-only", s3_client)


if __name__ == "__main__":
    unittest.main()


# ── Tests: create_endpoint_config_for_model (Task 5.3.2) ─────────────────────

class TestCreateEndpointConfigForModel(unittest.TestCase):
    """Tests for create_endpoint_config_for_model() — Task 5.3.2."""

    MODEL_PACKAGE_ARN = (
        "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/5"
    )

    def test_creates_endpoint_config_with_timestamp_suffix(self):
        """Should create an EndpointConfig with a timestamp-based unique name."""
        sm_client = MagicMock()
        # create_model succeeds
        sm_client.create_model.return_value = {}
        # create_endpoint_config succeeds
        sm_client.create_endpoint_config.return_value = {}

        config_name = lambda_function.create_endpoint_config_for_model(
            self.MODEL_PACKAGE_ARN, sm_client
        )

        # Name should start with the expected prefix
        self.assertTrue(
            config_name.startswith("forecast-endpoint-config-"),
            f"Expected name to start with 'forecast-endpoint-config-', got: {config_name!r}",
        )
        # Name should have a timestamp suffix (14 digits: YYYYMMDDHHMMSS)
        suffix = config_name[len("forecast-endpoint-config-"):]
        self.assertEqual(len(suffix), 14, f"Expected 14-digit timestamp suffix, got: {suffix!r}")
        self.assertTrue(suffix.isdigit(), f"Expected numeric timestamp suffix, got: {suffix!r}")

    def test_calls_create_endpoint_config_with_correct_model_name(self):
        """Should call create_endpoint_config with the model name derived from the package ARN."""
        sm_client = MagicMock()
        sm_client.create_model.return_value = {}
        sm_client.create_endpoint_config.return_value = {}

        lambda_function.create_endpoint_config_for_model(self.MODEL_PACKAGE_ARN, sm_client)

        # Verify create_endpoint_config was called once
        sm_client.create_endpoint_config.assert_called_once()
        call_kwargs = sm_client.create_endpoint_config.call_args[1]

        # Verify ProductionVariants contains exactly one variant
        variants = call_kwargs["ProductionVariants"]
        self.assertEqual(len(variants), 1)

        # Verify the variant references the model derived from the ARN
        variant = variants[0]
        self.assertIn("ModelName", variant)
        self.assertTrue(
            variant["ModelName"].startswith("forecast-model-"),
            f"Expected ModelName to start with 'forecast-model-', got: {variant['ModelName']!r}",
        )
        self.assertEqual(variant["VariantName"], "AllTraffic")
        self.assertEqual(variant["InitialInstanceCount"], 1)

    def test_reuses_existing_model_resource_when_already_exists(self):
        """Should not raise when create_model returns 'already exists' ValidationException."""
        from botocore.exceptions import ClientError as BotoCoreClientError

        sm_client = MagicMock()

        # Simulate create_model raising "already exists" ValidationException
        error_response = {
            "Error": {
                "Code": "ValidationException",
                "Message": "Model with name forecast-model-xxx already exists",
            }
        }
        sm_client.create_model.side_effect = BotoCoreClientError(
            error_response, "CreateModel"
        )
        sm_client.create_endpoint_config.return_value = {}

        # Should not raise — reuses existing model
        config_name = lambda_function.create_endpoint_config_for_model(
            self.MODEL_PACKAGE_ARN, sm_client
        )

        self.assertTrue(config_name.startswith("forecast-endpoint-config-"))
        sm_client.create_endpoint_config.assert_called_once()

    def test_propagates_unexpected_create_model_error(self):
        """Should re-raise ClientError when create_model fails for unexpected reasons."""
        from botocore.exceptions import ClientError as BotoCoreClientError

        sm_client = MagicMock()

        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform sagemaker:CreateModel",
            }
        }
        sm_client.create_model.side_effect = BotoCoreClientError(
            error_response, "CreateModel"
        )

        with self.assertRaises(BotoCoreClientError):
            lambda_function.create_endpoint_config_for_model(
                self.MODEL_PACKAGE_ARN, sm_client
            )


# ── Tests: update_sagemaker_endpoint (Task 5.3.2) ────────────────────────────

class TestUpdateSageMakerEndpoint(unittest.TestCase):
    """Tests for update_sagemaker_endpoint() — Task 5.3.2."""

    ENDPOINT_NAME = "forecast-endpoint"
    CONFIG_NAME = "forecast-endpoint-config-20240101120000"

    def test_calls_update_endpoint_with_correct_args(self):
        """Should call update_endpoint with the correct endpoint and config names."""
        sm_client = MagicMock()
        sm_client.update_endpoint.return_value = {}

        lambda_function.update_sagemaker_endpoint(
            self.ENDPOINT_NAME, self.CONFIG_NAME, sm_client
        )

        sm_client.update_endpoint.assert_called_once_with(
            EndpointName=self.ENDPOINT_NAME,
            EndpointConfigName=self.CONFIG_NAME,
        )

    def test_handles_endpoint_already_updating_gracefully(self):
        """Should not raise when endpoint is already in Updating state."""
        from botocore.exceptions import ClientError as BotoCoreClientError

        sm_client = MagicMock()

        error_response = {
            "Error": {
                "Code": "ValidationException",
                "Message": "Cannot update in-progress endpoint forecast-endpoint",
            }
        }
        sm_client.update_endpoint.side_effect = BotoCoreClientError(
            error_response, "UpdateEndpoint"
        )

        # Should NOT raise — graceful handling
        lambda_function.update_sagemaker_endpoint(
            self.ENDPOINT_NAME, self.CONFIG_NAME, sm_client
        )

    def test_handles_updating_state_in_message(self):
        """Should not raise when error message contains 'updating' (case-insensitive)."""
        from botocore.exceptions import ClientError as BotoCoreClientError

        sm_client = MagicMock()

        error_response = {
            "Error": {
                "Code": "ValidationException",
                "Message": "Endpoint is currently updating, please try again later",
            }
        }
        sm_client.update_endpoint.side_effect = BotoCoreClientError(
            error_response, "UpdateEndpoint"
        )

        # Should NOT raise
        lambda_function.update_sagemaker_endpoint(
            self.ENDPOINT_NAME, self.CONFIG_NAME, sm_client
        )

    def test_propagates_unexpected_update_endpoint_error(self):
        """Should re-raise ClientError for unexpected errors (e.g., AccessDenied)."""
        from botocore.exceptions import ClientError as BotoCoreClientError

        sm_client = MagicMock()

        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform sagemaker:UpdateEndpoint",
            }
        }
        sm_client.update_endpoint.side_effect = BotoCoreClientError(
            error_response, "UpdateEndpoint"
        )

        with self.assertRaises(BotoCoreClientError):
            lambda_function.update_sagemaker_endpoint(
                self.ENDPOINT_NAME, self.CONFIG_NAME, sm_client
            )


# ── Tests: lambda_handler endpoint update integration (Task 5.3.2) ────────────

class TestLambdaHandlerEndpointUpdate(unittest.TestCase):
    """
    Integration-style tests for the endpoint update path in lambda_handler.

    Task 5.3.2: When the new model is approved (better metric), the handler
    must create a new EndpointConfig and call update_endpoint.
    When rejected, the endpoint must NOT be touched.
    """

    NEW_ARN = "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/2"
    OLD_ARN = "arn:aws:sagemaker:ap-southeast-2:123456789012:model-package/forecast_model_registry/1"
    GROUP_NAME = "forecast_model_registry"
    NEW_METRICS_URI = "s3://my-bucket/model-artifacts/job-2/output/metrics.json"
    OLD_METRICS_URI = "s3://my-bucket/model-artifacts/job-1/output/metrics.json"
    ENDPOINT_NAME = "forecast-endpoint"

    def _build_clients(self, new_rmse: float, current_rmse: float):
        """Build mock sm_client and s3_client for a two-model comparison scenario."""
        sm_client = MagicMock()
        s3_client = MagicMock()

        new_response = {
            "ModelPackageGroupName": self.GROUP_NAME,
            "ModelApprovalStatus": "PendingManualApproval",
            "ModelMetrics": {
                "ModelQuality": {
                    "Statistics": {
                        "ContentType": "application/json",
                        "S3Uri": self.NEW_METRICS_URI,
                    }
                }
            },
        }
        old_response = {
            "ModelPackageGroupName": self.GROUP_NAME,
            "ModelApprovalStatus": "Approved",
            "ModelMetrics": {
                "ModelQuality": {
                    "Statistics": {
                        "ContentType": "application/json",
                        "S3Uri": self.OLD_METRICS_URI,
                    }
                }
            },
        }
        # describe_model_package: call 1 = new model (metric), call 2 = new model (group name), call 3 = old model (metric)
        sm_client.describe_model_package.side_effect = [new_response, new_response, old_response]

        paginator = MagicMock()
        sm_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "ModelPackageSummaryList": [
                    {"ModelPackageArn": self.OLD_ARN, "CreationTime": "2024-01-01"},
                ]
            }
        ]

        new_s3 = MagicMock()
        new_s3.read.return_value = json.dumps({"mean_rmse": new_rmse, "mean_mae": new_rmse * 0.8}).encode()
        old_s3 = MagicMock()
        old_s3.read.return_value = json.dumps({"mean_rmse": current_rmse, "mean_mae": current_rmse * 0.8}).encode()
        s3_client.get_object.side_effect = [{"Body": new_s3}, {"Body": old_s3}]

        # Endpoint-related calls succeed by default
        sm_client.create_model.return_value = {}
        sm_client.create_endpoint_config.return_value = {}
        sm_client.update_endpoint.return_value = {}
        sm_client.update_model_package.return_value = {}

        return sm_client, s3_client

    def test_approved_model_triggers_endpoint_update(self):
        """
        Task 5.3.2: When new model RMSE < current RMSE, lambda_handler must call
        create_endpoint_config and update_endpoint.
        """
        sm_client, s3_client = self._build_clients(new_rmse=0.000100, current_rmse=0.000150)

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN, "endpoint_name": self.ENDPOINT_NAME},
                None,
            )

        self.assertEqual(result["decision"], "Approved")

        # create_endpoint_config must have been called
        sm_client.create_endpoint_config.assert_called_once()

        # update_endpoint must have been called with the correct endpoint name
        sm_client.update_endpoint.assert_called_once()
        update_kwargs = sm_client.update_endpoint.call_args[1]
        self.assertEqual(update_kwargs["EndpointName"], self.ENDPOINT_NAME)

        # Response must include endpoint_name and endpoint_config_name
        self.assertEqual(result["endpoint_name"], self.ENDPOINT_NAME)
        self.assertIsNotNone(result["endpoint_config_name"])
        self.assertTrue(result["endpoint_config_name"].startswith("forecast-endpoint-config-"))

    def test_rejected_model_does_not_update_endpoint(self):
        """
        Task 5.3.2: When new model RMSE >= current RMSE, lambda_handler must NOT
        call create_endpoint_config or update_endpoint.
        """
        sm_client, s3_client = self._build_clients(new_rmse=0.000200, current_rmse=0.000150)

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN, "endpoint_name": self.ENDPOINT_NAME},
                None,
            )

        self.assertEqual(result["decision"], "Rejected")

        # Neither create_endpoint_config nor update_endpoint should be called
        sm_client.create_endpoint_config.assert_not_called()
        sm_client.update_endpoint.assert_not_called()

        # endpoint_name and endpoint_config_name should be None in the response
        self.assertIsNone(result["endpoint_name"])
        self.assertIsNone(result["endpoint_config_name"])

    def test_endpoint_name_falls_back_to_env_variable(self):
        """
        Task 5.3.2: When endpoint_name is not in the event, it should fall back
        to the SAGEMAKER_ENDPOINT_NAME environment variable.
        """
        sm_client, s3_client = self._build_clients(new_rmse=0.000100, current_rmse=0.000150)

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client), \
             patch.dict(os.environ, {"SAGEMAKER_ENDPOINT_NAME": "env-forecast-endpoint"}):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN},  # no endpoint_name in event
                None,
            )

        self.assertEqual(result["decision"], "Approved")
        self.assertEqual(result["endpoint_name"], "env-forecast-endpoint")

        update_kwargs = sm_client.update_endpoint.call_args[1]
        self.assertEqual(update_kwargs["EndpointName"], "env-forecast-endpoint")

    def test_endpoint_update_failure_propagates_exception(self):
        """
        Task 5.3.2: If update_endpoint raises an unexpected ClientError,
        lambda_handler must re-raise it so Step Functions marks the execution as failed.
        """
        from botocore.exceptions import ClientError as BotoCoreClientError

        sm_client, s3_client = self._build_clients(new_rmse=0.000100, current_rmse=0.000150)

        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Not authorized to update endpoint",
            }
        }
        sm_client.update_endpoint.side_effect = BotoCoreClientError(
            error_response, "UpdateEndpoint"
        )

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            with self.assertRaises(BotoCoreClientError):
                lambda_function.lambda_handler(
                    {"model_package_arn": self.NEW_ARN, "endpoint_name": self.ENDPOINT_NAME},
                    None,
                )

    def test_approved_response_contains_all_required_keys(self):
        """
        Task 5.3.2: The response for an approved model must contain all required keys
        including the new endpoint_name and endpoint_config_name fields.
        """
        sm_client, s3_client = self._build_clients(new_rmse=0.000100, current_rmse=0.000150)

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN, "endpoint_name": self.ENDPOINT_NAME},
                None,
            )

        required_keys = {
            "decision",
            "model_package_arn",
            "new_model_metric",
            "current_model_metric",
            "current_model_arn",
            "metric_name",
            "reason",
            "endpoint_name",
            "endpoint_config_name",
        }
        self.assertEqual(required_keys, set(result.keys()))

    def test_first_deployment_also_updates_endpoint(self):
        """
        Task 5.3.2: On first deployment (no current approved model), the handler
        must also create EndpointConfig and update the endpoint.
        """
        sm_client = MagicMock()
        s3_client = MagicMock()

        describe_response = {
            "ModelPackageGroupName": self.GROUP_NAME,
            "ModelApprovalStatus": "PendingManualApproval",
            "ModelMetrics": {
                "ModelQuality": {
                    "Statistics": {
                        "ContentType": "application/json",
                        "S3Uri": self.NEW_METRICS_URI,
                    }
                }
            },
        }
        sm_client.describe_model_package.return_value = describe_response

        paginator = MagicMock()
        sm_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{"ModelPackageSummaryList": []}]

        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({"mean_rmse": 0.000123, "mean_mae": 0.0001}).encode()
        s3_client.get_object.return_value = {"Body": mock_body}

        sm_client.create_model.return_value = {}
        sm_client.create_endpoint_config.return_value = {}
        sm_client.update_endpoint.return_value = {}
        sm_client.update_model_package.return_value = {}

        with patch.object(lambda_function, "_get_sagemaker_client", return_value=sm_client), \
             patch.object(lambda_function, "_get_s3_client", return_value=s3_client):
            result = lambda_function.lambda_handler(
                {"model_package_arn": self.NEW_ARN, "endpoint_name": self.ENDPOINT_NAME},
                None,
            )

        self.assertEqual(result["decision"], "Approved")
        sm_client.create_endpoint_config.assert_called_once()
        sm_client.update_endpoint.assert_called_once()
        self.assertEqual(result["endpoint_name"], self.ENDPOINT_NAME)


if __name__ == "__main__":
    unittest.main()
