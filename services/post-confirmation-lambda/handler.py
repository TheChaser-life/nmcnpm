"""
Post-Confirmation Lambda — Cognito trigger

Được gọi tự động sau khi user xác nhận email thành công.
Nhiệm vụ: INSERT user mới vào bảng `users` với balance=0.

Cognito trigger contract: Lambda PHẢI trả về event object không thay đổi.
Nếu Lambda raise exception, Cognito sẽ rollback confirmation — đảm bảo
User_DB và Cognito luôn đồng bộ.
"""

import json
import logging
import os

import boto3
import psycopg2
from botocore.exceptions import ClientError

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _log(level: str, message: str, **kwargs) -> None:
    """Emit structured JSON log entry to stdout (CloudWatch Logs)."""
    entry = {"level": level, "message": message, **kwargs}
    print(json.dumps(entry, default=str))


# ── Secrets Manager ───────────────────────────────────────────────────────────

def _get_db_credentials(secret_arn: str) -> dict:
    """
    Lấy DB credentials từ AWS Secrets Manager.

    Secret format mong đợi:
        {"username": "...", "password": "..."}

    Returns:
        dict với keys 'username' và 'password'

    Raises:
        RuntimeError nếu không lấy được secret
    """
    client = boto3.client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=secret_arn)
    except ClientError as exc:
        _log("ERROR", "Không thể lấy DB credentials từ Secrets Manager",
             secret_arn=secret_arn, error=str(exc))
        raise RuntimeError(f"Secrets Manager error: {exc}") from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError("SecretString rỗng — kiểm tra lại secret format")

    try:
        return json.loads(secret_string)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Secret không phải JSON hợp lệ: {exc}") from exc


# ── Database ──────────────────────────────────────────────────────────────────

def _get_db_connection(credentials: dict):
    """
    Tạo kết nối psycopg2 đến RDS PostgreSQL.

    Đọc host/port/dbname từ environment variables:
        DB_HOST  — RDS endpoint hostname
        DB_PORT  — RDS port (mặc định 5432)
        DB_NAME  — tên database

    Returns:
        psycopg2 connection object
    """
    host = os.environ["DB_HOST"]
    port = int(os.environ.get("DB_PORT", "5432"))
    dbname = os.environ["DB_NAME"]
    username = credentials["username"]
    password = credentials["password"]

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=username,
        password=password,
        connect_timeout=5,
        sslmode="require",          # RDS yêu cầu SSL
    )


def _insert_user(conn, cognito_sub: str, email: str) -> bool:
    """
    INSERT user mới vào bảng `users`.

    Sử dụng ON CONFLICT DO NOTHING để đảm bảo idempotency:
    nếu Lambda được gọi lại (retry), không bị lỗi duplicate key.

    Returns:
        True  — row mới được INSERT
        False — row đã tồn tại (conflict, bỏ qua)
    """
    sql = """
        INSERT INTO users (cognito_sub, email, balance, version)
        VALUES (%s, %s, 0, 0)
        ON CONFLICT (cognito_sub) DO NOTHING
    """
    with conn.cursor() as cur:
        cur.execute(sql, (cognito_sub, email))
        inserted = cur.rowcount  # 1 nếu INSERT thành công, 0 nếu conflict
    conn.commit()
    return inserted == 1


# ── Lambda Handler ────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """
    Entry point của Lambda — Cognito Post-Confirmation trigger.

    Event structure (Cognito PostConfirmation_ConfirmSignUp):
    {
        "version": "1",
        "triggerSource": "PostConfirmation_ConfirmSignUp",
        "region": "ap-southeast-2",
        "userPoolId": "ap-southeast-2_XXXXXXXXX",
        "userName": "<cognito_sub>",          ← dùng làm cognito_sub
        "request": {
            "userAttributes": {
                "email": "user@example.com",
                ...
            }
        },
        "response": {}
    }

    Lambda PHẢI trả về event không thay đổi (Cognito trigger contract).
    Nếu raise exception, Cognito rollback confirmation.
    """
    _log("INFO", "Post-Confirmation Lambda bắt đầu xử lý",
         trigger_source=event.get("triggerSource"),
         user_pool_id=event.get("userPoolId"),
         username=event.get("userName"))

    # ── 1. Trích xuất thông tin từ event ──────────────────────────────────────
    try:
        cognito_sub = event["userName"]
        email = event["request"]["userAttributes"]["email"]
    except KeyError as exc:
        _log("ERROR", "Event thiếu trường bắt buộc", missing_key=str(exc),
             event=event)
        raise RuntimeError(f"Event không hợp lệ — thiếu trường: {exc}") from exc

    _log("INFO", "Trích xuất thông tin user thành công",
         cognito_sub=cognito_sub, email=email)

    # ── 2. Lấy DB credentials từ Secrets Manager ──────────────────────────────
    secret_arn = os.environ["DB_SECRET_ARN"]
    credentials = _get_db_credentials(secret_arn)

    # ── 3. Kết nối DB và INSERT user ──────────────────────────────────────────
    conn = None
    try:
        conn = _get_db_connection(credentials)
        inserted = _insert_user(conn, cognito_sub, email)

        if inserted:
            _log("INFO", "INSERT user thành công",
                 cognito_sub=cognito_sub, email=email)
        else:
            # Đây là retry — user đã tồn tại, không phải lỗi
            _log("INFO", "User đã tồn tại (idempotent retry), bỏ qua INSERT",
                 cognito_sub=cognito_sub, email=email)

    except psycopg2.Error as exc:
        _log("ERROR", "Lỗi database khi INSERT user",
             cognito_sub=cognito_sub, email=email,
             pg_error=str(exc), pg_code=exc.pgcode if hasattr(exc, "pgcode") else None)
        raise RuntimeError(f"Database error: {exc}") from exc

    except Exception as exc:
        _log("ERROR", "Lỗi không xác định",
             cognito_sub=cognito_sub, email=email, error=str(exc))
        raise

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass  # ignore close errors

    # ── 4. Trả về event không thay đổi (Cognito trigger contract) ─────────────
    _log("INFO", "Post-Confirmation Lambda hoàn thành",
         cognito_sub=cognito_sub, email=email)
    return event
