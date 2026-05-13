"""
Unit tests for Tour Service

Tests cover:
- S3TourReader.list_tour_keys: listing, filtering, pagination, error handling
- S3TourReader.read_tour: JSON parsing, missing key, invalid JSON, error handling
- S3TourReader.generate_presigned_url: success, empty key, exception handling
- GET /tours/{currency_code}: full endpoint behavior
- GET /health: health check endpoint
"""

import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

# Add parent directory to path so we can import tour_service
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tour_service import S3TourReader, create_app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client_error(code: str, operation: str = "Operation") -> ClientError:
    """Create a botocore ClientError with the given error code."""
    error_response = {"Error": {"Code": code, "Message": f"Simulated {code}"}}
    return ClientError(error_response, operation)


def _make_s3_reader() -> S3TourReader:
    """Create an S3TourReader with a mocked _client."""
    reader = S3TourReader(bucket="test-bucket", region="ap-southeast-1")
    reader._client = MagicMock()
    return reader


# ── TestS3TourReaderListKeys ──────────────────────────────────────────────────

class TestS3TourReaderListKeys(unittest.TestCase):
    """Tests for S3TourReader.list_tour_keys()."""

    def setUp(self):
        self.reader = _make_s3_reader()
        self.mock_client = self.reader._client

    def _setup_paginator(self, pages: list) -> MagicMock:
        """Configure mock paginator to return the given list of pages."""
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = pages
        self.mock_client.get_paginator.return_value = mock_paginator
        return mock_paginator

    def test_returns_tour_keys_when_objects_exist(self):
        """list_tour_keys returns tour-*.json keys found under the prefix."""
        self._setup_paginator([
            {"Contents": [
                {"Key": "tours/JPY/tour-abc123.json"},
                {"Key": "tours/JPY/tour-def456.json"},
            ]}
        ])

        keys = self.reader.list_tour_keys("JPY")

        self.assertEqual(len(keys), 2)
        self.assertIn("tours/JPY/tour-abc123.json", keys)
        self.assertIn("tours/JPY/tour-def456.json", keys)

    def test_returns_empty_list_when_no_contents(self):
        """list_tour_keys returns empty list when S3 page has no Contents."""
        self._setup_paginator([{}])  # Page with no 'Contents' key

        keys = self.reader.list_tour_keys("JPY")

        self.assertEqual(keys, [])

    def test_returns_empty_list_on_no_such_bucket(self):
        """list_tour_keys returns empty list when S3 raises NoSuchBucket."""
        mock_paginator = MagicMock()
        mock_paginator.paginate.side_effect = _make_client_error("NoSuchBucket", "ListObjectsV2")
        self.mock_client.get_paginator.return_value = mock_paginator

        keys = self.reader.list_tour_keys("JPY")

        self.assertEqual(keys, [])

    def test_returns_empty_list_on_no_such_key(self):
        """list_tour_keys returns empty list when S3 raises NoSuchKey."""
        mock_paginator = MagicMock()
        mock_paginator.paginate.side_effect = _make_client_error("NoSuchKey", "ListObjectsV2")
        self.mock_client.get_paginator.return_value = mock_paginator

        keys = self.reader.list_tour_keys("JPY")

        self.assertEqual(keys, [])

    def test_reraises_other_client_errors(self):
        """list_tour_keys re-raises ClientError codes other than NoSuchBucket/NoSuchKey."""
        mock_paginator = MagicMock()
        mock_paginator.paginate.side_effect = _make_client_error("AccessDenied", "ListObjectsV2")
        self.mock_client.get_paginator.return_value = mock_paginator

        with self.assertRaises(ClientError) as ctx:
            self.reader.list_tour_keys("JPY")

        self.assertEqual(
            ctx.exception.response["Error"]["Code"], "AccessDenied"
        )

    def test_filters_out_non_tour_files(self):
        """list_tour_keys excludes index.json and directory-like entries."""
        self._setup_paginator([
            {"Contents": [
                {"Key": "tours/JPY/tour-abc123.json"},
                {"Key": "tours/JPY/index.json"},
                {"Key": "tours/JPY/images/"},
                {"Key": "tours/JPY/metadata.json"},
            ]}
        ])

        keys = self.reader.list_tour_keys("JPY")

        self.assertEqual(keys, ["tours/JPY/tour-abc123.json"])

    def test_handles_paginated_results(self):
        """list_tour_keys collects keys across multiple paginator pages."""
        self._setup_paginator([
            {"Contents": [{"Key": "tours/JPY/tour-page1a.json"}]},
            {"Contents": [{"Key": "tours/JPY/tour-page2a.json"}, {"Key": "tours/JPY/tour-page2b.json"}]},
        ])

        keys = self.reader.list_tour_keys("JPY")

        self.assertEqual(len(keys), 3)
        self.assertIn("tours/JPY/tour-page1a.json", keys)
        self.assertIn("tours/JPY/tour-page2a.json", keys)
        self.assertIn("tours/JPY/tour-page2b.json", keys)


# ── TestS3TourReaderReadTour ──────────────────────────────────────────────────

class TestS3TourReaderReadTour(unittest.TestCase):
    """Tests for S3TourReader.read_tour()."""

    def setUp(self):
        self.reader = _make_s3_reader()
        self.mock_client = self.reader._client

    def _mock_get_object(self, body: bytes):
        """Configure mock get_object to return the given body bytes."""
        mock_body = MagicMock()
        mock_body.read.return_value = body
        self.mock_client.get_object.return_value = {"Body": mock_body}

    def test_returns_parsed_dict_for_valid_json(self):
        """read_tour returns a parsed dict when S3 object contains valid JSON."""
        tour_data = {"id": "abc123", "name": "Tokyo Tour", "price": 100}
        self._mock_get_object(json.dumps(tour_data).encode("utf-8"))

        result = self.reader.read_tour("tours/JPY/tour-abc123.json")

        self.assertEqual(result, tour_data)

    def test_returns_none_on_no_such_key(self):
        """read_tour returns None when S3 raises NoSuchKey."""
        self.mock_client.get_object.side_effect = _make_client_error("NoSuchKey", "GetObject")

        result = self.reader.read_tour("tours/JPY/tour-missing.json")

        self.assertIsNone(result)

    def test_returns_none_on_no_such_bucket(self):
        """read_tour returns None when S3 raises NoSuchBucket."""
        self.mock_client.get_object.side_effect = _make_client_error("NoSuchBucket", "GetObject")

        result = self.reader.read_tour("tours/JPY/tour-abc123.json")

        self.assertIsNone(result)

    def test_returns_none_for_invalid_json(self):
        """read_tour returns None when S3 object contains invalid JSON."""
        self._mock_get_object(b"this is not valid json {{{")

        result = self.reader.read_tour("tours/JPY/tour-bad.json")

        self.assertIsNone(result)

    def test_reraises_other_client_errors(self):
        """read_tour re-raises ClientError codes other than NoSuchKey/NoSuchBucket."""
        self.mock_client.get_object.side_effect = _make_client_error("AccessDenied", "GetObject")

        with self.assertRaises(ClientError) as ctx:
            self.reader.read_tour("tours/JPY/tour-abc123.json")

        self.assertEqual(
            ctx.exception.response["Error"]["Code"], "AccessDenied"
        )


# ── TestS3TourReaderPresignedUrl ──────────────────────────────────────────────

class TestS3TourReaderPresignedUrl(unittest.TestCase):
    """Tests for S3TourReader.generate_presigned_url()."""

    def setUp(self):
        self.reader = _make_s3_reader()
        self.mock_client = self.reader._client

    def test_returns_presigned_url_on_success(self):
        """generate_presigned_url returns the URL string when S3 call succeeds."""
        expected_url = "https://test-bucket.s3.amazonaws.com/tours/images/JPY/abc123.jpg?X-Amz-Signature=abc"
        self.mock_client.generate_presigned_url.return_value = expected_url

        result = self.reader.generate_presigned_url("tours/images/JPY/abc123.jpg")

        self.assertEqual(result, expected_url)
        self.mock_client.generate_presigned_url.assert_called_once()

    def test_returns_empty_string_for_empty_image_key(self):
        """generate_presigned_url returns empty string when image_key is empty."""
        result = self.reader.generate_presigned_url("")

        self.assertEqual(result, "")
        self.mock_client.generate_presigned_url.assert_not_called()

    def test_returns_empty_string_when_exception_raised(self):
        """generate_presigned_url returns empty string when S3 raises an exception."""
        self.mock_client.generate_presigned_url.side_effect = Exception("S3 error")

        result = self.reader.generate_presigned_url("tours/images/JPY/abc123.jpg")

        self.assertEqual(result, "")


# ── TestToursEndpoint ─────────────────────────────────────────────────────────

class TestToursEndpoint(unittest.TestCase):
    """Tests for the GET /tours/{currency_code} HTTP endpoint."""

    def setUp(self):
        """Set up Flask test client with a mocked S3TourReader."""
        self.mock_reader = MagicMock(spec=S3TourReader)
        self.app = create_app(s3_reader=self.mock_reader)
        self.client = self.app.test_client()

    def test_returns_200_with_tours_when_found(self):
        """GET /tours/{currency_code} returns 200 with tours list and count when tours exist."""
        self.mock_reader.list_tour_keys.return_value = [
            "tours/JPY/tour-abc123.json",
            "tours/JPY/tour-def456.json",
        ]
        self.mock_reader.read_tour.side_effect = [
            {"id": "abc123", "name": "Tokyo Tour", "price": 100, "image_key": "tours/images/JPY/abc123.jpg"},
            {"id": "def456", "name": "Kyoto Tour", "price": 200, "image_key": "tours/images/JPY/def456.jpg"},
        ]
        self.mock_reader.generate_presigned_url.return_value = "https://presigned.url/image.jpg"

        response = self.client.get("/tours/JPY")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["currency_code"], "JPY")
        self.assertEqual(len(data["tours"]), 2)

    def test_returns_200_with_empty_list_when_no_tours(self):
        """GET /tours/{currency_code} returns 200 with empty list and message when no tours found."""
        self.mock_reader.list_tour_keys.return_value = []

        response = self.client.get("/tours/JPY")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["tours"], [])
        self.assertEqual(data["count"], 0)
        self.assertIn("message", data)

    def test_returns_500_when_list_tour_keys_raises_client_error(self):
        """GET /tours/{currency_code} returns 500 when list_tour_keys raises ClientError."""
        self.mock_reader.list_tour_keys.side_effect = _make_client_error("InternalError", "ListObjectsV2")

        response = self.client.get("/tours/JPY")

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "internal_error")

    def test_returns_500_when_read_tour_raises_client_error(self):
        """GET /tours/{currency_code} returns 500 when read_tour raises ClientError."""
        self.mock_reader.list_tour_keys.return_value = ["tours/JPY/tour-abc123.json"]
        self.mock_reader.read_tour.side_effect = _make_client_error("InternalError", "GetObject")

        response = self.client.get("/tours/JPY")

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "internal_error")

    def test_skips_tours_where_read_tour_returns_none(self):
        """GET /tours/{currency_code} skips tours where read_tour returns None."""
        self.mock_reader.list_tour_keys.return_value = [
            "tours/JPY/tour-abc123.json",
            "tours/JPY/tour-bad.json",
            "tours/JPY/tour-def456.json",
        ]
        self.mock_reader.read_tour.side_effect = [
            {"id": "abc123", "name": "Tokyo Tour", "price": 100, "image_key": ""},
            None,  # Simulates invalid JSON or not found
            {"id": "def456", "name": "Kyoto Tour", "price": 200, "image_key": ""},
        ]
        self.mock_reader.generate_presigned_url.return_value = ""

        response = self.client.get("/tours/JPY")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["tours"]), 2)

    def test_includes_image_presigned_url_in_each_tour(self):
        """GET /tours/{currency_code} includes image_presigned_url field in each tour."""
        self.mock_reader.list_tour_keys.return_value = ["tours/JPY/tour-abc123.json"]
        self.mock_reader.read_tour.return_value = {
            "id": "abc123",
            "name": "Tokyo Tour",
            "image_key": "tours/images/JPY/abc123.jpg",
        }
        self.mock_reader.generate_presigned_url.return_value = "https://presigned.url/image.jpg"

        response = self.client.get("/tours/JPY")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("image_presigned_url", data["tours"][0])
        self.assertEqual(data["tours"][0]["image_presigned_url"], "https://presigned.url/image.jpg")

    def test_sets_image_presigned_url_to_empty_string_when_image_key_empty(self):
        """GET /tours/{currency_code} sets image_presigned_url to empty string when image_key is empty."""
        self.mock_reader.list_tour_keys.return_value = ["tours/JPY/tour-abc123.json"]
        self.mock_reader.read_tour.return_value = {
            "id": "abc123",
            "name": "Tokyo Tour",
            "image_key": "",
        }

        response = self.client.get("/tours/JPY")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["tours"][0]["image_presigned_url"], "")
        self.mock_reader.generate_presigned_url.assert_not_called()

    def test_normalizes_currency_code_to_uppercase(self):
        """GET /tours/{currency_code} normalizes currency_code to uppercase."""
        self.mock_reader.list_tour_keys.return_value = []

        response = self.client.get("/tours/jpy")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["currency_code"], "JPY")
        # Verify list_tour_keys was called with uppercase code
        self.mock_reader.list_tour_keys.assert_called_once_with("JPY")


# ── TestHealthEndpoint ────────────────────────────────────────────────────────

class TestHealthEndpoint(unittest.TestCase):
    """Tests for the GET /health HTTP endpoint."""

    def setUp(self):
        """Set up Flask test client with a mocked S3TourReader."""
        self.mock_reader = MagicMock(spec=S3TourReader)
        self.app = create_app(s3_reader=self.mock_reader)
        self.client = self.app.test_client()

    def test_health_returns_200_with_status_ok(self):
        """GET /health returns HTTP 200 with {'status': 'ok'}."""
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "ok")


if __name__ == "__main__":
    unittest.main()
