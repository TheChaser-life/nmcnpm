# Forecast Service

Service ECS cung cấp REST API dự báo tỉ giá tiền tệ cho Premium Users. Xác thực JWT từ Cognito, kiểm tra `custom:premium` claim, và gọi SageMaker Endpoint để lấy kết quả dự báo.

## Kiến trúc

```
Frontend (Premium_User)
        │  (HTTP GET /forecast/{currency_code}, Authorization: Bearer <JWT>)
Forecast Service (ECS, Private Subnet)
        │  (verify JWT: custom:premium = true)
        │  (if JWT missing/expired/invalid → HTTP 401)
        │  (if not premium → HTTP 403)
SageMaker Endpoint (Private Subnet via Interface Endpoint)
        │  (inference result)
Forecast Service
        │  (HTTP 200 + forecast data)
Frontend
```

**Deployment:** ECS Fargate trong Private Subnet (truy cập qua ALB)  
**JWT Verification:** JWKS public keys từ Cognito (cached 24h, thread-safe)  
**SageMaker:** Truy cập qua VPC Interface Endpoint (traffic không ra internet)

---

## Cấu trúc thư mục

```
services/forecast-service/
├── forecast_service.py          # Main service code
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable template
├── Dockerfile                   # Multi-stage Docker build
├── .dockerignore                # Docker build exclusions
├── README.md                    # This file
└── tests/
    ├── __init__.py
    ├── test_forecast_service.py # Unit tests
    └── test_integration.py      # Integration tests
```

---

## Cài đặt và chạy local

### 1. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 2. Cấu hình environment variables

```bash
cp .env.example .env
# Chỉnh sửa .env với các giá trị thực tế
```

### 3. Chạy service

```bash
python forecast_service.py
```

Service sẽ lắng nghe trên port `8080` (hoặc giá trị `PORT` env var).

---

## API Endpoints

### `GET /health`

Health check endpoint.

**Response:**
```json
{"status": "ok"}
```

### `GET /forecast/{currency_code}`

Lấy dự báo tỉ giá cho một loại tiền tệ.

**Headers:**
- `Authorization: Bearer <JWT>` — JWT id_token từ Cognito (bắt buộc)

**Path Parameters:**
- `currency_code` — Mã tiền tệ ISO 4217 (ví dụ: `USD`, `EUR`)

**Responses:**

| Status | Mô tả |
|--------|-------|
| `200` | Forecast data từ SageMaker |
| `401` | JWT thiếu, hết hạn, hoặc không hợp lệ |
| `403` | JWT hợp lệ nhưng `custom:premium != true` |
| `503` | SageMaker Endpoint không khả dụng |

**200 Response Example:**
```json
{
  "currency_code": "USD",
  "forecast": [0.000043, 0.000044, 0.000042],
  "model_version": "v1.2.3"
}
```

**401 Response Examples:**
```json
{"error": "missing_token", "message": "Authorization header required"}
{"error": "token_expired", "message": "Token has expired"}
{"error": "invalid_token", "message": "Token is invalid"}
```

**403 Response:**
```json
{"error": "forbidden", "message": "Premium subscription required"}
```

**503 Response:**
```json
{"error": "service_unavailable", "message": "Forecast service temporarily unavailable"}
```

---

## Environment Variables

| Variable | Mô tả | Mặc định |
|---|---|---|
| `PORT` | Port service lắng nghe | `8080` |
| `AWS_REGION` | AWS region | `ap-southeast-1` |
| `SAGEMAKER_ENDPOINT_NAME` | Tên SageMaker Endpoint | `forecast-endpoint` |
| `COGNITO_USER_POOL_ID` | Cognito User Pool ID | _(bắt buộc)_ |
| `COGNITO_REGION` | Region của Cognito User Pool | `ap-southeast-1` |
| `JWKS_CACHE_TTL_SECONDS` | TTL cache JWKS public keys (giây) | `86400` |

---

## JWT Verification

Service xác thực JWT theo quy trình:

1. Extract `Authorization: Bearer <token>` header
2. Decode JWT header để lấy `kid` (key ID)
3. Fetch JWKS từ Cognito: `https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json`
4. Tìm public key khớp với `kid`
5. Verify signature, expiry, issuer
6. Extract `custom:premium` claim từ payload

**JWKS Cache:** Public keys được cache trong memory với TTL 24h (thread-safe). Tự động refresh khi hết hạn hoặc khi `kid` không tìm thấy.

---

## Logging

Service emit structured JSON logs ra stdout (CloudWatch Logs):

```json
{
  "level": "INFO",
  "message": "Forecast request completed successfully",
  "service": "forecast-service",
  "currency_code": "USD"
}
```

---

## Chạy tests

```bash
# Unit tests
python -m pytest tests/test_forecast_service.py -v

# Integration tests
python -m pytest tests/test_integration.py -v

# Tất cả tests
python -m pytest tests/ -v
```

---

## Deployment (ECS Fargate)

Service được containerize bằng Dockerfile và deploy lên ECS Fargate:

- **Private Subnet**: Không expose trực tiếp ra internet
- **ALB**: Nhận traffic từ ALB (port 8080)
- **desired_count = 2**: Multi-AZ deployment
- **Secrets**: Không có secrets trực tiếp (JWT verification dùng public keys)
- **IAM Task Role**: `Forecast_Exchange_Rate_Task_Role` với quyền `sagemaker:InvokeEndpoint`

---

## Security

- JWT verification sử dụng RSA public keys (không cần round-trip đến Cognito)
- SageMaker Endpoint truy cập qua VPC Interface Endpoint (traffic không ra internet)
- Container chạy với non-root user (`appuser`, uid/gid 1001)
- `custom:premium` claim phải là boolean `true` (không phải string `"true"`)
