"""
Forecast Service — ECS Service

Cung cấp REST API dự báo tỉ giá tiền tệ cho Premium Users.
Xác thực JWT từ Cognito, kiểm tra custom:premium claim, gọi SageMaker Endpoint.

Deployment: ECS Fargate trong Private Subnet (truy cập qua ALB)
JWT Verification: JWKS public keys từ Cognito (cached 24h)
SageMaker: Truy cập qua VPC Interface Endpoint
"""

import json
import os
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple

import boto3
import botocore.exceptions
from botocore.config import Config as BotoConfig
import jwt
import requests
from flask import Flask, jsonify, request
from jwt.algorithms import RSAAlgorithm

# ── Logging ──────────────────────────────────────────────────────────────────


def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout (CloudWatch Logs)."""
    entry = {
        "level": level,
        "message": message,
        "service": "forecast-service",
        **kwargs,
    }
    print(json.dumps(entry, default=str), flush=True)


# ── Configuration ─────────────────────────────────────────────────────────────


class Config:
    """Configuration loaded from environment variables."""

    PORT: int = int(os.environ.get("PORT", "8080"))
    AWS_REGION: str = os.environ.get("AWS_REGION", "ap-southeast-2")
    SAGEMAKER_ENDPOINT_NAME: str = os.environ.get("SAGEMAKER_ENDPOINT_NAME", "forecast-endpoint")
    SAGEMAKER_CONNECT_TIMEOUT_SECONDS: int = int(os.environ.get("SAGEMAKER_CONNECT_TIMEOUT_SECONDS", "3"))
    SAGEMAKER_READ_TIMEOUT_SECONDS: int = int(os.environ.get("SAGEMAKER_READ_TIMEOUT_SECONDS", "8"))
    COGNITO_USER_POOL_ID: str = os.environ.get("COGNITO_USER_POOL_ID", "")
    COGNITO_REGION: str = os.environ.get("COGNITO_REGION", "ap-southeast-2")
    JWKS_CACHE_TTL_SECONDS: int = int(os.environ.get("JWKS_CACHE_TTL_SECONDS", "86400"))

    @classmethod
    def get_jwks_url(cls) -> str:
        """Build the Cognito JWKS URL from config."""
        return (
            f"https://cognito-idp.{cls.COGNITO_REGION}.amazonaws.com"
            f"/{cls.COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        )

    @classmethod
    def get_issuer(cls) -> str:
        """Build the expected JWT issuer URL."""
        return (
            f"https://cognito-idp.{cls.COGNITO_REGION}.amazonaws.com"
            f"/{cls.COGNITO_USER_POOL_ID}"
        )

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.COGNITO_USER_POOL_ID:
            raise ValueError("COGNITO_USER_POOL_ID environment variable is required")
        if not cls.SAGEMAKER_ENDPOINT_NAME:
            raise ValueError("SAGEMAKER_ENDPOINT_NAME environment variable is required")


# ── JWKS Cache ────────────────────────────────────────────────────────────────


class JWKSCache:
    """
    Thread-safe in-memory cache for Cognito JWKS public keys.

    Fetches JWKS from Cognito on first request and refreshes every
    JWKS_CACHE_TTL_SECONDS (default 86400 = 24 hours).
    """

    def __init__(self, jwks_url: str, ttl_seconds: int = 86400):
        self._jwks_url = jwks_url
        self._ttl_seconds = ttl_seconds
        self._keys: Dict[str, Any] = {}  # kid → public key object
        self._fetched_at: Optional[float] = None
        self._lock = threading.Lock()

    def _is_expired(self) -> bool:
        """Return True if the cache is empty or older than TTL."""
        if self._fetched_at is None:
            return True
        return (time.time() - self._fetched_at) >= self._ttl_seconds

    def _fetch_and_cache(self) -> None:
        """Fetch JWKS from Cognito and populate the key cache."""
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
        """
        Return the public key for the given key ID.

        Refreshes the cache if expired or if the kid is not found.

        Args:
            kid: The key ID from the JWT header.

        Returns:
            The RSA public key object, or None if not found.
        """
        with self._lock:
            if self._is_expired():
                self._fetch_and_cache()

            if kid not in self._keys:
                # Try refreshing once in case a new key was added
                _log("INFO", "Key ID not found in cache, refreshing", kid=kid)
                self._fetch_and_cache()

            return self._keys.get(kid)


# ── JWT Verification ──────────────────────────────────────────────────────────


class JWTVerificationError(Exception):
    """Base class for JWT verification errors."""
    pass


class MissingTokenError(JWTVerificationError):
    """Raised when the Authorization header is missing."""
    pass


class TokenExpiredError(JWTVerificationError):
    """Raised when the JWT has expired."""
    pass


class InvalidTokenError(JWTVerificationError):
    """Raised when the JWT signature or format is invalid."""
    pass


class PremiumRequiredError(Exception):
    """Raised when the JWT is valid but custom:premium != true."""
    pass


class JWTVerifier:
    """
    Verifies Cognito JWTs and extracts claims.

    Uses JWKS public keys (cached) to verify signature, expiry, and issuer.
    Extracts the custom:premium claim to enforce premium access control.
    """

    def __init__(self, jwks_cache: JWKSCache, issuer: str):
        self._jwks_cache = jwks_cache
        self._issuer = issuer

    def verify(self, token: str) -> Dict[str, Any]:
        """
        Verify a JWT and return its claims.

        Args:
            token: The raw JWT string (without "Bearer " prefix).

        Returns:
            Dict of JWT claims if verification succeeds.

        Raises:
            TokenExpiredError: If the token has expired.
            InvalidTokenError: If the token signature or format is invalid.
        """
        try:
            # Decode header to get kid without verifying signature
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            if not kid:
                raise InvalidTokenError("JWT header missing 'kid' field")

            # Get the matching public key from cache
            public_key = self._jwks_cache.get_public_key(kid)
            if public_key is None:
                raise InvalidTokenError(f"No public key found for kid: {kid}")

            # Verify and decode the JWT
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": False,
                },
            )
            return claims

        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError(f"Token is invalid: {exc}")

    def extract_token_from_header(self, authorization_header: Optional[str]) -> str:
        """
        Extract the JWT from the Authorization header.

        Args:
            authorization_header: The value of the Authorization header.

        Returns:
            The raw JWT string.

        Raises:
            MissingTokenError: If the header is missing or malformed.
        """
        if not authorization_header:
            raise MissingTokenError("Authorization header required")

        parts = authorization_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise MissingTokenError("Authorization header required")

        return parts[1]

    def check_premium(self, claims: Dict[str, Any]) -> None:
        """
        Check that the JWT claims include custom:premium = true.

        Args:
            claims: The decoded JWT claims dict.

        Raises:
            PremiumRequiredError: If custom:premium is not true.
        """
        premium_value = claims.get("custom:premium")
        if premium_value is not True and premium_value != "true":
            raise PremiumRequiredError(
                f"Premium subscription required (custom:premium={premium_value!r})"
            )


# ── SageMaker Client ──────────────────────────────────────────────────────────


class SageMakerClient:
    """Client for invoking the SageMaker forecast endpoint."""

    def __init__(self, endpoint_name: str, region: str):
        self._endpoint_name = endpoint_name
        self._client = boto3.client(
            "sagemaker-runtime",
            region_name=region,
            config=BotoConfig(
                connect_timeout=Config.SAGEMAKER_CONNECT_TIMEOUT_SECONDS,
                read_timeout=Config.SAGEMAKER_READ_TIMEOUT_SECONDS,
                retries={"max_attempts": 1},
            ),
        )
        _log(
            "INFO",
            "SageMaker client initialized",
            endpoint=endpoint_name,
            region=region,
            connect_timeout=Config.SAGEMAKER_CONNECT_TIMEOUT_SECONDS,
            read_timeout=Config.SAGEMAKER_READ_TIMEOUT_SECONDS,
        )

    def invoke(self, currency_code: str) -> Dict[str, Any]:
        """
        Invoke the SageMaker endpoint with the given currency code.

        Args:
            currency_code: The ISO 4217 currency code to forecast.

        Returns:
            Parsed JSON response from SageMaker.

        Raises:
            botocore.exceptions.ClientError: If the endpoint is unavailable.
        """
        payload = json.dumps({"currency_code": currency_code})

        _log("INFO", "Invoking SageMaker endpoint",
             endpoint=self._endpoint_name, currency_code=currency_code)

        response = self._client.invoke_endpoint(
            EndpointName=self._endpoint_name,
            ContentType="application/json",
            Body=payload,
        )

        result_body = response["Body"].read()
        result = json.loads(result_body)

        _log("INFO", "SageMaker endpoint responded",
             endpoint=self._endpoint_name, currency_code=currency_code)

        return result


# ── Flask Application ─────────────────────────────────────────────────────────


def create_app(
    jwks_cache: Optional[JWKSCache] = None,
    jwt_verifier: Optional[JWTVerifier] = None,
    sagemaker_client: Optional[SageMakerClient] = None,
) -> Flask:
    """
    Create and configure the Flask application.

    Accepts optional dependency injection for testing.
    """
    app = Flask(__name__)

    # Use provided dependencies or create defaults
    _jwks_cache = jwks_cache or JWKSCache(
        jwks_url=Config.get_jwks_url(),
        ttl_seconds=Config.JWKS_CACHE_TTL_SECONDS,
    )
    _jwt_verifier = jwt_verifier or JWTVerifier(
        jwks_cache=_jwks_cache,
        issuer=Config.get_issuer(),
    )
    _sagemaker_client = sagemaker_client or SageMakerClient(
        endpoint_name=Config.SAGEMAKER_ENDPOINT_NAME,
        region=Config.AWS_REGION,
    )

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok"}), 200

    @app.route("/forecast/<string:currency_code>", methods=["GET"])
    def forecast(currency_code: str):
        """
        GET /forecast/{currency_code}

        Returns ML forecast for the given currency code.
        Requires a valid premium JWT in the Authorization header.

        Responses:
            200: Forecast data
            401: Missing/expired/invalid JWT
            403: Valid JWT but not premium
            503: SageMaker endpoint unavailable
        """
        # ── Step 1: Extract JWT from Authorization header ─────────────────
        try:
            token = _jwt_verifier.extract_token_from_header(
                request.headers.get("Authorization")
            )
        except MissingTokenError:
            _log("WARN", "Missing Authorization header",
                 path=request.path, method=request.method)
            return jsonify({
                "error": "missing_token",
                "message": "Authorization header required",
            }), 401

        # ── Step 2: Verify JWT ────────────────────────────────────────────
        try:
            claims = _jwt_verifier.verify(token)
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

        # ── Step 3: Check premium claim ───────────────────────────────────
        try:
            _jwt_verifier.check_premium(claims)
        except PremiumRequiredError:
            _log("WARN", "Non-premium user attempted forecast access",
                 path=request.path,
                 premium_value=claims.get("custom:premium"))
            return jsonify({
                "error": "forbidden",
                "message": "Premium subscription required",
            }), 403

        # ── Step 4: Call SageMaker Endpoint ───────────────────────────────
        try:
            result = _sagemaker_client.invoke(currency_code)
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            _log("ERROR", "SageMaker endpoint unavailable",
                 endpoint=Config.SAGEMAKER_ENDPOINT_NAME,
                 currency_code=currency_code,
                 error_code=error_code,
                 error=str(exc),
                 timestamp=time.time())
            return jsonify({
                "error": "service_unavailable",
                "message": "Forecast service temporarily unavailable",
            }), 503
        except Exception as exc:
            _log("ERROR", "Unexpected error calling SageMaker",
                 endpoint=Config.SAGEMAKER_ENDPOINT_NAME,
                 currency_code=currency_code,
                 error=str(exc),
                 error_type=type(exc).__name__,
                 timestamp=time.time())
            return jsonify({
                "error": "service_unavailable",
                "message": "Forecast service temporarily unavailable",
            }), 503

        # ── Step 5: Return forecast result ────────────────────────────────
        _log("INFO", "Forecast request completed successfully",
             currency_code=currency_code)
        return jsonify(result), 200

    return app


# ── Entry Point ───────────────────────────────────────────────────────────────


def main() -> int:
    """Entry point for the service."""
    _log("INFO", "Forecast Service starting")

    try:
        Config.validate()
    except ValueError as exc:
        _log("ERROR", "Configuration validation failed", error=str(exc))
        return 1

    app = create_app()

    _log("INFO", "Forecast Service listening",
         port=Config.PORT,
         sagemaker_endpoint=Config.SAGEMAKER_ENDPOINT_NAME,
         cognito_user_pool_id=Config.COGNITO_USER_POOL_ID)

    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
