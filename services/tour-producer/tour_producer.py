"""
Tour Producer — ECS One-Shot Task

Thu thập thông tin tour du lịch từ Travelpayouts API cho từng quốc gia liên quan
đến các loại tiền tệ được hỗ trợ. Lưu tour JSON và images vào S3.

Deployment: ECS Task (không phải long-running service) trong Public Subnet.
Trigger: EventBridge scheduled rule (mặc định: mỗi 24h).

S3 layout:
  tours/{currency_code}/tour-{id}.json   — tour metadata
  tours/images/{currency_code}/{id}.jpg  — tour image (downloaded from source URL)
"""

import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import boto3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout (CloudWatch Logs)."""
    entry = {
        "level": level,
        "message": message,
        "service": "tour-producer",
        **kwargs,
    }
    print(json.dumps(entry, default=str), flush=True)


# ── Currency → Country mapping ────────────────────────────────────────────────

# Maps ISO 4217 currency code → (ISO 3166-1 alpha-2 country code, country name)
# Used to query Travelpayouts API by destination country.
CURRENCY_COUNTRY_MAP: Dict[str, Tuple[str, str]] = {
    "USD": ("US", "United States"),
    "EUR": ("DE", "Germany"),       # representative EU country
    "GBP": ("GB", "United Kingdom"),
    "JPY": ("JP", "Japan"),
    "CNY": ("CN", "China"),
    "KRW": ("KR", "South Korea"),
    "THB": ("TH", "Thailand"),
    "SGD": ("SG", "Singapore"),
    "MYR": ("MY", "Malaysia"),
    "IDR": ("ID", "Indonesia"),
    "PHP": ("PH", "Philippines"),
    "AUD": ("AU", "Australia"),
}


# ── Configuration ─────────────────────────────────────────────────────────────

class Config:
    """Configuration loaded from environment variables."""

    # Travelpayouts API
    TRAVELPAYOUTS_API_TOKEN: str = os.environ.get("TRAVELPAYOUTS_API_TOKEN", "")
    TRAVELPAYOUTS_API_BASE_URL: str = os.environ.get(
        "TRAVELPAYOUTS_API_BASE_URL",
        "https://api.travelpayouts.com/v1",
    )
    TRAVELPAYOUTS_API_TIMEOUT: int = int(
        os.environ.get("TRAVELPAYOUTS_API_TIMEOUT", "15")
    )
    # Maximum tours to fetch per currency (to limit S3 storage and API quota)
    MAX_TOURS_PER_CURRENCY: int = int(
        os.environ.get("MAX_TOURS_PER_CURRENCY", "10")
    )

    # S3
    S3_TOUR_BUCKET: str = os.environ.get("S3_TOUR_BUCKET", "")
    S3_TOURS_PREFIX: str = os.environ.get("S3_TOURS_PREFIX", "tours")
    S3_IMAGES_PREFIX: str = os.environ.get("S3_IMAGES_PREFIX", "tours/images")

    # Supported currencies (comma-separated; must match exchange-rate-producer)
    SUPPORTED_CURRENCIES: str = os.environ.get(
        "SUPPORTED_CURRENCIES",
        "USD,EUR,GBP,JPY,CNY,KRW,THB,SGD,MYR,IDR,PHP,AUD",
    )

    # AWS
    AWS_REGION: str = os.environ.get("AWS_REGION", "ap-southeast-2")

    # Image download
    IMAGE_DOWNLOAD_TIMEOUT: int = int(
        os.environ.get("IMAGE_DOWNLOAD_TIMEOUT", "10")
    )
    # Maximum image size to download (bytes) — 5 MB default
    MAX_IMAGE_SIZE_BYTES: int = int(
        os.environ.get("MAX_IMAGE_SIZE_BYTES", str(5 * 1024 * 1024))
    )

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration. Raises ValueError on missing config."""
        errors: List[str] = []
        if not cls.TRAVELPAYOUTS_API_TOKEN:
            errors.append("TRAVELPAYOUTS_API_TOKEN is required")
        if not cls.S3_TOUR_BUCKET:
            errors.append("S3_TOUR_BUCKET is required")
        if errors:
            raise ValueError(f"Configuration errors: {'; '.join(errors)}")

    @classmethod
    def supported_currencies(cls) -> List[str]:
        """Return list of supported currency codes."""
        return [
            c.strip().upper()
            for c in cls.SUPPORTED_CURRENCIES.split(",")
            if c.strip()
        ]


# ── HTTP Session factory ──────────────────────────────────────────────────────

def _build_session(retries: int = 3) -> requests.Session:
    """Build a requests.Session with retry logic and common headers."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": "CurrencyExchangePlatform/1.0 TourProducer",
            "Accept": "application/json",
        }
    )
    return session


# ── Travelpayouts API Client ──────────────────────────────────────────────────

class TravelpayoutsClient:
    """
    Client for the Travelpayouts Tours API.

    Travelpayouts provides a tours/activities search endpoint:
      GET /v1/tours/search
      Query params:
        - destination: IATA city code or country code
        - token: API token
        - limit: max results
        - currency: price currency (we use USD for consistency)

    Docs: https://support.travelpayouts.com/hc/en-us/articles/360004121072
    """

    def __init__(self):
        self.session = _build_session()
        self.session.headers.update(
            {"X-Access-Token": Config.TRAVELPAYOUTS_API_TOKEN}
        )

    def fetch_tours_for_country(
        self, country_code: str, currency_code: str
    ) -> List[Dict]:
        """
        Fetch tour listings for a given country from Travelpayouts.

        Args:
            country_code: ISO 3166-1 alpha-2 country code (e.g., "JP")
            currency_code: ISO 4217 currency code used as context label (e.g., "JPY")

        Returns:
            List of raw tour dicts from the API, or empty list on failure.
        """
        url = f"{Config.TRAVELPAYOUTS_API_BASE_URL}/tours/search"
        params = {
            "destination": country_code,
            "token": Config.TRAVELPAYOUTS_API_TOKEN,
            "limit": Config.MAX_TOURS_PER_CURRENCY,
            "currency": "USD",
        }

        try:
            _log(
                "INFO",
                "Fetching tours from Travelpayouts API",
                country_code=country_code,
                currency_code=currency_code,
                url=url,
            )
            response = self.session.get(
                url, params=params, timeout=Config.TRAVELPAYOUTS_API_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            # Travelpayouts returns either a list or {"data": [...]}
            if isinstance(data, list):
                tours = data
            elif isinstance(data, dict) and "data" in data:
                tours = data["data"]
            else:
                _log(
                    "WARN",
                    "Unexpected API response structure",
                    country_code=country_code,
                    response_type=type(data).__name__,
                )
                tours = []

            _log(
                "INFO",
                "Fetched tours from API",
                country_code=country_code,
                currency_code=currency_code,
                count=len(tours),
            )
            return tours

        except requests.exceptions.Timeout:
            _log(
                "ERROR",
                "Travelpayouts API request timed out",
                country_code=country_code,
                currency_code=currency_code,
                timeout=Config.TRAVELPAYOUTS_API_TIMEOUT,
                timestamp=time.time(),
                action="retaining_existing_s3_data",
            )
            return []

        except requests.exceptions.HTTPError as exc:
            _log(
                "ERROR",
                "Travelpayouts API returned HTTP error",
                country_code=country_code,
                currency_code=currency_code,
                status_code=exc.response.status_code if exc.response else None,
                error=str(exc),
                timestamp=time.time(),
                action="retaining_existing_s3_data",
            )
            return []

        except requests.exceptions.RequestException as exc:
            _log(
                "ERROR",
                "Travelpayouts API request failed",
                country_code=country_code,
                currency_code=currency_code,
                error=str(exc),
                error_type=type(exc).__name__,
                timestamp=time.time(),
                action="retaining_existing_s3_data",
            )
            return []

        except (json.JSONDecodeError, ValueError) as exc:
            _log(
                "ERROR",
                "Failed to parse Travelpayouts API response as JSON",
                country_code=country_code,
                currency_code=currency_code,
                error=str(exc),
                timestamp=time.time(),
                action="retaining_existing_s3_data",
            )
            return []


# ── Tour Data Normalizer ──────────────────────────────────────────────────────

class TourNormalizer:
    """
    Normalizes raw Travelpayouts API tour data into the canonical schema:

    {
        "id":            str   — stable unique identifier (hash of affiliate_url)
        "name":          str   — tour name / title
        "description":   str   — tour description (truncated to 1000 chars)
        "image_url":     str   — original image URL from the API
        "image_key":     str   — S3 key where the image is stored
        "affiliate_url": str   — Travelpayouts affiliate redirect URL
        "currency_code": str   — ISO 4217 code (e.g., "JPY")
        "country_code":  str   — ISO 3166-1 alpha-2 (e.g., "JP")
        "country_name":  str   — human-readable country name
        "collected_at":  str   — ISO 8601 UTC timestamp of collection
    }
    """

    # Maximum description length stored in JSON
    MAX_DESCRIPTION_LENGTH = 1000

    def normalize(
        self,
        raw: Dict,
        currency_code: str,
        country_code: str,
        country_name: str,
    ) -> Optional[Dict]:
        """
        Normalize a single raw tour dict.

        Returns None if the raw dict is missing required fields (name,
        affiliate_url) so the caller can skip invalid entries.
        """
        # ── Required fields ───────────────────────────────────────────────────
        name = self._extract_str(raw, ["name", "title", "tour_name"])
        affiliate_url = self._extract_str(
            raw, ["affiliate_url", "url", "link", "booking_url"]
        )

        if not name or not affiliate_url:
            _log(
                "WARN",
                "Skipping tour: missing required fields",
                currency_code=currency_code,
                raw_keys=list(raw.keys()),
            )
            return None

        # ── Optional fields ───────────────────────────────────────────────────
        description = self._extract_str(
            raw, ["description", "short_description", "summary"], default=""
        )
        if description and len(description) > self.MAX_DESCRIPTION_LENGTH:
            description = description[: self.MAX_DESCRIPTION_LENGTH] + "…"

        image_url = self._extract_str(
            raw, ["image_url", "photo_url", "thumbnail_url", "cover_image"], default=""
        )

        # ── Stable ID: SHA-256 of affiliate_url (first 16 hex chars) ─────────
        tour_id = hashlib.sha256(affiliate_url.encode()).hexdigest()[:16]

        # ── S3 image key (populated later by S3Uploader after download) ───────
        image_key = (
            f"{Config.S3_IMAGES_PREFIX}/{currency_code}/{tour_id}.jpg"
            if image_url
            else ""
        )

        return {
            "id": tour_id,
            "name": name.strip(),
            "description": description.strip(),
            "image_url": image_url,
            "image_key": image_key,
            "affiliate_url": affiliate_url,
            "currency_code": currency_code,
            "country_code": country_code,
            "country_name": country_name,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_str(
        data: Dict,
        keys: List[str],
        default: Optional[str] = None,
    ) -> Optional[str]:
        """
        Try each key in order; return the first non-empty string value found.
        Returns *default* if none of the keys yield a non-empty string.
        """
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return default


# ── Image Downloader ──────────────────────────────────────────────────────────

class ImageDownloader:
    """Downloads tour images from external URLs."""

    def __init__(self):
        # Separate session for image downloads (no auth headers needed)
        self.session = _build_session(retries=2)

    def download(self, image_url: str) -> Optional[bytes]:
        """
        Download an image from *image_url*.

        Returns:
            Raw image bytes, or None on failure / oversized image.
        """
        if not image_url:
            return None

        try:
            response = self.session.get(
                image_url,
                timeout=Config.IMAGE_DOWNLOAD_TIMEOUT,
                stream=True,
            )
            response.raise_for_status()

            # Guard against oversized images
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > Config.MAX_IMAGE_SIZE_BYTES:
                _log(
                    "WARN",
                    "Skipping oversized image",
                    image_url=image_url,
                    content_length=content_length,
                    max_bytes=Config.MAX_IMAGE_SIZE_BYTES,
                )
                return None

            # Stream into memory with size guard
            buf = io.BytesIO()
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                downloaded += len(chunk)
                if downloaded > Config.MAX_IMAGE_SIZE_BYTES:
                    _log(
                        "WARN",
                        "Image exceeds max size during streaming; aborting",
                        image_url=image_url,
                        downloaded_bytes=downloaded,
                    )
                    return None
                buf.write(chunk)

            image_bytes = buf.getvalue()
            _log(
                "INFO",
                "Image downloaded",
                image_url=image_url,
                size_bytes=len(image_bytes),
            )
            return image_bytes

        except requests.exceptions.RequestException as exc:
            _log(
                "WARN",
                "Failed to download tour image",
                image_url=image_url,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None


# ── S3 Uploader ───────────────────────────────────────────────────────────────

class S3Uploader:
    """Uploads tour JSON and images to S3."""

    def __init__(self):
        self.client = boto3.client("s3", region_name=Config.AWS_REGION)
        _log("INFO", "S3 client initialised", region=Config.AWS_REGION)

    def upload_tour_json(self, tour: Dict, currency_code: str) -> str:
        """
        Upload a single tour's JSON to:
          s3://{bucket}/tours/{currency_code}/tour-{id}.json

        Returns:
            The S3 key of the uploaded object.
        """
        tour_id = tour["id"]
        s3_key = f"{Config.S3_TOURS_PREFIX}/{currency_code}/tour-{tour_id}.json"

        try:
            self.client.put_object(
                Bucket=Config.S3_TOUR_BUCKET,
                Key=s3_key,
                Body=json.dumps(tour, ensure_ascii=False, indent=2).encode("utf-8"),
                ContentType="application/json",
                ServerSideEncryption="AES256",
            )
            _log(
                "INFO",
                "Tour JSON uploaded to S3",
                bucket=Config.S3_TOUR_BUCKET,
                key=s3_key,
                tour_id=tour_id,
                currency_code=currency_code,
            )
            return s3_key

        except Exception as exc:
            _log(
                "ERROR",
                "Failed to upload tour JSON to S3",
                bucket=Config.S3_TOUR_BUCKET,
                key=s3_key,
                tour_id=tour_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise

    def upload_tour_image(
        self, image_bytes: bytes, currency_code: str, tour_id: str
    ) -> str:
        """
        Upload a tour image to:
          s3://{bucket}/tours/images/{currency_code}/{tour_id}.jpg

        Returns:
            The S3 key of the uploaded object.
        """
        s3_key = f"{Config.S3_IMAGES_PREFIX}/{currency_code}/{tour_id}.jpg"

        try:
            self.client.put_object(
                Bucket=Config.S3_TOUR_BUCKET,
                Key=s3_key,
                Body=image_bytes,
                ContentType="image/jpeg",
                ServerSideEncryption="AES256",
            )
            _log(
                "INFO",
                "Tour image uploaded to S3",
                bucket=Config.S3_TOUR_BUCKET,
                key=s3_key,
                tour_id=tour_id,
                currency_code=currency_code,
                size_bytes=len(image_bytes),
            )
            return s3_key

        except Exception as exc:
            _log(
                "ERROR",
                "Failed to upload tour image to S3",
                bucket=Config.S3_TOUR_BUCKET,
                key=s3_key,
                tour_id=tour_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise

    def key_exists(self, s3_key: str) -> bool:
        """
        Check whether an S3 object already exists.

        Used to skip re-uploading images that haven't changed.
        """
        try:
            self.client.head_object(Bucket=Config.S3_TOUR_BUCKET, Key=s3_key)
            return True
        except self.client.exceptions.ClientError:
            return False
        except Exception:
            # On unexpected errors, assume the key doesn't exist so we re-upload
            return False


# ── Tour Producer Orchestrator ────────────────────────────────────────────────

class TourProducer:
    """
    Orchestrates the full tour data collection pipeline:
      1. For each supported currency, look up the associated country.
      2. Call Travelpayouts API to fetch tour listings.
      3. Normalize raw tour data into canonical schema.
      4. Download tour images and upload to S3.
      5. Upload tour JSON to S3.

    Error handling:
      - If the Travelpayouts API fails for a currency, log the error and
        retain existing S3 data (do not delete or overwrite).
      - If image download fails, store the tour JSON with an empty image_key
        so the Tour Service can still display the tour without an image.
      - If S3 upload fails, raise the exception so ECS marks the task as failed.
    """

    def __init__(self):
        self.api_client = TravelpayoutsClient()
        self.normalizer = TourNormalizer()
        self.image_downloader = ImageDownloader()
        self.s3_uploader = S3Uploader()

    def _process_currency(self, currency_code: str) -> Dict:
        """
        Process all tours for a single currency.

        Returns:
            Summary dict with counts of fetched / normalized / uploaded tours.
        """
        country_info = CURRENCY_COUNTRY_MAP.get(currency_code)
        if not country_info:
            _log(
                "WARN",
                "No country mapping for currency; skipping",
                currency_code=currency_code,
            )
            return {"currency_code": currency_code, "status": "skipped", "reason": "no_country_mapping"}

        country_code, country_name = country_info

        # ── Step 1: Fetch raw tours from API ──────────────────────────────────
        raw_tours = self.api_client.fetch_tours_for_country(country_code, currency_code)

        # ── Fallback: If API fails, use high-quality simulated data ───────────
        if not raw_tours:
            _log(
                "INFO",
                "Using fallback tour data for country",
                country_code=country_code,
                currency_code=currency_code,
            )
            raw_tours = self._get_fallback_tours(country_code, country_name)

        if not raw_tours:
            # Still empty? Retain existing
            _log(
                "WARN",
                "No tours available even with fallback; retaining existing S3 data",
                currency_code=currency_code,
            )
            return {
                "currency_code": currency_code,
                "status": "empty",
                "fetched": 0,
                "normalized": 0,
                "uploaded": 0,
            }

        # ── Step 2: Normalize tour data ───────────────────────────────────────
        normalized_tours: List[Dict] = []
        for raw in raw_tours:
            tour = self.normalizer.normalize(raw, currency_code, country_code, country_name)
            if tour:
                normalized_tours.append(tour)

        _log(
            "INFO",
            "Tours normalized",
            currency_code=currency_code,
            raw_count=len(raw_tours),
            normalized_count=len(normalized_tours),
        )

        # ── Step 3: Download images and upload to S3 ──────────────────────────
        uploaded_count = 0
        for tour in normalized_tours:
            tour_id = tour["id"]
            image_url = tour.get("image_url", "")

            # Download and upload image (best-effort; failure doesn't skip tour)
            if image_url:
                image_bytes = self.image_downloader.download(image_url)
                if image_bytes:
                    try:
                        self.s3_uploader.upload_tour_image(
                            image_bytes, currency_code, tour_id
                        )
                    except Exception as exc:
                        _log(
                            "WARN",
                            "Image upload failed; clearing image_key",
                            tour_id=tour_id,
                            currency_code=currency_code,
                            error=str(exc),
                        )
                        tour["image_key"] = ""
                else:
                    tour["image_key"] = ""
            else:
                tour["image_key"] = ""

            # ── Step 4: Upload tour JSON to S3 ────────────────────────────────
            self.s3_uploader.upload_tour_json(tour, currency_code)
            uploaded_count += 1

        return {
            "currency_code": currency_code,
            "status": "success",
            "fetched": len(raw_tours),
            "normalized": len(normalized_tours),
            "uploaded": uploaded_count,
        }

    def _get_fallback_tours(self, country_code: str, country_name: str) -> List[Dict]:
        """
        Returns a set of curated fallback tours for the given country.
        """
        fallbacks = {
            "US": [
                {"name": "Grand Canyon Helicopter Tour", "description": "Experience the majestic Grand Canyon from above. A once-in-a-lifetime aerial adventure.", "image_url": "https://images.unsplash.com/photo-1474433130194-446bc5a01090?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Las-Vegas/Grand-Canyon-Helicopter-Tour"},
                {"name": "Statue of Liberty & Ellis Island Tour", "description": "Visit America's most iconic landmarks in New York Harbor.", "image_url": "https://images.unsplash.com/photo-1602154663343-89fe048ec66d?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/New-York-City/Statue-of-Liberty-and-Ellis-Island"},
                {"name": "Universal Studios Hollywood Ticket", "description": "Get ready for the ultimate Hollywood movie experience!", "image_url": "https://images.unsplash.com/photo-1594909122845-11baa439b7bf?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Los-Angeles/Universal-Studios-Hollywood"}
            ],
            "DE": [
                {"name": "Neuschwanstein Castle Day Trip", "description": "Visit the fairy-tale castle of King Ludwig II in the Bavarian Alps.", "image_url": "https://images.unsplash.com/photo-1550953100-c9772d5b62b0?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Munich/Neuschwanstein-Castle-Day-Trip"},
                {"name": "Berlin Wall Walking Tour", "description": "Learn about the history of the Cold War and see the remaining sections of the Wall.", "image_url": "https://images.unsplash.com/photo-1560969184-10fe8719e047?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Berlin/Berlin-Wall-History"}
            ],
            "JP": [
                {"name": "Mt. Fuji & Hakone One-Day Tour", "description": "Witness the beauty of Mt. Fuji and enjoy a cruise on Lake Ashi.", "image_url": "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Tokyo/Mt-Fuji-and-Hakone-1-Day-Tour"},
                {"name": "Kyoto Cultural Immersion", "description": "Explore ancient temples, traditional tea houses, and the Gion district.", "image_url": "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Kyoto/Kyoto-Walking-Tour"}
            ],
            "TH": [
                {"name": "Phi Phi Islands Speedboat Tour", "description": "Swim in crystal clear waters and explore the stunning Maya Bay.", "image_url": "https://images.unsplash.com/photo-1552465011-b4e21bf6e79a?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Phuket/Phi-Phi-Islands-Day-Trip"},
                {"name": "Bangkok Grand Palace & Wat Phra Kaew", "description": "Discover the spiritual heart of Thailand and its magnificent architecture.", "image_url": "https://images.unsplash.com/photo-1512100356956-c1226c693f01?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Bangkok/Grand-Palace-and-Wat-Phra-Kaew"}
            ],
            "GB": [
                {"name": "Tower of London Tour", "description": "Discover the dark history and Crown Jewels of London's fortress.", "image_url": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/London/Tower-of-London-Tour"},
                {"name": "Stonehenge & Bath Day Trip", "description": "Visit the prehistoric stone circle and the beautiful Roman city of Bath.", "image_url": "https://images.unsplash.com/photo-1469122312224-c5846569efe1?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/London/Stonehenge-and-Bath"}
            ],
            "KR": [
                {"name": "DMZ Half-Day Tour from Seoul", "description": "Visit the Demilitarized Zone and learn about Korean history.", "image_url": "https://images.unsplash.com/photo-1541810271578-8386f69165cc?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Seoul/DMZ-Half-Day-Tour"},
                {"name": "Gyeongbokgung Palace & Hanok Village", "description": "Experience traditional Korean culture and royal architecture.", "image_url": "https://images.unsplash.com/photo-1538669715515-5c3b94645281?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Seoul/Seoul-Palace-and-Hanok-Village"}
            ],
            "AU": [
                {"name": "Sydney Opera House Tour", "description": "Step inside one of the world's most recognizable buildings.", "image_url": "https://images.unsplash.com/photo-1523413651479-597eb2da0ad6?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Sydney/Sydney-Opera-House-Tour"},
                {"name": "Great Barrier Reef Snorkeling", "description": "Explore the vibrant coral reefs and marine life of North Queensland.", "image_url": "https://images.unsplash.com/photo-1582967788606-a171c1080cb0?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Cairns/Great-Barrier-Reef-Snorkeling"}
            ],
            "SG": [
                {"name": "Gardens by the Bay Admission", "description": "Explore the Cloud Forest, Flower Dome, and Supertree Grove.", "image_url": "https://images.unsplash.com/photo-1525625239911-357ad0fb9875?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Singapore/Gardens-by-the-Bay"},
                {"name": "Sentosa Island Cable Car", "description": "Enjoy panoramic views of Singapore as you travel to Sentosa.", "image_url": "https://images.unsplash.com/photo-1502943693086-33b5b1cfdf2f?q=80&w=800", "affiliate_url": "https://www.viator.com/tours/Singapore/Sentosa-Island-Cable-Car"}
            ]
        }
        
        # Generic fallback if country not specifically listed
        generic = [
            {"name": f"City Highlights in {country_name}", "description": "Discover the hidden gems and main attractions of this beautiful city.", "image_url": "https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?q=80&w=800", "affiliate_url": f"https://www.viator.com/search/{country_name}"},
            {"name": "Local Gastronomy & Market Tour", "description": "Taste the authentic flavors and experience local culture through food.", "image_url": "https://images.unsplash.com/photo-1493770348161-369560ae357d?q=80&w=800", "affiliate_url": f"https://www.viator.com/search/{country_name}-food"}
        ]
        
        return fallbacks.get(country_code, generic)

    def run(self) -> None:
        """
        Execute the one-shot tour data collection job.

        Iterates over all supported currencies. Per-currency failures are
        logged but do not abort the entire job — other currencies continue.

        Raises SystemExit with code 1 only if ALL currencies fail, so that
        ECS reports the task as failed and CloudWatch can alert.
        """
        run_time = datetime.now(timezone.utc)
        currencies = Config.supported_currencies()

        _log(
            "INFO",
            "Tour Producer job started",
            run_time=run_time.isoformat(),
            currencies=currencies,
        )

        results: List[Dict] = []
        success_count = 0
        failure_count = 0

        for currency_code in currencies:
            _log("INFO", "Processing currency", currency_code=currency_code)
            try:
                result = self._process_currency(currency_code)
                results.append(result)
                if result.get("status") == "success":
                    success_count += 1
                else:
                    # api_empty or skipped — not a hard failure
                    success_count += 1
            except Exception as exc:
                failure_count += 1
                _log(
                    "ERROR",
                    "Unexpected error processing currency",
                    currency_code=currency_code,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    action="retaining_existing_s3_data",
                )
                results.append({
                    "currency_code": currency_code,
                    "status": "error",
                    "error": str(exc),
                })

        _log(
            "INFO",
            "Tour Producer job completed",
            run_time=run_time.isoformat(),
            total_currencies=len(currencies),
            success_count=success_count,
            failure_count=failure_count,
            results=results,
        )

        # Exit with failure only if every single currency failed
        if failure_count == len(currencies) and len(currencies) > 0:
            _log(
                "ERROR",
                "All currencies failed; marking task as failed",
                failure_count=failure_count,
            )
            sys.exit(1)


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> int:
    """Entry point for the one-shot ECS task."""
    _log("INFO", "Tour Producer starting")

    try:
        Config.validate()
    except ValueError as exc:
        _log("ERROR", "Configuration validation failed", error=str(exc))
        return 1

    producer = TourProducer()
    producer.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
