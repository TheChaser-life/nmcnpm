"""
Unit tests for Exchange Rate Producer

Tests cover:
- Rate filtering logic
- Cache update logic
- API response parsing
- Error handling (API failure, Redis failure)
"""

import json
import time
import unittest
from unittest.mock import MagicMock, patch, call

import sys
import os

# Add parent directory to path so we can import producer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestExchangeRateAPIClient:
    """Tests for ExchangeRateAPIClient."""
    pass


class TestFilterSupportedRates(unittest.TestCase):
    """Tests for _filter_supported_rates logic."""
    
    def setUp(self):
        """Set up test fixtures with mocked dependencies."""
        # Patch Redis and requests to avoid real connections
        self.redis_patcher = patch("producer.redis.Redis")
        self.mock_redis_class = self.redis_patcher.start()
        self.mock_redis = MagicMock()
        self.mock_redis.ping.return_value = True
        self.mock_redis_class.return_value = self.mock_redis
        
        # Import after patching
        import producer
        self.producer_module = producer
        
        # Create producer instance with mocked API client
        with patch.object(producer.ExchangeRateAPIClient, "__init__", return_value=None):
            self.producer = producer.ExchangeRateProducer.__new__(producer.ExchangeRateProducer)
            self.producer.redis_client = producer.RedisClient.__new__(producer.RedisClient)
            self.producer.redis_client.client = self.mock_redis
            self.producer.api_client = MagicMock()
            self.producer.supported_currencies = ["USD", "EUR", "GBP", "JPY"]
    
    def tearDown(self):
        self.redis_patcher.stop()
    
    def test_filter_keeps_supported_currencies(self):
        """Only supported currencies should be kept."""
        all_rates = {
            "USD": 0.000043,
            "EUR": 0.000039,
            "GBP": 0.000034,
            "JPY": 0.0065,
            "AED": 0.000158,  # Not in supported list
            "ZAR": 0.00079,   # Not in supported list
        }
        
        result = self.producer._filter_supported_rates(all_rates)
        
        self.assertIn("USD", result)
        self.assertIn("EUR", result)
        self.assertIn("GBP", result)
        self.assertIn("JPY", result)
        self.assertNotIn("AED", result)
        self.assertNotIn("ZAR", result)
    
    def test_filter_preserves_rate_values(self):
        """Rate values should not be modified during filtering."""
        all_rates = {
            "USD": 0.000043,
            "EUR": 0.000039,
        }
        
        result = self.producer._filter_supported_rates(all_rates)
        
        self.assertAlmostEqual(result["USD"], 0.000043)
        self.assertAlmostEqual(result["EUR"], 0.000039)
    
    def test_filter_handles_empty_rates(self):
        """Empty rates dict should return empty dict."""
        result = self.producer._filter_supported_rates({})
        self.assertEqual(result, {})
    
    def test_filter_handles_no_matching_currencies(self):
        """If no currencies match, return empty dict."""
        all_rates = {
            "AED": 0.000158,
            "ZAR": 0.00079,
        }
        
        result = self.producer._filter_supported_rates(all_rates)
        self.assertEqual(result, {})
    
    def test_filter_handles_all_supported_currencies_present(self):
        """When all supported currencies are present, all should be returned."""
        all_rates = {
            "USD": 0.000043,
            "EUR": 0.000039,
            "GBP": 0.000034,
            "JPY": 0.0065,
        }
        
        result = self.producer._filter_supported_rates(all_rates)
        
        self.assertEqual(len(result), 4)
        for currency in ["USD", "EUR", "GBP", "JPY"]:
            self.assertIn(currency, result)


class TestCacheUpdate(unittest.TestCase):
    """Tests for cache update logic."""
    
    def setUp(self):
        """Set up test fixtures with mocked Redis."""
        self.redis_patcher = patch("producer.redis.Redis")
        self.mock_redis_class = self.redis_patcher.start()
        self.mock_redis = MagicMock()
        self.mock_redis.ping.return_value = True
        self.mock_redis_class.return_value = self.mock_redis
        
        import producer
        self.producer_module = producer
        
        with patch.object(producer.ExchangeRateAPIClient, "__init__", return_value=None):
            self.producer = producer.ExchangeRateProducer.__new__(producer.ExchangeRateProducer)
            self.producer.redis_client = producer.RedisClient.__new__(producer.RedisClient)
            self.producer.redis_client.client = self.mock_redis
            self.producer.api_client = MagicMock()
            self.producer.supported_currencies = ["USD", "EUR"]
            self.producer.cloudwatch_client = MagicMock()
    
    def tearDown(self):
        self.redis_patcher.stop()
    
    def test_cache_update_calls_setex_for_each_currency(self):
        """Each currency should be stored with setex."""
        self.mock_redis.setex.return_value = True
        
        rates = {"USD": 0.000043, "EUR": 0.000039}
        self.producer._update_cache(rates)
        
        self.assertEqual(self.mock_redis.setex.call_count, 2)
    
    def test_cache_update_uses_correct_key_format(self):
        """Keys should follow exchange_rate:{currency} format."""
        self.mock_redis.setex.return_value = True
        
        rates = {"USD": 0.000043}
        self.producer._update_cache(rates)
        
        call_args = self.mock_redis.setex.call_args
        key = call_args[0][0]
        self.assertEqual(key, "exchange_rate:USD")
    
    def test_cache_update_stores_json_value(self):
        """Stored value should be valid JSON with currency, rate, and timestamp."""
        self.mock_redis.setex.return_value = True
        
        rates = {"USD": 0.000043}
        self.producer._update_cache(rates)
        
        call_args = self.mock_redis.setex.call_args
        value_str = call_args[0][2]
        value = json.loads(value_str)
        
        self.assertEqual(value["currency"], "USD")
        self.assertAlmostEqual(value["rate"], 0.000043)
        self.assertIn("timestamp", value)
    
    def test_cache_update_uses_configured_ttl(self):
        """TTL should match CACHE_TTL_SECONDS config."""
        self.mock_redis.setex.return_value = True
        
        import producer
        original_ttl = producer.Config.CACHE_TTL_SECONDS
        
        rates = {"USD": 0.000043}
        self.producer._update_cache(rates)
        
        call_args = self.mock_redis.setex.call_args
        ttl = call_args[0][1]
        self.assertEqual(ttl, original_ttl)
    
    def test_cache_update_continues_on_redis_failure(self):
        """If one currency fails to cache, others should still be attempted."""
        import redis as redis_lib
        
        # First call fails, second succeeds
        self.mock_redis.setex.side_effect = [
            redis_lib.RedisError("Connection error"),
            True
        ]
        
        rates = {"USD": 0.000043, "EUR": 0.000039}
        # Should not raise
        self.producer._update_cache(rates)
        
        # Both currencies should have been attempted
        self.assertEqual(self.mock_redis.setex.call_count, 2)


class TestPollOnce(unittest.TestCase):
    """Tests for poll_once method."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.redis_patcher = patch("producer.redis.Redis")
        self.mock_redis_class = self.redis_patcher.start()
        self.mock_redis = MagicMock()
        self.mock_redis.ping.return_value = True
        self.mock_redis.setex.return_value = True
        self.mock_redis_class.return_value = self.mock_redis
        
        import producer
        self.producer_module = producer
        
        with patch.object(producer.ExchangeRateAPIClient, "__init__", return_value=None):
            self.producer = producer.ExchangeRateProducer.__new__(producer.ExchangeRateProducer)
            self.producer.redis_client = producer.RedisClient.__new__(producer.RedisClient)
            self.producer.redis_client.client = self.mock_redis
            self.producer.api_client = MagicMock()
            self.producer.supported_currencies = ["USD", "EUR", "GBP"]
            self.producer.cloudwatch_client = MagicMock()
    
    def tearDown(self):
        self.redis_patcher.stop()
    
    def test_poll_once_returns_true_on_success(self):
        """poll_once should return True when API call succeeds."""
        self.producer.api_client.fetch_rates.return_value = {
            "USD": 0.000043,
            "EUR": 0.000039,
            "GBP": 0.000034,
        }
        
        result = self.producer.poll_once()
        
        self.assertTrue(result)
    
    def test_poll_once_returns_false_when_api_fails(self):
        """poll_once should return False when API returns None."""
        self.producer.api_client.fetch_rates.return_value = None
        
        result = self.producer.poll_once()
        
        self.assertFalse(result)
    
    def test_poll_once_does_not_update_cache_on_api_failure(self):
        """Cache should NOT be updated when API fails (retain existing data)."""
        self.producer.api_client.fetch_rates.return_value = None
        
        self.producer.poll_once()
        
        # Redis setex should NOT have been called
        self.mock_redis.setex.assert_not_called()
    
    def test_poll_once_updates_cache_on_success(self):
        """Cache should be updated when API succeeds."""
        self.producer.api_client.fetch_rates.return_value = {
            "USD": 0.000043,
            "EUR": 0.000039,
        }
        
        self.producer.poll_once()
        
        # Redis setex should have been called for each currency
        self.assertGreater(self.mock_redis.setex.call_count, 0)
    
    def test_poll_once_returns_false_when_no_supported_currencies(self):
        """poll_once should return False when API returns no supported currencies."""
        self.producer.api_client.fetch_rates.return_value = {
            "AED": 0.000158,  # Not in supported list
            "ZAR": 0.00079,   # Not in supported list
        }
        
        result = self.producer.poll_once()
        
        self.assertFalse(result)
    
    @patch("producer._log")
    def test_poll_once_logs_cache_preserved_on_api_failure(self, mock_log):
        """poll_once should log that cache is preserved when API fails."""
        self.producer.api_client.fetch_rates.return_value = None
        
        self.producer.poll_once()
        
        # Find the WARN log about cache preservation
        warn_calls = [c for c in mock_log.call_args_list if c[0][0] == "WARN"]
        self.assertGreater(len(warn_calls), 0)
        # At least one WARN log should mention cache_preserved action
        cache_preserved_logs = [
            c for c in warn_calls
            if c[1].get("action") == "cache_preserved"
        ]
        self.assertGreater(len(cache_preserved_logs), 0)
    
    @patch("producer._log")
    def test_poll_once_logs_timestamp_on_api_failure(self, mock_log):
        """poll_once should include timestamp in the failure log."""
        self.producer.api_client.fetch_rates.return_value = None
        
        self.producer.poll_once()
        
        warn_calls = [c for c in mock_log.call_args_list if c[0][0] == "WARN"]
        cache_preserved_logs = [
            c for c in warn_calls
            if c[1].get("action") == "cache_preserved"
        ]
        self.assertGreater(len(cache_preserved_logs), 0)
        self.assertIn("timestamp", cache_preserved_logs[0][1])


class TestRedisSetRate(unittest.TestCase):
    """Tests for RedisClient.set_rate method."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.redis_patcher = patch("producer.redis.Redis")
        self.mock_redis_class = self.redis_patcher.start()
        self.mock_redis = MagicMock()
        self.mock_redis.ping.return_value = True
        self.mock_redis_class.return_value = self.mock_redis
        
        import producer
        self.redis_client = producer.RedisClient()
    
    def tearDown(self):
        self.redis_patcher.stop()
    
    def test_set_rate_returns_true_on_success(self):
        """set_rate should return True when Redis call succeeds."""
        self.mock_redis.setex.return_value = True
        
        result = self.redis_client.set_rate("USD", 0.000043, 30)
        
        self.assertTrue(result)
    
    def test_set_rate_returns_false_on_redis_error(self):
        """set_rate should return False when Redis raises an error."""
        import redis as redis_lib
        self.mock_redis.setex.side_effect = redis_lib.RedisError("Connection lost")
        
        result = self.redis_client.set_rate("USD", 0.000043, 30)
        
        self.assertFalse(result)
    
    def test_set_rate_uses_correct_key_format(self):
        """Key should be exchange_rate:{currency}."""
        self.mock_redis.setex.return_value = True
        
        self.redis_client.set_rate("EUR", 0.000039, 30)
        
        call_args = self.mock_redis.setex.call_args
        self.assertEqual(call_args[0][0], "exchange_rate:EUR")
    
    def test_set_rate_stores_rate_in_json(self):
        """Value should be JSON with currency, rate, and timestamp."""
        self.mock_redis.setex.return_value = True
        
        self.redis_client.set_rate("JPY", 0.0065, 30)
        
        call_args = self.mock_redis.setex.call_args
        value = json.loads(call_args[0][2])
        
        self.assertEqual(value["currency"], "JPY")
        self.assertAlmostEqual(value["rate"], 0.0065)
        self.assertIn("timestamp", value)
        # Timestamp should be recent
        self.assertAlmostEqual(value["timestamp"], time.time(), delta=5)


class TestNormalizeRatesToVND(unittest.TestCase):
    """Tests for ExchangeRateAPIClient._normalize_rates_to_vnd."""

    def setUp(self):
        import producer
        self.client = producer.ExchangeRateAPIClient()

    # ── VND base (no conversion needed) ──────────────────────────────────────

    def test_vnd_base_returns_rates_unchanged(self):
        """When base is VND, rates should be returned as-is."""
        rates = {"USD": 0.000043, "EUR": 0.000039, "JPY": 0.0065}
        result = self.client._normalize_rates_to_vnd("VND", rates)
        self.assertAlmostEqual(result["USD"], 0.000043)
        self.assertAlmostEqual(result["EUR"], 0.000039)
        self.assertAlmostEqual(result["JPY"], 0.0065)

    def test_vnd_base_case_insensitive(self):
        """Base currency comparison should be case-insensitive."""
        rates = {"USD": 0.000043}
        result_lower = self.client._normalize_rates_to_vnd("vnd", rates)
        result_upper = self.client._normalize_rates_to_vnd("VND", rates)
        self.assertAlmostEqual(result_lower["USD"], result_upper["USD"])

    def test_vnd_base_filters_zero_rates(self):
        """Zero rates should be excluded from the result."""
        rates = {"USD": 0.000043, "EUR": 0.0, "GBP": 0.000034}
        result = self.client._normalize_rates_to_vnd("VND", rates)
        self.assertIn("USD", result)
        self.assertNotIn("EUR", result)
        self.assertIn("GBP", result)

    def test_vnd_base_filters_negative_rates(self):
        """Negative rates should be excluded from the result."""
        rates = {"USD": 0.000043, "EUR": -0.5}
        result = self.client._normalize_rates_to_vnd("VND", rates)
        self.assertIn("USD", result)
        self.assertNotIn("EUR", result)

    def test_vnd_base_empty_rates_returns_empty_dict(self):
        """Empty rates dict with VND base should return empty dict."""
        result = self.client._normalize_rates_to_vnd("VND", {})
        self.assertEqual(result, {})

    # ── Non-VND base (conversion required) ───────────────────────────────────

    def test_usd_base_converts_correctly(self):
        """
        When base is USD, rates must be converted to VND base.

        API says: 1 USD = 23256 VND, 1 USD = 0.92 EUR
        Therefore: 1 VND = 0.92 / 23256 EUR ≈ 0.00003956 EUR
        """
        rates = {"VND": 23256.0, "EUR": 0.92, "GBP": 0.79}
        result = self.client._normalize_rates_to_vnd("USD", rates)

        self.assertIsNotNone(result)
        self.assertNotIn("VND", result)  # VND itself should not appear
        self.assertAlmostEqual(result["EUR"], 0.92 / 23256.0, places=12)
        self.assertAlmostEqual(result["GBP"], 0.79 / 23256.0, places=12)

    def test_eur_base_converts_correctly(self):
        """
        When base is EUR, rates must be converted to VND base.

        API says: 1 EUR = 26000 VND, 1 EUR = 1.09 USD
        Therefore: 1 VND = 1.09 / 26000 USD ≈ 0.0000419 USD
        """
        rates = {"VND": 26000.0, "USD": 1.09, "GBP": 0.86}
        result = self.client._normalize_rates_to_vnd("EUR", rates)

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["USD"], 1.09 / 26000.0, places=12)
        self.assertAlmostEqual(result["GBP"], 0.86 / 26000.0, places=12)

    def test_non_vnd_base_missing_vnd_returns_none(self):
        """If the API response with non-VND base doesn't include VND rate, return None."""
        rates = {"EUR": 0.92, "GBP": 0.79}  # VND missing
        result = self.client._normalize_rates_to_vnd("USD", rates)
        self.assertIsNone(result)

    def test_non_vnd_base_zero_vnd_rate_returns_none(self):
        """If VND rate is zero (would cause division by zero), return None."""
        rates = {"VND": 0.0, "EUR": 0.92}
        result = self.client._normalize_rates_to_vnd("USD", rates)
        self.assertIsNone(result)

    def test_non_vnd_base_negative_vnd_rate_returns_none(self):
        """If VND rate is negative (invalid), return None."""
        rates = {"VND": -100.0, "EUR": 0.92}
        result = self.client._normalize_rates_to_vnd("USD", rates)
        self.assertIsNone(result)

    def test_non_vnd_base_filters_invalid_rates_during_conversion(self):
        """Zero/negative rates for other currencies should be skipped during conversion."""
        rates = {"VND": 23256.0, "EUR": 0.92, "BAD": 0.0, "NEG": -1.0}
        result = self.client._normalize_rates_to_vnd("USD", rates)
        self.assertIsNotNone(result)
        self.assertIn("EUR", result)
        self.assertNotIn("BAD", result)
        self.assertNotIn("NEG", result)

    def test_non_vnd_base_vnd_excluded_from_result(self):
        """VND should never appear as a key in the normalized output."""
        rates = {"VND": 23256.0, "USD": 1.0, "EUR": 0.92}
        result = self.client._normalize_rates_to_vnd("USD", rates)
        self.assertNotIn("VND", result)

    def test_non_vnd_base_only_vnd_in_rates_returns_empty(self):
        """If the only rate is VND itself, result should be empty (no other currencies)."""
        rates = {"VND": 23256.0}
        result = self.client._normalize_rates_to_vnd("USD", rates)
        self.assertIsNotNone(result)
        self.assertEqual(result, {})


class TestAPIResponseParsing(unittest.TestCase):
    """Tests for API response parsing in ExchangeRateAPIClient."""
    
    def setUp(self):
        """Set up test fixtures."""
        import producer
        self.client = producer.ExchangeRateAPIClient()
    
    @patch("producer.requests.Session.get")
    @patch("producer._log")
    def test_fetch_rates_logs_timeout_with_timestamp(self, mock_log, mock_get):
        """fetch_rates should log timeout errors with timestamp and cache preservation action."""
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.Timeout("Request timed out")
        
        result = self.client.fetch_rates()
        
        self.assertIsNone(result)
        # Verify that ERROR log was called with timestamp and action
        error_calls = [call for call in mock_log.call_args_list if call[0][0] == "ERROR"]
        self.assertGreater(len(error_calls), 0)
        # Check that the log includes timestamp and action
        log_kwargs = error_calls[0][1]
        self.assertIn("timestamp", log_kwargs)
        self.assertEqual(log_kwargs["action"], "retaining_existing_cache")
    
    @patch("producer.requests.Session.get")
    @patch("producer._log")
    def test_fetch_rates_logs_http_error_with_timestamp(self, mock_log, mock_get):
        """fetch_rates should log HTTP errors with timestamp and cache preservation action."""
        import requests as req_lib
        mock_response = MagicMock()
        mock_response.status_code = 500
        http_error = req_lib.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response
        
        result = self.client.fetch_rates()
        
        self.assertIsNone(result)
        error_calls = [call for call in mock_log.call_args_list if call[0][0] == "ERROR"]
        self.assertGreater(len(error_calls), 0)
        log_kwargs = error_calls[0][1]
        self.assertIn("timestamp", log_kwargs)
        self.assertEqual(log_kwargs["action"], "retaining_existing_cache")
    
    @patch("producer.requests.Session.get")
    @patch("producer._log")
    def test_fetch_rates_logs_connection_error_with_details(self, mock_log, mock_get):
        """fetch_rates should log connection errors with error type, timestamp, and action."""
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.ConnectionError("Connection refused")
        
        result = self.client.fetch_rates()
        
        self.assertIsNone(result)
        error_calls = [call for call in mock_log.call_args_list if call[0][0] == "ERROR"]
        self.assertGreater(len(error_calls), 0)
        log_kwargs = error_calls[0][1]
        self.assertIn("timestamp", log_kwargs)
        self.assertIn("error_type", log_kwargs)
        self.assertEqual(log_kwargs["action"], "retaining_existing_cache")
    
    @patch("producer.requests.Session.get")
    @patch("producer._log")
    def test_fetch_rates_logs_json_decode_error_with_timestamp(self, mock_log, mock_get):
        """fetch_rates should log JSON decode errors with timestamp and action."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_get.return_value = mock_response
        
        result = self.client.fetch_rates()
        
        self.assertIsNone(result)
        error_calls = [call for call in mock_log.call_args_list if call[0][0] == "ERROR"]
        self.assertGreater(len(error_calls), 0)
        log_kwargs = error_calls[0][1]
        self.assertIn("timestamp", log_kwargs)
        self.assertEqual(log_kwargs["action"], "retaining_existing_cache")
    
    @patch("producer.requests.Session.get")
    def test_fetch_rates_returns_dict_on_success_vnd_base(self, mock_get):
        """fetch_rates should return a normalized dict of rates when base is VND."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "base": "VND",
            "rates": {
                "USD": 0.000043,
                "EUR": 0.000039,
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = self.client.fetch_rates()
        
        self.assertIsNotNone(result)
        self.assertIn("USD", result)
        self.assertIn("EUR", result)
        self.assertAlmostEqual(result["USD"], 0.000043)
        self.assertAlmostEqual(result["EUR"], 0.000039)

    @patch("producer.requests.Session.get")
    def test_fetch_rates_normalizes_non_vnd_base(self, mock_get):
        """
        fetch_rates should convert rates to VND base when API returns a different base.

        API: 1 USD = 23256 VND, 1 USD = 0.92 EUR
        Expected: 1 VND = 0.92 / 23256 EUR
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "base": "USD",
            "rates": {
                "VND": 23256.0,
                "EUR": 0.92,
                "GBP": 0.79,
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.client.fetch_rates()

        self.assertIsNotNone(result)
        self.assertNotIn("VND", result)
        self.assertAlmostEqual(result["EUR"], 0.92 / 23256.0, places=12)
        self.assertAlmostEqual(result["GBP"], 0.79 / 23256.0, places=12)

    @patch("producer.requests.Session.get")
    def test_fetch_rates_returns_none_when_non_vnd_base_missing_vnd(self, mock_get):
        """fetch_rates should return None when base is not VND and VND is absent from rates."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "base": "USD",
            "rates": {
                "EUR": 0.92,
                "GBP": 0.79,
                # VND missing — cannot convert
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.client.fetch_rates()

        self.assertIsNone(result)

    @patch("producer.requests.Session.get")
    def test_fetch_rates_returns_none_on_timeout(self, mock_get):
        """fetch_rates should return None when request times out."""
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.Timeout("Request timed out")
        
        result = self.client.fetch_rates()
        
        self.assertIsNone(result)
    
    @patch("producer.requests.Session.get")
    def test_fetch_rates_returns_none_on_http_error(self, mock_get):
        """fetch_rates should return None on HTTP error responses."""
        import requests as req_lib
        mock_response = MagicMock()
        mock_response.status_code = 429
        http_error = req_lib.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response
        
        result = self.client.fetch_rates()
        
        self.assertIsNone(result)
    
    @patch("producer.requests.Session.get")
    def test_fetch_rates_returns_none_on_invalid_json(self, mock_get):
        """fetch_rates should return None when response is not valid JSON."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_get.return_value = mock_response
        
        result = self.client.fetch_rates()
        
        self.assertIsNone(result)
    
    @patch("producer.requests.Session.get")
    def test_fetch_rates_returns_none_when_rates_field_missing(self, mock_get):
        """fetch_rates should return None when 'rates' field is absent."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "base": "VND",
            # 'rates' field is missing
        }
        mock_get.return_value = mock_response
        
        result = self.client.fetch_rates()
        
        self.assertIsNone(result)
    
    @patch("producer.requests.Session.get")
    def test_fetch_rates_returns_none_on_connection_error(self, mock_get):
        """fetch_rates should return None on connection errors."""
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.ConnectionError("Connection refused")
        
        result = self.client.fetch_rates()
        
        self.assertIsNone(result)

    @patch("producer.requests.Session.get")
    def test_fetch_rates_filters_zero_rates_with_vnd_base(self, mock_get):
        """fetch_rates should exclude currencies with zero rates when base is VND."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "base": "VND",
            "rates": {
                "USD": 0.000043,
                "EUR": 0.0,   # invalid — should be excluded
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.client.fetch_rates()

        self.assertIsNotNone(result)
        self.assertIn("USD", result)
        self.assertNotIn("EUR", result)

    @patch("producer.requests.Session.get")
    def test_fetch_rates_assumes_vnd_base_when_base_field_missing(self, mock_get):
        """fetch_rates should default to VND base when 'base' field is absent."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            # 'base' field missing — should default to VND
            "rates": {
                "USD": 0.000043,
                "EUR": 0.000039,
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.client.fetch_rates()

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["USD"], 0.000043)
        self.assertAlmostEqual(result["EUR"], 0.000039)


class TestCloudWatchMetricEmission(unittest.TestCase):
    """Tests for CloudWatch metric emission after cache writes."""

    def setUp(self):
        self.redis_patcher = patch("producer.redis.Redis")
        self.mock_redis_class = self.redis_patcher.start()
        self.mock_redis = MagicMock()
        self.mock_redis.ping.return_value = True
        self.mock_redis.setex.return_value = True
        self.mock_redis_class.return_value = self.mock_redis

        import producer
        self.producer_module = producer

        with patch.object(producer.ExchangeRateAPIClient, "__init__", return_value=None):
            self.producer = producer.ExchangeRateProducer.__new__(producer.ExchangeRateProducer)
            self.producer.redis_client = producer.RedisClient.__new__(producer.RedisClient)
            self.producer.redis_client.client = self.mock_redis
            self.producer.api_client = MagicMock()
            self.producer.supported_currencies = ["USD", "EUR"]
            self.producer.cloudwatch_client = MagicMock()

    def tearDown(self):
        self.redis_patcher.stop()

    def test_cloudwatch_metric_emitted_after_successful_cache_write(self):
        """emit_cache_updated should be called when at least one currency is written."""
        rates = {"USD": 0.000043, "EUR": 0.000039}
        self.producer._update_cache(rates)

        self.producer.cloudwatch_client.emit_cache_updated.assert_called_once()

    def test_cloudwatch_metric_not_emitted_when_all_redis_writes_fail(self):
        """emit_cache_updated should NOT be called when all Redis writes fail."""
        import redis as redis_lib
        self.mock_redis.setex.side_effect = redis_lib.RedisError("Connection lost")

        rates = {"USD": 0.000043, "EUR": 0.000039}
        self.producer._update_cache(rates)

        self.producer.cloudwatch_client.emit_cache_updated.assert_not_called()

    def test_cloudwatch_metric_emitted_when_partial_redis_writes_succeed(self):
        """emit_cache_updated should be called even if only some currencies succeed."""
        import redis as redis_lib
        self.mock_redis.setex.side_effect = [
            redis_lib.RedisError("Connection error"),
            True,  # second currency succeeds
        ]

        rates = {"USD": 0.000043, "EUR": 0.000039}
        self.producer._update_cache(rates)

        self.producer.cloudwatch_client.emit_cache_updated.assert_called_once()

    def test_cloudwatch_emit_failure_does_not_raise(self):
        """A failure in CloudWatch emission must not propagate to the caller."""
        self.producer.cloudwatch_client.emit_cache_updated.side_effect = Exception(
            "CloudWatch unavailable"
        )

        rates = {"USD": 0.000043}
        # Should not raise
        try:
            self.producer._update_cache(rates)
        except Exception:
            self.fail("_update_cache raised an exception when CloudWatch failed")


class TestCloudWatchClientEmitCacheUpdated(unittest.TestCase):
    """Tests for CloudWatchClient.emit_cache_updated."""

    def setUp(self):
        import producer
        self.producer_module = producer

    @patch("producer.boto3.client")
    def test_emit_cache_updated_calls_put_metric_data(self, mock_boto_client):
        """emit_cache_updated should call put_metric_data with correct parameters."""
        import producer
        original = producer.Config.ENABLE_CLOUDWATCH_METRICS
        try:
            producer.Config.ENABLE_CLOUDWATCH_METRICS = True
            mock_cw = MagicMock()
            mock_boto_client.return_value = mock_cw

            client = producer.CloudWatchClient()
            client.emit_cache_updated()

            mock_cw.put_metric_data.assert_called_once()
            call_kwargs = mock_cw.put_metric_data.call_args[1]
            self.assertEqual(call_kwargs["Namespace"], producer.Config.CLOUDWATCH_NAMESPACE)
            metric = call_kwargs["MetricData"][0]
            self.assertEqual(metric["MetricName"], "ExchangeRateCacheAge")
            self.assertEqual(metric["Value"], 0)
            self.assertEqual(metric["Unit"], "Seconds")
        finally:
            producer.Config.ENABLE_CLOUDWATCH_METRICS = original

    @patch("producer.boto3.client")
    def test_emit_cache_updated_skipped_when_metrics_disabled(self, mock_boto_client):
        """emit_cache_updated should do nothing when ENABLE_CLOUDWATCH_METRICS is False."""
        import producer
        original = producer.Config.ENABLE_CLOUDWATCH_METRICS
        try:
            producer.Config.ENABLE_CLOUDWATCH_METRICS = False
            client = producer.CloudWatchClient()
            client.emit_cache_updated()

            mock_boto_client.assert_not_called()
        finally:
            producer.Config.ENABLE_CLOUDWATCH_METRICS = original

    @patch("producer.boto3.client")
    def test_emit_cache_updated_swallows_cloudwatch_errors(self, mock_boto_client):
        """emit_cache_updated should not raise when put_metric_data fails."""
        import producer
        original = producer.Config.ENABLE_CLOUDWATCH_METRICS
        try:
            producer.Config.ENABLE_CLOUDWATCH_METRICS = True
            mock_cw = MagicMock()
            mock_cw.put_metric_data.side_effect = Exception("CloudWatch error")
            mock_boto_client.return_value = mock_cw

            client = producer.CloudWatchClient()
            # Should not raise
            client.emit_cache_updated()
        finally:
            producer.Config.ENABLE_CLOUDWATCH_METRICS = original


class TestConfigValidation(unittest.TestCase):
    """Tests for Config validation."""
    
    def test_validate_raises_on_missing_redis_host(self):
        """Config.validate should raise ValueError when REDIS_HOST is empty."""
        import producer
        original = producer.Config.REDIS_HOST
        try:
            producer.Config.REDIS_HOST = ""
            with self.assertRaises(ValueError):
                producer.Config.validate()
        finally:
            producer.Config.REDIS_HOST = original
    
    def test_validate_raises_on_zero_polling_interval(self):
        """Config.validate should raise ValueError when POLLING_INTERVAL_SECONDS is 0."""
        import producer
        original = producer.Config.POLLING_INTERVAL_SECONDS
        try:
            producer.Config.POLLING_INTERVAL_SECONDS = 0
            with self.assertRaises(ValueError):
                producer.Config.validate()
        finally:
            producer.Config.POLLING_INTERVAL_SECONDS = original
    
    def test_validate_raises_on_negative_polling_interval(self):
        """Config.validate should raise ValueError when POLLING_INTERVAL_SECONDS is negative."""
        import producer
        original = producer.Config.POLLING_INTERVAL_SECONDS
        try:
            producer.Config.POLLING_INTERVAL_SECONDS = -5
            with self.assertRaises(ValueError):
                producer.Config.validate()
        finally:
            producer.Config.POLLING_INTERVAL_SECONDS = original
    
    def test_validate_passes_with_valid_config(self):
        """Config.validate should not raise with valid configuration."""
        import producer
        # Should not raise
        producer.Config.validate()


if __name__ == "__main__":
    unittest.main()
