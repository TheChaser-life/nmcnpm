"""
Unit tests for Money Service — POST /exchange, POST /topup, POST /premium/upgrade endpoints

Tests cover:
- JWTVerifier: token extraction and verification
- ExchangeRateCache: rate calculation logic
- IdempotencyCache: get/set behavior
- execute_exchange: optimistic locking, insufficient balance
- execute_premium_upgrade: balance deduction, idempotency, optimistic locking
- PremiumReconciliationJob: retry Cognito update for pending users
- POST /exchange endpoint: all HTTP response codes
- POST /topup endpoint: all HTTP response codes
- POST /premium/upgrade endpoint: all HTTP response codes

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 10.1, 10.2, 10.3, 10.4, 10.6**
"""

import json
import sys
import os
import time
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

# Add parent directory to path so we can import money_service
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import money_service as ms
from money_service import (
    Config,
    JWKSCache,
    JWTVerifier,
    MissingTokenError,
    TokenExpiredError,
    InvalidTokenError,
    ExchangeRateCache,
    IdempotencyCache,
    DatabaseClient,
    InsufficientBalanceError,
    OptimisticLockConflictError,
    execute_exchange,
    execute_topup,
    execute_premium_upgrade,
    get_premium_fee_from_ssm,
    update_cognito_premium_attribute,
    mark_cognito_update_complete,
    get_users_pending_cognito_update,
    AlreadyPremiumError,
    PremiumReconciliationJob,
    create_app,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_verifier(claims=None, side_effect=None):
    mock = MagicMock(spec=JWTVerifier)
    if side_effect:
        mock.verify.side_effect = side_effect
        mock.extract_token_from_header.return_value = "mock.jwt.token"
    elif claims is not None:
        mock.verify.return_value = claims
        mock.extract_token_from_header.return_value = "mock.jwt.token"
    return mock


def _make_mock_rate_cache(rates=None):
    """rates: dict mapping (from, to) -> float"""
    mock = MagicMock(spec=ExchangeRateCache)
    if rates is not None:
        def get_rate(from_c, to_c):
            return rates.get((from_c.upper(), to_c.upper()))
        mock.get_rate.side_effect = get_rate
    return mock


def _make_mock_idem_cache(cached=None):
    mock = MagicMock(spec=IdempotencyCache)
    mock.get.return_value = cached
    return mock


def _make_mock_db():
    mock = MagicMock(spec=DatabaseClient)
    mock._ensure_connected.return_value = None
    return mock


# ── TestJWTVerifier ───────────────────────────────────────────────────────────

class TestJWTVerifier(unittest.TestCase):
    """Tests for JWTVerifier token extraction."""

    def setUp(self):
        self.mock_cache = MagicMock(spec=JWKSCache)
        self.verifier = JWTVerifier(
            jwks_cache=self.mock_cache,
            issuer="https://cognito-idp.ap-southeast-1.amazonaws.com/test",
        )

    def test_extract_valid_bearer_token(self):
        token = self.verifier.extract_token_from_header("Bearer my.jwt.token")
        self.assertEqual(token, "my.jwt.token")

    def test_extract_raises_missing_when_none(self):
        with self.assertRaises(MissingTokenError):
            self.verifier.extract_token_from_header(None)

    def test_extract_raises_missing_when_empty(self):
        with self.assertRaises(MissingTokenError):
            self.verifier.extract_token_from_header("")

    def test_extract_raises_missing_when_no_bearer_prefix(self):
        with self.assertRaises(MissingTokenError):
            self.verifier.extract_token_from_header("Token abc")

    def test_extract_raises_missing_when_only_bearer(self):
        with self.assertRaises(MissingTokenError):
            self.verifier.extract_token_from_header("Bearer")

    @patch("money_service.jwt.get_unverified_header")
    @patch("money_service.jwt.decode")
    def test_verify_valid_token_returns_claims(self, mock_decode, mock_header):
        mock_header.return_value = {"kid": "kid1", "alg": "RS256"}
        self.mock_cache.get_public_key.return_value = MagicMock()
        expected = {"sub": "user-123"}
        mock_decode.return_value = expected
        result = self.verifier.verify("valid.token")
        self.assertEqual(result, expected)

    @patch("money_service.jwt.get_unverified_header")
    @patch("money_service.jwt.decode")
    def test_verify_expired_token_raises(self, mock_decode, mock_header):
        import jwt as pyjwt
        mock_header.return_value = {"kid": "kid1"}
        self.mock_cache.get_public_key.return_value = MagicMock()
        mock_decode.side_effect = pyjwt.ExpiredSignatureError("expired")
        with self.assertRaises(TokenExpiredError):
            self.verifier.verify("expired.token")

    @patch("money_service.jwt.get_unverified_header")
    @patch("money_service.jwt.decode")
    def test_verify_invalid_token_raises(self, mock_decode, mock_header):
        import jwt as pyjwt
        mock_header.return_value = {"kid": "kid1"}
        self.mock_cache.get_public_key.return_value = MagicMock()
        mock_decode.side_effect = pyjwt.InvalidSignatureError("bad sig")
        with self.assertRaises(InvalidTokenError):
            self.verifier.verify("bad.token")

    @patch("money_service.jwt.get_unverified_header")
    def test_verify_missing_kid_raises(self, mock_header):
        mock_header.return_value = {"alg": "RS256"}
        with self.assertRaises(InvalidTokenError):
            self.verifier.verify("no.kid.token")

    def test_get_cognito_sub_returns_sub(self):
        claims = {"sub": "user-abc-123"}
        result = self.verifier.get_cognito_sub(claims)
        self.assertEqual(result, "user-abc-123")

    def test_get_cognito_sub_raises_when_missing(self):
        with self.assertRaises(InvalidTokenError):
            self.verifier.get_cognito_sub({})


# ── TestExchangeRateCacheLogic ────────────────────────────────────────────────

class TestExchangeRateCacheLogic(unittest.TestCase):
    """Tests for exchange rate calculation logic (without real Redis)."""

    def _make_cache_with_redis(self, redis_data):
        """Create ExchangeRateCache with a mocked Redis client."""
        with patch("money_service.redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_cls.return_value = mock_redis

            def mock_get(key):
                return redis_data.get(key)

            mock_redis.get.side_effect = mock_get
            cache = ExchangeRateCache()
            cache.client = mock_redis
            return cache

    def test_same_currency_returns_1(self):
        cache = self._make_cache_with_redis({})
        result = cache.get_rate("USD", "USD")
        self.assertEqual(result, 1.0)

    def test_vnd_to_foreign_returns_direct_rate(self):
        redis_data = {
            "exchange_rate:USD": json.dumps({"currency": "USD", "rate": 0.000043}),
        }
        cache = self._make_cache_with_redis(redis_data)
        result = cache.get_rate("VND", "USD")
        self.assertAlmostEqual(result, 0.000043, places=8)

    def test_foreign_to_vnd_returns_inverse(self):
        redis_data = {
            "exchange_rate:USD": json.dumps({"currency": "USD", "rate": 0.000043}),
        }
        cache = self._make_cache_with_redis(redis_data)
        result = cache.get_rate("USD", "VND")
        expected = 1.0 / 0.000043
        self.assertAlmostEqual(result, expected, places=2)

    def test_cross_rate_calculation(self):
        # 1 VND = 0.000043 USD, 1 VND = 0.000039 EUR
        # 1 USD = (0.000039 / 0.000043) EUR
        redis_data = {
            "exchange_rate:USD": json.dumps({"currency": "USD", "rate": 0.000043}),
            "exchange_rate:EUR": json.dumps({"currency": "EUR", "rate": 0.000039}),
        }
        cache = self._make_cache_with_redis(redis_data)
        result = cache.get_rate("USD", "EUR")
        expected = 0.000039 / 0.000043
        self.assertAlmostEqual(result, expected, places=6)

    def test_missing_currency_returns_none(self):
        cache = self._make_cache_with_redis({})
        result = cache.get_rate("VND", "XYZ")
        self.assertIsNone(result)


# ── TestIdempotencyCache ──────────────────────────────────────────────────────

class TestIdempotencyCache(unittest.TestCase):
    """Tests for IdempotencyCache get/set behavior."""

    def _make_cache(self):
        with patch("money_service.redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_cls.return_value = mock_redis
            cache = IdempotencyCache()
            cache.client = mock_redis
            return cache, mock_redis

    def test_get_returns_none_when_key_not_found(self):
        cache, mock_redis = self._make_cache()
        mock_redis.hget.return_value = None
        result = cache.get("nonexistent-key")
        self.assertIsNone(result)

    def test_get_returns_parsed_result_when_found(self):
        cache, mock_redis = self._make_cache()
        stored = {"transaction_id": "tx-123", "amount": 100.0}
        mock_redis.hget.return_value = json.dumps(stored)
        result = cache.get("existing-key")
        self.assertEqual(result["transaction_id"], "tx-123")

    def test_set_stores_result_and_timestamp(self):
        cache, mock_redis = self._make_cache()
        result = {"transaction_id": "tx-456"}
        cache.set("my-key", result)
        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        self.assertIn("result", call_args.kwargs.get("mapping", {}))
        self.assertIn("created_at", call_args.kwargs.get("mapping", {}))

    def test_set_does_not_set_ttl(self):
        """Idempotency cache must NOT set TTL (noeviction policy)."""
        cache, mock_redis = self._make_cache()
        cache.set("my-key", {"data": "value"})
        mock_redis.expire.assert_not_called()
        mock_redis.setex.assert_not_called()


# ── TestExchangeEndpoint ──────────────────────────────────────────────────────

class TestExchangeEndpoint(unittest.TestCase):
    """Tests for POST /exchange HTTP endpoint behavior."""

    def _make_app(self, verifier=None, rate_cache=None, idem_cache=None, db=None):
        app = create_app(
            jwt_verifier=verifier,
            exchange_rate_cache=rate_cache,
            idempotency_cache=idem_cache,
            db_client=db,
        )
        return app.test_client()

    def test_health_check_returns_200(self):
        client = self._make_app()
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.data)["status"], "ok")

    def test_missing_auth_header_returns_401(self):
        verifier = MagicMock(spec=JWTVerifier)
        verifier.extract_token_from_header.side_effect = MissingTokenError("required")
        client = self._make_app(verifier=verifier)
        resp = client.post("/exchange",
                           headers={"Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"from_currency": "USD", "to_currency": "EUR", "amount": 100})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(json.loads(resp.data)["error"], "missing_token")

    def test_expired_token_returns_401(self):
        verifier = MagicMock(spec=JWTVerifier)
        verifier.extract_token_from_header.return_value = "expired.token"
        verifier.verify.side_effect = TokenExpiredError("expired")
        client = self._make_app(verifier=verifier)
        resp = client.post("/exchange",
                           headers={"Authorization": "Bearer expired.token",
                                    "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"from_currency": "USD", "to_currency": "EUR", "amount": 100})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(json.loads(resp.data)["error"], "token_expired")

    def test_invalid_token_returns_401(self):
        verifier = MagicMock(spec=JWTVerifier)
        verifier.extract_token_from_header.return_value = "bad.token"
        verifier.verify.side_effect = InvalidTokenError("invalid")
        client = self._make_app(verifier=verifier)
        resp = client.post("/exchange",
                           headers={"Authorization": "Bearer bad.token",
                                    "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"from_currency": "USD", "to_currency": "EUR", "amount": 100})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(json.loads(resp.data)["error"], "invalid_token")

    def test_missing_idempotency_key_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        client = self._make_app(verifier=verifier)
        resp = client.post("/exchange",
                           headers={"Authorization": "Bearer valid.token"},
                           json={"from_currency": "USD", "to_currency": "EUR", "amount": 100})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "missing_idempotency_key")

    def test_invalid_uuid_idempotency_key_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        client = self._make_app(verifier=verifier)
        resp = client.post("/exchange",
                           headers={"Authorization": "Bearer valid.token",
                                    "Idempotency-Key": "not-a-uuid"},
                           json={"from_currency": "USD", "to_currency": "EUR", "amount": 100})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "invalid_idempotency_key")

    def test_cached_idempotency_key_returns_200_without_db(self):
        """If idempotency key exists in cache, return cached result without DB write."""
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        cached = {"transaction_id": "tx-cached", "amount": 100.0}
        idem_cache = _make_mock_idem_cache(cached=cached)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        resp = client.post("/exchange",
                           headers={"Authorization": "Bearer valid.token",
                                    "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"from_currency": "USD", "to_currency": "EUR", "amount": 100})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["transaction_id"], "tx-cached")
        # DB should NOT be called
        db._ensure_connected.assert_not_called()

    def test_missing_from_currency_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        client = self._make_app(verifier=verifier, idem_cache=idem_cache)
        resp = client.post("/exchange",
                           headers={"Authorization": "Bearer valid.token",
                                    "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"to_currency": "EUR", "amount": 100})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "invalid_request")

    def test_negative_amount_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        client = self._make_app(verifier=verifier, idem_cache=idem_cache)
        resp = client.post("/exchange",
                           headers={"Authorization": "Bearer valid.token",
                                    "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"from_currency": "VND", "to_currency": "EUR", "amount": -50})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "invalid_request")

    def test_non_vnd_source_currency_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        client = self._make_app(verifier=verifier, idem_cache=idem_cache)
        resp = client.post("/exchange",
                           headers={"Authorization": "Bearer valid.token",
                                    "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"from_currency": "USD", "to_currency": "EUR", "amount": 100})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "unsupported_exchange_direction")

    def test_unavailable_exchange_rate_returns_503(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        rate_cache = _make_mock_rate_cache(rates={})  # No rates available
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, rate_cache=rate_cache)
        resp = client.post("/exchange",
                           headers={"Authorization": "Bearer valid.token",
                                    "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"from_currency": "VND", "to_currency": "EUR", "amount": 100})
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(json.loads(resp.data)["error"], "rate_unavailable")

    def test_insufficient_balance_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        rate_cache = _make_mock_rate_cache(rates={
            ("VND", "EUR"): 0.000039,
        })
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache,
                                rate_cache=rate_cache, db=db)

        with patch("money_service.execute_exchange",
                   side_effect=InsufficientBalanceError("not enough")):
            resp = client.post("/exchange",
                               headers={"Authorization": "Bearer valid.token",
                                        "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                               json={"from_currency": "VND", "to_currency": "EUR", "amount": 100000})

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "insufficient_balance")

    def test_optimistic_lock_conflict_after_retries_returns_409(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        rate_cache = _make_mock_rate_cache(rates={
            ("VND", "EUR"): 0.000039,
        })
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache,
                                rate_cache=rate_cache, db=db)

        with patch("money_service.execute_exchange",
                   side_effect=OptimisticLockConflictError("conflict")):
            with patch("money_service.time.sleep"):  # Skip backoff delay
                resp = client.post("/exchange",
                                   headers={"Authorization": "Bearer valid.token",
                                            "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                                   json={"from_currency": "VND", "to_currency": "EUR", "amount": 100000})

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(json.loads(resp.data)["error"], "conflict")

    def test_successful_exchange_returns_200_and_stores_idempotency(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        rate_cache = _make_mock_rate_cache(rates={
            ("VND", "EUR"): 0.000039,
        })
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache,
                                rate_cache=rate_cache, db=db)

        tx_result = {
            "transaction_id": "tx-new-123",
            "type": "exchange",
            "from_currency": "VND",
            "to_currency": "EUR",
            "amount": 1000000.0,
            "rate_applied": 0.000039,
            "received_amount": 39.0,
            "new_balance_vnd": 4000000.0,
            "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
        }

        with patch("money_service.execute_exchange", return_value=tx_result):
            resp = client.post("/exchange",
                               headers={"Authorization": "Bearer valid.token",
                                        "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                               json={"from_currency": "VND", "to_currency": "EUR", "amount": 1000000})

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["transaction_id"], "tx-new-123")
        # Idempotency cache should be populated
        idem_cache.set.assert_called_once()


# ── TestIdempotencyProperty ───────────────────────────────────────────────────

class TestIdempotencyProperty(unittest.TestCase):
    """
    Property 1: Idempotency of financial transactions.
    Submitting the same Idempotency-Key N times must return the same result
    and the balance must change exactly once.

    **Validates: Requirements 5.2, 5.3, 5.6**
    """

    def test_same_idempotency_key_returns_same_result(self):
        """
        Sending the same Idempotency-Key twice must return the cached result
        on the second call without executing the transaction again.
        """
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = MagicMock(spec=IdempotencyCache)
        rate_cache = _make_mock_rate_cache(rates={
            ("VND", "EUR"): 0.000039,
        })
        db = _make_mock_db()

        tx_result = {
            "transaction_id": "tx-idem-test",
            "type": "exchange",
            "from_currency": "VND",
            "to_currency": "EUR",
            "amount": 500000.0,
            "rate_applied": 0.000039,
            "received_amount": 19.5,
            "new_balance_vnd": 4500000.0,
            "idempotency_key": "550e8400-e29b-41d4-a716-446655440001",
        }

        # First call: cache miss, execute transaction
        idem_cache.get.return_value = None
        idem_cache.set.return_value = None

        app = create_app(
            jwt_verifier=verifier,
            exchange_rate_cache=rate_cache,
            idempotency_cache=idem_cache,
            db_client=db,
        )
        client = app.test_client()

        with patch("money_service.execute_exchange", return_value=tx_result) as mock_exec:
            # First request
            resp1 = client.post(
                "/exchange",
                headers={"Authorization": "Bearer valid.token",
                         "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440001"},
                json={"from_currency": "VND", "to_currency": "EUR", "amount": 500000},
            )
            self.assertEqual(resp1.status_code, 200)
            self.assertEqual(mock_exec.call_count, 1)

            # Second request with same key — now cache returns the stored result
            idem_cache.get.return_value = tx_result

            resp2 = client.post(
                "/exchange",
                headers={"Authorization": "Bearer valid.token",
                         "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440001"},
                json={"from_currency": "VND", "to_currency": "EUR", "amount": 500000},
            )
            self.assertEqual(resp2.status_code, 200)
            # execute_exchange must NOT be called again
            self.assertEqual(mock_exec.call_count, 1, "execute_exchange called more than once!")

        data1 = json.loads(resp1.data)
        data2 = json.loads(resp2.data)
        self.assertEqual(data1["transaction_id"], data2["transaction_id"])

    def test_different_idempotency_keys_execute_independently(self):
        """Different idempotency keys must each trigger a separate transaction."""
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        rate_cache = _make_mock_rate_cache(rates={
            ("VND", "EUR"): 0.000039,
        })
        db = _make_mock_db()

        app = create_app(
            jwt_verifier=verifier,
            exchange_rate_cache=rate_cache,
            idempotency_cache=idem_cache,
            db_client=db,
        )
        client = app.test_client()

        results = [
            {"transaction_id": f"tx-{i}", "type": "exchange",
             "from_currency": "VND", "to_currency": "EUR",
             "amount": 100.0, "rate_applied": 0.000039,
             "received_amount": 0.0039, "new_balance_vnd": 900.0,
             "idempotency_key": f"key-{i}"}
            for i in range(3)
        ]

        keys = [
            "550e8400-e29b-41d4-a716-446655440010",
            "550e8400-e29b-41d4-a716-446655440011",
            "550e8400-e29b-41d4-a716-446655440012",
        ]

        with patch("money_service.execute_exchange", side_effect=results) as mock_exec:
            for i, key in enumerate(keys):
                resp = client.post(
                    "/exchange",
                    headers={"Authorization": "Bearer valid.token",
                             "Idempotency-Key": key},
                    json={"from_currency": "VND", "to_currency": "EUR", "amount": 100},
                )
                self.assertEqual(resp.status_code, 200)

        self.assertEqual(mock_exec.call_count, 3)


# ── TestExecuteTopup ──────────────────────────────────────────────────────────

class TestExecuteTopup(unittest.TestCase):
    """Tests for execute_topup function directly."""

    def _make_db_with_user(self, balance="5000000", version=0, user_found=True, rowcount=1):
        """Create a mock DatabaseClient that simulates a user row."""
        mock_db = MagicMock(spec=DatabaseClient)
        mock_db._ensure_connected.return_value = None

        mock_conn = MagicMock()
        mock_db.conn = mock_conn

        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        if user_found:
            mock_cur.fetchone.return_value = {
                "id": "db-user-uuid-001",
                "balance": balance,
                "version": version,
            }
        else:
            mock_cur.fetchone.return_value = None

        mock_cur.rowcount = rowcount
        return mock_db, mock_conn, mock_cur

    def test_successful_topup_credits_balance(self):
        """execute_topup should add amount to balance and return correct result."""
        mock_db, mock_conn, mock_cur = self._make_db_with_user(
            balance="5000000", version=2, rowcount=1
        )
        result = execute_topup(
            db=mock_db,
            user_id="cognito-sub-abc",
            amount=Decimal("100000"),
            idempotency_key="550e8400-e29b-41d4-a716-446655440099",
        )

        self.assertEqual(result["type"], "topup")
        self.assertEqual(result["to_currency"], "VND")
        self.assertIsNone(result["from_currency"])
        self.assertIsNone(result["rate_applied"])
        self.assertEqual(result["amount"], 100000.0)
        self.assertAlmostEqual(result["new_balance_vnd"], 5100000.0)
        self.assertIn("transaction_id", result)
        mock_conn.commit.assert_called_once()

    def test_topup_user_not_found_raises_value_error(self):
        """execute_topup should raise ValueError when user does not exist."""
        mock_db, mock_conn, mock_cur = self._make_db_with_user(user_found=False)
        with self.assertRaises(ValueError):
            execute_topup(
                db=mock_db,
                user_id="nonexistent-sub",
                amount=Decimal("50000"),
                idempotency_key="550e8400-e29b-41d4-a716-446655440098",
            )

    def test_topup_version_conflict_raises_optimistic_lock_error(self):
        """execute_topup should raise OptimisticLockConflictError on version mismatch."""
        mock_db, mock_conn, mock_cur = self._make_db_with_user(
            balance="1000000", version=1, rowcount=0  # rowcount=0 → conflict
        )
        with self.assertRaises(OptimisticLockConflictError):
            execute_topup(
                db=mock_db,
                user_id="cognito-sub-abc",
                amount=Decimal("50000"),
                idempotency_key="550e8400-e29b-41d4-a716-446655440097",
            )
        mock_conn.rollback.assert_called()

    def test_topup_inserts_correct_audit_record(self):
        """execute_topup should insert a transaction record with type='topup'."""
        mock_db, mock_conn, mock_cur = self._make_db_with_user(
            balance="2000000", version=0, rowcount=1
        )
        execute_topup(
            db=mock_db,
            user_id="cognito-sub-abc",
            amount=Decimal("200000"),
            idempotency_key="550e8400-e29b-41d4-a716-446655440096",
        )

        # Find the INSERT call among all execute calls
        insert_call = None
        for call_args in mock_cur.execute.call_args_list:
            sql = call_args[0][0]
            if "INSERT INTO transactions" in sql:
                insert_call = call_args
                break

        self.assertIsNotNone(insert_call, "INSERT INTO transactions was not called")
        params = insert_call[0][1]
        # params: (id, user_id, type, from_currency, to_currency, amount, rate_applied, idempotency_key)
        self.assertEqual(params[2], "topup")       # type
        self.assertIsNone(params[3])               # from_currency
        self.assertEqual(params[4], "VND")         # to_currency
        self.assertIsNone(params[6])               # rate_applied


# ── TestTopupEndpoint ─────────────────────────────────────────────────────────

class TestTopupEndpoint(unittest.TestCase):
    """Tests for POST /topup HTTP endpoint behavior.

    **Validates: Requirement 5.8**
    """

    def _make_app(self, verifier=None, idem_cache=None, db=None):
        app = create_app(
            jwt_verifier=verifier,
            idempotency_cache=idem_cache,
            db_client=db,
        )
        return app.test_client()

    def test_missing_auth_header_returns_401(self):
        verifier = MagicMock(spec=JWTVerifier)
        verifier.extract_token_from_header.side_effect = MissingTokenError("required")
        client = self._make_app(verifier=verifier)
        resp = client.post("/topup",
                           headers={"Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"amount": 100000})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(json.loads(resp.data)["error"], "missing_token")

    def test_missing_idempotency_key_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        client = self._make_app(verifier=verifier)
        resp = client.post("/topup",
                           headers={"Authorization": "Bearer valid.token"},
                           json={"amount": 100000})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "missing_idempotency_key")

    def test_cached_idempotency_key_returns_200_without_db(self):
        """If idempotency key exists in cache, return cached result without DB write."""
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        cached = {"transaction_id": "tx-topup-cached", "type": "topup", "amount": 100000.0}
        idem_cache = _make_mock_idem_cache(cached=cached)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        resp = client.post("/topup",
                           headers={"Authorization": "Bearer valid.token",
                                    "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"amount": 100000})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["transaction_id"], "tx-topup-cached")
        # DB should NOT be called
        db._ensure_connected.assert_not_called()

    def test_negative_amount_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        client = self._make_app(verifier=verifier, idem_cache=idem_cache)
        resp = client.post("/topup",
                           headers={"Authorization": "Bearer valid.token",
                                    "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"amount": -50000})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "invalid_request")

    def test_zero_amount_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        client = self._make_app(verifier=verifier, idem_cache=idem_cache)
        resp = client.post("/topup",
                           headers={"Authorization": "Bearer valid.token",
                                    "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                           json={"amount": 0})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "invalid_request")

    def test_successful_topup_returns_200_and_stores_idempotency(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        tx_result = {
            "transaction_id": "tx-topup-new-456",
            "type": "topup",
            "from_currency": None,
            "to_currency": "VND",
            "amount": 500000.0,
            "rate_applied": None,
            "new_balance_vnd": 5500000.0,
            "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
        }

        with patch("money_service.execute_topup", return_value=tx_result):
            resp = client.post("/topup",
                               headers={"Authorization": "Bearer valid.token",
                                        "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                               json={"amount": 500000})

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["transaction_id"], "tx-topup-new-456")
        self.assertEqual(data["type"], "topup")
        # Idempotency cache should be populated
        idem_cache.set.assert_called_once()

    def test_lock_conflict_after_retries_returns_409(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        with patch("money_service.execute_topup",
                   side_effect=OptimisticLockConflictError("conflict")):
            with patch("money_service.time.sleep"):  # Skip backoff delay
                resp = client.post("/topup",
                                   headers={"Authorization": "Bearer valid.token",
                                            "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                                   json={"amount": 100000})

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(json.loads(resp.data)["error"], "conflict")

    def test_user_not_found_returns_404(self):
        verifier = _make_mock_verifier(claims={"sub": "unknown-user"})
        idem_cache = _make_mock_idem_cache(cached=None)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        with patch("money_service.execute_topup",
                   side_effect=ValueError("User not found: unknown-user")):
            resp = client.post("/topup",
                               headers={"Authorization": "Bearer valid.token",
                                        "Idempotency-Key": "550e8400-e29b-41d4-a716-446655440000"},
                               json={"amount": 100000})

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(json.loads(resp.data)["error"], "user_not_found")


if __name__ == "__main__":
    unittest.main()


# ── TestExecutePremiumUpgrade ─────────────────────────────────────────────────


class TestExecutePremiumUpgrade(unittest.TestCase):
    """
    Tests for execute_premium_upgrade function.

    **Validates: Requirements 10.1, 10.2, 10.3**
    """

    def _make_db_with_user(
        self,
        balance="5000000",
        version=0,
        user_found=True,
        rowcount=1,
        premium_deducted=False,
    ):
        """Create a mock DatabaseClient that simulates a user row."""
        mock_db = MagicMock(spec=DatabaseClient)
        mock_db._ensure_connected.return_value = None

        mock_conn = MagicMock()
        mock_db.conn = mock_conn

        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        if user_found:
            mock_cur.fetchone.return_value = {
                "id": "db-user-uuid-001",
                "balance": balance,
                "version": version,
                "premium_deducted": premium_deducted,
            }
        else:
            mock_cur.fetchone.return_value = None

        mock_cur.rowcount = rowcount
        return mock_db, mock_conn, mock_cur

    def test_successful_upgrade_deducts_fee_and_returns_result(self):
        """
        execute_premium_upgrade should deduct premium_fee from balance,
        set premium_deducted=TRUE, and return a result dict.
        """
        mock_db, mock_conn, mock_cur = self._make_db_with_user(
            balance="1000000", version=0, rowcount=1, premium_deducted=False
        )
        result = execute_premium_upgrade(
            db=mock_db,
            user_id="cognito-sub-abc",
            premium_fee=Decimal("500000"),
            idempotency_key="550e8400-e29b-41d4-a716-446655440200",
        )

        self.assertEqual(result["type"], "premium_upgrade")
        self.assertAlmostEqual(result["new_balance_vnd"], 500000.0)
        self.assertAlmostEqual(result["amount"], 500000.0)
        self.assertIn("transaction_id", result)
        mock_conn.commit.assert_called_once()

    def test_insufficient_balance_raises_error(self):
        """
        execute_premium_upgrade should raise InsufficientBalanceError
        when balance < premium_fee.

        **Validates: Requirement 10.2**
        """
        mock_db, mock_conn, mock_cur = self._make_db_with_user(
            balance="100000", version=0, rowcount=1, premium_deducted=False
        )
        with self.assertRaises(InsufficientBalanceError):
            execute_premium_upgrade(
                db=mock_db,
                user_id="cognito-sub-abc",
                premium_fee=Decimal("500000"),
                idempotency_key="550e8400-e29b-41d4-a716-446655440201",
            )
        mock_conn.rollback.assert_called()

    def test_already_deducted_raises_already_premium_error(self):
        """
        execute_premium_upgrade should raise AlreadyPremiumError when
        premium_deducted is already TRUE (DB-level idempotency guard).
        """
        mock_db, mock_conn, mock_cur = self._make_db_with_user(
            balance="5000000", version=1, rowcount=1, premium_deducted=True
        )
        with self.assertRaises(AlreadyPremiumError):
            execute_premium_upgrade(
                db=mock_db,
                user_id="cognito-sub-abc",
                premium_fee=Decimal("500000"),
                idempotency_key="550e8400-e29b-41d4-a716-446655440202",
            )

    def test_version_conflict_raises_optimistic_lock_error(self):
        """
        execute_premium_upgrade should raise OptimisticLockConflictError
        when the UPDATE rowcount is 0 (version mismatch).
        """
        mock_db, mock_conn, mock_cur = self._make_db_with_user(
            balance="5000000", version=0, rowcount=0, premium_deducted=False
        )
        with self.assertRaises(OptimisticLockConflictError):
            execute_premium_upgrade(
                db=mock_db,
                user_id="cognito-sub-abc",
                premium_fee=Decimal("500000"),
                idempotency_key="550e8400-e29b-41d4-a716-446655440203",
            )
        mock_conn.rollback.assert_called()

    def test_user_not_found_raises_value_error(self):
        """execute_premium_upgrade should raise ValueError when user does not exist."""
        mock_db, mock_conn, mock_cur = self._make_db_with_user(user_found=False)
        with self.assertRaises(ValueError):
            execute_premium_upgrade(
                db=mock_db,
                user_id="nonexistent-sub",
                premium_fee=Decimal("500000"),
                idempotency_key="550e8400-e29b-41d4-a716-446655440204",
            )

    def test_inserts_premium_upgrade_audit_record(self):
        """execute_premium_upgrade should insert a transaction with type='premium_upgrade'."""
        mock_db, mock_conn, mock_cur = self._make_db_with_user(
            balance="2000000", version=0, rowcount=1, premium_deducted=False
        )
        execute_premium_upgrade(
            db=mock_db,
            user_id="cognito-sub-abc",
            premium_fee=Decimal("500000"),
            idempotency_key="550e8400-e29b-41d4-a716-446655440205",
        )

        insert_call = None
        for call_args in mock_cur.execute.call_args_list:
            sql = call_args[0][0]
            if "INSERT INTO transactions" in sql:
                insert_call = call_args
                break

        self.assertIsNotNone(insert_call, "INSERT INTO transactions was not called")
        params = insert_call[0][1]
        # params: (id, user_id, type, from_currency, to_currency, amount, rate_applied, idempotency_key)
        self.assertEqual(params[2], "premium_upgrade")  # type
        self.assertEqual(params[3], "VND")              # from_currency
        self.assertIsNone(params[4])                    # to_currency
        self.assertIsNone(params[6])                    # rate_applied


# ── TestGetPremiumFeeFromSSM ──────────────────────────────────────────────────


class TestGetPremiumFeeFromSSM(unittest.TestCase):
    """
    Tests for get_premium_fee_from_ssm.

    **Validates: Requirement 10.7 (fee not hardcoded, read from Parameter Store)**
    """

    def test_reads_fee_from_ssm_parameter_store(self):
        """get_premium_fee_from_ssm should call SSM and return a Decimal."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "500000"}
        }
        with patch("money_service.boto3.client", return_value=mock_ssm):
            fee = get_premium_fee_from_ssm()

        self.assertEqual(fee, Decimal("500000"))
        mock_ssm.get_parameter.assert_called_once_with(
            Name=Config.SSM_PREMIUM_FEE_PARAM,
            WithDecryption=True,
        )

    def test_raises_value_error_on_invalid_parameter_value(self):
        """get_premium_fee_from_ssm should raise ValueError for non-numeric values."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "not-a-number"}
        }
        with patch("money_service.boto3.client", return_value=mock_ssm):
            with self.assertRaises(ValueError):
                get_premium_fee_from_ssm()

    def test_raises_value_error_on_zero_fee(self):
        """get_premium_fee_from_ssm should raise ValueError if fee is 0."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "0"}
        }
        with patch("money_service.boto3.client", return_value=mock_ssm):
            with self.assertRaises(ValueError):
                get_premium_fee_from_ssm()

    def test_raises_value_error_on_ssm_error(self):
        """get_premium_fee_from_ssm should raise ValueError when SSM call fails."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.side_effect = Exception("SSM unavailable")
        with patch("money_service.boto3.client", return_value=mock_ssm):
            with self.assertRaises(ValueError):
                get_premium_fee_from_ssm()


# ── TestPremiumUpgradeEndpoint ────────────────────────────────────────────────


class TestPremiumUpgradeEndpoint(unittest.TestCase):
    """
    Tests for POST /premium/upgrade HTTP endpoint.

    **Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.6**
    """

    _IDEM_KEY = "550e8400-e29b-41d4-a716-446655440300"
    _AUTH_HEADER = "Bearer valid.token"

    def _make_app(self, verifier=None, idem_cache=None, db=None):
        app = create_app(
            jwt_verifier=verifier,
            idempotency_cache=idem_cache,
            db_client=db,
        )
        return app.test_client()

    def _default_headers(self):
        return {
            "Authorization": self._AUTH_HEADER,
            "Idempotency-Key": self._IDEM_KEY,
        }

    def test_missing_auth_header_returns_401(self):
        verifier = MagicMock(spec=JWTVerifier)
        verifier.extract_token_from_header.side_effect = MissingTokenError("required")
        client = self._make_app(verifier=verifier)
        resp = client.post(
            "/premium/upgrade",
            headers={"Idempotency-Key": self._IDEM_KEY},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(json.loads(resp.data)["error"], "missing_token")

    def test_expired_token_returns_401(self):
        verifier = MagicMock(spec=JWTVerifier)
        verifier.extract_token_from_header.return_value = "expired.token"
        verifier.verify.side_effect = TokenExpiredError("expired")
        client = self._make_app(verifier=verifier)
        resp = client.post(
            "/premium/upgrade",
            headers=self._default_headers(),
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(json.loads(resp.data)["error"], "token_expired")

    def test_missing_idempotency_key_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        client = self._make_app(verifier=verifier)
        resp = client.post(
            "/premium/upgrade",
            headers={"Authorization": self._AUTH_HEADER},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "missing_idempotency_key")

    def test_invalid_uuid_idempotency_key_returns_400(self):
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        client = self._make_app(verifier=verifier)
        resp = client.post(
            "/premium/upgrade",
            headers={"Authorization": self._AUTH_HEADER, "Idempotency-Key": "not-a-uuid"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "invalid_idempotency_key")

    def test_cached_idempotency_key_returns_200_without_db(self):
        """
        If idempotency key exists in cache, return cached result without DB write.

        **Validates: Requirement 10.3 (idempotency prevents double-charge)**
        """
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        cached = {
            "transaction_id": "tx-premium-cached",
            "type": "premium_upgrade",
            "amount": 500000.0,
        }
        idem_cache = _make_mock_idem_cache(cached=cached)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        resp = client.post(
            "/premium/upgrade",
            headers=self._default_headers(),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["transaction_id"], "tx-premium-cached")
        # DB should NOT be called
        db._ensure_connected.assert_not_called()

    def test_insufficient_balance_returns_400(self):
        """
        POST /premium/upgrade should return HTTP 400 when balance < premium_fee.

        **Validates: Requirement 10.2**
        """
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        with patch("money_service.get_premium_fee_from_ssm", return_value=Decimal("500000")):
            with patch("money_service.execute_premium_upgrade",
                       side_effect=InsufficientBalanceError("not enough")):
                resp = client.post(
                    "/premium/upgrade",
                    headers=self._default_headers(),
                )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "insufficient_balance")

    def test_optimistic_lock_conflict_after_retries_returns_409(self):
        """
        POST /premium/upgrade should return HTTP 409 after 3 failed lock retries.
        """
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        with patch("money_service.get_premium_fee_from_ssm", return_value=Decimal("500000")):
            with patch("money_service.execute_premium_upgrade",
                       side_effect=OptimisticLockConflictError("conflict")):
                with patch("money_service.time.sleep"):
                    resp = client.post(
                        "/premium/upgrade",
                        headers=self._default_headers(),
                    )

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(json.loads(resp.data)["error"], "conflict")

    def test_successful_upgrade_calls_cognito_and_returns_200(self):
        """
        POST /premium/upgrade should call Cognito AdminUpdateUserAttributes
        and return HTTP 200 on success.

        **Validates: Requirements 10.3, 10.4**
        """
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        tx_result = {
            "transaction_id": "tx-premium-new-001",
            "type": "premium_upgrade",
            "amount": 500000.0,
            "new_balance_vnd": 500000.0,
            "idempotency_key": self._IDEM_KEY,
            "created_at": "2024-01-01T00:00:00Z",
        }

        with patch("money_service.get_premium_fee_from_ssm", return_value=Decimal("500000")):
            with patch("money_service.execute_premium_upgrade", return_value=tx_result):
                with patch("money_service.update_cognito_premium_attribute") as mock_cognito:
                    with patch("money_service.mark_cognito_update_complete"):
                        resp = client.post(
                            "/premium/upgrade",
                            headers=self._default_headers(),
                        )

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["transaction_id"], "tx-premium-new-001")
        self.assertEqual(data["type"], "premium_upgrade")
        # Cognito must be called
        mock_cognito.assert_called_once_with("user-123")
        # Idempotency cache must be populated
        idem_cache.set.assert_called_once()

    def test_cognito_failure_after_deduction_still_returns_200(self):
        """
        If Cognito update fails after balance deduction, the endpoint must
        still return HTTP 200 (money was taken; reconciliation job will retry).

        **Validates: Requirement 10.6**
        """
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        tx_result = {
            "transaction_id": "tx-premium-cognito-fail",
            "type": "premium_upgrade",
            "amount": 500000.0,
            "new_balance_vnd": 500000.0,
            "idempotency_key": self._IDEM_KEY,
            "created_at": "2024-01-01T00:00:00Z",
        }

        with patch("money_service.get_premium_fee_from_ssm", return_value=Decimal("500000")):
            with patch("money_service.execute_premium_upgrade", return_value=tx_result):
                with patch("money_service.update_cognito_premium_attribute",
                           side_effect=Exception("Cognito unavailable")):
                    resp = client.post(
                        "/premium/upgrade",
                        headers=self._default_headers(),
                    )

        # Must still return 200 — money was deducted, reconciliation will handle Cognito
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["transaction_id"], "tx-premium-cognito-fail")

    def test_ssm_unavailable_returns_503(self):
        """
        POST /premium/upgrade should return HTTP 503 when premium_fee
        cannot be read from Parameter Store.
        """
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = _make_mock_idem_cache(cached=None)
        db = _make_mock_db()
        client = self._make_app(verifier=verifier, idem_cache=idem_cache, db=db)

        with patch("money_service.get_premium_fee_from_ssm",
                   side_effect=ValueError("SSM unavailable")):
            resp = client.post(
                "/premium/upgrade",
                headers=self._default_headers(),
            )

        self.assertEqual(resp.status_code, 503)
        self.assertEqual(json.loads(resp.data)["error"], "configuration_error")

    def test_idempotency_same_key_submitted_twice_charges_only_once(self):
        """
        Submitting the same Idempotency-Key twice must return the cached result
        on the second call without executing the upgrade again.

        **Validates: Requirement 10.3 (idempotency prevents double-charge)**
        """
        verifier = _make_mock_verifier(claims={"sub": "user-123"})
        idem_cache = MagicMock(spec=IdempotencyCache)
        db = _make_mock_db()

        tx_result = {
            "transaction_id": "tx-premium-idem-test",
            "type": "premium_upgrade",
            "amount": 500000.0,
            "new_balance_vnd": 500000.0,
            "idempotency_key": self._IDEM_KEY,
            "created_at": "2024-01-01T00:00:00Z",
        }

        # First call: cache miss
        idem_cache.get.return_value = None
        idem_cache.set.return_value = None

        app = create_app(
            jwt_verifier=verifier,
            idempotency_cache=idem_cache,
            db_client=db,
        )
        client = app.test_client()

        with patch("money_service.get_premium_fee_from_ssm", return_value=Decimal("500000")):
            with patch("money_service.execute_premium_upgrade",
                       return_value=tx_result) as mock_exec:
                with patch("money_service.update_cognito_premium_attribute"):
                    with patch("money_service.mark_cognito_update_complete"):
                        # First request
                        resp1 = client.post(
                            "/premium/upgrade",
                            headers=self._default_headers(),
                        )
                        self.assertEqual(resp1.status_code, 200)
                        self.assertEqual(mock_exec.call_count, 1)

                        # Second request with same key — cache now returns stored result
                        idem_cache.get.return_value = tx_result

                        resp2 = client.post(
                            "/premium/upgrade",
                            headers=self._default_headers(),
                        )
                        self.assertEqual(resp2.status_code, 200)
                        # execute_premium_upgrade must NOT be called again
                        self.assertEqual(
                            mock_exec.call_count, 1,
                            "execute_premium_upgrade called more than once!"
                        )

        data1 = json.loads(resp1.data)
        data2 = json.loads(resp2.data)
        self.assertEqual(data1["transaction_id"], data2["transaction_id"])


# ── TestPremiumReconciliationJob ──────────────────────────────────────────────


class TestPremiumReconciliationJob(unittest.TestCase):
    """
    Tests for PremiumReconciliationJob reconciliation logic.

    **Validates: Requirement 10.6**
    """

    def test_reconcile_retries_cognito_for_pending_users(self):
        """
        Reconciliation job should call update_cognito_premium_attribute for
        each user with premium_deducted = TRUE.
        """
        mock_db = _make_mock_db()
        job = PremiumReconciliationJob(db_client=mock_db)

        pending_users = [
            {"cognito_sub": "user-pending-001"},
            {"cognito_sub": "user-pending-002"},
        ]

        with patch("money_service.get_users_pending_cognito_update",
                   return_value=pending_users):
            with patch("money_service.update_cognito_premium_attribute") as mock_cognito:
                with patch("money_service.mark_cognito_update_complete") as mock_clear:
                    job._reconcile()

        self.assertEqual(mock_cognito.call_count, 2)
        mock_cognito.assert_any_call("user-pending-001")
        mock_cognito.assert_any_call("user-pending-002")
        self.assertEqual(mock_clear.call_count, 2)

    def test_reconcile_clears_flag_on_cognito_success(self):
        """
        After a successful Cognito update, mark_cognito_update_complete
        must be called to clear the premium_deducted flag.
        """
        mock_db = _make_mock_db()
        job = PremiumReconciliationJob(db_client=mock_db)

        pending_users = [{"cognito_sub": "user-abc"}]

        with patch("money_service.get_users_pending_cognito_update",
                   return_value=pending_users):
            with patch("money_service.update_cognito_premium_attribute"):
                with patch("money_service.mark_cognito_update_complete") as mock_clear:
                    job._reconcile()

        mock_clear.assert_called_once_with(mock_db, "user-abc")

    def test_reconcile_continues_on_cognito_failure(self):
        """
        If Cognito update fails for one user, the job should continue
        processing other users and not raise an exception.
        """
        mock_db = _make_mock_db()
        job = PremiumReconciliationJob(db_client=mock_db)

        pending_users = [
            {"cognito_sub": "user-fail"},
            {"cognito_sub": "user-ok"},
        ]

        def cognito_side_effect(sub):
            if sub == "user-fail":
                raise Exception("Cognito error")

        with patch("money_service.get_users_pending_cognito_update",
                   return_value=pending_users):
            with patch("money_service.update_cognito_premium_attribute",
                       side_effect=cognito_side_effect):
                with patch("money_service.mark_cognito_update_complete") as mock_clear:
                    # Should not raise
                    job._reconcile()

        # Only the successful user should have its flag cleared
        mock_clear.assert_called_once_with(mock_db, "user-ok")

    def test_reconcile_does_nothing_when_no_pending_users(self):
        """
        Reconciliation job should be a no-op when no users are pending.
        """
        mock_db = _make_mock_db()
        job = PremiumReconciliationJob(db_client=mock_db)

        with patch("money_service.get_users_pending_cognito_update", return_value=[]):
            with patch("money_service.update_cognito_premium_attribute") as mock_cognito:
                job._reconcile()

        mock_cognito.assert_not_called()


if __name__ == "__main__":
    unittest.main()
