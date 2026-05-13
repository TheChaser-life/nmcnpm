"""
Integration tests for Forecast Service

Tests the full request/response cycle using Flask's test client.
All external dependencies (JWKS, SageMaker) are mocked.

**Validates: Requirements 9.1, 9.2, 9.3, 9.4**
"""

import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

import botocore.exceptions

# Add parent directory to path so we can import forecast_service
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import forecast_service as fs
from forecast_service import (
    JWKSCache,
    JWTVerifier,
    MissingTokenError,
    TokenExpiredError,
    InvalidTokenError,
    PremiumRequiredError,
    create_app,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_premium_verifier(premium: bool = True) -> MagicMock:
    """Create a mock JWTVerifier that simulates a user with the given premium status."""
    mock_verifier = MagicMock(spec=JWTVerifier)
    mock_verifier.extract_token_from_header.return_value = "mock.jwt.token"
    mock_verifier.verify.return_value = {
        "sub": "user-123",
        "email": "user@example.com",
        "custom:premium": premium,
    }
    if premium:
        mock_verifier.check_premium.return_value = None
    else:
        mock_verifier.check_premium.side_effect = PremiumRequiredError(
            "Premium subscription required"
        )
    return mock_verifier


def _make_sagemaker_client(result: dict = None, error=None) -> MagicMock:
    """Create a mock SageMaker client."""
    mock_client = MagicMock()
    if error:
        mock_client.invoke.side_effect = error
    else:
        mock_client.invoke.return_value = result or {
            "currency_code": "USD",
            "forecast": [0.000043, 0.000044, 0.000042],
            "model_version": "v1.0",
        }
    return mock_client


# ── Integration Tests ─────────────────────────────────────────────────────────

class TestForecastIntegration(unittest.TestCase):
    """Integration tests for the full request/response cycle."""

    def _make_app(self, verifier=None, sagemaker=None):
        """Create a Flask test app with the given dependencies."""
        return create_app(
            jwks_cache=MagicMock(spec=JWKSCache),
            jwt_verifier=verifier or _make_premium_verifier(premium=True),
            sagemaker_client=sagemaker or _make_sagemaker_client(),
        )

    # ── Health endpoint ───────────────────────────────────────────────────────

    def test_health_endpoint_returns_200(self):
        """GET /health should return 200 with status ok."""
        app = self._make_app()
        client = app.test_client()

        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "ok")

    # ── 401 cases ─────────────────────────────────────────────────────────────

    def test_forecast_without_auth_returns_401(self):
        """GET /forecast/{code} without Authorization header should return 401."""
        mock_verifier = MagicMock(spec=JWTVerifier)
        mock_verifier.extract_token_from_header.side_effect = MissingTokenError(
            "Authorization header required"
        )

        app = self._make_app(verifier=mock_verifier)
        client = app.test_client()

        response = client.get("/forecast/USD")

        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "missing_token")
        self.assertIn("message", data)

    def test_forecast_with_expired_token_returns_401(self):
        """GET /forecast/{code} with expired token should return 401."""
        mock_verifier = MagicMock(spec=JWTVerifier)
        mock_verifier.extract_token_from_header.return_value = "expired.token"
        mock_verifier.verify.side_effect = TokenExpiredError("Token has expired")

        app = self._make_app(verifier=mock_verifier)
        client = app.test_client()

        response = client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer expired.token"},
        )

        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "token_expired")
        self.assertIn("message", data)

    def test_forecast_with_invalid_token_returns_401(self):
        """GET /forecast/{code} with invalid/malformed token should return 401."""
        mock_verifier = MagicMock(spec=JWTVerifier)
        mock_verifier.extract_token_from_header.return_value = "bad.token"
        mock_verifier.verify.side_effect = InvalidTokenError("Token is invalid")

        app = self._make_app(verifier=mock_verifier)
        client = app.test_client()

        response = client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer bad.token"},
        )

        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "invalid_token")
        self.assertIn("message", data)

    # ── 403 cases ─────────────────────────────────────────────────────────────

    def test_forecast_with_standard_user_returns_403(self):
        """GET /forecast/{code} with non-premium JWT should return 403."""
        mock_verifier = _make_premium_verifier(premium=False)

        app = self._make_app(verifier=mock_verifier)
        client = app.test_client()

        response = client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer standard.token"},
        )

        self.assertEqual(response.status_code, 403)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "forbidden")
        self.assertIn("message", data)

    # ── 200 cases ─────────────────────────────────────────────────────────────

    def test_forecast_with_premium_user_and_sagemaker_success_returns_200(self):
        """GET /forecast/{code} with premium JWT and working SageMaker should return 200."""
        mock_verifier = _make_premium_verifier(premium=True)
        mock_sagemaker = _make_sagemaker_client(result={
            "currency_code": "USD",
            "forecast": [0.000043, 0.000044, 0.000042],
            "model_version": "v1.0",
        })

        app = self._make_app(verifier=mock_verifier, sagemaker=mock_sagemaker)
        client = app.test_client()

        response = client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer premium.token"},
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["currency_code"], "USD")
        self.assertIn("forecast", data)

    # ── 503 cases ─────────────────────────────────────────────────────────────

    def test_forecast_with_premium_user_and_sagemaker_unavailable_returns_503(self):
        """GET /forecast/{code} when SageMaker is unavailable should return 503."""
        mock_verifier = _make_premium_verifier(premium=True)
        error_response = {
            "Error": {"Code": "ModelError", "Message": "Endpoint not found"}
        }
        mock_sagemaker = _make_sagemaker_client(
            error=botocore.exceptions.ClientError(error_response, "InvokeEndpoint")
        )

        app = self._make_app(verifier=mock_verifier, sagemaker=mock_sagemaker)
        client = app.test_client()

        response = client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer premium.token"},
        )

        self.assertEqual(response.status_code, 503)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "service_unavailable")
        self.assertIn("message", data)

    # ── Response structure ────────────────────────────────────────────────────

    def test_forecast_response_contains_required_fields(self):
        """Successful forecast response must contain currency_code and forecast fields."""
        mock_verifier = _make_premium_verifier(premium=True)
        mock_sagemaker = _make_sagemaker_client(result={
            "currency_code": "EUR",
            "forecast": [0.000039, 0.000040, 0.000038],
            "model_version": "v2.1",
        })

        app = self._make_app(verifier=mock_verifier, sagemaker=mock_sagemaker)
        client = app.test_client()

        response = client.get(
            "/forecast/EUR",
            headers={"Authorization": "Bearer premium.token"},
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        # Required fields
        self.assertIn("currency_code", data)
        self.assertIn("forecast", data)

        # Validate types
        self.assertIsInstance(data["currency_code"], str)
        self.assertIsInstance(data["forecast"], list)

    def test_forecast_sagemaker_called_with_correct_currency_code(self):
        """SageMaker should be invoked with the currency code from the URL path."""
        mock_verifier = _make_premium_verifier(premium=True)
        mock_sagemaker = _make_sagemaker_client(result={
            "currency_code": "JPY",
            "forecast": [0.0065],
            "model_version": "v1.0",
        })

        app = self._make_app(verifier=mock_verifier, sagemaker=mock_sagemaker)
        client = app.test_client()

        client.get(
            "/forecast/JPY",
            headers={"Authorization": "Bearer premium.token"},
        )

        mock_sagemaker.invoke.assert_called_once_with("JPY")

    def test_forecast_401_response_has_error_and_message_fields(self):
        """401 responses must include 'error' and 'message' fields."""
        mock_verifier = MagicMock(spec=JWTVerifier)
        mock_verifier.extract_token_from_header.side_effect = MissingTokenError(
            "Authorization header required"
        )

        app = self._make_app(verifier=mock_verifier)
        client = app.test_client()

        response = client.get("/forecast/USD")

        data = json.loads(response.data)
        self.assertIn("error", data)
        self.assertIn("message", data)

    def test_forecast_403_response_has_error_and_message_fields(self):
        """403 responses must include 'error' and 'message' fields."""
        mock_verifier = _make_premium_verifier(premium=False)

        app = self._make_app(verifier=mock_verifier)
        client = app.test_client()

        response = client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer standard.token"},
        )

        data = json.loads(response.data)
        self.assertIn("error", data)
        self.assertIn("message", data)

    def test_forecast_503_response_has_error_and_message_fields(self):
        """503 responses must include 'error' and 'message' fields."""
        mock_verifier = _make_premium_verifier(premium=True)
        error_response = {"Error": {"Code": "ServiceUnavailable", "Message": "Down"}}
        mock_sagemaker = _make_sagemaker_client(
            error=botocore.exceptions.ClientError(error_response, "InvokeEndpoint")
        )

        app = self._make_app(verifier=mock_verifier, sagemaker=mock_sagemaker)
        client = app.test_client()

        response = client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer premium.token"},
        )

        data = json.loads(response.data)
        self.assertIn("error", data)
        self.assertIn("message", data)


if __name__ == "__main__":
    unittest.main()
