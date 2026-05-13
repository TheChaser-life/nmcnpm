"""
Exchange Rate Producer — ECS Service

Định kỳ polling External Exchange API để lấy tỉ giá tiền tệ so với VND.
Lưu kết quả vào Exchange_Rate_Cache (Redis) với TTL=30s.

Deployment: ECS Fargate trong Public Subnet (cần internet access để gọi external API)
Multi-AZ: AZ 1 active, AZ 2 standby (auto-activate khi AZ 1 fail)
"""

import json
import logging
import os
import sys
import time
from typing import Dict, Optional

import boto3
import redis
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout (CloudWatch Logs)."""
    entry = {"level": level, "message": message, "service": "exchange-rate-producer", **kwargs}
    print(json.dumps(entry, default=str), flush=True)


# ── Configuration ────────────────────────────────────────────────────────────

class Config:
    """Configuration loaded from environment variables."""
    
    # External API
    EXCHANGE_API_URL: str = os.environ.get(
        "EXCHANGE_API_URL",
        "https://api.exchangerate-api.com/v4/latest/VND"
    )
    EXCHANGE_API_KEY: Optional[str] = os.environ.get("EXCHANGE_API_KEY")
    EXCHANGE_API_TIMEOUT: int = int(os.environ.get("EXCHANGE_API_TIMEOUT", "10"))
    
    # Redis (ElastiCache)
    REDIS_HOST: str = os.environ.get("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.environ.get("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.environ.get("REDIS_PASSWORD")
    REDIS_SSL: bool = os.environ.get("REDIS_SSL", "true").lower() == "true"
    
    # Polling
    # Default 420s (7 phút) = 1,440 requests/tuần — nằm trong free plan 1,500 req/tháng
    # Tính toán: 7 ngày × 24h × 60 phút / 7 phút = 1,440 requests
    # Có thể override bằng env var POLLING_INTERVAL_SECONDS nếu dùng paid plan
    POLLING_INTERVAL_SECONDS: int = int(os.environ.get("POLLING_INTERVAL_SECONDS", "420"))
    # Cache TTL = polling interval + 60s buffer để tránh gap giữa 2 lần poll
    CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL_SECONDS", "480"))
    
    # Supported currencies (comma-separated)
    SUPPORTED_CURRENCIES: str = os.environ.get(
        "SUPPORTED_CURRENCIES",
        "USD,EUR,GBP,JPY,CNY,KRW,THB,SGD,MYR,IDR,PHP,AUD"
    )
    
    # CloudWatch metrics
    CLOUDWATCH_NAMESPACE: str = os.environ.get(
        "CLOUDWATCH_NAMESPACE", "CurrencyExchangePlatform"
    )
    CLOUDWATCH_REGION: str = os.environ.get("AWS_REGION", "ap-southeast-2")
    ENABLE_CLOUDWATCH_METRICS: bool = os.environ.get(
        "ENABLE_CLOUDWATCH_METRICS", "true"
    ).lower() == "true"
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.REDIS_HOST:
            raise ValueError("REDIS_HOST environment variable is required")
        if cls.POLLING_INTERVAL_SECONDS <= 0:
            raise ValueError("POLLING_INTERVAL_SECONDS must be positive")
        # Tính số request/tuần để cảnh báo nếu vượt free plan
        requests_per_week = (7 * 24 * 3600) // cls.POLLING_INTERVAL_SECONDS
        if requests_per_week > 1500:
            _log("WARN", "Polling interval may exceed ExchangeRate-API free plan (1,500 req/month)",
                 interval_seconds=cls.POLLING_INTERVAL_SECONDS,
                 estimated_requests_per_week=requests_per_week)


# ── Redis Client ─────────────────────────────────────────────────────────────

class RedisClient:
    """Wrapper for Redis connection with retry logic."""
    
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self._connect()
    
    def _connect(self) -> None:
        """Establish Redis connection."""
        try:
            self.client = redis.Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=Config.REDIS_DB,
                password=Config.REDIS_PASSWORD,
                ssl=Config.REDIS_SSL,
                socket_connect_timeout=5,
                socket_timeout=5,
                decode_responses=True,  # Return strings instead of bytes
                retry_on_timeout=True,
            )
            # Test connection
            self.client.ping()
            _log("INFO", "Redis connection established",
                 host=Config.REDIS_HOST, port=Config.REDIS_PORT)
        except redis.RedisError as exc:
            _log("ERROR", "Failed to connect to Redis",
                 host=Config.REDIS_HOST, port=Config.REDIS_PORT, error=str(exc))
            raise
    
    def set_rate(self, currency: str, rate: float, ttl: int) -> bool:
        """
        Store exchange rate in Redis with TTL.
        
        Key format: exchange_rate:{currency}
        Value: JSON string with rate and timestamp
        
        Returns:
            True if successful, False otherwise
        """
        key = f"exchange_rate:{currency}"
        value = json.dumps({
            "currency": currency,
            "rate": rate,
            "timestamp": time.time(),
        })
        
        try:
            self.client.setex(key, ttl, value)
            return True
        except redis.RedisError as exc:
            _log("ERROR", "Failed to set rate in Redis",
                 currency=currency, rate=rate, error=str(exc))
            return False
    
    def health_check(self) -> bool:
        """Check if Redis connection is alive."""
        try:
            self.client.ping()
            return True
        except redis.RedisError:
            return False


# ── CloudWatch Metrics Client ─────────────────────────────────────────────────

class CloudWatchClient:
    """Client for emitting custom CloudWatch metrics."""

    METRIC_CACHE_AGE = "ExchangeRateCacheAge"

    def __init__(self):
        self._client = None
        if Config.ENABLE_CLOUDWATCH_METRICS:
            try:
                self._client = boto3.client(
                    "cloudwatch", region_name=Config.CLOUDWATCH_REGION
                )
                _log("INFO", "CloudWatch client initialized",
                     namespace=Config.CLOUDWATCH_NAMESPACE,
                     region=Config.CLOUDWATCH_REGION)
            except Exception as exc:  # pragma: no cover
                _log("WARN", "Failed to initialize CloudWatch client; "
                     "metrics will be disabled", error=str(exc))
                self._client = None

    def emit_cache_updated(self) -> None:
        """
        Emit ExchangeRateCacheAge = 0 to CloudWatch after a successful cache write.

        The CloudWatch Alarm (task 2.2.5) triggers when this metric has not been
        published for 120 seconds, which means the producer has stopped updating
        the cache.  Publishing 0 on every successful write resets the alarm.
        """
        if self._client is None:
            return

        try:
            self._client.put_metric_data(
                Namespace=Config.CLOUDWATCH_NAMESPACE,
                MetricData=[
                    {
                        "MetricName": self.METRIC_CACHE_AGE,
                        "Value": 0,
                        "Unit": "Seconds",
                        "Timestamp": time.time(),
                    }
                ],
            )
            _log("INFO", "Emitted CloudWatch metric",
                 metric=self.METRIC_CACHE_AGE, value=0,
                 namespace=Config.CLOUDWATCH_NAMESPACE)
        except Exception as exc:
            # Metric emission failure must never interrupt the main polling loop.
            _log("WARN", "Failed to emit CloudWatch metric",
                 metric=self.METRIC_CACHE_AGE, error=str(exc))


# ── Exchange Rate API Client ─────────────────────────────────────────────────

class ExchangeRateAPIClient:
    """Client for external exchange rate API with retry logic."""
    
    def __init__(self):
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set headers
        self.session.headers.update({
            "User-Agent": "CurrencyExchangePlatform/1.0",
            "Accept": "application/json",
        })
        
        if Config.EXCHANGE_API_KEY:
            self.session.headers.update({
                "Authorization": f"Bearer {Config.EXCHANGE_API_KEY}"
            })
    
    def _normalize_rates_to_vnd(
        self,
        base: str,
        rates: Dict[str, float],
    ) -> Optional[Dict[str, float]]:
        """
        Normalize exchange rates so that VND is always the base currency.

        The system stores rates as "1 VND = X foreign currency".

        Cases:
        - base == "VND": rates are already in the correct form; return as-is
          after filtering out zero/invalid values.
        - base != "VND": the API returned rates relative to a different base
          (e.g., "1 USD = X other_currency").  We need to convert so that
          "1 VND = X foreign_currency".

          Conversion formula:
            rate_vnd_base[currency] = rate_api[currency] / rate_api["VND"]

          where rate_api["VND"] is the number of VND per 1 unit of base
          currency as reported by the API.

        Returns:
            Dict mapping currency code → rate (1 VND = X currency),
            or None if conversion is impossible (e.g., VND rate missing or zero).
        """
        base = base.upper()

        if base == "VND":
            # Rates are already expressed as "1 VND = X foreign currency".
            # Filter out any zero or negative rates to avoid downstream errors.
            normalized: Dict[str, float] = {}
            for currency, rate in rates.items():
                if not isinstance(rate, (int, float)) or rate <= 0:
                    _log("WARN", "Skipping invalid rate in VND-base response",
                         currency=currency, rate=rate)
                    continue
                normalized[currency] = float(rate)
            return normalized

        # base != "VND": convert from base-relative rates to VND-relative rates.
        # We need the rate for VND in the API response (i.e., how many VND per
        # 1 unit of the API base currency).
        vnd_rate = rates.get("VND")
        if vnd_rate is None:
            _log("ERROR",
                 "Cannot normalize rates: API response with non-VND base is "
                 "missing 'VND' in rates dict",
                 base=base)
            return None

        if not isinstance(vnd_rate, (int, float)) or vnd_rate <= 0:
            _log("ERROR",
                 "Cannot normalize rates: VND rate is zero or invalid",
                 base=base, vnd_rate=vnd_rate)
            return None

        _log("INFO",
             "Converting rates from non-VND base to VND base",
             api_base=base,
             vnd_rate_in_api=vnd_rate)

        normalized = {}
        for currency, rate in rates.items():
            if currency == "VND":
                # Skip VND itself — we don't store "1 VND = 1 VND"
                continue
            if not isinstance(rate, (int, float)) or rate <= 0:
                _log("WARN", "Skipping invalid rate during base conversion",
                     currency=currency, rate=rate, api_base=base)
                continue
            # rate_api[currency] = X currency per 1 base_currency
            # rate_api["VND"]    = Y VND per 1 base_currency
            # Therefore: 1 VND = (X / Y) currency
            normalized[currency] = float(rate) / float(vnd_rate)

        return normalized

    def fetch_rates(self) -> Optional[Dict[str, float]]:
        """
        Fetch exchange rates from external API and normalize to VND base.

        The API may return rates with any base currency.  This method always
        returns rates expressed as "1 VND = X foreign currency" regardless of
        what base the API used.

        Expected API response format (VND base — ideal case):
        {
            "base": "VND",
            "rates": {
                "USD": 0.000043,
                "EUR": 0.000039,
                ...
            }
        }

        Alternative API response format (non-VND base):
        {
            "base": "USD",
            "rates": {
                "VND": 23256,
                "EUR": 0.92,
                ...
            }
        }

        Returns:
            Dict mapping currency code to rate (1 VND = X currency),
            or None on failure.
        """
        try:
            _log("INFO", "Fetching exchange rates from external API",
                 url=Config.EXCHANGE_API_URL)
            
            response = self.session.get(
                Config.EXCHANGE_API_URL,
                timeout=Config.EXCHANGE_API_TIMEOUT
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Validate response structure
            rates = data.get("rates") or data.get("conversion_rates")
            if not rates:
                _log("ERROR", "Invalid API response: missing 'rates' or 'conversion_rates' field",
                     response_keys=list(data.keys()))
                return None
            
            base = data.get("base") or data.get("base_code") or "VND"

            _log("INFO", "Successfully fetched exchange rates from API",
                 base=base, currency_count=len(rates))

            # Normalize so all rates are expressed relative to VND
            normalized = self._normalize_rates_to_vnd(base, rates)
            if normalized is None:
                _log("ERROR", "Rate normalization failed; discarding API response",
                     base=base)
                return None

            _log("INFO", "Exchange rates normalized to VND base",
                 original_base=base,
                 normalized_currency_count=len(normalized))

            return normalized
            
        except requests.exceptions.Timeout:
            _log("ERROR", "API request timed out",
                 url=Config.EXCHANGE_API_URL,
                 timeout=Config.EXCHANGE_API_TIMEOUT,
                 timestamp=time.time(),
                 action="retaining_existing_cache")
            return None
        
        except requests.exceptions.HTTPError as exc:
            _log("ERROR", "API returned HTTP error",
                 url=Config.EXCHANGE_API_URL,
                 status_code=exc.response.status_code,
                 error=str(exc),
                 timestamp=time.time(),
                 action="retaining_existing_cache")
            return None
        
        except requests.exceptions.RequestException as exc:
            _log("ERROR", "API request failed",
                 url=Config.EXCHANGE_API_URL,
                 error=str(exc),
                 error_type=type(exc).__name__,
                 timestamp=time.time(),
                 action="retaining_existing_cache")
            return None
        
        except json.JSONDecodeError as exc:
            _log("ERROR", "Failed to parse API response as JSON",
                 error=str(exc),
                 timestamp=time.time(),
                 action="retaining_existing_cache")
            return None


# ── Producer Main Logic ──────────────────────────────────────────────────────

class ExchangeRateProducer:
    """Main producer service that polls API and updates cache."""
    
    def __init__(self):
        self.redis_client = RedisClient()
        self.api_client = ExchangeRateAPIClient()
        self.cloudwatch_client = CloudWatchClient()
        self.supported_currencies = [
            c.strip().upper() 
            for c in Config.SUPPORTED_CURRENCIES.split(",")
            if c.strip()
        ]
        
        _log("INFO", "Exchange Rate Producer initialized",
             supported_currencies=self.supported_currencies,
             polling_interval=Config.POLLING_INTERVAL_SECONDS)
    
    def _filter_supported_rates(self, rates: Dict[str, float]) -> Dict[str, float]:
        """Filter rates to only include supported currencies."""
        filtered = {
            currency: rate
            for currency, rate in rates.items()
            if currency in self.supported_currencies
        }
        
        missing = set(self.supported_currencies) - set(filtered.keys())
        if missing:
            _log("WARN", "Some supported currencies not found in API response",
                 missing_currencies=list(missing))
        
        return filtered
    
    def _update_cache(self, rates: Dict[str, float]) -> None:
        """Update Redis cache with new rates."""
        success_count = 0
        failure_count = 0
        
        for currency, rate in rates.items():
            if self.redis_client.set_rate(currency, rate, Config.CACHE_TTL_SECONDS):
                success_count += 1
            else:
                failure_count += 1
        
        _log("INFO", "Cache update completed",
             success_count=success_count,
             failure_count=failure_count,
             total=len(rates))
        
        # Emit CloudWatch metric so the ExchangeRateCacheAge alarm (task 2.2.5)
        # can detect if the cache stops being updated.  Only emit when at least
        # one currency was written successfully.
        if success_count > 0:
            try:
                self.cloudwatch_client.emit_cache_updated()
            except Exception as exc:
                _log("WARN", "CloudWatch metric emission failed in _update_cache",
                     error=str(exc))
    
    def poll_once(self) -> bool:
        """
        Execute one polling cycle.
        
        Returns:
            True if successful, False if API call failed
        
        Error Handling:
            When API call fails, this method returns False without updating
            the cache, thereby preserving the existing cached rates. This
            ensures that clients continue to receive the last known good
            rates until the external API becomes available again.
        """
        # Fetch rates from external API
        rates = self.api_client.fetch_rates()
        
        if rates is None:
            _log("WARN", "Polling cycle failed: API returned no data",
                 timestamp=time.time(),
                 action="cache_preserved")
            # Per design: retain existing cache, do not overwrite
            return False
        
        # Filter to supported currencies
        filtered_rates = self._filter_supported_rates(rates)
        
        if not filtered_rates:
            _log("ERROR", "No supported currencies found in API response")
            return False
        
        # Update cache
        self._update_cache(filtered_rates)
        
        return True
    
    def run(self) -> None:
        """
        Main loop: poll API at configured interval.
        
        Runs indefinitely until interrupted (SIGTERM from ECS).
        """
        _log("INFO", "Starting polling loop",
             interval_seconds=Config.POLLING_INTERVAL_SECONDS)
        
        cycle_count = 0
        success_count = 0
        failure_count = 0
        
        try:
            while True:
                cycle_count += 1
                cycle_start = time.time()
                
                _log("INFO", "Starting polling cycle",
                     cycle=cycle_count,
                     success_total=success_count,
                     failure_total=failure_count)
                
                # Execute polling
                success = self.poll_once()
                
                if success:
                    success_count += 1
                else:
                    failure_count += 1
                
                # Calculate sleep time
                cycle_duration = time.time() - cycle_start
                sleep_time = max(0, Config.POLLING_INTERVAL_SECONDS - cycle_duration)
                
                _log("INFO", "Polling cycle completed",
                     cycle=cycle_count,
                     success=success,
                     duration_seconds=round(cycle_duration, 2),
                     sleep_seconds=round(sleep_time, 2))
                
                # Sleep until next cycle
                if sleep_time > 0:
                    time.sleep(sleep_time)
        
        except KeyboardInterrupt:
            _log("INFO", "Received interrupt signal, shutting down gracefully")
        
        except Exception as exc:
            _log("ERROR", "Unexpected error in polling loop",
                 error=str(exc), error_type=type(exc).__name__)
            raise
        
        finally:
            _log("INFO", "Producer stopped",
                 total_cycles=cycle_count,
                 total_success=success_count,
                 total_failure=failure_count)


# ── Entry Point ──────────────────────────────────────────────────────────────

def main() -> int:
    """Entry point for the service."""
    _log("INFO", "Exchange Rate Producer starting")
    
    try:
        # Validate configuration
        Config.validate()
        
        # Create and run producer
        producer = ExchangeRateProducer()
        producer.run()
        
        return 0
    
    except Exception as exc:
        _log("ERROR", "Fatal error during startup",
             error=str(exc), error_type=type(exc).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
