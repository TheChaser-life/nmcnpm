"""
Tour Service — ECS Service

Cung cấp REST API danh sách tour du lịch cho frontend.
Đọc tour JSON từ S3 (được ghi bởi Tour Producer) và trả về danh sách tour
kèm pre-signed URL cho ảnh.

Deployment: ECS Fargate trong Private Subnet (truy cập qua ALB)
S3 access: VPC Gateway Endpoint (không qua internet, không tốn NAT cost)

S3 layout (written by Tour Producer):
  tours/{currency_code}/tour-{id}.json   — tour metadata
  tours/images/{currency_code}/{id}.jpg  — tour image
"""

import json
import os
import sys
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import boto3
import botocore.exceptions
from flask import Flask, jsonify

# ── Logging ───────────────────────────────────────────────────────────────────


def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout (CloudWatch Logs)."""
    entry = {
        "level": level,
        "message": message,
        "service": "tour-service",
        **kwargs,
    }
    print(json.dumps(entry, default=str), flush=True)


def _normalize_affiliate_url(affiliate_url: str, tour_name: str) -> str:
    """
    Convert legacy placeholder Viator URLs into durable search pages.

    Older tour JSON can contain product-like Viator paths without a product id,
    for example /tours/Kyoto/Kyoto-Walking-Tour. Viator returns 404 for those.
    """
    if not isinstance(affiliate_url, str):
        return ""

    affiliate_url = affiliate_url.strip()
    parsed = urlparse(affiliate_url)
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if host.endswith("viator.com") and path_parts:
        search_text = ""

        if path_parts[0] == "search" and len(path_parts) >= 2:
            search_text = " ".join(path_parts[1:]).replace("-", " ")
        elif (
            path_parts[0] == "tours"
            and len(path_parts) == 3
            and not any(char.isdigit() for char in path_parts[2])
        ):
            city = path_parts[1].replace("-", " ")
            if city.lower() in tour_name.lower():
                search_text = tour_name.strip()
            else:
                search_text = f"{city} {tour_name}".strip()

        if search_text:
            return f"https://www.viator.com/searchResults/all?text={quote_plus(search_text)}"

    return affiliate_url


# ── Configuration ─────────────────────────────────────────────────────────────


class Config:
    """Configuration loaded from environment variables."""

    PORT: int = int(os.environ.get("PORT", "7000"))
    AWS_REGION: str = os.environ.get("AWS_REGION", "ap-southeast-2")
    S3_TOUR_BUCKET: str = os.environ.get("S3_TOUR_BUCKET", "")
    S3_TOURS_PREFIX: str = os.environ.get("S3_TOURS_PREFIX", "tours")
    S3_IMAGES_PREFIX: str = os.environ.get("S3_IMAGES_PREFIX", "tours/images")
    PRESIGNED_URL_EXPIRY_SECONDS: int = int(
        os.environ.get("PRESIGNED_URL_EXPIRY_SECONDS", "3600")
    )

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration. Raises ValueError on missing config."""
        errors: List[str] = []
        if not cls.S3_TOUR_BUCKET:
            errors.append("S3_TOUR_BUCKET is required")
        if errors:
            raise ValueError(f"Configuration errors: {'; '.join(errors)}")


# ── S3 Tour Reader ────────────────────────────────────────────────────────────


class S3TourReader:
    """
    Reads tour data from S3.

    Provides methods to list tour keys, read individual tour JSON files,
    and generate pre-signed URLs for tour images.
    """

    def __init__(self, bucket: str = "", region: str = ""):
        self._bucket = bucket or Config.S3_TOUR_BUCKET
        self._region = region or Config.AWS_REGION
        self._client = boto3.client("s3", region_name=self._region)
        _log("INFO", "S3 client initialised",
             bucket=self._bucket, region=self._region)

    def list_tour_keys(self, currency_code: str) -> List[str]:
        """
        List all tour-*.json keys under tours/{currency_code}/ prefix.

        Args:
            currency_code: ISO 4217 currency code (e.g., "JPY")

        Returns:
            List of S3 keys for tour JSON files. Empty list if none found
            or if the prefix does not exist.
        """
        prefix = f"{Config.S3_TOURS_PREFIX}/{currency_code}/"
        keys: List[str] = []

        try:
            paginator = self._client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self._bucket, Prefix=prefix)

            for page in pages:
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    # Only include tour-*.json files, not directories or other files
                    filename = key.split("/")[-1]
                    if filename.startswith("tour-") and filename.endswith(".json"):
                        keys.append(key)

            _log(
                "INFO",
                "Listed tour keys from S3",
                currency_code=currency_code,
                prefix=prefix,
                count=len(keys),
            )
            return keys

        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            if error_code in ("NoSuchBucket", "NoSuchKey"):
                _log(
                    "INFO",
                    "S3 prefix not found; returning empty list",
                    currency_code=currency_code,
                    prefix=prefix,
                    error_code=error_code,
                )
                return []
            # Re-raise other client errors for the caller to handle
            raise

    def read_tour(self, s3_key: str) -> Optional[Dict]:
        """
        Download and parse a single tour JSON file from S3.

        Args:
            s3_key: The full S3 key of the tour JSON file.

        Returns:
            Parsed tour dict, or None if the key does not exist or JSON is invalid.
        """
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
            body = response["Body"].read()
            tour = json.loads(body)
            _log("INFO", "Tour JSON read from S3", key=s3_key)
            return tour

        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            if error_code in ("NoSuchKey", "NoSuchBucket"):
                _log(
                    "INFO",
                    "Tour JSON key not found in S3",
                    key=s3_key,
                    error_code=error_code,
                )
                return None
            # Re-raise other client errors
            raise

        except (json.JSONDecodeError, ValueError) as exc:
            _log(
                "WARN",
                "Failed to parse tour JSON; skipping",
                key=s3_key,
                error=str(exc),
            )
            return None

    def generate_presigned_url(self, image_key: str) -> str:
        """
        Generate a pre-signed URL for a tour image stored in S3.

        Args:
            image_key: The S3 key of the image (e.g., "tours/images/JPY/abc123.jpg")

        Returns:
            Pre-signed URL string, or empty string on error.
        """
        if not image_key:
            return ""

        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": image_key},
                ExpiresIn=Config.PRESIGNED_URL_EXPIRY_SECONDS,
            )
            _log(
                "INFO",
                "Pre-signed URL generated",
                image_key=image_key,
                expiry_seconds=Config.PRESIGNED_URL_EXPIRY_SECONDS,
            )
            return url

        except Exception as exc:
            _log(
                "WARN",
                "Failed to generate pre-signed URL; returning empty string",
                image_key=image_key,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return ""


# ── Flask Application ─────────────────────────────────────────────────────────


def create_app(s3_reader: Optional[S3TourReader] = None) -> Flask:
    """
    Create and configure the Flask application.

    Accepts an optional S3TourReader for dependency injection (testing).
    """
    app = Flask(__name__)

    # Use provided reader or create a default one
    _s3_reader = s3_reader or S3TourReader()

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok"}), 200

    @app.route("/tours/<string:currency_code>", methods=["GET"])
    def get_tours(currency_code: str):
        """
        GET /tours/{currency_code}

        Retrieves all tours for the given currency code from S3.
        For each tour with a non-empty image_key, generates a pre-signed URL.

        Responses:
            200: List of tours (may be empty with a message if none found)
            500: Internal S3 error
        """
        currency_code = currency_code.upper()

        _log(
            "INFO",
            "Tour list request received",
            currency_code=currency_code,
        )

        # ── Step 1: List tour keys from S3 ────────────────────────────────
        try:
            tour_keys = _s3_reader.list_tour_keys(currency_code)
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            _log(
                "ERROR",
                "S3 error listing tour keys",
                currency_code=currency_code,
                error_code=error_code,
                error=str(exc),
            )
            return jsonify({
                "error": "internal_error",
                "message": "Failed to retrieve tour data",
            }), 500

        # ── Step 2: Handle empty result ───────────────────────────────────
        if not tour_keys:
            _log(
                "INFO",
                "No tours found for currency",
                currency_code=currency_code,
            )
            return jsonify({
                "tours": [],
                "count": 0,
                "currency_code": currency_code,
                "message": "No tours currently available for this currency",
            }), 200

        # ── Step 3: Read each tour JSON and enrich with pre-signed URL ────
        tours: List[Dict] = []

        for key in tour_keys:
            try:
                tour = _s3_reader.read_tour(key)
            except botocore.exceptions.ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "Unknown")
                _log(
                    "ERROR",
                    "S3 error reading tour JSON",
                    key=key,
                    currency_code=currency_code,
                    error_code=error_code,
                    error=str(exc),
                )
                return jsonify({
                    "error": "internal_error",
                    "message": "Failed to retrieve tour data",
                }), 500

            if tour is None:
                # read_tour already logged the reason (not found or invalid JSON)
                continue

            tour["affiliate_url"] = _normalize_affiliate_url(
                tour.get("affiliate_url", ""),
                tour.get("name", ""),
            )

            # Generate pre-signed URL for the image if an image_key is present
            image_key = tour.get("image_key", "")
            presigned_url = _s3_reader.generate_presigned_url(image_key) if image_key else ""
            tour["image_presigned_url"] = presigned_url

            tours.append(tour)

        _log(
            "INFO",
            "Tour list request completed",
            currency_code=currency_code,
            count=len(tours),
        )

        return jsonify({
            "tours": tours,
            "count": len(tours),
            "currency_code": currency_code,
        }), 200

    return app


# ── Entry Point ───────────────────────────────────────────────────────────────


def main() -> int:
    """Entry point for the service."""
    _log("INFO", "Tour Service starting")

    try:
        Config.validate()
    except ValueError as exc:
        _log("ERROR", "Configuration validation failed", error=str(exc))
        return 1

    app = create_app()

    _log(
        "INFO",
        "Tour Service listening",
        port=Config.PORT,
        bucket=Config.S3_TOUR_BUCKET,
        region=Config.AWS_REGION,
    )

    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
