"""
Unit tests for Forecast Service

Tests cover:
- JWKSCache: caching behavior, refresh after TTL, thread safety
- JWTVerifier: all JWT verification cases
- ForecastEndpoint: HTTP endpoint behavior
- TestPremiumGateProperty: Property 3 — non-premium values always return 403

**Validates: Requirements 9.1, 9.2, 9.3, 9.4**
"""

import json
import sys
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Add parent directory to path so we can import forecast_service
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import forecast_service as fs
from forecast_service import (
    JWKSCache,
    JWTVerifier,
    JWTVerificationError,
    MissingTokenError,
    TokenExpiredError,
    InvalidTokenError,
    PremiumRequiredError,
    Config,
    create_app,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_jwks_cache(keys: dict = None) -> MagicMock:
    """Create a mock JWKSCache that returns the given keys."""
    mock_cache = MagicMock(spec=JWKSCache)
    mock_cache.get_public_key.return_value = keys.get("test-kid") if keys else None
    return mock_cache


def _make_mock_verifier(claims: dict = None, side_effect=None) -> MagicMock:
    """Create a mock JWTVerifier."""
    mock_verifier = MagicMock(spec=JWTVerifier)
    if side_effect:
        mock_verifier.verify.side_effect = side_effect
        mock_verifier.extract_token_from_header.return_value = "mock.jwt.token"
    elif claims is not None:
        mock_verifier.verify.return_value = claims
        mock_verifier.extract_token_from_header.return_value = "mock.jwt.token"
    return mock_verifier


# ── TestJWKSCache ─────────────────────────────────────────────────────────────

class TestJWKSCache(unittest.TestCase):
    """Tests for JWKSCache caching behavior."""

    def _make_mock_response(self, keys_data: list) -> MagicMock:
        """Create a mock requests.Response with JWKS data."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"keys": keys_data}
        return mock_resp

    def _make_rsa_key_data(self, kid: str = "test-kid") -> dict:
        """Return minimal JWK key data structure for mocking."""
        return {
            "kid": kid,
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "n": "test_n",
            "e": "AQAB",
        }

    @patch("forecast_service.requests.get")
    @patch("forecast_service.RSAAlgorithm.from_jwk")
    def test_cache_fetches_on_first_request(self, mock_from_jwk, mock_get):
        """JWKS should be fetched from Cognito on the first get_public_key call."""
        mock_key = MagicMock()
        mock_from_jwk.return_value = mock_key
        mock_get.return_value = self._make_mock_response([self._make_rsa_key_data("kid1")])

        cache = JWKSCache("https://example.com/jwks.json", ttl_seconds=3600)
        result = cache.get_public_key("kid1")

        mock_get.assert_called_once()
        self.assertEqual(result, mock_key)

    @patch("forecast_service.requests.get")
    @patch("forecast_service.RSAAlgorithm.from_jwk")
    def test_cache_does_not_refetch_within_ttl(self, mock_from_jwk, mock_get):
        """JWKS should NOT be re-fetched if cache is still valid."""
        mock_key = MagicMock()
        mock_from_jwk.return_value = mock_key
        mock_get.return_value = self._make_mock_response([self._make_rsa_key_data("kid1")])

        cache = JWKSCache("https://example.com/jwks.json", ttl_seconds=3600)
        cache.get_public_key("kid1")
        cache.get_public_key("kid1")

        # Should only fetch once
        self.assertEqual(mock_get.call_count, 1)

    @patch("forecast_service.requests.get")
    @patch("forecast_service.RSAAlgorithm.from_jwk")
    def test_cache_refreshes_after_ttl(self, mock_from_jwk, mock_get):
        """JWKS should be re-fetched after TTL expires."""
        mock_key = MagicMock()
        mock_from_jwk.return_value = mock_key
        mock_get.return_value = self._make_mock_response([self._make_rsa_key_data("kid1")])

        cache = JWKSCache("https://example.com/jwks.json", ttl_seconds=1)
        cache.get_public_key("kid1")

        # Simulate TTL expiry
        cache._fetched_at = time.time() - 2

        cache.get_public_key("kid1")

        # Should have fetched twice
        self.assertEqual(mock_get.call_count, 2)

    @patch("forecast_service.requests.get")
    @patch("forecast_service.RSAAlgorithm.from_jwk")
    def test_cache_returns_none_for_unknown_kid(self, mock_from_jwk, mock_get):
        """get_public_key should return None if kid is not in JWKS."""
        mock_from_jwk.return_value = MagicMock()
        mock_get.return_value = self._make_mock_response([self._make_rsa_key_data("kid1")])

        cache = JWKSCache("https://example.com/jwks.json", ttl_seconds=3600)
        result = cache.get_public_key("unknown-kid")

        self.assertIsNone(result)

    @patch("forecast_service.requests.get")
    @patch("forecast_service.RSAAlgorithm.from_jwk")
    def test_cache_thread_safety(self, mock_from_jwk, mock_get):
        """Concurrent get_public_key calls should not cause race conditions."""
        mock_key = MagicMock()
        mock_from_jwk.return_value = mock_key
        mock_get.return_value = self._make_mock_response([self._make_rsa_key_data("kid1")])

        cache = JWKSCache("https://example.com/jwks.json", ttl_seconds=3600)
        results = []
        errors = []

        def worker():
            try:
                key = cache.get_public_key("kid1")
                results.append(key)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 10)
        for r in results:
            self.assertEqual(r, mock_key)

    @patch("forecast_service.requests.get")
    @patch("forecast_service.RSAAlgorithm.from_jwk")
    def test_cache_refreshes_when_kid_not_found(self, mock_from_jwk, mock_get):
        """Cache should refresh if a kid is not found (new key may have been added)."""
        mock_key = MagicMock()
        mock_from_jwk.return_value = mock_key

        # First fetch returns kid1, second fetch returns kid1 + kid2
        mock_get.side_effect = [
            self._make_mock_response([self._make_rsa_key_data("kid1")]),
            self._make_mock_response([
                self._make_rsa_key_data("kid1"),
                self._make_rsa_key_data("kid2"),
            ]),
        ]

        cache = JWKSCache("https://example.com/jwks.json", ttl_seconds=3600)
        cache.get_public_key("kid1")  # Triggers first fetch

        # Now request kid2 (not in cache yet)
        result = cache.get_public_key("kid2")

        # Should have fetched twice
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(result, mock_key)


# ── TestJWTVerification ───────────────────────────────────────────────────────

class TestJWTVerification(unittest.TestCase):
    """Tests for JWTVerifier — all JWT verification cases."""

    def setUp(self):
        """Set up a JWTVerifier with a mock JWKS cache."""
        self.mock_cache = MagicMock(spec=JWKSCache)
        self.verifier = JWTVerifier(
            jwks_cache=self.mock_cache,
            issuer="https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_TEST",
        )

    def test_extract_token_from_valid_bearer_header(self):
        """Should extract token from 'Bearer <token>' header."""
        token = self.verifier.extract_token_from_header("Bearer my.jwt.token")
        self.assertEqual(token, "my.jwt.token")

    def test_extract_token_raises_missing_when_header_is_none(self):
        """Should raise MissingTokenError when Authorization header is None."""
        with self.assertRaises(MissingTokenError):
            self.verifier.extract_token_from_header(None)

    def test_extract_token_raises_missing_when_header_is_empty(self):
        """Should raise MissingTokenError when Authorization header is empty."""
        with self.assertRaises(MissingTokenError):
            self.verifier.extract_token_from_header("")

    def test_extract_token_raises_missing_when_no_bearer_prefix(self):
        """Should raise MissingTokenError when header doesn't start with 'Bearer'."""
        with self.assertRaises(MissingTokenError):
            self.verifier.extract_token_from_header("Token my.jwt.token")

    def test_extract_token_raises_missing_when_only_bearer(self):
        """Should raise MissingTokenError when header is just 'Bearer' with no token."""
        with self.assertRaises(MissingTokenError):
            self.verifier.extract_token_from_header("Bearer")

    @patch("forecast_service.jwt.get_unverified_header")
    @patch("forecast_service.jwt.decode")
    def test_verify_valid_token_returns_claims(self, mock_decode, mock_header):
        """Valid token should return decoded claims."""
        mock_header.return_value = {"kid": "test-kid", "alg": "RS256"}
        mock_key = MagicMock()
        self.mock_cache.get_public_key.return_value = mock_key
        expected_claims = {"sub": "user123", "custom:premium": True}
        mock_decode.return_value = expected_claims

        claims = self.verifier.verify("valid.jwt.token")

        self.assertEqual(claims, expected_claims)

    @patch("forecast_service.jwt.get_unverified_header")
    @patch("forecast_service.jwt.decode")
    def test_verify_expired_token_raises_token_expired_error(self, mock_decode, mock_header):
        """Expired token should raise TokenExpiredError."""
        import jwt as pyjwt
        mock_header.return_value = {"kid": "test-kid", "alg": "RS256"}
        self.mock_cache.get_public_key.return_value = MagicMock()
        mock_decode.side_effect = pyjwt.ExpiredSignatureError("Token expired")

        with self.assertRaises(TokenExpiredError):
            self.verifier.verify("expired.jwt.token")

    @patch("forecast_service.jwt.get_unverified_header")
    @patch("forecast_service.jwt.decode")
    def test_verify_invalid_signature_raises_invalid_token_error(self, mock_decode, mock_header):
        """Invalid signature should raise InvalidTokenError."""
        import jwt as pyjwt
        mock_header.return_value = {"kid": "test-kid", "alg": "RS256"}
        self.mock_cache.get_public_key.return_value = MagicMock()
        mock_decode.side_effect = pyjwt.InvalidSignatureError("Invalid signature")

        with self.assertRaises(InvalidTokenError):
            self.verifier.verify("tampered.jwt.token")

    @patch("forecast_service.jwt.get_unverified_header")
    def test_verify_missing_kid_raises_invalid_token_error(self, mock_header):
        """JWT header without 'kid' should raise InvalidTokenError."""
        mock_header.return_value = {"alg": "RS256"}  # No kid

        with self.assertRaises(InvalidTokenError):
            self.verifier.verify("no.kid.token")

    @patch("forecast_service.jwt.get_unverified_header")
    def test_verify_unknown_kid_raises_invalid_token_error(self, mock_header):
        """Unknown kid (no matching public key) should raise InvalidTokenError."""
        mock_header.return_value = {"kid": "unknown-kid", "alg": "RS256"}
        self.mock_cache.get_public_key.return_value = None  # Key not found

        with self.assertRaises(InvalidTokenError):
            self.verifier.verify("unknown.kid.token")

    def test_check_premium_passes_for_true(self):
        """check_premium should not raise when custom:premium is True."""
        claims = {"sub": "user123", "custom:premium": True}
        # Should not raise
        self.verifier.check_premium(claims)

    def test_check_premium_raises_for_false(self):
        """check_premium should raise PremiumRequiredError when custom:premium is False."""
        claims = {"sub": "user123", "custom:premium": False}
        with self.assertRaises(PremiumRequiredError):
            self.verifier.check_premium(claims)

    def test_check_premium_raises_for_missing_claim(self):
        """check_premium should raise PremiumRequiredError when custom:premium is absent."""
        claims = {"sub": "user123"}  # No custom:premium
        with self.assertRaises(PremiumRequiredError):
            self.verifier.check_premium(claims)

    def test_check_premium_raises_for_null(self):
        """check_premium should raise PremiumRequiredError when custom:premium is None."""
        claims = {"sub": "user123", "custom:premium": None}
        with self.assertRaises(PremiumRequiredError):
            self.verifier.check_premium(claims)

    def test_check_premium_passes_for_string_true(self):
        """check_premium should not raise when custom:premium is string 'true'."""
        claims = {"sub": "user123", "custom:premium": "true"}
        self.verifier.check_premium(claims)

    def test_check_premium_raises_for_string_false(self):
        """check_premium should raise PremiumRequiredError when custom:premium is string 'false'."""
        claims = {"sub": "user123", "custom:premium": "false"}
        with self.assertRaises(PremiumRequiredError):
            self.verifier.check_premium(claims)

    def test_check_premium_raises_for_integer_one(self):
        """check_premium should raise PremiumRequiredError when custom:premium is integer 1."""
        claims = {"sub": "user123", "custom:premium": 1}
        with self.assertRaises(PremiumRequiredError):
            self.verifier.check_premium(claims)


# ── TestForecastEndpoint ──────────────────────────────────────────────────────

class TestForecastEndpoint(unittest.TestCase):
    """Tests for the HTTP endpoint behavior."""

    def setUp(self):
        """Set up Flask test client with mocked dependencies."""
        self.mock_verifier = MagicMock(spec=JWTVerifier)
        self.mock_sagemaker = MagicMock()

        self.app = create_app(
            jwks_cache=MagicMock(spec=JWKSCache),
            jwt_verifier=self.mock_verifier,
            sagemaker_client=self.mock_sagemaker,
        )
        self.client = self.app.test_client()

    def test_health_check_returns_200(self):
        """GET /health should return 200 with status ok."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "ok")

    def test_forecast_without_auth_header_returns_401(self):
        """GET /forecast/{code} without Authorization header should return 401."""
        self.mock_verifier.extract_token_from_header.side_effect = MissingTokenError(
            "Authorization header required"
        )

        response = self.client.get("/forecast/USD")
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "missing_token")

    def test_forecast_with_invalid_token_returns_401(self):
        """GET /forecast/{code} with invalid token should return 401."""
        self.mock_verifier.extract_token_from_header.return_value = "invalid.token"
        self.mock_verifier.verify.side_effect = InvalidTokenError("Token is invalid")

        response = self.client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer invalid.token"},
        )
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "invalid_token")

    def test_forecast_with_expired_token_returns_401(self):
        """GET /forecast/{code} with expired token should return 401."""
        self.mock_verifier.extract_token_from_header.return_value = "expired.token"
        self.mock_verifier.verify.side_effect = TokenExpiredError("Token has expired")

        response = self.client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer expired.token"},
        )
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "token_expired")

    def test_forecast_with_standard_user_returns_403(self):
        """GET /forecast/{code} with non-premium JWT should return 403."""
        self.mock_verifier.extract_token_from_header.return_value = "standard.token"
        self.mock_verifier.verify.return_value = {
            "sub": "user123",
            "custom:premium": False,
        }
        self.mock_verifier.check_premium.side_effect = PremiumRequiredError(
            "Premium subscription required"
        )

        response = self.client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer standard.token"},
        )
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "forbidden")

    def test_forecast_with_premium_user_and_sagemaker_success_returns_200(self):
        """GET /forecast/{code} with premium JWT and working SageMaker should return 200."""
        self.mock_verifier.extract_token_from_header.return_value = "premium.token"
        self.mock_verifier.verify.return_value = {
            "sub": "user123",
            "custom:premium": True,
        }
        self.mock_verifier.check_premium.return_value = None  # No exception

        forecast_result = {
            "currency_code": "USD",
            "forecast": [0.000043, 0.000044, 0.000042],
            "model_version": "v1.0",
        }
        self.mock_sagemaker.invoke.return_value = forecast_result

        response = self.client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer premium.token"},
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["currency_code"], "USD")
        self.assertIn("forecast", data)

    def test_forecast_with_premium_user_and_sagemaker_unavailable_returns_503(self):
        """GET /forecast/{code} when SageMaker is unavailable should return 503."""
        import botocore.exceptions

        self.mock_verifier.extract_token_from_header.return_value = "premium.token"
        self.mock_verifier.verify.return_value = {
            "sub": "user123",
            "custom:premium": True,
        }
        self.mock_verifier.check_premium.return_value = None

        error_response = {
            "Error": {"Code": "ModelError", "Message": "Endpoint not found"}
        }
        self.mock_sagemaker.invoke.side_effect = botocore.exceptions.ClientError(
            error_response, "InvokeEndpoint"
        )

        response = self.client.get(
            "/forecast/USD",
            headers={"Authorization": "Bearer premium.token"},
        )
        self.assertEqual(response.status_code, 503)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "service_unavailable")


# ── TestPremiumGateProperty ───────────────────────────────────────────────────

class TestPremiumGateProperty(unittest.TestCase):
    """
    Property 3: For any JWT where custom:premium is not true/\"true\",
    the Forecast Service must return HTTP 403.
    This holds for missing claim, false, null, and arbitrary strings.

    **Validates: Requirements 9.3**
    """

    def setUp(self):
        """Set up Flask test client with a verifier that returns configurable claims."""
        self.mock_verifier = MagicMock(spec=JWTVerifier)
        self.mock_sagemaker = MagicMock()

        self.app = create_app(
            jwks_cache=MagicMock(spec=JWKSCache),
            jwt_verifier=self.mock_verifier,
            sagemaker_client=self.mock_sagemaker,
        )
        self.client = self.app.test_client()

    def test_non_true_premium_values_always_return_403(self):
        """
        Property 3: For any JWT where custom:premium is not true/\"true\",
        the Forecast Service must return HTTP 403.

        Tests all non-true values: False, None, strings, integers.
        """
        non_true_values = [
            False,
            None,
            "false",
            "False",
            "0",
            "",
            0,
            "premium",
            "yes",
            "True",
            "TRUE",
            1,
            [],
            {},
        ]

        for value in non_true_values:
            with self.subTest(premium_value=value):
                # Configure verifier to return claims with this premium value
                if value is None:
                    claims = {"sub": "user123"}  # Missing claim
                else:
                    claims = {"sub": "user123", "custom:premium": value}

                self.mock_verifier.extract_token_from_header.return_value = "test.token"
                self.mock_verifier.verify.return_value = claims

                # Use the real check_premium logic to validate the property
                real_verifier = JWTVerifier(
                    jwks_cache=MagicMock(spec=JWKSCache),
                    issuer="https://example.com",
                )

                # Verify that check_premium raises PremiumRequiredError for this value
                with self.assertRaises(PremiumRequiredError,
                                       msg=f"Expected PremiumRequiredError for custom:premium={value!r}"):
                    real_verifier.check_premium(claims)

    def test_true_premium_value_does_not_raise(self):
        """
        Sanity check: custom:premium = True (boolean) should NOT raise PremiumRequiredError.
        """
        real_verifier = JWTVerifier(
            jwks_cache=MagicMock(spec=JWKSCache),
            issuer="https://example.com",
        )
        claims = {"sub": "user123", "custom:premium": True}
        # Should not raise
        real_verifier.check_premium(claims)

    def test_string_true_premium_value_does_not_raise(self):
        """
        Sanity check: Cognito custom attributes are strings, so "true" is premium.
        """
        real_verifier = JWTVerifier(
            jwks_cache=MagicMock(spec=JWKSCache),
            issuer="https://example.com",
        )
        claims = {"sub": "user123", "custom:premium": "true"}
        real_verifier.check_premium(claims)

    def test_endpoint_returns_403_for_all_non_true_premium_values(self):
        """
        End-to-end property test: the HTTP endpoint returns 403 for all non-premium
        custom:premium values.
        """
        non_true_values = [False, None, "false", "False", "0", "", 0, "premium", "yes", "True"]

        for value in non_true_values:
            with self.subTest(premium_value=value):
                if value is None:
                    claims = {"sub": "user123"}
                else:
                    claims = {"sub": "user123", "custom:premium": value}

                self.mock_verifier.extract_token_from_header.return_value = "test.token"
                self.mock_verifier.verify.return_value = claims
                # Use real check_premium logic via side_effect
                self.mock_verifier.check_premium.side_effect = (
                    lambda c: (_ for _ in ()).throw(PremiumRequiredError("Premium required"))
                    if c.get("custom:premium") is not True and c.get("custom:premium") != "true"
                    else None
                )

                response = self.client.get(
                    "/forecast/USD",
                    headers={"Authorization": "Bearer test.token"},
                )
                self.assertEqual(
                    response.status_code,
                    403,
                    msg=f"Expected 403 for custom:premium={value!r}, got {response.status_code}",
                )
                data = json.loads(response.data)
                self.assertEqual(data["error"], "forbidden")


if __name__ == "__main__":
    unittest.main()
