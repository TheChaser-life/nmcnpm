"""
Money Service — ECS Service

Cung cap REST API xu ly trao doi tien te (POST /exchange) voi idempotency va optimistic locking.

Deployment: ECS Fargate trong Private Subnet (truy cap qua ALB)
JWT Verification: JWKS public keys tu Cognito (cached 24h)
Idempotency: ElastiCache Redis (noeviction)
Exchange Rate: ElastiCache Redis (volatile-lru)
Database: RDS PostgreSQL (optimistic locking via version column)
"""

import json
import os
import sys
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

import boto3
import psycopg2
import psycopg2.extras
import redis
import requests
from flask import Flask, jsonify, request
import jwt
from jwt.algorithms import RSAAlgorithm


# ── Logging ───────────────────────────────────────────────────────────────────


def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout (CloudWatch Logs)."""
    entry = {
        "level": level,
        "message": message,
        "service": "money-service",
        **kwargs,
    }
    print(json.dumps(entry, default=str), flush=True)


# ── Configuration ─────────────────────────────────────────────────────────────


class Config:
    """Configuration loaded from environment variables."""

    PORT: int = int(os.environ.get("PORT", "8080"))
    AWS_REGION: str = os.environ.get("AWS_REGION", "ap-southeast-2")

    # Cognito
    COGNITO_USER_POOL_ID: str = os.environ.get("COGNITO_USER_POOL_ID", "")
    COGNITO_REGION: str = os.environ.get("COGNITO_REGION", "ap-southeast-2")
    JWKS_CACHE_TTL_SECONDS: int = int(os.environ.get("JWKS_CACHE_TTL_SECONDS", "86400"))

    # RDS PostgreSQL
    DB_HOST: str = os.environ.get("DB_HOST", "localhost")
    DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
    DB_NAME: str = os.environ.get("DB_NAME", "currency_exchange")
    DB_USER: str = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")

    # Exchange Rate Cache (Redis)
    EXCHANGE_RATE_REDIS_HOST: str = os.environ.get("EXCHANGE_RATE_REDIS_HOST", "localhost")
    EXCHANGE_RATE_REDIS_PORT: int = int(os.environ.get("EXCHANGE_RATE_REDIS_PORT", "6379"))
    EXCHANGE_RATE_REDIS_PASSWORD: Optional[str] = os.environ.get("EXCHANGE_RATE_REDIS_PASSWORD")
    EXCHANGE_RATE_REDIS_SSL: bool = os.environ.get("EXCHANGE_RATE_REDIS_SSL", "true").lower() == "true"

    # Idempotency Cache (Redis)
    IDEMPOTENCY_REDIS_HOST: str = os.environ.get("IDEMPOTENCY_REDIS_HOST", "localhost")
    IDEMPOTENCY_REDIS_PORT: int = int(os.environ.get("IDEMPOTENCY_REDIS_PORT", "6379"))
    IDEMPOTENCY_REDIS_PASSWORD: Optional[str] = os.environ.get("IDEMPOTENCY_REDIS_PASSWORD")
    IDEMPOTENCY_REDIS_SSL: bool = os.environ.get("IDEMPOTENCY_REDIS_SSL", "true").lower() == "true"

    # Transaction settings
    MAX_LOCK_RETRIES: int = int(os.environ.get("MAX_LOCK_RETRIES", "3"))

    # Cleanup job
    CLEANUP_INTERVAL_SECONDS: int = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", "86400"))
    IDEMPOTENCY_TTL_DAYS: int = int(os.environ.get("IDEMPOTENCY_TTL_DAYS", "7"))

    # Premium upgrade
    # AWS SSM / Parameter Store
    SSM_PREMIUM_FEE_PARAM: str = os.environ.get(
        "SSM_PREMIUM_FEE_PARAM", "/nmcnpm/premium_fee"
    )
    # Reconciliation job: how often to retry failed Cognito updates (seconds)
    RECONCILIATION_INTERVAL_SECONDS: int = int(
        os.environ.get("RECONCILIATION_INTERVAL_SECONDS", "300")  # 5 minutes
    )

    @classmethod
    def get_jwks_url(cls) -> str:
        return (
            f"https://cognito-idp.{cls.COGNITO_REGION}.amazonaws.com"
            f"/{cls.COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        )

    @classmethod
    def get_issuer(cls) -> str:
        return (
            f"https://cognito-idp.{cls.COGNITO_REGION}.amazonaws.com"
            f"/{cls.COGNITO_USER_POOL_ID}"
        )

    @classmethod
    def validate(cls) -> None:
        errors = []
        if not cls.COGNITO_USER_POOL_ID:
            errors.append("COGNITO_USER_POOL_ID is required")
        if not cls.DB_HOST:
            errors.append("DB_HOST is required")
        if not cls.EXCHANGE_RATE_REDIS_HOST:
            errors.append("EXCHANGE_RATE_REDIS_HOST is required")
        if not cls.IDEMPOTENCY_REDIS_HOST:
            errors.append("IDEMPOTENCY_REDIS_HOST is required")
        if errors:
            raise ValueError(f"Configuration errors: {'; '.join(errors)}")


# ── JWKS Cache ────────────────────────────────────────────────────────────────


class JWKSCache:
    """Thread-safe in-memory cache for Cognito JWKS public keys."""

    def __init__(self, jwks_url: str, ttl_seconds: int = 86400):
        self._jwks_url = jwks_url
        self._ttl_seconds = ttl_seconds
        self._keys: Dict[str, Any] = {}
        self._fetched_at: Optional[float] = None
        self._lock = threading.Lock()

    def _is_expired(self) -> bool:
        if self._fetched_at is None:
            return True
        return (time.time() - self._fetched_at) >= self._ttl_seconds

    def _fetch_and_cache(self) -> None:
        _log("INFO", "Fetching JWKS from Cognito", url=self._jwks_url)
        try:
            response = requests.get(self._jwks_url, timeout=10)
            response.raise_for_status()
            jwks = response.json()
            new_keys: Dict[str, Any] = {}
            for key_data in jwks.get("keys", []):
                kid = key_data.get("kid")
                if kid:
                    public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
                    new_keys[kid] = public_key
            self._keys = new_keys
            self._fetched_at = time.time()
            _log("INFO", "JWKS cache refreshed", key_count=len(new_keys))
        except requests.RequestException as exc:
            _log("ERROR", "Failed to fetch JWKS from Cognito",
                 url=self._jwks_url, error=str(exc))
            raise

    def get_public_key(self, kid: str) -> Optional[Any]:
        with self._lock:
            if self._is_expired():
                self._fetch_and_cache()
            if kid not in self._keys:
                _log("INFO", "Key ID not found in cache, refreshing", kid=kid)
                self._fetch_and_cache()
            return self._keys.get(kid)


# ── JWT Errors ────────────────────────────────────────────────────────────────


class JWTVerificationError(Exception):
    pass


class MissingTokenError(JWTVerificationError):
    pass


class TokenExpiredError(JWTVerificationError):
    pass


class InvalidTokenError(JWTVerificationError):
    pass


# ── JWT Verifier ──────────────────────────────────────────────────────────────


class JWTVerifier:
    """Verifies Cognito JWTs and extracts claims."""

    def __init__(self, jwks_cache: JWKSCache, issuer: str):
        self._jwks_cache = jwks_cache
        self._issuer = issuer

    def extract_token_from_header(self, authorization_header: Optional[str]) -> str:
        if not authorization_header:
            raise MissingTokenError("Authorization header required")
        parts = authorization_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise MissingTokenError("Authorization header must be: Bearer <token>")
        return parts[1]

    def verify(self, token: str) -> Dict[str, Any]:
        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            if not kid:
                raise InvalidTokenError("JWT header missing 'kid' field")
            public_key = self._jwks_cache.get_public_key(kid)
            if public_key is None:
                raise InvalidTokenError(f"No public key found for kid: {kid}")
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={"verify_exp": True, "verify_iss": True, "verify_aud": False},
            )
            return claims
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError(f"Token is invalid: {exc}")

    def get_cognito_sub(self, claims: Dict[str, Any]) -> str:
        """Extract cognito_sub from JWT claims."""
        sub = claims.get("sub")
        if not sub:
            raise InvalidTokenError("JWT missing 'sub' claim")
        return sub


# ── Exchange Rate Cache Client ────────────────────────────────────────────────


class ExchangeRateCache:
    """Read-only client for Exchange Rate Cache (Redis)."""

    RATE_KEY_PREFIX = "exchange_rate:"

    def __init__(self):
        self.client = redis.Redis(
            host=Config.EXCHANGE_RATE_REDIS_HOST,
            port=Config.EXCHANGE_RATE_REDIS_PORT,
            password=Config.EXCHANGE_RATE_REDIS_PASSWORD if Config.EXCHANGE_RATE_REDIS_PASSWORD else None,
            ssl=Config.EXCHANGE_RATE_REDIS_SSL,
            socket_connect_timeout=5,
            socket_timeout=5,
            decode_responses=True,
            retry_on_timeout=True,
        )
        self.client.ping()
        _log("INFO", "Exchange Rate Cache connected",
             host=Config.EXCHANGE_RATE_REDIS_HOST,
             port=Config.EXCHANGE_RATE_REDIS_PORT)

    def get_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        """
        Get the exchange rate for converting from_currency to to_currency.

        Exchange rates are stored as "1 VND = X foreign_currency".
        To convert from_currency -> to_currency:
          1. Get rate_from: 1 VND = rate_from * from_currency  =>  1 from_currency = 1/rate_from VND
          2. Get rate_to:   1 VND = rate_to * to_currency
          3. Result: 1 from_currency = (1/rate_from) * rate_to to_currency
                                     = rate_to / rate_from

        Special case: if from_currency == "VND", rate = rate_to (direct lookup).
        Special case: if to_currency == "VND", rate = 1/rate_from.
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency == to_currency:
            return 1.0

        try:
            if from_currency == "VND":
                raw = self.client.get(f"{self.RATE_KEY_PREFIX}{to_currency}")
                if raw is None:
                    _log("WARN", "Exchange rate not found in cache",
                         currency=to_currency)
                    return None
                data = json.loads(raw)
                return float(data["rate"])

            if to_currency == "VND":
                raw = self.client.get(f"{self.RATE_KEY_PREFIX}{from_currency}")
                if raw is None:
                    _log("WARN", "Exchange rate not found in cache",
                         currency=from_currency)
                    return None
                data = json.loads(raw)
                rate_from = float(data["rate"])
                if rate_from == 0:
                    return None
                return 1.0 / rate_from

            # Both non-VND: cross rate via VND
            raw_from = self.client.get(f"{self.RATE_KEY_PREFIX}{from_currency}")
            raw_to = self.client.get(f"{self.RATE_KEY_PREFIX}{to_currency}")
            if raw_from is None or raw_to is None:
                _log("WARN", "Exchange rate not found in cache",
                     from_currency=from_currency, to_currency=to_currency)
                return None
            rate_from = float(json.loads(raw_from)["rate"])
            rate_to = float(json.loads(raw_to)["rate"])
            if rate_from == 0:
                return None
            return rate_to / rate_from

        except (redis.RedisError, json.JSONDecodeError, KeyError, ValueError) as exc:
            _log("ERROR", "Failed to read exchange rate from cache",
                 from_currency=from_currency, to_currency=to_currency,
                 error=str(exc))
            return None


# ── Idempotency Cache Client ──────────────────────────────────────────────────


class IdempotencyCache:
    """Client for Idempotency Cache (Redis, noeviction)."""

    KEY_PREFIX = "idempotency:"

    def __init__(self):
        self.client = redis.Redis(
            host=Config.IDEMPOTENCY_REDIS_HOST,
            port=Config.IDEMPOTENCY_REDIS_PORT,
            password=Config.IDEMPOTENCY_REDIS_PASSWORD if Config.IDEMPOTENCY_REDIS_PASSWORD else None,
            ssl=Config.IDEMPOTENCY_REDIS_SSL,
            socket_connect_timeout=5,
            socket_timeout=5,
            decode_responses=True,
            retry_on_timeout=True,
        )
        self.client.ping()
        _log("INFO", "Idempotency Cache connected",
             host=Config.IDEMPOTENCY_REDIS_HOST,
             port=Config.IDEMPOTENCY_REDIS_PORT)

    def get(self, idempotency_key: str) -> Optional[Dict]:
        """Return cached result for the given key, or None if not found."""
        try:
            raw = self.client.hget(f"{self.KEY_PREFIX}{idempotency_key}", "result")
            if raw is None:
                return None
            return json.loads(raw)
        except (redis.RedisError, json.JSONDecodeError) as exc:
            _log("ERROR", "Failed to read from idempotency cache",
                 key=idempotency_key, error=str(exc))
            return None

    def set(self, idempotency_key: str, result: Dict) -> None:
        """
        Store result in idempotency cache with no TTL.
        Also stores created_at timestamp for the background cleanup job.
        """
        try:
            key = f"{self.KEY_PREFIX}{idempotency_key}"
            self.client.hset(key, mapping={
                "result": json.dumps(result, default=str),
                "created_at": str(time.time()),
            })
            # No TTL — cleanup job handles expiry
            _log("INFO", "Stored result in idempotency cache",
                 idempotency_key=idempotency_key)
        except redis.RedisError as exc:
            _log("ERROR", "Failed to write to idempotency cache",
                 key=idempotency_key, error=str(exc))
            raise

    def delete_old_keys(self, ttl_days: int) -> int:
        """
        Background cleanup: delete idempotency keys older than ttl_days.
        Returns the number of keys deleted.
        """
        cutoff = time.time() - (ttl_days * 86400)
        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = self.client.scan(
                    cursor=cursor,
                    match=f"{self.KEY_PREFIX}*",
                    count=100,
                )
                for key in keys:
                    created_at_raw = self.client.hget(key, "created_at")
                    if created_at_raw is not None:
                        try:
                            created_at = float(created_at_raw)
                            if created_at < cutoff:
                                self.client.delete(key)
                                deleted += 1
                        except (ValueError, TypeError):
                            pass
                if cursor == 0:
                    break
            _log("INFO", "Idempotency cache cleanup completed",
                 deleted=deleted, ttl_days=ttl_days)
        except redis.RedisError as exc:
            _log("ERROR", "Idempotency cache cleanup failed", error=str(exc))
        return deleted


# ── PostgreSQL Client ─────────────────────────────────────────────────────────


class DatabaseClient:
    """PostgreSQL client with connection management."""

    def __init__(self):
        self.conn: Optional[psycopg2.extensions.connection] = None
        self._connect()

    def _connect(self) -> None:
        self.conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            dbname=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            connect_timeout=10,
            sslmode="require",
        )
        self.conn.autocommit = False
        _log("INFO", "PostgreSQL connection established",
             host=Config.DB_HOST, dbname=Config.DB_NAME)

    def _ensure_connected(self) -> None:
        """Reconnect if connection was lost."""
        try:
            if self.conn is None or self.conn.closed:
                self._connect()
            else:
                self.conn.cursor().execute("SELECT 1")
        except psycopg2.Error:
            self._connect()

    def close(self) -> None:
        if self.conn and not self.conn.closed:
            self.conn.close()


# ── Exchange Transaction Logic ────────────────────────────────────────────────


class InsufficientBalanceError(Exception):
    pass


class OptimisticLockConflictError(Exception):
    pass


def execute_exchange(
    db: DatabaseClient,
    user_id: str,
    from_currency: str,
    to_currency: str,
    original_amount: Decimal,
    vnd_cost: Decimal,
    rate: float,
    received_amount: float,
    idempotency_key: str,
) -> Dict:
    """
    Execute a currency exchange transaction with optimistic locking.

    Uses optimistic locking via the version column:
      1. SELECT balance, version FROM users WHERE cognito_sub = ?
      2. Validate sufficient balance
      3. UPDATE users SET balance = ?, version = version+1 WHERE id = ? AND version = ?
         (rowcount == 0 means version conflict → caller retries)
      4. INSERT INTO transactions (audit log)
      5. COMMIT

    The balance is stored in VND. The caller pre-computes vnd_cost (the VND
    amount to deduct) and received_amount (the to_currency amount the user
    receives), so this function only handles DB operations.

    Args:
        db: DatabaseClient instance
        user_id: cognito_sub of the user
        from_currency: Source currency code (e.g. "USD")
        to_currency: Destination currency code (e.g. "EUR")
        original_amount: Amount in from_currency units (for audit record)
        vnd_cost: VND amount to deduct from balance
        rate: Exchange rate (1 from_currency = rate to_currency) for audit
        received_amount: Amount in to_currency the user receives (for audit)
        idempotency_key: Idempotency key for this transaction

    Returns:
        Dict with transaction result

    Raises:
        InsufficientBalanceError: If balance is insufficient
        OptimisticLockConflictError: If version mismatch (caller should retry)
        ValueError: If user not found
    """
    db._ensure_connected()
    conn = db.conn

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Step 1: Read current user state (no FOR UPDATE — optimistic locking)
            cur.execute(
                "SELECT id, balance, version FROM users WHERE cognito_sub = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                raise ValueError(f"User not found: {user_id}")

            db_user_id = str(row["id"])
            current_balance = Decimal(str(row["balance"]))
            current_version = int(row["version"])

            # Step 2: Validate sufficient balance
            if current_balance < vnd_cost:
                conn.rollback()
                raise InsufficientBalanceError(
                    f"Insufficient balance: {current_balance} VND < {vnd_cost} VND required"
                )

            new_balance = current_balance - vnd_cost
            new_version = current_version + 1

            # Step 3: Optimistic lock update — only succeeds if version unchanged
            cur.execute(
                """
                UPDATE users
                SET balance = %s, version = %s, updated_at = NOW()
                WHERE id = %s AND version = %s
                """,
                (str(new_balance), new_version, db_user_id, current_version),
            )

            if cur.rowcount == 0:
                # Version mismatch — another concurrent transaction modified the row
                conn.rollback()
                raise OptimisticLockConflictError("Version conflict detected")

            # Step 4: Insert audit record
            transaction_id = str(uuid.uuid4())

            cur.execute(
                """
                INSERT INTO transactions
                    (id, user_id, type, from_currency, to_currency, amount, rate_applied, idempotency_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    transaction_id,
                    db_user_id,
                    "exchange",
                    from_currency.upper(),
                    to_currency.upper(),
                    str(original_amount),
                    str(rate),
                    idempotency_key,
                ),
            )

            # Step 5: Commit
            conn.commit()

            result = {
                "transaction_id": transaction_id,
                "user_id": db_user_id,
                "type": "exchange",
                "from_currency": from_currency.upper(),
                "to_currency": to_currency.upper(),
                "amount": float(original_amount),
                "rate_applied": rate,
                "received_amount": received_amount,
                "new_balance_vnd": float(new_balance),
                "idempotency_key": idempotency_key,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

            _log("INFO", "Exchange transaction committed",
                 transaction_id=transaction_id,
                 user_id=db_user_id,
                 from_currency=from_currency,
                 to_currency=to_currency,
                 original_amount=float(original_amount),
                 vnd_cost=float(vnd_cost),
                 rate=rate)

            return result

    except (InsufficientBalanceError, OptimisticLockConflictError, ValueError):
        raise
    except psycopg2.Error as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        _log("ERROR", "Database error during exchange", error=str(exc))
        raise


# ── Top-Up Transaction Logic ──────────────────────────────────────────────────


def execute_topup(
    db: DatabaseClient,
    user_id: str,
    amount: Decimal,
    idempotency_key: str,
) -> Dict:
    """
    Execute a top-up transaction with optimistic locking.

    Credits the specified VND amount directly to the user's balance.

    Uses optimistic locking via the version column:
      1. SELECT balance, version FROM users WHERE cognito_sub = ?
      2. UPDATE users SET balance = balance + amount, version = version+1
         WHERE id = ? AND version = ?
         (rowcount == 0 means version conflict → caller retries)
      3. INSERT INTO transactions (audit log, type='topup')
      4. COMMIT

    Args:
        db: DatabaseClient instance
        user_id: cognito_sub of the user
        amount: VND amount to credit to the user's balance
        idempotency_key: Idempotency key for this transaction

    Returns:
        Dict with transaction result

    Raises:
        OptimisticLockConflictError: If version mismatch (caller should retry)
        ValueError: If user not found
    """
    db._ensure_connected()
    conn = db.conn

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Step 1: Read current user state (no FOR UPDATE — optimistic locking)
            cur.execute(
                "SELECT id, balance, version FROM users WHERE cognito_sub = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                raise ValueError(f"User not found: {user_id}")

            db_user_id = str(row["id"])
            current_balance = Decimal(str(row["balance"]))
            current_version = int(row["version"])

            new_balance = current_balance + amount
            new_version = current_version + 1

            # Step 2: Optimistic lock update — only succeeds if version unchanged
            cur.execute(
                """
                UPDATE users
                SET balance = %s, version = %s, updated_at = NOW()
                WHERE id = %s AND version = %s
                """,
                (str(new_balance), new_version, db_user_id, current_version),
            )

            if cur.rowcount == 0:
                # Version mismatch — another concurrent transaction modified the row
                conn.rollback()
                raise OptimisticLockConflictError("Version conflict detected")

            # Step 3: Insert audit record
            transaction_id = str(uuid.uuid4())

            cur.execute(
                """
                INSERT INTO transactions
                    (id, user_id, type, from_currency, to_currency, amount, rate_applied, idempotency_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    transaction_id,
                    db_user_id,
                    "topup",
                    None,
                    "VND",
                    str(amount),
                    None,
                    idempotency_key,
                ),
            )

            # Step 4: Commit
            conn.commit()

            result = {
                "transaction_id": transaction_id,
                "user_id": db_user_id,
                "type": "topup",
                "from_currency": None,
                "to_currency": "VND",
                "amount": float(amount),
                "rate_applied": None,
                "new_balance_vnd": float(new_balance),
                "idempotency_key": idempotency_key,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

            _log("INFO", "Top-up transaction committed",
                 transaction_id=transaction_id,
                 user_id=db_user_id,
                 amount=float(amount),
                 new_balance_vnd=float(new_balance))

            return result

    except (OptimisticLockConflictError, ValueError):
        raise
    except psycopg2.Error as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        _log("ERROR", "Database error during topup", error=str(exc))
        raise


# ── Premium Upgrade Logic ─────────────────────────────────────────────────────


class AlreadyPremiumError(Exception):
    """Raised when the user is already a premium subscriber."""
    pass


def get_premium_fee_from_ssm() -> Decimal:
    """
    Read the premium subscription fee from AWS SSM Parameter Store.

    Parameter name: /currency-exchange/premium_fee
    The value is stored as a plain numeric string (e.g. "500000").

    Returns:
        Decimal: The premium fee in VND.

    Raises:
        ValueError: If the parameter is missing or cannot be parsed.
    """
    try:
        ssm = boto3.client("ssm", region_name=Config.AWS_REGION)
        response = ssm.get_parameter(
            Name=Config.SSM_PREMIUM_FEE_PARAM,
            WithDecryption=True,
        )
        raw_value = response["Parameter"]["Value"]
        fee = Decimal(raw_value)
        if fee <= 0:
            raise ValueError(f"premium_fee must be positive, got: {raw_value}")
        _log("INFO", "Premium fee loaded from Parameter Store",
             param=Config.SSM_PREMIUM_FEE_PARAM, fee=str(fee))
        return fee
    except (InvalidOperation, ValueError) as exc:
        _log("ERROR", "Invalid premium_fee value in Parameter Store",
             param=Config.SSM_PREMIUM_FEE_PARAM, error=str(exc))
        raise ValueError(f"Invalid premium_fee value: {exc}") from exc
    except Exception as exc:
        _log("ERROR", "Failed to read premium_fee from SSM Parameter Store",
             param=Config.SSM_PREMIUM_FEE_PARAM, error=str(exc))
        raise ValueError(f"Cannot read premium_fee from Parameter Store: {exc}") from exc


def update_cognito_premium_attribute(cognito_sub: str) -> None:
    """
    Call Cognito AdminUpdateUserAttributes to set custom:premium = true.

    Args:
        cognito_sub: The Cognito user's sub (username in Cognito).

    Raises:
        Exception: If the Cognito API call fails.
    """
    cognito = boto3.client("cognito-idp", region_name=Config.COGNITO_REGION)
    cognito.admin_update_user_attributes(
        UserPoolId=Config.COGNITO_USER_POOL_ID,
        Username=cognito_sub,
        UserAttributes=[
            {"Name": "custom:premium", "Value": "true"},
        ],
    )
    _log("INFO", "Cognito premium attribute updated",
         cognito_sub=cognito_sub, user_pool_id=Config.COGNITO_USER_POOL_ID)


def execute_premium_upgrade(
    db: DatabaseClient,
    user_id: str,
    premium_fee: Decimal,
    idempotency_key: str,
) -> Dict:
    """
    Execute the premium upgrade balance deduction with optimistic locking.

    Steps:
      1. SELECT balance, version, premium_deducted FROM users WHERE cognito_sub = ?
      2. Validate balance ≥ premium_fee
      3. UPDATE users SET balance = balance - fee, version = version+1,
                          premium_deducted = TRUE, updated_at = NOW()
         WHERE id = ? AND version = ?
         (rowcount == 0 → version conflict → caller retries)
      4. INSERT INTO transactions (type='premium_upgrade')
      5. COMMIT

    Args:
        db: DatabaseClient instance
        user_id: cognito_sub of the user
        premium_fee: VND amount to deduct
        idempotency_key: Idempotency key for this transaction

    Returns:
        Dict with transaction result including new_balance_vnd

    Raises:
        InsufficientBalanceError: If balance < premium_fee
        AlreadyPremiumError: If premium_deducted is already True
        OptimisticLockConflictError: If version mismatch (caller should retry)
        ValueError: If user not found
    """
    db._ensure_connected()
    conn = db.conn

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Step 1: Read current user state
            cur.execute(
                "SELECT id, balance, version, premium_deducted FROM users WHERE cognito_sub = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                raise ValueError(f"User not found: {user_id}")

            db_user_id = str(row["id"])
            current_balance = Decimal(str(row["balance"]))
            current_version = int(row["version"])
            already_deducted = bool(row["premium_deducted"])

            # If premium_deducted is already True, the fee was already charged.
            # This is the idempotency guard at the DB level.
            if already_deducted:
                conn.rollback()
                raise AlreadyPremiumError(
                    f"Premium fee already deducted for user: {user_id}"
                )

            # Step 2: Validate sufficient balance
            if current_balance < premium_fee:
                conn.rollback()
                raise InsufficientBalanceError(
                    f"Insufficient balance: {current_balance} VND < {premium_fee} VND required"
                )

            new_balance = current_balance - premium_fee
            new_version = current_version + 1

            # Step 3: Optimistic lock update — mark premium_deducted = TRUE
            cur.execute(
                """
                UPDATE users
                SET balance = %s,
                    version = %s,
                    premium_deducted = TRUE,
                    updated_at = NOW()
                WHERE id = %s AND version = %s
                """,
                (str(new_balance), new_version, db_user_id, current_version),
            )

            if cur.rowcount == 0:
                conn.rollback()
                raise OptimisticLockConflictError("Version conflict detected")

            # Step 4: Insert audit record
            transaction_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO transactions
                    (id, user_id, type, from_currency, to_currency, amount, rate_applied, idempotency_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    transaction_id,
                    db_user_id,
                    "premium_upgrade",
                    "VND",
                    None,
                    str(premium_fee),
                    None,
                    idempotency_key,
                ),
            )

            # Step 5: Commit
            conn.commit()

            result = {
                "transaction_id": transaction_id,
                "user_id": db_user_id,
                "type": "premium_upgrade",
                "amount": float(premium_fee),
                "new_balance_vnd": float(new_balance),
                "idempotency_key": idempotency_key,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

            _log("INFO", "Premium upgrade balance deducted",
                 transaction_id=transaction_id,
                 user_id=db_user_id,
                 premium_fee=float(premium_fee),
                 new_balance_vnd=float(new_balance))

            return result

    except (InsufficientBalanceError, AlreadyPremiumError, OptimisticLockConflictError, ValueError):
        raise
    except psycopg2.Error as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        _log("ERROR", "Database error during premium upgrade", error=str(exc))
        raise


def mark_cognito_update_complete(db: DatabaseClient, user_id: str) -> None:
    """
    Clear the premium_deducted flag after a successful Cognito update.
    This marks the reconciliation as complete for this user.

    Args:
        db: DatabaseClient instance
        user_id: cognito_sub of the user
    """
    db._ensure_connected()
    conn = db.conn
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET premium_deducted = FALSE, updated_at = NOW()
                WHERE cognito_sub = %s
                """,
                (user_id,),
            )
        conn.commit()
        _log("INFO", "Cleared premium_deducted flag after successful Cognito update",
             cognito_sub=user_id)
    except psycopg2.Error as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        _log("ERROR", "Failed to clear premium_deducted flag",
             cognito_sub=user_id, error=str(exc))
        raise


def get_users_pending_cognito_update(db: DatabaseClient) -> list:
    """
    Query users where premium_deducted = TRUE (balance deducted but Cognito
    update has not been confirmed yet).

    Returns:
        List of dicts with keys: cognito_sub
    """
    db._ensure_connected()
    conn = db.conn
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT cognito_sub FROM users WHERE premium_deducted = TRUE"
            )
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    except psycopg2.Error as exc:
        _log("ERROR", "Failed to query users pending Cognito update", error=str(exc))
        return []


# ── Reconciliation Job ────────────────────────────────────────────────────────


class PremiumReconciliationJob:
    """
    Background thread that periodically retries Cognito AdminUpdateUserAttributes
    for users whose balance was deducted (premium_deducted = TRUE) but whose
    Cognito attribute was not successfully updated.

    This handles the partial-failure scenario described in design.md Section 6:
    Steps 4 (DB deduction) and 5 (Cognito update) are not atomic. If Cognito
    fails after the DB commit, this job retries until it succeeds.
    """

    def __init__(self, db_client: DatabaseClient):
        self._db = db_client
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="premium-reconciliation"
        )
        self._thread.start()
        _log("INFO", "Premium reconciliation job started",
             interval_seconds=Config.RECONCILIATION_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.wait(timeout=Config.RECONCILIATION_INTERVAL_SECONDS):
            try:
                self._reconcile()
            except Exception as exc:
                _log("ERROR", "Reconciliation cycle failed", error=str(exc))

    def _reconcile(self) -> None:
        """
        Find all users with premium_deducted = TRUE and retry Cognito update.
        On success, clear the flag. Log all attempts.
        """
        pending = get_users_pending_cognito_update(self._db)
        if not pending:
            return

        _log("INFO", "Reconciliation: found users pending Cognito update",
             count=len(pending))

        for user_row in pending:
            cognito_sub = user_row["cognito_sub"]
            try:
                update_cognito_premium_attribute(cognito_sub)
                mark_cognito_update_complete(self._db, cognito_sub)
                _log("INFO", "Reconciliation: Cognito update succeeded",
                     cognito_sub=cognito_sub)
            except Exception as exc:
                _log("ERROR", "Reconciliation: Cognito update failed, will retry next cycle",
                     cognito_sub=cognito_sub, error=str(exc))


class IdempotencyCleanupJob:
    """Background thread that periodically removes old idempotency keys."""

    def __init__(self, idempotency_cache: IdempotencyCache):
        self._cache = idempotency_cache
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="idempotency-cleanup")
        self._thread.start()
        _log("INFO", "Idempotency cleanup job started",
             interval_seconds=Config.CLEANUP_INTERVAL_SECONDS,
             ttl_days=Config.IDEMPOTENCY_TTL_DAYS)

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.wait(timeout=Config.CLEANUP_INTERVAL_SECONDS):
            try:
                deleted = self._cache.delete_old_keys(Config.IDEMPOTENCY_TTL_DAYS)
                _log("INFO", "Cleanup job cycle completed", deleted=deleted)
            except Exception as exc:
                _log("ERROR", "Cleanup job cycle failed", error=str(exc))


# ── Flask Application ─────────────────────────────────────────────────────────


def create_app(
    jwt_verifier: Optional[JWTVerifier] = None,
    exchange_rate_cache: Optional[ExchangeRateCache] = None,
    idempotency_cache: Optional[IdempotencyCache] = None,
    db_client: Optional[DatabaseClient] = None,
) -> Flask:
    """
    Create and configure the Flask application.
    Accepts optional dependency injection for testing.
    """
    app = Flask(__name__)

    _jwt_verifier = jwt_verifier
    _exchange_rate_cache = exchange_rate_cache
    _idempotency_cache = idempotency_cache
    _db_client = db_client

    def _get_jwt_verifier() -> JWTVerifier:
        nonlocal _jwt_verifier
        if _jwt_verifier is None:
            jwks_url = Config.get_jwks_url()
            _log("INFO", "Initializing JWT Verifier", jwks_url=jwks_url, issuer=Config.get_issuer())
            jwks_cache = JWKSCache(
                jwks_url=jwks_url,
                ttl_seconds=Config.JWKS_CACHE_TTL_SECONDS,
            )
            _jwt_verifier = JWTVerifier(
                jwks_cache=jwks_cache,
                issuer=Config.get_issuer(),
            )
        return _jwt_verifier

    def _get_exchange_rate_cache() -> ExchangeRateCache:
        nonlocal _exchange_rate_cache
        if _exchange_rate_cache is None:
            _exchange_rate_cache = ExchangeRateCache()
        return _exchange_rate_cache

    def _get_idempotency_cache() -> IdempotencyCache:
        nonlocal _idempotency_cache
        if _idempotency_cache is None:
            _idempotency_cache = IdempotencyCache()
        return _idempotency_cache

    def _get_db_client() -> DatabaseClient:
        nonlocal _db_client
        if _db_client is None:
            _db_client = DatabaseClient()
        return _db_client

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/balance", methods=["GET"])
    def balance():
        """
        GET /balance
        Returns the current user's VND balance and recent transaction history.
        """
        verifier = _get_jwt_verifier()
        try:
            token = verifier.extract_token_from_header(request.headers.get("Authorization"))
            claims = verifier.verify(token)
            cognito_sub = claims.get("sub")
        except JWTVerificationError as exc:
            _log("WARN", "JWT Verification failed in /balance", error=str(exc))
            return jsonify({"error": "unauthorized", "message": str(exc)}), 401

        db = _get_db_client()
        db._ensure_connected()
        try:
            with db.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get balance
                cur.execute("SELECT id, balance FROM users WHERE cognito_sub = %s", (cognito_sub,))
                user_row = cur.fetchone()
                if not user_row:
                    return jsonify({"error": "user_not_found", "message": "User not found"}), 404
                
                user_db_id = user_row["id"]
                balance_vnd = float(user_row["balance"])

                # Get recent transactions
                cur.execute(
                    """
                    SELECT id, type, from_currency, to_currency, amount, rate_applied, created_at
                    FROM transactions
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT 20
                    """,
                    (user_db_id,)
                )
                tx_rows = cur.fetchall()
                
                transactions = []
                for tx in tx_rows:
                    transactions.append({
                        "id": str(tx["id"]),
                        "type": tx["type"],
                        "from_currency": tx["from_currency"],
                        "to_currency": tx["to_currency"],
                        "amount": float(tx["amount"]),
                        "rate_applied": float(tx["rate_applied"]) if tx["rate_applied"] else None,
                        "created_at": tx["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
                    })

                return jsonify({
                    "balance_vnd": balance_vnd,
                    "transactions": transactions
                }), 200
        except Exception as exc:
            _log("ERROR", "Failed to fetch balance", error=str(exc))
            return jsonify({"error": "internal_error", "message": str(exc)}), 500

    @app.route("/premium/fee", methods=["GET"])
    def premium_fee():
        """
        GET /premium/fee
        Returns the premium upgrade fee in VND.
        """
        try:
            fee = get_premium_fee_from_ssm()
            return jsonify({"premium_fee": float(fee)}), 200
        except Exception as exc:
            _log("ERROR", "Failed to fetch premium fee", error=str(exc))
            return jsonify({"error": "internal_error", "message": str(exc)}), 500

    @app.route("/exchange", methods=["POST"])
    def exchange():
        """
        POST /exchange

        Headers:
          Authorization: Bearer <JWT>
          Idempotency-Key: <UUID>

        Body:
          { "from_currency": "VND", "to_currency": "USD", "amount": 100000.0 }

        Responses:
          200: Transaction result (or cached result for duplicate key)
          400: Insufficient balance or invalid request
          401: Missing/invalid/expired JWT
          409: Optimistic lock conflict after 3 retries
          503: Exchange rate unavailable
        """
        verifier = _get_jwt_verifier()

        # ── Step 1: Extract and verify JWT ───────────────────────────────────
        try:
            token = verifier.extract_token_from_header(
                request.headers.get("Authorization")
            )
        except MissingTokenError:
            _log("WARN", "Missing Authorization header", path=request.path)
            return jsonify({
                "error": "missing_token",
                "message": "Authorization header required",
            }), 401

        try:
            claims = verifier.verify(token)
        except TokenExpiredError:
            _log("WARN", "Expired JWT token", path=request.path)
            return jsonify({
                "error": "token_expired",
                "message": "Token has expired",
            }), 401
        except InvalidTokenError as exc:
            _log("WARN", "Invalid JWT token", path=request.path, error=str(exc))
            return jsonify({
                "error": "invalid_token",
                "message": "Token is invalid",
            }), 401

        cognito_sub = claims.get("sub")
        if not cognito_sub:
            return jsonify({
                "error": "invalid_token",
                "message": "Token missing sub claim",
            }), 401

        # ── Step 2: Validate Idempotency-Key header ───────────────────────────
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            return jsonify({
                "error": "missing_idempotency_key",
                "message": "Idempotency-Key header is required",
            }), 400

        # Validate UUID format
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            return jsonify({
                "error": "invalid_idempotency_key",
                "message": "Idempotency-Key must be a valid UUID",
            }), 400

        # ── Step 3: Check Idempotency Cache ───────────────────────────────────
        idem_cache = _get_idempotency_cache()
        cached_result = idem_cache.get(idempotency_key)
        if cached_result is not None:
            _log("INFO", "Returning cached idempotency result",
                 idempotency_key=idempotency_key)
            return jsonify(cached_result), 200

        # ── Step 4: Validate request body ─────────────────────────────────────
        body = request.get_json(silent=True)
        if not body:
            return jsonify({
                "error": "invalid_request",
                "message": "Request body must be valid JSON",
            }), 400

        from_currency = str(body.get("from_currency", "")).strip().upper()
        to_currency = str(body.get("to_currency", "")).strip().upper()
        amount_raw = body.get("amount")

        if not from_currency or not to_currency:
            return jsonify({
                "error": "invalid_request",
                "message": "from_currency and to_currency are required",
            }), 400

        if from_currency != "VND":
            return jsonify({
                "error": "unsupported_exchange_direction",
                "message": "Only exchanges from VND are supported",
            }), 400

        if to_currency == "VND":
            return jsonify({
                "error": "invalid_request",
                "message": "to_currency must be different from VND",
            }), 400

        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except (InvalidOperation, ValueError, TypeError):
            return jsonify({
                "error": "invalid_request",
                "message": "amount must be a positive number",
            }), 400

        # ── Step 5: Read exchange rate from cache ─────────────────────────────
        rate_cache = _get_exchange_rate_cache()
        rate = rate_cache.get_rate(from_currency, to_currency)
        if rate is None:
            _log("WARN", "Exchange rate unavailable",
                 from_currency=from_currency, to_currency=to_currency)
            return jsonify({
                "error": "rate_unavailable",
                "message": f"Exchange rate for {from_currency}/{to_currency} is not available",
            }), 503

        # ── Step 6: Calculate VND cost and received amount ────────────────────
        # The wallet stores one VND balance only, so exchange always spends VND.
        vnd_cost = amount
        received_amount = float(amount) * rate

        # ── Step 7: Execute with optimistic locking (retry up to 3 times) ─────
        db = _get_db_client()
        last_error = None
        result = None
        for attempt in range(1, Config.MAX_LOCK_RETRIES + 1):
            try:
                result = execute_exchange(
                    db=db,
                    user_id=cognito_sub,
                    from_currency=from_currency,
                    to_currency=to_currency,
                    original_amount=amount,
                    vnd_cost=vnd_cost,
                    rate=rate,
                    received_amount=received_amount,
                    idempotency_key=idempotency_key,
                )
                break  # Success
            except InsufficientBalanceError:
                _log("WARN", "Insufficient balance",
                     cognito_sub=cognito_sub,
                     from_currency=from_currency,
                     to_currency=to_currency,
                     amount=float(amount))
                return jsonify({
                    "error": "insufficient_balance",
                    "message": "Insufficient balance for this exchange",
                }), 400
            except OptimisticLockConflictError as exc:
                last_error = exc
                _log("WARN", "Optimistic lock conflict, retrying",
                     attempt=attempt,
                     max_retries=Config.MAX_LOCK_RETRIES,
                     cognito_sub=cognito_sub)
                if attempt < Config.MAX_LOCK_RETRIES:
                    time.sleep(0.05 * attempt)  # Brief backoff
                continue
            except ValueError as exc:
                _log("WARN", "User not found", cognito_sub=cognito_sub, error=str(exc))
                return jsonify({
                    "error": "user_not_found",
                    "message": "User account not found",
                }), 404
            except Exception as exc:
                _log("ERROR", "Unexpected error during exchange",
                     error=str(exc), error_type=type(exc).__name__)
                return jsonify({
                    "error": "internal_error",
                    "message": "An internal error occurred",
                }), 500
        else:
            # All retries exhausted
            _log("ERROR", "Optimistic lock conflict after max retries",
                 cognito_sub=cognito_sub,
                 max_retries=Config.MAX_LOCK_RETRIES)
            return jsonify({
                "error": "conflict",
                "message": "Transaction conflict — please retry",
            }), 409

        # ── Step 8: Store result in Idempotency Cache ─────────────────────────
        try:
            idem_cache.set(idempotency_key, result)
        except Exception as exc:
            # Non-fatal: log but still return success
            _log("WARN", "Failed to store idempotency result",
                 idempotency_key=idempotency_key, error=str(exc))

        _log("INFO", "Exchange request completed",
             transaction_id=result.get("transaction_id"),
             cognito_sub=cognito_sub)

        return jsonify(result), 200

    @app.route("/topup", methods=["POST"])
    def topup():
        """
        POST /topup

        Headers:
          Authorization: Bearer <JWT>
          Idempotency-Key: <UUID>

        Body:
          { "amount": 100000.0 }  (amount in VND to credit)

        Responses:
          200: Transaction result (or cached result for duplicate key)
          400: Invalid amount or missing idempotency key
          401: Missing/invalid/expired JWT
          404: User not found
          409: Optimistic lock conflict after 3 retries
        """
        verifier = _get_jwt_verifier()

        # ── Step 1: Extract and verify JWT ───────────────────────────────────
        try:
            token = verifier.extract_token_from_header(
                request.headers.get("Authorization")
            )
        except MissingTokenError:
            _log("WARN", "Missing Authorization header", path=request.path)
            return jsonify({
                "error": "missing_token",
                "message": "Authorization header required",
            }), 401

        try:
            claims = verifier.verify(token)
        except TokenExpiredError:
            _log("WARN", "Expired JWT token", path=request.path)
            return jsonify({
                "error": "token_expired",
                "message": "Token has expired",
            }), 401
        except InvalidTokenError as exc:
            _log("WARN", "Invalid JWT token", path=request.path, error=str(exc))
            return jsonify({
                "error": "invalid_token",
                "message": "Token is invalid",
            }), 401

        cognito_sub = claims.get("sub")
        if not cognito_sub:
            return jsonify({
                "error": "invalid_token",
                "message": "Token missing sub claim",
            }), 401

        # ── Step 2: Validate Idempotency-Key header ───────────────────────────
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            return jsonify({
                "error": "missing_idempotency_key",
                "message": "Idempotency-Key header is required",
            }), 400

        # Validate UUID format
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            return jsonify({
                "error": "invalid_idempotency_key",
                "message": "Idempotency-Key must be a valid UUID",
            }), 400

        # ── Step 3: Check Idempotency Cache ───────────────────────────────────
        idem_cache = _get_idempotency_cache()
        cached_result = idem_cache.get(idempotency_key)
        if cached_result is not None:
            _log("INFO", "Returning cached idempotency result",
                 idempotency_key=idempotency_key)
            return jsonify(cached_result), 200

        # ── Step 4: Validate request body ─────────────────────────────────────
        body = request.get_json(silent=True)
        if not body:
            return jsonify({
                "error": "invalid_request",
                "message": "Request body must be valid JSON",
            }), 400

        amount_raw = body.get("amount")

        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except (InvalidOperation, ValueError, TypeError):
            return jsonify({
                "error": "invalid_request",
                "message": "amount must be a positive number",
            }), 400

        # ── Step 5: Execute with optimistic locking (retry up to 3 times) ─────
        db = _get_db_client()
        last_error = None
        result = None
        for attempt in range(1, Config.MAX_LOCK_RETRIES + 1):
            try:
                result = execute_topup(
                    db=db,
                    user_id=cognito_sub,
                    amount=amount,
                    idempotency_key=idempotency_key,
                )
                break  # Success
            except OptimisticLockConflictError as exc:
                last_error = exc
                _log("WARN", "Optimistic lock conflict, retrying",
                     attempt=attempt,
                     max_retries=Config.MAX_LOCK_RETRIES,
                     cognito_sub=cognito_sub)
                if attempt < Config.MAX_LOCK_RETRIES:
                    time.sleep(0.05 * attempt)  # Brief backoff
                continue
            except ValueError as exc:
                _log("WARN", "User not found", cognito_sub=cognito_sub, error=str(exc))
                return jsonify({
                    "error": "user_not_found",
                    "message": "User account not found",
                }), 404
            except Exception as exc:
                _log("ERROR", "Unexpected error during topup",
                     error=str(exc), error_type=type(exc).__name__)
                return jsonify({
                    "error": "internal_error",
                    "message": "An internal error occurred",
                }), 500
        else:
            # All retries exhausted
            _log("ERROR", "Optimistic lock conflict after max retries",
                 cognito_sub=cognito_sub,
                 max_retries=Config.MAX_LOCK_RETRIES)
            return jsonify({
                "error": "conflict",
                "message": "Transaction conflict — please retry",
            }), 409

        # ── Step 6: Store result in Idempotency Cache ─────────────────────────
        try:
            idem_cache.set(idempotency_key, result)
        except Exception as exc:
            # Non-fatal: log but still return success
            _log("WARN", "Failed to store idempotency result",
                 idempotency_key=idempotency_key, error=str(exc))

        _log("INFO", "Top-up request completed",
             transaction_id=result.get("transaction_id"),
             cognito_sub=cognito_sub)

        return jsonify(result), 200

    @app.route("/premium/upgrade", methods=["POST"])
    def premium_upgrade():
        """
        POST /premium/upgrade

        Upgrade the authenticated user to premium by deducting the premium fee
        from their balance and setting custom:premium = true in Cognito.

        Headers:
          Authorization: Bearer <JWT>
          Idempotency-Key: <UUID>

        Responses:
          200: Upgrade successful (or cached result for duplicate key)
          400: Insufficient balance or invalid request
          401: Missing/invalid/expired JWT
          402: premium_fee unavailable from Parameter Store
          404: User not found
          409: Optimistic lock conflict after 3 retries
        """
        verifier = _get_jwt_verifier()

        # ── Step 1: Extract and verify JWT ───────────────────────────────────
        try:
            token = verifier.extract_token_from_header(
                request.headers.get("Authorization")
            )
        except MissingTokenError:
            _log("WARN", "Missing Authorization header", path=request.path)
            return jsonify({
                "error": "missing_token",
                "message": "Authorization header required",
            }), 401

        try:
            claims = verifier.verify(token)
        except TokenExpiredError:
            _log("WARN", "Expired JWT token", path=request.path)
            return jsonify({
                "error": "token_expired",
                "message": "Token has expired",
            }), 401
        except InvalidTokenError as exc:
            _log("WARN", "Invalid JWT token", path=request.path, error=str(exc))
            return jsonify({
                "error": "invalid_token",
                "message": "Token is invalid",
            }), 401

        cognito_sub = claims.get("sub")
        if not cognito_sub:
            return jsonify({
                "error": "invalid_token",
                "message": "Token missing sub claim",
            }), 401

        # ── Step 2: Validate Idempotency-Key header ───────────────────────────
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            return jsonify({
                "error": "missing_idempotency_key",
                "message": "Idempotency-Key header is required",
            }), 400

        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            return jsonify({
                "error": "invalid_idempotency_key",
                "message": "Idempotency-Key must be a valid UUID",
            }), 400

        # ── Step 3: Check Idempotency Cache ───────────────────────────────────
        idem_cache = _get_idempotency_cache()
        cached_result = idem_cache.get(idempotency_key)
        if cached_result is not None:
            _log("INFO", "Returning cached idempotency result",
                 idempotency_key=idempotency_key)
            return jsonify(cached_result), 200

        # ── Step 4: Read premium_fee from AWS Parameter Store ─────────────────
        try:
            premium_fee = get_premium_fee_from_ssm()
        except ValueError as exc:
            _log("ERROR", "Cannot determine premium fee", error=str(exc))
            return jsonify({
                "error": "configuration_error",
                "message": "Premium fee configuration is unavailable",
            }), 503

        # ── Step 5: Execute balance deduction with optimistic locking ─────────
        db = _get_db_client()
        result = None
        for attempt in range(1, Config.MAX_LOCK_RETRIES + 1):
            try:
                result = execute_premium_upgrade(
                    db=db,
                    user_id=cognito_sub,
                    premium_fee=premium_fee,
                    idempotency_key=idempotency_key,
                )
                break  # Success
            except InsufficientBalanceError:
                _log("WARN", "Insufficient balance for premium upgrade",
                     cognito_sub=cognito_sub, premium_fee=float(premium_fee))
                return jsonify({
                    "error": "insufficient_balance",
                    "message": "Insufficient balance for premium upgrade",
                }), 400
            except AlreadyPremiumError:
                # Balance was already deducted — idempotency at DB level.
                # Treat as success: Cognito update may still be pending.
                _log("INFO", "Premium fee already deducted, skipping DB step",
                     cognito_sub=cognito_sub)
                # Fall through to Cognito update below with a synthetic result
                result = {
                    "type": "premium_upgrade",
                    "message": "Premium fee already deducted",
                    "idempotency_key": idempotency_key,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                break
            except OptimisticLockConflictError as exc:
                _log("WARN", "Optimistic lock conflict, retrying",
                     attempt=attempt,
                     max_retries=Config.MAX_LOCK_RETRIES,
                     cognito_sub=cognito_sub)
                if attempt < Config.MAX_LOCK_RETRIES:
                    time.sleep(0.05 * attempt)
                continue
            except ValueError as exc:
                _log("WARN", "User not found", cognito_sub=cognito_sub, error=str(exc))
                return jsonify({
                    "error": "user_not_found",
                    "message": "User account not found",
                }), 404
            except Exception as exc:
                _log("ERROR", "Unexpected error during premium upgrade",
                     error=str(exc), error_type=type(exc).__name__)
                return jsonify({
                    "error": "internal_error",
                    "message": "An internal error occurred",
                }), 500
        else:
            # All retries exhausted
            _log("ERROR", "Optimistic lock conflict after max retries",
                 cognito_sub=cognito_sub,
                 max_retries=Config.MAX_LOCK_RETRIES)
            return jsonify({
                "error": "conflict",
                "message": "Transaction conflict — please retry",
            }), 409

        # ── Step 6: Call Cognito Admin API to set custom:premium = true ────────
        # Balance has been deducted. Even if Cognito fails, we return success
        # and let the reconciliation job retry the Cognito update.
        try:
            update_cognito_premium_attribute(cognito_sub)
            # Cognito succeeded — clear the reconciliation flag
            try:
                mark_cognito_update_complete(db, cognito_sub)
            except Exception as exc:
                # Non-fatal: flag will be cleared on next reconciliation cycle
                _log("WARN", "Failed to clear premium_deducted flag",
                     cognito_sub=cognito_sub, error=str(exc))
        except Exception as exc:
            # Cognito failed AFTER balance was deducted.
            # Log the inconsistency — reconciliation job will retry.
            _log("ERROR",
                 "Cognito update failed after balance deduction — reconciliation required",
                 cognito_sub=cognito_sub,
                 error=str(exc),
                 premium_deducted=True)
            # Do NOT return an error — money was taken, upgrade will be completed
            # by the reconciliation job.

        # ── Step 7: Store result in Idempotency Cache ─────────────────────────
        try:
            idem_cache.set(idempotency_key, result)
        except Exception as exc:
            _log("WARN", "Failed to store idempotency result",
                 idempotency_key=idempotency_key, error=str(exc))

        _log("INFO", "Premium upgrade request completed",
             transaction_id=result.get("transaction_id"),
             cognito_sub=cognito_sub)

        return jsonify(result), 200

    return app


# ── Entry Point ───────────────────────────────────────────────────────────────


def main() -> int:
    _log("INFO", "Money Service starting")

    try:
        Config.validate()
    except ValueError as exc:
        _log("ERROR", "Configuration validation failed", error=str(exc))
        return 1

    # Start background cleanup job
    try:
        idem_cache = IdempotencyCache()
        cleanup_job = IdempotencyCleanupJob(idem_cache)
        cleanup_job.start()
    except Exception as exc:
        _log("WARN", "Failed to start idempotency cleanup job", error=str(exc))

    # Start premium reconciliation job
    try:
        db_for_reconciliation = DatabaseClient()
        reconciliation_job = PremiumReconciliationJob(db_for_reconciliation)
        reconciliation_job.start()
    except Exception as exc:
        _log("WARN", "Failed to start premium reconciliation job", error=str(exc))

    app = create_app()

    _log("INFO", "Money Service listening",
         port=Config.PORT,
         cognito_user_pool_id=Config.COGNITO_USER_POOL_ID)

    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
