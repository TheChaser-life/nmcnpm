"""
Unit tests for Dataset Maker service.

Tests cover:
- Config validation
- RedisClient.fetch_all_rates — parsing, malformed entries, empty cache
- PostgreSQLClient.fetch_transaction_stats — query logic, empty results
- DataProcessor helpers — _parse_timestamp, _extract_time_features,
  _normalize_rates, _forward_fill_missing
- DataProcessor.build_csv — column structure, merging, sorting, normalisation,
  time features, forward-fill, empty inputs
- S3Uploader.upload — correct S3 key path, content type
- DatasetMaker.run — happy path, Redis empty, DB failure, S3 failure
"""

import csv
import io
import json
import sys
import os
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

# Add parent directory to path so we can import dataset_maker
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Config Tests ──────────────────────────────────────────────────────────────

class TestConfig(unittest.TestCase):
    """Tests for Config.validate()."""

    def _make_env(self, overrides=None):
        """Return a minimal valid env dict, with optional overrides."""
        base = {
            "REDIS_HOST": "redis-host",
            "REDIS_PORT": "6379",
            "DB_HOST": "db-host",
            "DB_PORT": "5432",
            "DB_NAME": "mydb",
            "DB_USER": "user",
            "DB_PASSWORD": "pass",
            "S3_BUCKET": "my-bucket",
            "S3_PREFIX": "training-data",
            "LOOKBACK_HOURS": "24",
            "AWS_REGION": "ap-southeast-1",
        }
        if overrides:
            base.update(overrides)
        return base

    def test_validate_passes_with_all_required_vars(self):
        """Config.validate() should not raise when all required vars are set."""
        with patch.dict(os.environ, self._make_env(), clear=True):
            import importlib
            import dataset_maker
            importlib.reload(dataset_maker)
            # Should not raise
            dataset_maker.Config.validate()

    def test_validate_raises_when_s3_bucket_missing(self):
        """Config.validate() should raise ValueError when S3_BUCKET is empty."""
        env = self._make_env({"S3_BUCKET": ""})
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import dataset_maker
            importlib.reload(dataset_maker)
            with self.assertRaises(ValueError) as ctx:
                dataset_maker.Config.validate()
            self.assertIn("S3_BUCKET", str(ctx.exception))

    def test_validate_raises_when_lookback_hours_zero(self):
        """Config.validate() should raise ValueError when LOOKBACK_HOURS is 0."""
        env = self._make_env({"LOOKBACK_HOURS": "0"})
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import dataset_maker
            importlib.reload(dataset_maker)
            with self.assertRaises(ValueError) as ctx:
                dataset_maker.Config.validate()
            self.assertIn("LOOKBACK_HOURS", str(ctx.exception))

    def test_validate_raises_when_redis_host_missing(self):
        """Config.validate() should raise ValueError when REDIS_HOST is empty."""
        env = self._make_env({"REDIS_HOST": ""})
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import dataset_maker
            importlib.reload(dataset_maker)
            with self.assertRaises(ValueError) as ctx:
                dataset_maker.Config.validate()
            self.assertIn("REDIS_HOST", str(ctx.exception))

    def test_s3_training_bucket_takes_precedence_over_s3_bucket(self):
        """S3_TRAINING_BUCKET env var should be used when set, overriding S3_BUCKET."""
        env = self._make_env({"S3_BUCKET": "old-bucket", "S3_TRAINING_BUCKET": "new-training-bucket"})
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import dataset_maker
            importlib.reload(dataset_maker)
            # S3_TRAINING_BUCKET should win
            self.assertEqual(dataset_maker.Config.S3_BUCKET, "new-training-bucket")

    def test_s3_bucket_used_when_s3_training_bucket_not_set(self):
        """S3_BUCKET env var should be used when S3_TRAINING_BUCKET is absent."""
        env = self._make_env({"S3_BUCKET": "fallback-bucket"})
        # Ensure S3_TRAINING_BUCKET is not in env
        env.pop("S3_TRAINING_BUCKET", None)
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import dataset_maker
            importlib.reload(dataset_maker)
            self.assertEqual(dataset_maker.Config.S3_BUCKET, "fallback-bucket")


# ── RedisClient Tests ─────────────────────────────────────────────────────────

class TestRedisClientFetchAllRates(unittest.TestCase):
    """Tests for RedisClient.fetch_all_rates()."""

    def _make_redis_client(self, mock_redis):
        """Create a RedisClient with a pre-injected mock Redis connection."""
        import dataset_maker
        client = dataset_maker.RedisClient.__new__(dataset_maker.RedisClient)
        client.client = mock_redis
        return client

    def test_returns_parsed_records_for_valid_keys(self):
        """fetch_all_rates should return one record per valid exchange_rate:* key."""
        import dataset_maker

        mock_redis = MagicMock()
        # SCAN returns cursor=0 (done) and two keys
        mock_redis.scan.return_value = (
            0,
            ["exchange_rate:USD", "exchange_rate:EUR"],
        )
        mock_redis.get.side_effect = [
            json.dumps({"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}),
            json.dumps({"currency": "EUR", "rate": 0.000039, "timestamp": 1700000001.0}),
        ]

        client = self._make_redis_client(mock_redis)
        records = client.fetch_all_rates()

        self.assertEqual(len(records), 2)
        currencies = {r["currency"] for r in records}
        self.assertIn("USD", currencies)
        self.assertIn("EUR", currencies)

    def test_skips_expired_keys(self):
        """fetch_all_rates should skip keys that return None (expired between SCAN and GET)."""
        import dataset_maker

        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, ["exchange_rate:USD", "exchange_rate:EUR"])
        # USD expired, EUR still present
        mock_redis.get.side_effect = [None, json.dumps({"currency": "EUR", "rate": 0.000039, "timestamp": 1700000000.0})]

        client = self._make_redis_client(mock_redis)
        records = client.fetch_all_rates()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["currency"], "EUR")

    def test_skips_malformed_json_entries(self):
        """fetch_all_rates should skip entries with invalid JSON."""
        import dataset_maker

        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, ["exchange_rate:USD", "exchange_rate:BAD"])
        mock_redis.get.side_effect = [
            json.dumps({"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}),
            "not-valid-json{{",
        ]

        client = self._make_redis_client(mock_redis)
        records = client.fetch_all_rates()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["currency"], "USD")

    def test_skips_entries_missing_required_fields(self):
        """fetch_all_rates should skip entries missing 'currency' or 'rate'."""
        import dataset_maker

        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, ["exchange_rate:USD", "exchange_rate:INCOMPLETE"])
        mock_redis.get.side_effect = [
            json.dumps({"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}),
            json.dumps({"currency": "INCOMPLETE"}),  # missing 'rate'
        ]

        client = self._make_redis_client(mock_redis)
        records = client.fetch_all_rates()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["currency"], "USD")

    def test_returns_empty_list_when_no_keys(self):
        """fetch_all_rates should return [] when Redis has no exchange_rate:* keys."""
        import dataset_maker

        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, [])

        client = self._make_redis_client(mock_redis)
        records = client.fetch_all_rates()

        self.assertEqual(records, [])

    def test_handles_multiple_scan_pages(self):
        """fetch_all_rates should follow SCAN cursor pagination correctly."""
        import dataset_maker

        mock_redis = MagicMock()
        # First call returns cursor=5 (more pages), second returns cursor=0 (done)
        mock_redis.scan.side_effect = [
            (5, ["exchange_rate:USD"]),
            (0, ["exchange_rate:EUR"]),
        ]
        mock_redis.get.side_effect = [
            json.dumps({"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}),
            json.dumps({"currency": "EUR", "rate": 0.000039, "timestamp": 1700000001.0}),
        ]

        client = self._make_redis_client(mock_redis)
        records = client.fetch_all_rates()

        self.assertEqual(len(records), 2)
        self.assertEqual(mock_redis.scan.call_count, 2)


# ── DataProcessor Helper Tests ────────────────────────────────────────────────

class TestDataProcessorParseTimestamp(unittest.TestCase):
    """Tests for DataProcessor._parse_timestamp()."""

    def setUp(self):
        import dataset_maker
        self.processor = dataset_maker.DataProcessor()

    def test_parses_unix_float(self):
        """Should parse a Unix epoch float into a UTC datetime."""
        import dataset_maker
        dt = dataset_maker.DataProcessor._parse_timestamp(1700000000.0)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_parses_unix_int(self):
        """Should parse a Unix epoch int into a UTC datetime."""
        import dataset_maker
        dt = dataset_maker.DataProcessor._parse_timestamp(1700000000)
        self.assertIsNotNone(dt)

    def test_parses_iso_string_with_timezone(self):
        """Should parse an ISO 8601 string with timezone offset."""
        import dataset_maker
        dt = dataset_maker.DataProcessor._parse_timestamp("2024-01-15T00:00:00+00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)

    def test_parses_iso_string_without_timezone(self):
        """Should parse a naive ISO 8601 string and treat it as UTC."""
        import dataset_maker
        dt = dataset_maker.DataProcessor._parse_timestamp("2024-01-15T12:30:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.hour, 12)

    def test_returns_none_for_none_input(self):
        """Should return None when input is None."""
        import dataset_maker
        self.assertIsNone(dataset_maker.DataProcessor._parse_timestamp(None))

    def test_returns_none_for_invalid_string(self):
        """Should return None for unparseable strings."""
        import dataset_maker
        self.assertIsNone(dataset_maker.DataProcessor._parse_timestamp("not-a-date"))


class TestDataProcessorExtractTimeFeatures(unittest.TestCase):
    """Tests for DataProcessor._extract_time_features()."""

    def test_extracts_correct_hour(self):
        """Should extract the correct hour from a datetime."""
        import dataset_maker
        dt = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        hour, _, _ = dataset_maker.DataProcessor._extract_time_features(dt)
        self.assertEqual(hour, 14)

    def test_extracts_correct_day_of_week(self):
        """Should extract day_of_week as 0=Monday … 6=Sunday."""
        import dataset_maker
        # 2024-01-15 is a Monday
        dt = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        _, dow, _ = dataset_maker.DataProcessor._extract_time_features(dt)
        self.assertEqual(dow, 0)  # Monday

    def test_extracts_correct_day_of_month(self):
        """Should extract the correct day of month."""
        import dataset_maker
        dt = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        _, _, dom = dataset_maker.DataProcessor._extract_time_features(dt)
        self.assertEqual(dom, 15)

    def test_midnight_hour_is_zero(self):
        """Hour at midnight should be 0."""
        import dataset_maker
        dt = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        hour, _, _ = dataset_maker.DataProcessor._extract_time_features(dt)
        self.assertEqual(hour, 0)


class TestDataProcessorNormalizeRates(unittest.TestCase):
    """Tests for DataProcessor._normalize_rates()."""

    def test_normalizes_to_zero_one_range(self):
        """Min rate should map to 0.0 and max rate to 1.0."""
        import dataset_maker
        rows = [
            {"currency_code": "USD", "rate_to_vnd": 0.00004},
            {"currency_code": "USD", "rate_to_vnd": 0.00006},
            {"currency_code": "USD", "rate_to_vnd": 0.00005},
        ]
        result = dataset_maker.DataProcessor._normalize_rates(rows)
        rates_norm = [r["rate_normalized"] for r in result]
        self.assertAlmostEqual(min(rates_norm), 0.0)
        self.assertAlmostEqual(max(rates_norm), 1.0)

    def test_single_data_point_gets_0_5(self):
        """A currency with only one data point should get rate_normalized = 0.5."""
        import dataset_maker
        rows = [{"currency_code": "JPY", "rate_to_vnd": 0.0065}]
        result = dataset_maker.DataProcessor._normalize_rates(rows)
        self.assertAlmostEqual(result[0]["rate_normalized"], 0.5)

    def test_all_identical_rates_get_0_5(self):
        """When all rates for a currency are identical, normalized value should be 0.5."""
        import dataset_maker
        rows = [
            {"currency_code": "EUR", "rate_to_vnd": 0.00004},
            {"currency_code": "EUR", "rate_to_vnd": 0.00004},
        ]
        result = dataset_maker.DataProcessor._normalize_rates(rows)
        for r in result:
            self.assertAlmostEqual(r["rate_normalized"], 0.5)

    def test_normalizes_independently_per_currency(self):
        """Each currency should be normalised independently."""
        import dataset_maker
        rows = [
            {"currency_code": "USD", "rate_to_vnd": 0.00004},
            {"currency_code": "USD", "rate_to_vnd": 0.00006},
            {"currency_code": "EUR", "rate_to_vnd": 0.00003},
            {"currency_code": "EUR", "rate_to_vnd": 0.00009},
        ]
        result = dataset_maker.DataProcessor._normalize_rates(rows)
        usd_norms = [r["rate_normalized"] for r in result if r["currency_code"] == "USD"]
        eur_norms = [r["rate_normalized"] for r in result if r["currency_code"] == "EUR"]
        # Both currencies should span 0.0–1.0 independently
        self.assertAlmostEqual(min(usd_norms), 0.0)
        self.assertAlmostEqual(max(usd_norms), 1.0)
        self.assertAlmostEqual(min(eur_norms), 0.0)
        self.assertAlmostEqual(max(eur_norms), 1.0)

    def test_normalized_values_in_zero_one_range(self):
        """All normalized values must be in [0.0, 1.0]."""
        import dataset_maker
        rows = [
            {"currency_code": "USD", "rate_to_vnd": 0.00001},
            {"currency_code": "USD", "rate_to_vnd": 0.00005},
            {"currency_code": "USD", "rate_to_vnd": 0.00010},
        ]
        result = dataset_maker.DataProcessor._normalize_rates(rows)
        for r in result:
            self.assertGreaterEqual(r["rate_normalized"], 0.0)
            self.assertLessEqual(r["rate_normalized"], 1.0)


class TestDataProcessorForwardFill(unittest.TestCase):
    """Tests for DataProcessor._forward_fill_missing()."""

    def _make_row(self, ts_iso: str, currency: str, rate: float) -> dict:
        """Helper to build a minimal row dict."""
        dt = datetime.fromisoformat(ts_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return {
            "timestamp": dt.isoformat(),
            "currency_code": currency,
            "rate_to_vnd": rate,
            "rate_normalized": 0.5,
            "transaction_volume": 100.0,
            "transaction_count": 2,
            "hour": dt.hour,
            "day_of_week": dt.weekday(),
            "day_of_month": dt.day,
        }

    def test_no_gap_returns_same_rows(self):
        """Consecutive hourly rows should not produce any synthetic rows."""
        import dataset_maker
        rows = [
            self._make_row("2024-01-15T00:00:00+00:00", "USD", 0.00004),
            self._make_row("2024-01-15T01:00:00+00:00", "USD", 0.00005),
        ]
        result = dataset_maker.DataProcessor._forward_fill_missing(rows)
        usd_rows = [r for r in result if r["currency_code"] == "USD"]
        self.assertEqual(len(usd_rows), 2)

    def test_two_hour_gap_inserts_one_synthetic_row(self):
        """A 2-hour gap should produce 1 synthetic row between the two real rows."""
        import dataset_maker
        rows = [
            self._make_row("2024-01-15T00:00:00+00:00", "USD", 0.00004),
            self._make_row("2024-01-15T02:00:00+00:00", "USD", 0.00006),
        ]
        result = dataset_maker.DataProcessor._forward_fill_missing(rows)
        usd_rows = [r for r in result if r["currency_code"] == "USD"]
        self.assertEqual(len(usd_rows), 3)
        # The synthetic row should be at 01:00
        timestamps = [r["timestamp"] for r in usd_rows]
        self.assertTrue(any("T01:00:00" in ts for ts in timestamps))

    def test_synthetic_row_carries_forward_rate(self):
        """Synthetic rows should carry the previous row's rate_to_vnd."""
        import dataset_maker
        rows = [
            self._make_row("2024-01-15T00:00:00+00:00", "USD", 0.00004),
            self._make_row("2024-01-15T02:00:00+00:00", "USD", 0.00006),
        ]
        result = dataset_maker.DataProcessor._forward_fill_missing(rows)
        usd_rows = sorted(
            [r for r in result if r["currency_code"] == "USD"],
            key=lambda r: r["timestamp"],
        )
        # Middle row (01:00) should carry rate from 00:00
        self.assertAlmostEqual(usd_rows[1]["rate_to_vnd"], 0.00004)

    def test_synthetic_row_has_zero_transaction_stats(self):
        """Synthetic gap-fill rows should have transaction_volume=0 and transaction_count=0."""
        import dataset_maker
        rows = [
            self._make_row("2024-01-15T00:00:00+00:00", "USD", 0.00004),
            self._make_row("2024-01-15T02:00:00+00:00", "USD", 0.00006),
        ]
        result = dataset_maker.DataProcessor._forward_fill_missing(rows)
        usd_rows = sorted(
            [r for r in result if r["currency_code"] == "USD"],
            key=lambda r: r["timestamp"],
        )
        # Middle row is synthetic
        self.assertAlmostEqual(usd_rows[1]["transaction_volume"], 0.0)
        self.assertEqual(usd_rows[1]["transaction_count"], 0)

    def test_gap_larger_than_24h_not_filled(self):
        """Gaps larger than 24 hours should not be forward-filled."""
        import dataset_maker
        rows = [
            self._make_row("2024-01-15T00:00:00+00:00", "USD", 0.00004),
            self._make_row("2024-01-17T00:00:00+00:00", "USD", 0.00006),  # 48h gap
        ]
        result = dataset_maker.DataProcessor._forward_fill_missing(rows)
        usd_rows = [r for r in result if r["currency_code"] == "USD"]
        # Only the two original rows — no fill
        self.assertEqual(len(usd_rows), 2)

    def test_fill_is_independent_per_currency(self):
        """Forward-fill should operate independently for each currency."""
        import dataset_maker
        rows = [
            self._make_row("2024-01-15T00:00:00+00:00", "USD", 0.00004),
            self._make_row("2024-01-15T02:00:00+00:00", "USD", 0.00006),
            self._make_row("2024-01-15T00:00:00+00:00", "EUR", 0.00003),
            self._make_row("2024-01-15T01:00:00+00:00", "EUR", 0.00004),
        ]
        result = dataset_maker.DataProcessor._forward_fill_missing(rows)
        usd_rows = [r for r in result if r["currency_code"] == "USD"]
        eur_rows = [r for r in result if r["currency_code"] == "EUR"]
        # USD has a 2h gap → 3 rows; EUR has no gap → 2 rows
        self.assertEqual(len(usd_rows), 3)
        self.assertEqual(len(eur_rows), 2)

    def test_synthetic_row_has_correct_time_features(self):
        """Synthetic rows should have correct hour, day_of_week, day_of_month."""
        import dataset_maker
        rows = [
            self._make_row("2024-01-15T00:00:00+00:00", "USD", 0.00004),
            self._make_row("2024-01-15T02:00:00+00:00", "USD", 0.00006),
        ]
        result = dataset_maker.DataProcessor._forward_fill_missing(rows)
        usd_rows = sorted(
            [r for r in result if r["currency_code"] == "USD"],
            key=lambda r: r["timestamp"],
        )
        synthetic = usd_rows[1]  # 01:00 row
        self.assertEqual(synthetic["hour"], 1)
        self.assertEqual(synthetic["day_of_month"], 15)


# ── DataProcessor Tests ───────────────────────────────────────────────────────

class TestDataProcessorBuildCsv(unittest.TestCase):
    """Tests for DataProcessor.build_csv()."""

    def setUp(self):
        import dataset_maker
        self.processor = dataset_maker.DataProcessor()

    def _parse_csv(self, csv_content: str):
        """Parse CSV string into list of dicts."""
        reader = csv.DictReader(io.StringIO(csv_content))
        return list(reader)

    def test_csv_has_correct_columns(self):
        """CSV must contain exactly the nine required columns."""
        rate_records = [{"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}]
        tx_records = []

        csv_content = self.processor.build_csv(rate_records, tx_records)
        rows = self._parse_csv(csv_content)

        self.assertEqual(len(rows), 1)
        expected_cols = {
            "timestamp", "currency_code", "rate_to_vnd", "rate_normalized",
            "transaction_volume", "transaction_count",
            "hour", "day_of_week", "day_of_month",
        }
        self.assertEqual(set(rows[0].keys()), expected_cols)

    def test_rate_values_are_preserved(self):
        """rate_to_vnd in CSV must match the value from Redis."""
        rate_records = [{"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}]
        csv_content = self.processor.build_csv(rate_records, [])
        rows = self._parse_csv(csv_content)

        self.assertAlmostEqual(float(rows[0]["rate_to_vnd"]), 0.000043)

    def test_rate_normalized_is_present_and_in_range(self):
        """rate_normalized must be present and in [0.0, 1.0]."""
        rate_records = [
            {"currency": "USD", "rate": 0.000040, "timestamp": 1700000000.0},
            {"currency": "USD", "rate": 0.000060, "timestamp": 1700003600.0},
        ]
        csv_content = self.processor.build_csv(rate_records, [])
        rows = self._parse_csv(csv_content)

        for row in rows:
            norm = float(row["rate_normalized"])
            self.assertGreaterEqual(norm, 0.0)
            self.assertLessEqual(norm, 1.0)

    def test_single_currency_rate_normalized_is_0_5(self):
        """A single data point for a currency should get rate_normalized = 0.5."""
        rate_records = [{"currency": "JPY", "rate": 0.0065, "timestamp": 1700000000.0}]
        csv_content = self.processor.build_csv(rate_records, [])
        rows = self._parse_csv(csv_content)

        self.assertAlmostEqual(float(rows[0]["rate_normalized"]), 0.5)

    def test_time_features_are_present(self):
        """CSV rows must contain hour, day_of_week, and day_of_month columns."""
        rate_records = [{"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}]
        csv_content = self.processor.build_csv(rate_records, [])
        rows = self._parse_csv(csv_content)

        self.assertIn("hour", rows[0])
        self.assertIn("day_of_week", rows[0])
        self.assertIn("day_of_month", rows[0])

    def test_time_features_are_valid_ranges(self):
        """hour must be 0–23, day_of_week 0–6, day_of_month 1–31."""
        rate_records = [{"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}]
        csv_content = self.processor.build_csv(rate_records, [])
        rows = self._parse_csv(csv_content)

        hour = int(rows[0]["hour"])
        dow = int(rows[0]["day_of_week"])
        dom = int(rows[0]["day_of_month"])

        self.assertGreaterEqual(hour, 0)
        self.assertLessEqual(hour, 23)
        self.assertGreaterEqual(dow, 0)
        self.assertLessEqual(dow, 6)
        self.assertGreaterEqual(dom, 1)
        self.assertLessEqual(dom, 31)

    def test_transaction_stats_merged_by_currency(self):
        """Transaction volume and count should be merged from PostgreSQL data."""
        rate_records = [{"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}]
        tx_records = [
            {
                "timestamp": "2024-01-15T00:00:00+00:00",
                "currency_code": "USD",
                "transaction_volume": 5000.0,
                "transaction_count": 10,
            }
        ]

        csv_content = self.processor.build_csv(rate_records, tx_records)
        rows = self._parse_csv(csv_content)

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(float(rows[0]["transaction_volume"]), 5000.0)
        self.assertEqual(int(rows[0]["transaction_count"]), 10)

    def test_transaction_stats_aggregated_across_hours(self):
        """Multiple hour buckets for the same currency should be summed."""
        rate_records = [{"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}]
        tx_records = [
            {"timestamp": "2024-01-15T00:00:00+00:00", "currency_code": "USD", "transaction_volume": 1000.0, "transaction_count": 5},
            {"timestamp": "2024-01-15T01:00:00+00:00", "currency_code": "USD", "transaction_volume": 2000.0, "transaction_count": 8},
        ]

        csv_content = self.processor.build_csv(rate_records, tx_records)
        rows = self._parse_csv(csv_content)

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(float(rows[0]["transaction_volume"]), 3000.0)
        self.assertEqual(int(rows[0]["transaction_count"]), 13)

    def test_currency_with_no_transactions_gets_zero_values(self):
        """Currencies with no transaction data should have volume=0 and count=0."""
        rate_records = [{"currency": "JPY", "rate": 0.0065, "timestamp": 1700000000.0}]
        tx_records = []  # No transactions for JPY

        csv_content = self.processor.build_csv(rate_records, tx_records)
        rows = self._parse_csv(csv_content)

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(float(rows[0]["transaction_volume"]), 0.0)
        self.assertEqual(int(rows[0]["transaction_count"]), 0)

    def test_rows_sorted_by_timestamp_then_currency(self):
        """Rows should be sorted by timestamp ASC, then currency_code ASC."""
        rate_records = [
            {"currency": "USD", "rate": 0.000043, "timestamp": 1700003600.0},
            {"currency": "EUR", "rate": 0.000039, "timestamp": 1700000000.0},
        ]
        csv_content = self.processor.build_csv(rate_records, [])
        rows = self._parse_csv(csv_content)

        # EUR has earlier timestamp, so it should come first
        self.assertEqual(rows[0]["currency_code"], "EUR")
        self.assertEqual(rows[1]["currency_code"], "USD")

    def test_returns_header_only_when_no_rate_records(self):
        """When rate_records is empty, CSV should contain only the header row."""
        csv_content = self.processor.build_csv([], [])
        lines = [l for l in csv_content.strip().splitlines() if l]
        # Only header
        self.assertEqual(len(lines), 1)
        self.assertIn("timestamp", lines[0])

    def test_multiple_currencies_produce_multiple_rows(self):
        """Each currency in rate_records should produce one row in the CSV."""
        rate_records = [
            {"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0},
            {"currency": "EUR", "rate": 0.000039, "timestamp": 1700000000.0},
            {"currency": "JPY", "rate": 0.0065, "timestamp": 1700000000.0},
        ]
        csv_content = self.processor.build_csv(rate_records, [])
        rows = self._parse_csv(csv_content)

        self.assertEqual(len(rows), 3)
        currencies = {r["currency_code"] for r in rows}
        self.assertEqual(currencies, {"USD", "EUR", "JPY"})

    def test_csv_column_order_matches_spec(self):
        """CSV columns must appear in the exact order defined by CSV_COLUMNS."""
        import dataset_maker
        rate_records = [{"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}]
        csv_content = self.processor.build_csv(rate_records, [])
        header_line = csv_content.splitlines()[0]
        actual_cols = header_line.split(",")
        self.assertEqual(actual_cols, dataset_maker.DataProcessor.CSV_COLUMNS)

    def test_normalized_min_is_zero_and_max_is_one_for_multiple_rates(self):
        """When multiple rates exist for a currency, min→0.0 and max→1.0."""
        rate_records = [
            {"currency": "USD", "rate": 0.000040, "timestamp": 1700000000.0},
            {"currency": "USD", "rate": 0.000060, "timestamp": 1700003600.0},
        ]
        csv_content = self.processor.build_csv(rate_records, [])
        rows = self._parse_csv(csv_content)
        norms = sorted([float(r["rate_normalized"]) for r in rows])
        self.assertAlmostEqual(norms[0], 0.0)
        self.assertAlmostEqual(norms[-1], 1.0)


# ── S3Uploader Tests ──────────────────────────────────────────────────────────

class TestS3UploaderUpload(unittest.TestCase):
    """Tests for S3Uploader.upload()."""

    def setUp(self):
        import dataset_maker
        self.mock_s3 = MagicMock()
        self.uploader = dataset_maker.S3Uploader.__new__(dataset_maker.S3Uploader)
        self.uploader.client = self.mock_s3

    def test_upload_uses_correct_s3_key_format(self):
        """S3 key must follow training-data/{YYYY}/{MM}/{DD}/rates_{timestamp}.csv."""
        import dataset_maker
        dataset_maker.Config.S3_BUCKET = "test-bucket"
        dataset_maker.Config.S3_PREFIX = "training-data"

        run_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        self.uploader.upload("col1,col2\nval1,val2\n", run_time)

        call_kwargs = self.mock_s3.put_object.call_args[1]
        key = call_kwargs["Key"]

        self.assertTrue(key.startswith("training-data/2024/01/15/"))
        self.assertTrue(key.endswith(".csv"))
        self.assertIn("rates_", key)

    def test_upload_sets_content_type_to_text_csv(self):
        """S3 object ContentType must be text/csv."""
        import dataset_maker
        dataset_maker.Config.S3_BUCKET = "test-bucket"
        dataset_maker.Config.S3_PREFIX = "training-data"

        run_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        self.uploader.upload("col1\nval1\n", run_time)

        call_kwargs = self.mock_s3.put_object.call_args[1]
        self.assertEqual(call_kwargs["ContentType"], "text/csv")

    def test_upload_encodes_content_as_utf8(self):
        """S3 Body must be UTF-8 encoded bytes."""
        import dataset_maker
        dataset_maker.Config.S3_BUCKET = "test-bucket"
        dataset_maker.Config.S3_PREFIX = "training-data"

        csv_content = "timestamp,currency_code\n2024-01-15,USD\n"
        run_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        self.uploader.upload(csv_content, run_time)

        call_kwargs = self.mock_s3.put_object.call_args[1]
        self.assertEqual(call_kwargs["Body"], csv_content.encode("utf-8"))

    def test_upload_returns_s3_key(self):
        """upload() should return the S3 key string."""
        import dataset_maker
        dataset_maker.Config.S3_BUCKET = "test-bucket"
        dataset_maker.Config.S3_PREFIX = "training-data"

        run_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        result = self.uploader.upload("col1\nval1\n", run_time)

        self.assertIsInstance(result, str)
        self.assertIn("training-data/2024/01/15/", result)

    def test_upload_raises_on_s3_error(self):
        """upload() should propagate S3 exceptions."""
        import dataset_maker
        dataset_maker.Config.S3_BUCKET = "test-bucket"
        dataset_maker.Config.S3_PREFIX = "training-data"

        self.mock_s3.put_object.side_effect = Exception("S3 access denied")

        run_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(Exception) as ctx:
            self.uploader.upload("col1\nval1\n", run_time)
        self.assertIn("S3 access denied", str(ctx.exception))

    def test_upload_uses_server_side_encryption(self):
        """S3 put_object must include ServerSideEncryption=AES256 (SSE-S3)."""
        import dataset_maker
        dataset_maker.Config.S3_BUCKET = "test-bucket"
        dataset_maker.Config.S3_PREFIX = "training-data"

        run_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        self.uploader.upload("col1,col2\nval1,val2\n", run_time)

        call_kwargs = self.mock_s3.put_object.call_args[1]
        self.assertIn("ServerSideEncryption", call_kwargs)
        self.assertEqual(call_kwargs["ServerSideEncryption"], "AES256")


# ── DatasetMaker Integration Tests ────────────────────────────────────────────

class TestDatasetMakerRun(unittest.TestCase):
    """Integration-style tests for DatasetMaker.run()."""

    def _make_dataset_maker(self, rate_records, tx_records, s3_key="training-data/2024/01/15/rates_20240115T000000Z.csv"):
        """Build a DatasetMaker with all dependencies mocked."""
        import dataset_maker

        maker = dataset_maker.DatasetMaker.__new__(dataset_maker.DatasetMaker)

        # Mock Redis client
        maker.redis_client = MagicMock()
        maker.redis_client.fetch_all_rates.return_value = rate_records

        # Mock DB client
        maker.db_client = MagicMock()
        maker.db_client.fetch_transaction_stats.return_value = tx_records

        # Real processor
        maker.processor = dataset_maker.DataProcessor()

        # Mock S3 uploader
        maker.uploader = MagicMock()
        maker.uploader.upload.return_value = s3_key

        return maker

    def test_run_calls_all_steps_in_order(self):
        """run() should call Redis, DB, processor, and S3 uploader."""
        rate_records = [{"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}]
        tx_records = [{"timestamp": "2024-01-15T00:00:00+00:00", "currency_code": "USD", "transaction_volume": 100.0, "transaction_count": 2}]

        maker = self._make_dataset_maker(rate_records, tx_records)
        maker.run()

        maker.redis_client.fetch_all_rates.assert_called_once()
        maker.db_client.fetch_transaction_stats.assert_called_once()
        maker.uploader.upload.assert_called_once()

    def test_run_skips_upload_when_no_data_rows(self):
        """run() should skip S3 upload when CSV has no data rows."""
        maker = self._make_dataset_maker([], [])
        maker.run()

        maker.uploader.upload.assert_not_called()

    def test_run_continues_when_redis_is_empty(self):
        """run() should not fail when Redis has no exchange rate data."""
        # No rates from Redis, but some transactions
        tx_records = [{"timestamp": "2024-01-15T00:00:00+00:00", "currency_code": "USD", "transaction_volume": 100.0, "transaction_count": 2}]
        maker = self._make_dataset_maker([], tx_records)
        # Should not raise — just skip upload (no rate rows to write)
        maker.run()

    def test_run_exits_with_code_1_on_db_failure(self):
        """run() should call sys.exit(1) when PostgreSQL query fails."""
        import dataset_maker

        maker = dataset_maker.DatasetMaker.__new__(dataset_maker.DatasetMaker)
        maker.redis_client = MagicMock()
        maker.redis_client.fetch_all_rates.return_value = [
            {"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}
        ]
        maker.db_client = MagicMock()
        maker.db_client.fetch_transaction_stats.side_effect = Exception("DB connection refused")
        maker.processor = dataset_maker.DataProcessor()
        maker.uploader = MagicMock()

        with self.assertRaises(SystemExit) as ctx:
            maker.run()
        self.assertEqual(ctx.exception.code, 1)

    def test_run_exits_with_code_1_on_s3_failure(self):
        """run() should call sys.exit(1) when S3 upload fails."""
        import dataset_maker

        rate_records = [{"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}]
        maker = self._make_dataset_maker(rate_records, [])
        maker.uploader.upload.side_effect = Exception("S3 bucket not found")

        with self.assertRaises(SystemExit) as ctx:
            maker.run()
        self.assertEqual(ctx.exception.code, 1)

    def test_run_closes_db_connection_on_success(self):
        """run() should always close the DB connection after completion."""
        rate_records = [{"currency": "USD", "rate": 0.000043, "timestamp": 1700000000.0}]
        maker = self._make_dataset_maker(rate_records, [])
        maker.run()

        maker.db_client.close.assert_called_once()

    def test_run_closes_db_connection_on_failure(self):
        """run() should close the DB connection even when an error occurs."""
        import dataset_maker

        maker = dataset_maker.DatasetMaker.__new__(dataset_maker.DatasetMaker)
        maker.redis_client = MagicMock()
        maker.redis_client.fetch_all_rates.side_effect = Exception("Redis down")
        maker.db_client = MagicMock()
        maker.processor = dataset_maker.DataProcessor()
        maker.uploader = MagicMock()

        with self.assertRaises(SystemExit):
            maker.run()

        maker.db_client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
