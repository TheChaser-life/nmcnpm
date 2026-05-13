"""
Unit tests for Tour Producer service.

Tests cover:
  - TourNormalizer: canonical schema extraction, missing-field handling
  - TravelpayoutsClient: API response parsing (list vs dict wrapper)
  - TourProducer._process_currency: error handling when API returns empty
  - Config.supported_currencies: parsing from env var
"""

import hashlib
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# ── Make the parent directory importable ─────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch boto3 before importing tour_producer so no real AWS calls are made
with patch("boto3.client"):
    from tour_producer import (
        Config,
        CURRENCY_COUNTRY_MAP,
        ImageDownloader,
        TourNormalizer,
        TourProducer,
        TravelpayoutsClient,
    )


# ── TourNormalizer tests ──────────────────────────────────────────────────────

class TestTourNormalizer(unittest.TestCase):
    """Tests for TourNormalizer.normalize()."""

    def setUp(self):
        self.normalizer = TourNormalizer()
        self.currency = "JPY"
        self.country_code = "JP"
        self.country_name = "Japan"

    def _normalize(self, raw: dict) -> dict | None:
        return self.normalizer.normalize(
            raw, self.currency, self.country_code, self.country_name
        )

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_normalize_full_tour(self):
        """All fields present → canonical schema returned."""
        raw = {
            "name": "Tokyo City Tour",
            "description": "Explore the best of Tokyo.",
            "image_url": "https://cdn.example.com/tokyo.jpg",
            "affiliate_url": "https://tp.media/r?id=123",
        }
        result = self._normalize(raw)

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Tokyo City Tour")
        self.assertEqual(result["description"], "Explore the best of Tokyo.")
        self.assertEqual(result["image_url"], "https://cdn.example.com/tokyo.jpg")
        self.assertEqual(result["affiliate_url"], "https://tp.media/r?id=123")
        self.assertEqual(result["currency_code"], "JPY")
        self.assertEqual(result["country_code"], "JP")
        self.assertEqual(result["country_name"], "Japan")
        self.assertIn("id", result)
        self.assertIn("image_key", result)
        self.assertIn("collected_at", result)

    def test_id_is_stable_hash_of_affiliate_url(self):
        """Tour ID must be the first 16 hex chars of SHA-256(affiliate_url)."""
        affiliate_url = "https://tp.media/r?id=abc"
        raw = {"name": "Tour", "affiliate_url": affiliate_url}
        result = self._normalize(raw)

        expected_id = hashlib.sha256(affiliate_url.encode()).hexdigest()[:16]
        self.assertEqual(result["id"], expected_id)

    def test_image_key_uses_s3_images_prefix(self):
        """image_key must follow tours/images/{currency}/{id}.jpg pattern."""
        raw = {
            "name": "Tour",
            "affiliate_url": "https://tp.media/r?id=xyz",
            "image_url": "https://cdn.example.com/img.jpg",
        }
        result = self._normalize(raw)

        self.assertTrue(result["image_key"].startswith("tours/images/JPY/"))
        self.assertTrue(result["image_key"].endswith(".jpg"))

    def test_image_key_empty_when_no_image_url(self):
        """image_key must be empty string when no image_url is provided."""
        raw = {"name": "Tour", "affiliate_url": "https://tp.media/r?id=1"}
        result = self._normalize(raw)

        self.assertEqual(result["image_key"], "")

    def test_description_truncated_at_1000_chars(self):
        """Descriptions longer than 1000 chars must be truncated with ellipsis."""
        long_desc = "A" * 1500
        raw = {
            "name": "Tour",
            "affiliate_url": "https://tp.media/r?id=1",
            "description": long_desc,
        }
        result = self._normalize(raw)

        self.assertLessEqual(len(result["description"]), 1001)  # 1000 + "…"
        self.assertTrue(result["description"].endswith("…"))

    def test_description_not_truncated_when_short(self):
        """Short descriptions must not be modified."""
        short_desc = "Short description."
        raw = {
            "name": "Tour",
            "affiliate_url": "https://tp.media/r?id=1",
            "description": short_desc,
        }
        result = self._normalize(raw)

        self.assertEqual(result["description"], short_desc)

    # ── Alternative field names ───────────────────────────────────────────────

    def test_normalize_uses_title_fallback(self):
        """'title' field is accepted when 'name' is absent."""
        raw = {"title": "Osaka Tour", "affiliate_url": "https://tp.media/r?id=2"}
        result = self._normalize(raw)

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Osaka Tour")

    def test_normalize_uses_url_fallback_for_affiliate(self):
        """'url' field is accepted when 'affiliate_url' is absent."""
        raw = {"name": "Tour", "url": "https://tp.media/r?id=3"}
        result = self._normalize(raw)

        self.assertIsNotNone(result)
        self.assertEqual(result["affiliate_url"], "https://tp.media/r?id=3")

    def test_normalize_uses_photo_url_fallback(self):
        """'photo_url' field is accepted when 'image_url' is absent."""
        raw = {
            "name": "Tour",
            "affiliate_url": "https://tp.media/r?id=4",
            "photo_url": "https://cdn.example.com/photo.jpg",
        }
        result = self._normalize(raw)

        self.assertEqual(result["image_url"], "https://cdn.example.com/photo.jpg")

    # ── Missing required fields ───────────────────────────────────────────────

    def test_returns_none_when_name_missing(self):
        """Returns None when both 'name' and 'title' are absent."""
        raw = {"affiliate_url": "https://tp.media/r?id=5"}
        result = self._normalize(raw)

        self.assertIsNone(result)

    def test_returns_none_when_affiliate_url_missing(self):
        """Returns None when no affiliate URL field is present."""
        raw = {"name": "Tour Without URL"}
        result = self._normalize(raw)

        self.assertIsNone(result)

    def test_returns_none_for_empty_dict(self):
        """Returns None for an empty raw dict."""
        result = self._normalize({})
        self.assertIsNone(result)

    def test_returns_none_when_name_is_empty_string(self):
        """Returns None when name is present but empty."""
        raw = {"name": "   ", "affiliate_url": "https://tp.media/r?id=6"}
        result = self._normalize(raw)

        self.assertIsNone(result)

    # ── Whitespace stripping ──────────────────────────────────────────────────

    def test_name_is_stripped(self):
        """Leading/trailing whitespace in name must be stripped."""
        raw = {"name": "  Kyoto Tour  ", "affiliate_url": "https://tp.media/r?id=7"}
        result = self._normalize(raw)

        self.assertEqual(result["name"], "Kyoto Tour")


# ── TravelpayoutsClient response parsing tests ────────────────────────────────

class TestTravelpayoutsClientParsing(unittest.TestCase):
    """Tests for TravelpayoutsClient.fetch_tours_for_country() response parsing."""

    def setUp(self):
        # Patch the session so no real HTTP calls are made
        with patch("tour_producer._build_session") as mock_build:
            mock_build.return_value = MagicMock()
            self.client = TravelpayoutsClient()
        self.client.session = MagicMock()

    def _mock_response(self, data, status_code=200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = data
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_parses_list_response(self):
        """API returning a plain list is handled correctly."""
        tours = [{"name": "Tour A", "affiliate_url": "https://tp.media/r?id=1"}]
        self.client.session.get.return_value = self._mock_response(tours)

        result = self.client.fetch_tours_for_country("JP", "JPY")

        self.assertEqual(result, tours)

    def test_parses_dict_with_data_key(self):
        """API returning {'data': [...]} is unwrapped correctly."""
        tours = [{"name": "Tour B", "affiliate_url": "https://tp.media/r?id=2"}]
        self.client.session.get.return_value = self._mock_response({"data": tours})

        result = self.client.fetch_tours_for_country("JP", "JPY")

        self.assertEqual(result, tours)

    def test_returns_empty_list_for_unexpected_structure(self):
        """Unexpected response structure returns empty list (no exception)."""
        self.client.session.get.return_value = self._mock_response({"unexpected": True})

        result = self.client.fetch_tours_for_country("JP", "JPY")

        self.assertEqual(result, [])

    def test_returns_empty_list_on_timeout(self):
        """Timeout exception returns empty list and does not raise."""
        import requests as req
        self.client.session.get.side_effect = req.exceptions.Timeout()

        result = self.client.fetch_tours_for_country("JP", "JPY")

        self.assertEqual(result, [])

    def test_returns_empty_list_on_http_error(self):
        """HTTP error returns empty list and does not raise."""
        import requests as req
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        http_error = req.exceptions.HTTPError(response=mock_resp)
        self.client.session.get.side_effect = http_error

        result = self.client.fetch_tours_for_country("JP", "JPY")

        self.assertEqual(result, [])

    def test_returns_empty_list_on_json_decode_error(self):
        """JSON decode error returns empty list and does not raise."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        self.client.session.get.return_value = mock_resp

        result = self.client.fetch_tours_for_country("JP", "JPY")

        self.assertEqual(result, [])


# ── TourProducer._process_currency tests ─────────────────────────────────────

class TestTourProducerProcessCurrency(unittest.TestCase):
    """Tests for TourProducer._process_currency() error handling."""

    def _make_producer(self):
        """Build a TourProducer with all dependencies mocked."""
        with patch("boto3.client"):
            producer = TourProducer.__new__(TourProducer)
        producer.api_client = MagicMock()
        producer.normalizer = TourNormalizer()
        producer.image_downloader = MagicMock()
        producer.s3_uploader = MagicMock()
        return producer

    def test_returns_api_empty_when_no_tours_fetched(self):
        """When API returns empty list, status is 'api_empty' and S3 is not written."""
        producer = self._make_producer()
        producer.api_client.fetch_tours_for_country.return_value = []

        result = producer._process_currency("JPY")

        self.assertEqual(result["status"], "api_empty")
        self.assertEqual(result["fetched"], 0)
        producer.s3_uploader.upload_tour_json.assert_not_called()
        producer.s3_uploader.upload_tour_image.assert_not_called()

    def test_returns_skipped_for_unknown_currency(self):
        """Currency with no country mapping returns status 'skipped'."""
        producer = self._make_producer()

        result = producer._process_currency("XYZ")

        self.assertEqual(result["status"], "skipped")
        producer.api_client.fetch_tours_for_country.assert_not_called()

    def test_uploads_tour_json_for_each_normalized_tour(self):
        """Each normalized tour results in one S3 JSON upload."""
        producer = self._make_producer()
        raw_tours = [
            {"name": "Tour A", "affiliate_url": "https://tp.media/r?id=1"},
            {"name": "Tour B", "affiliate_url": "https://tp.media/r?id=2"},
        ]
        producer.api_client.fetch_tours_for_country.return_value = raw_tours
        producer.image_downloader.download.return_value = None  # no images

        result = producer._process_currency("JPY")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["uploaded"], 2)
        self.assertEqual(producer.s3_uploader.upload_tour_json.call_count, 2)

    def test_image_key_cleared_when_download_fails(self):
        """When image download fails, tour JSON is still uploaded with empty image_key."""
        producer = self._make_producer()
        raw_tours = [
            {
                "name": "Tour A",
                "affiliate_url": "https://tp.media/r?id=1",
                "image_url": "https://cdn.example.com/img.jpg",
            }
        ]
        producer.api_client.fetch_tours_for_country.return_value = raw_tours
        producer.image_downloader.download.return_value = None  # download fails

        producer._process_currency("JPY")

        # Capture the tour dict passed to upload_tour_json
        call_args = producer.s3_uploader.upload_tour_json.call_args
        uploaded_tour = call_args[0][0]
        self.assertEqual(uploaded_tour["image_key"], "")

    def test_image_key_cleared_when_image_upload_fails(self):
        """When S3 image upload raises, tour JSON is still uploaded with empty image_key."""
        producer = self._make_producer()
        raw_tours = [
            {
                "name": "Tour A",
                "affiliate_url": "https://tp.media/r?id=1",
                "image_url": "https://cdn.example.com/img.jpg",
            }
        ]
        producer.api_client.fetch_tours_for_country.return_value = raw_tours
        producer.image_downloader.download.return_value = b"fake_image_bytes"
        producer.s3_uploader.upload_tour_image.side_effect = Exception("S3 error")

        # Should not raise
        result = producer._process_currency("JPY")

        self.assertEqual(result["status"], "success")
        uploaded_tour = producer.s3_uploader.upload_tour_json.call_args[0][0]
        self.assertEqual(uploaded_tour["image_key"], "")

    def test_skips_invalid_tours_from_api(self):
        """Tours missing required fields are skipped; valid ones are uploaded."""
        producer = self._make_producer()
        raw_tours = [
            {"name": "Valid Tour", "affiliate_url": "https://tp.media/r?id=1"},
            {"description": "No name or URL"},  # invalid — should be skipped
        ]
        producer.api_client.fetch_tours_for_country.return_value = raw_tours
        producer.image_downloader.download.return_value = None

        result = producer._process_currency("JPY")

        self.assertEqual(result["normalized"], 1)
        self.assertEqual(result["uploaded"], 1)


# ── Config tests ──────────────────────────────────────────────────────────────

class TestConfig(unittest.TestCase):
    """Tests for Config helper methods."""

    def test_supported_currencies_parsed_correctly(self):
        """Comma-separated class attribute is split into a list of uppercase codes."""
        with patch.object(Config, "SUPPORTED_CURRENCIES", "USD,eur, GBP "):
            currencies = Config.supported_currencies()
        self.assertEqual(currencies, ["USD", "EUR", "GBP"])

    def test_supported_currencies_default(self):
        """Default currencies include the 12 expected codes."""
        env = {k: v for k, v in os.environ.items() if k != "SUPPORTED_CURRENCIES"}
        with patch.dict(os.environ, env, clear=True):
            currencies = Config.supported_currencies()
        self.assertIn("USD", currencies)
        self.assertIn("JPY", currencies)
        self.assertEqual(len(currencies), 12)

    def test_validate_raises_when_token_missing(self):
        """validate() raises ValueError when TRAVELPAYOUTS_API_TOKEN is empty."""
        with patch.dict(
            os.environ,
            {"TRAVELPAYOUTS_API_TOKEN": "", "S3_TOUR_BUCKET": "my-bucket"},
        ):
            Config.TRAVELPAYOUTS_API_TOKEN = ""
            Config.S3_TOUR_BUCKET = "my-bucket"
            with self.assertRaises(ValueError) as ctx:
                Config.validate()
            self.assertIn("TRAVELPAYOUTS_API_TOKEN", str(ctx.exception))

    def test_validate_raises_when_bucket_missing(self):
        """validate() raises ValueError when S3_TOUR_BUCKET is empty."""
        Config.TRAVELPAYOUTS_API_TOKEN = "token123"
        Config.S3_TOUR_BUCKET = ""
        with self.assertRaises(ValueError) as ctx:
            Config.validate()
        self.assertIn("S3_TOUR_BUCKET", str(ctx.exception))


# ── CURRENCY_COUNTRY_MAP tests ────────────────────────────────────────────────

class TestCurrencyCountryMap(unittest.TestCase):
    """Sanity checks on the currency → country mapping."""

    def test_all_default_currencies_have_mapping(self):
        """Every currency in the default SUPPORTED_CURRENCIES has a country mapping."""
        default_currencies = [
            "USD", "EUR", "GBP", "JPY", "CNY", "KRW",
            "THB", "SGD", "MYR", "IDR", "PHP", "AUD",
        ]
        for code in default_currencies:
            with self.subTest(currency=code):
                self.assertIn(code, CURRENCY_COUNTRY_MAP)

    def test_mapping_values_are_tuples_of_two_strings(self):
        """Each mapping value is a (country_code, country_name) tuple."""
        for currency, value in CURRENCY_COUNTRY_MAP.items():
            with self.subTest(currency=currency):
                self.assertIsInstance(value, tuple)
                self.assertEqual(len(value), 2)
                country_code, country_name = value
                self.assertIsInstance(country_code, str)
                self.assertIsInstance(country_name, str)
                self.assertEqual(len(country_code), 2)  # ISO 3166-1 alpha-2


if __name__ == "__main__":
    unittest.main()
