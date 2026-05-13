"""
Dataset Maker — ECS One-Shot Task

Thu thập dữ liệu tỉ giá lịch sử từ Exchange Rate Cache (Redis) và transaction log
(RDS PostgreSQL), xử lý thành CSV, và upload lên S3 để SageMaker Training Job sử dụng.

Deployment: ECS Task (không phải long-running service) trong Private Subnet.
Trigger: EventBridge scheduled rule (mặc định: hàng ngày lúc 00:00 UTC).
"""

import csv
import io
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import boto3
import psycopg2
import psycopg2.extras
import redis


# ── Logging ──────────────────────────────────────────────────────────────────

def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout (CloudWatch Logs)."""
    entry = {
        "level": level,
        "message": message,
        "service": "dataset-maker",
        **kwargs,
    }
    print(json.dumps(entry, default=str), flush=True)


# ── Configuration ─────────────────────────────────────────────────────────────

class Config:
    """Configuration loaded from environment variables."""

    # Redis (Exchange Rate Cache)
    REDIS_HOST: str = os.environ.get("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.environ.get("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.environ.get("REDIS_PASSWORD")
    REDIS_SSL: bool = os.environ.get("REDIS_SSL", "true").lower() == "true"

    # RDS PostgreSQL (User_DB)
    DB_HOST: str = os.environ.get("DB_HOST", "localhost")
    DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
    DB_NAME: str = os.environ.get("DB_NAME", "currency_exchange")
    DB_USER: str = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")

    # S3
    # S3_TRAINING_BUCKET takes precedence; S3_BUCKET is kept for backward compatibility.
    S3_BUCKET: str = os.environ.get("S3_TRAINING_BUCKET", "") or os.environ.get("S3_BUCKET", "")
    S3_PREFIX: str = os.environ.get("S3_PREFIX", "training-data")

    # Data collection window
    LOOKBACK_HOURS: int = int(os.environ.get("LOOKBACK_HOURS", "24"))

    # AWS
    AWS_REGION: str = os.environ.get("AWS_REGION", "ap-southeast-2")

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration. Raises ValueError on missing config."""
        errors = []
        if not cls.REDIS_HOST:
            errors.append("REDIS_HOST is required")
        if not cls.DB_HOST:
            errors.append("DB_HOST is required")
        if not cls.DB_NAME:
            errors.append("DB_NAME is required")
        if not cls.DB_USER:
            errors.append("DB_USER is required")
        if not cls.S3_BUCKET:
            errors.append("S3_BUCKET (or S3_TRAINING_BUCKET) is required")
        if cls.LOOKBACK_HOURS <= 0:
            errors.append("LOOKBACK_HOURS must be a positive integer")
        if errors:
            raise ValueError(f"Configuration errors: {'; '.join(errors)}")


# ── Redis Client ──────────────────────────────────────────────────────────────

class RedisClient:
    """Thin wrapper around Redis connection for reading exchange rate data."""

    # Key prefix used by Exchange Rate Producer (see producer.py)
    RATE_KEY_PREFIX = "exchange_rate:"

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
                decode_responses=True,
                retry_on_timeout=True,
            )
            self.client.ping()
            _log(
                "INFO",
                "Redis connection established",
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
            )
        except redis.RedisError as exc:
            _log(
                "ERROR",
                "Failed to connect to Redis",
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                error=str(exc),
            )
            raise

    def fetch_all_rates(self) -> List[Dict]:
        """
        Scan all exchange_rate:* keys and return their parsed JSON values.

        Returns:
            List of dicts with keys: currency, rate, timestamp
        """
        records: List[Dict] = []
        pattern = f"{self.RATE_KEY_PREFIX}*"

        try:
            # Use SCAN to avoid blocking Redis with KEYS on large datasets
            cursor = 0
            while True:
                cursor, keys = self.client.scan(cursor=cursor, match=pattern, count=100)
                for key in keys:
                    raw = self.client.get(key)
                    if raw is None:
                        # Key expired between SCAN and GET — skip silently
                        continue
                    try:
                        data = json.loads(raw)
                        # Validate required fields
                        if "currency" not in data or "rate" not in data:
                            _log(
                                "WARN",
                                "Skipping malformed Redis entry",
                                key=key,
                                raw=raw[:200],
                            )
                            continue
                        records.append(
                            {
                                "currency": data["currency"],
                                "rate": float(data["rate"]),
                                "timestamp": float(data.get("timestamp", time.time())),
                            }
                        )
                    except (json.JSONDecodeError, ValueError, TypeError) as exc:
                        _log(
                            "WARN",
                            "Failed to parse Redis value",
                            key=key,
                            error=str(exc),
                        )
                if cursor == 0:
                    break

            _log("INFO", "Fetched exchange rates from Redis", count=len(records))
            return records

        except redis.RedisError as exc:
            _log("ERROR", "Redis scan failed", error=str(exc))
            raise


# ── PostgreSQL Client ─────────────────────────────────────────────────────────

class PostgreSQLClient:
    """Client for reading transaction data from RDS PostgreSQL."""

    def __init__(self):
        self.conn: Optional[psycopg2.extensions.connection] = None
        self._connect()

    def _connect(self) -> None:
        """Establish PostgreSQL connection."""
        try:
            self.conn = psycopg2.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                dbname=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                connect_timeout=10,
                sslmode="require",
            )
            _log(
                "INFO",
                "PostgreSQL connection established",
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                dbname=Config.DB_NAME,
            )
        except psycopg2.Error as exc:
            _log(
                "ERROR",
                "Failed to connect to PostgreSQL",
                host=Config.DB_HOST,
                error=str(exc),
            )
            raise

    def fetch_transaction_stats(
        self, lookback_hours: int
    ) -> List[Dict]:
        """
        Query the transactions table for records within the lookback window.

        Groups by (currency, hour) to produce:
          - transaction_volume: sum of amounts exchanged
          - transaction_count: number of transactions

        Only 'exchange' type transactions are included (they have from_currency /
        to_currency and rate_applied, making them relevant for ML training).

        Args:
            lookback_hours: Number of hours to look back from now.

        Returns:
            List of dicts with keys:
              timestamp (ISO 8601 str), currency_code, transaction_volume,
              transaction_count
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

        query = """
            SELECT
                date_trunc('hour', created_at)  AS hour_bucket,
                to_currency                      AS currency_code,
                SUM(amount)                      AS transaction_volume,
                COUNT(*)                         AS transaction_count
            FROM transactions
            WHERE
                type = 'exchange'
                AND created_at >= %(cutoff)s
                AND to_currency IS NOT NULL
            GROUP BY
                date_trunc('hour', created_at),
                to_currency
            ORDER BY
                hour_bucket ASC,
                to_currency ASC
        """

        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, {"cutoff": cutoff})
                rows = cur.fetchall()

            records = []
            for row in rows:
                records.append(
                    {
                        "timestamp": row["hour_bucket"].isoformat(),
                        "currency_code": row["currency_code"],
                        "transaction_volume": float(row["transaction_volume"]),
                        "transaction_count": int(row["transaction_count"]),
                    }
                )

            _log(
                "INFO",
                "Fetched transaction stats from PostgreSQL",
                count=len(records),
                lookback_hours=lookback_hours,
                cutoff=cutoff.isoformat(),
            )
            return records

        except psycopg2.Error as exc:
            _log("ERROR", "Failed to query transactions table", error=str(exc))
            raise

    def close(self) -> None:
        """Close the database connection."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            _log("INFO", "PostgreSQL connection closed")


# ── Data Processor ────────────────────────────────────────────────────────────

class DataProcessor:
    """
    Combines Redis exchange rate data and PostgreSQL transaction stats into
    a single CSV suitable for SageMaker time-series training (e.g., DeepAR,
    XGBoost, or tabular algorithms).

    CSV columns:
        timestamp          — ISO 8601 datetime (hourly bucket)
        currency_code      — ISO 4217 currency code
        rate_to_vnd        — Exchange rate (1 VND = X currency), raw value
        rate_normalized    — Min-max normalised rate per currency (0.0–1.0);
                             falls back to 0.5 when only one data point exists
        transaction_volume — Sum of exchange amounts in the hour bucket
        transaction_count  — Number of exchange transactions in the hour bucket
        hour               — Hour of day (0–23) extracted from timestamp
        day_of_week        — Day of week (0=Monday … 6=Sunday)
        day_of_month       — Day of month (1–31)
    """

    CSV_COLUMNS = [
        "timestamp",
        "currency_code",
        "rate_to_vnd",
        "rate_normalized",
        "transaction_volume",
        "transaction_count",
        "hour",
        "day_of_week",
        "day_of_month",
    ]

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_timestamp(ts_value) -> Optional[datetime]:
        """
        Parse a timestamp value into a timezone-aware datetime.

        Accepts:
          - Unix epoch float/int
          - ISO 8601 string (with or without timezone)

        Returns None if the value cannot be parsed.
        """
        if ts_value is None:
            return None
        try:
            if isinstance(ts_value, (int, float)):
                return datetime.fromtimestamp(float(ts_value), tz=timezone.utc)
            if isinstance(ts_value, str):
                # Handle both offset-aware ("2024-01-15T00:00:00+00:00") and
                # naive ("2024-01-15T00:00:00") ISO strings.
                dt = datetime.fromisoformat(ts_value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
        except (ValueError, TypeError, OSError):
            pass
        return None

    @staticmethod
    def _floor_to_hour(dt: datetime) -> datetime:
        """Return *dt* truncated to the start of its hour."""
        return dt.replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def _extract_time_features(dt: datetime) -> Tuple[int, int, int]:
        """
        Extract cyclical time features from a datetime.

        Returns:
            (hour, day_of_week, day_of_month)
            hour         — 0–23
            day_of_week  — 0 (Monday) … 6 (Sunday)
            day_of_month — 1–31
        """
        return dt.hour, dt.weekday(), dt.day

    @staticmethod
    def _normalize_rates(rows: List[Dict]) -> List[Dict]:
        """
        Add ``rate_normalized`` (min-max per currency) to each row in-place.

        For each currency code the normalisation is:
            rate_normalized = (rate - min_rate) / (max_rate - min_rate)

        Edge cases:
          - Single data point for a currency → rate_normalized = 0.5
          - All rates identical (max == min) → rate_normalized = 0.5

        Args:
            rows: List of row dicts that already contain ``currency_code``
                  and ``rate_to_vnd`` keys.

        Returns:
            The same list with ``rate_normalized`` added to every dict.
        """
        # Group rates by currency
        rates_by_currency: Dict[str, List[float]] = {}
        for row in rows:
            code = row["currency_code"]
            rates_by_currency.setdefault(code, []).append(float(row["rate_to_vnd"]))

        # Compute per-currency min/max
        stats: Dict[str, Tuple[float, float]] = {}
        for code, rates in rates_by_currency.items():
            min_r = min(rates)
            max_r = max(rates)
            stats[code] = (min_r, max_r)

        # Annotate rows
        for row in rows:
            code = row["currency_code"]
            min_r, max_r = stats[code]
            if max_r == min_r:
                row["rate_normalized"] = 0.5
            else:
                row["rate_normalized"] = (float(row["rate_to_vnd"]) - min_r) / (max_r - min_r)

        return rows

    @staticmethod
    def _forward_fill_missing(rows: List[Dict]) -> List[Dict]:
        """
        Forward-fill missing values within each currency's time series.

        The function detects gaps in the hourly time series for each currency
        and inserts synthetic rows by carrying the last known ``rate_to_vnd``
        and ``transaction_volume``/``transaction_count`` = 0 forward.

        Only gaps up to 24 hours are filled; larger gaps are left as-is to
        avoid propagating stale data across day boundaries.

        Args:
            rows: Sorted list of row dicts (timestamp ASC, currency ASC).
                  Each row must have ``timestamp`` (ISO 8601 str) and
                  ``currency_code``.

        Returns:
            New list with gap-filling rows inserted, still sorted.
        """
        MAX_FILL_HOURS = 24

        # Group rows by currency, preserving order
        by_currency: Dict[str, List[Dict]] = {}
        for row in rows:
            by_currency.setdefault(row["currency_code"], []).append(row)

        filled_rows: List[Dict] = []

        for code, currency_rows in by_currency.items():
            # Sort by timestamp within the currency
            currency_rows.sort(key=lambda r: r["timestamp"])

            filled_rows.append(currency_rows[0])

            for i in range(1, len(currency_rows)):
                prev = currency_rows[i - 1]
                curr = currency_rows[i]

                prev_dt = DataProcessor._parse_timestamp(prev["timestamp"])
                curr_dt = DataProcessor._parse_timestamp(curr["timestamp"])

                if prev_dt is None or curr_dt is None:
                    filled_rows.append(curr)
                    continue

                prev_hour = DataProcessor._floor_to_hour(prev_dt)
                curr_hour = DataProcessor._floor_to_hour(curr_dt)
                gap_hours = int((curr_hour - prev_hour).total_seconds() // 3600)

                # Insert synthetic rows for gaps of 2–MAX_FILL_HOURS hours
                if 2 <= gap_hours <= MAX_FILL_HOURS:
                    for h in range(1, gap_hours):
                        fill_dt = prev_hour + timedelta(hours=h)
                        fill_hour, fill_dow, fill_dom = DataProcessor._extract_time_features(fill_dt)
                        synthetic = {
                            "timestamp": fill_dt.isoformat(),
                            "currency_code": code,
                            "rate_to_vnd": prev["rate_to_vnd"],
                            "rate_normalized": prev.get("rate_normalized", 0.5),
                            "transaction_volume": 0.0,
                            "transaction_count": 0,
                            "hour": fill_hour,
                            "day_of_week": fill_dow,
                            "day_of_month": fill_dom,
                        }
                        filled_rows.append(synthetic)

                filled_rows.append(curr)

        # Re-sort the combined list
        filled_rows.sort(key=lambda r: (r["timestamp"], r["currency_code"]))
        return filled_rows

    # ── Public API ────────────────────────────────────────────────────────────

    def build_csv(
        self,
        rate_records: List[Dict],
        transaction_records: List[Dict],
    ) -> str:
        """
        Merge rate and transaction data into a normalised, feature-enriched
        CSV string suitable for SageMaker training.

        Processing pipeline:
          1. Merge Redis rate records with PostgreSQL transaction stats.
          2. Add time-based features (hour, day_of_week, day_of_month).
          3. Normalise exchange rates per currency (min-max, 0.0–1.0).
          4. Forward-fill gaps in each currency's hourly time series.
          5. Sort rows (timestamp ASC, currency_code ASC).
          6. Serialise to CSV with a fixed column order.

        Args:
            rate_records: List of dicts from RedisClient.fetch_all_rates()
                          Keys: currency (str), rate (float), timestamp (float)
            transaction_records: List of dicts from
                                 PostgreSQLClient.fetch_transaction_stats()
                                 Keys: timestamp (str), currency_code (str),
                                       transaction_volume (float),
                                       transaction_count (int)

        Returns:
            CSV string with header row.
        """
        # ── Step 1: Build transaction lookup ─────────────────────────────────
        # currency_code → aggregated stats (sum across all hour buckets)
        tx_by_currency: Dict[str, Dict] = {}
        for tx in transaction_records:
            code = tx["currency_code"]
            if code not in tx_by_currency:
                tx_by_currency[code] = {
                    "transaction_volume": 0.0,
                    "transaction_count": 0,
                    "timestamp": tx["timestamp"],
                }
            tx_by_currency[code]["transaction_volume"] += tx["transaction_volume"]
            tx_by_currency[code]["transaction_count"] += tx["transaction_count"]
            # Keep the latest timestamp for this currency
            if tx["timestamp"] > tx_by_currency[code]["timestamp"]:
                tx_by_currency[code]["timestamp"] = tx["timestamp"]

        # ── Step 2: Build base rows from Redis rate records ───────────────────
        now_dt = self._floor_to_hour(datetime.now(timezone.utc))
        now_iso = now_dt.isoformat()

        rows: List[Dict] = []
        for rate_rec in rate_records:
            code = rate_rec["currency"]
            tx_stats = tx_by_currency.get(code, {})

            # Determine the hourly timestamp for this rate entry
            rate_ts = rate_rec.get("timestamp")
            parsed_dt = self._parse_timestamp(rate_ts)
            if parsed_dt is not None:
                row_dt = self._floor_to_hour(parsed_dt)
                ts = row_dt.isoformat()
            else:
                row_dt = now_dt
                ts = now_iso

            # Extract time-based features
            hour, day_of_week, day_of_month = self._extract_time_features(row_dt)

            rows.append(
                {
                    "timestamp": ts,
                    "currency_code": code,
                    "rate_to_vnd": rate_rec["rate"],
                    "rate_normalized": 0.5,  # placeholder; overwritten in step 3
                    "transaction_volume": tx_stats.get("transaction_volume", 0.0),
                    "transaction_count": tx_stats.get("transaction_count", 0),
                    "hour": hour,
                    "day_of_week": day_of_week,
                    "day_of_month": day_of_month,
                }
            )

        # ── Step 3: Normalise rates per currency ──────────────────────────────
        rows = self._normalize_rates(rows)

        # ── Step 4: Forward-fill gaps in each currency's time series ──────────
        rows = self._forward_fill_missing(rows)

        # ── Step 5: Sort for deterministic output ─────────────────────────────
        rows.sort(key=lambda r: (r["timestamp"], r["currency_code"]))

        # ── Step 6: Serialise to CSV ──────────────────────────────────────────
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

        csv_content = output.getvalue()
        _log(
            "INFO",
            "CSV built",
            row_count=len(rows),
            byte_size=len(csv_content.encode("utf-8")),
        )
        return csv_content


# ── S3 Uploader ───────────────────────────────────────────────────────────────

class S3Uploader:
    """Uploads CSV data to S3 under the training-data/ prefix."""

    def __init__(self):
        self.client = boto3.client("s3", region_name=Config.AWS_REGION)
        _log("INFO", "S3 client initialised", region=Config.AWS_REGION)

    def upload(self, csv_content: str, run_time: datetime) -> str:
        """
        Upload CSV to S3 at path:
            {S3_PREFIX}/{YYYY}/{MM}/{DD}/rates_{timestamp}.csv

        Args:
            csv_content: CSV string to upload.
            run_time: The datetime used to partition the S3 path.

        Returns:
            The full S3 key of the uploaded object.
        """
        timestamp_str = run_time.strftime("%Y%m%dT%H%M%SZ")
        s3_key = (
            f"{Config.S3_PREFIX}/"
            f"{run_time.strftime('%Y')}/"
            f"{run_time.strftime('%m')}/"
            f"{run_time.strftime('%d')}/"
            f"rates_{timestamp_str}.csv"
        )

        try:
            self.client.put_object(
                Bucket=Config.S3_BUCKET,
                Key=s3_key,
                Body=csv_content.encode("utf-8"),
                ContentType="text/csv",
                ServerSideEncryption="AES256",
            )
            _log(
                "INFO",
                "CSV uploaded to S3",
                bucket=Config.S3_BUCKET,
                key=s3_key,
                byte_size=len(csv_content.encode("utf-8")),
            )
            return s3_key

        except Exception as exc:
            _log(
                "ERROR",
                "Failed to upload CSV to S3",
                bucket=Config.S3_BUCKET,
                key=s3_key,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise


# ── Main Orchestrator ─────────────────────────────────────────────────────────

class DatasetMaker:
    """
    Orchestrates the full dataset collection pipeline:
      1. Read current exchange rates from Redis.
      2. Read transaction stats from PostgreSQL.
      3. Merge and normalise into CSV.
      4. Upload CSV to S3.
    """

    def __init__(self):
        self.redis_client = RedisClient()
        self.db_client = PostgreSQLClient()
        self.processor = DataProcessor()
        self.uploader = S3Uploader()

    def run(self) -> None:
        """
        Execute the one-shot dataset collection job.

        Raises SystemExit with code 1 on any unrecoverable error so that ECS
        reports the task as failed (enabling EventBridge / CloudWatch alerting).
        """
        run_time = datetime.now(timezone.utc)
        _log(
            "INFO",
            "Dataset Maker job started",
            run_time=run_time.isoformat(),
            lookback_hours=Config.LOOKBACK_HOURS,
        )

        try:
            # Step 1: Collect exchange rates from Redis
            _log("INFO", "Step 1/4: Collecting exchange rates from Redis")
            rate_records = self.redis_client.fetch_all_rates()

            if not rate_records:
                _log(
                    "WARN",
                    "No exchange rate data found in Redis cache; "
                    "CSV will contain only transaction data",
                )

            # Step 2: Collect transaction stats from PostgreSQL
            _log("INFO", "Step 2/4: Collecting transaction stats from PostgreSQL")
            transaction_records = self.db_client.fetch_transaction_stats(
                Config.LOOKBACK_HOURS
            )

            # Step 3: Build CSV
            _log("INFO", "Step 3/4: Building CSV")
            csv_content = self.processor.build_csv(rate_records, transaction_records)

            if not csv_content.strip() or csv_content.count("\n") <= 1:
                # Only header row — no data rows
                _log(
                    "WARN",
                    "CSV contains no data rows; skipping S3 upload",
                    csv_preview=csv_content[:200],
                )
                return

            # Step 4: Upload to S3
            _log("INFO", "Step 4/4: Uploading CSV to S3")
            s3_key = self.uploader.upload(csv_content, run_time)

            _log(
                "INFO",
                "Dataset Maker job completed successfully",
                s3_key=s3_key,
                run_time=run_time.isoformat(),
            )

        except Exception as exc:
            _log(
                "ERROR",
                "Dataset Maker job failed",
                error=str(exc),
                error_type=type(exc).__name__,
                run_time=run_time.isoformat(),
            )
            sys.exit(1)

        finally:
            # Always close DB connection
            try:
                self.db_client.close()
            except Exception:
                pass


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> int:
    """Entry point for the one-shot ECS task."""
    _log("INFO", "Dataset Maker starting")

    try:
        Config.validate()
    except ValueError as exc:
        _log("ERROR", "Configuration validation failed", error=str(exc))
        return 1

    maker = DatasetMaker()
    maker.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
