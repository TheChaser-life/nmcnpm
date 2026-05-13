# Money Service

Service ECS cung cấp REST API xử lý trao đổi tiền tệ (POST /exchange) và nạp tiền (POST /topup) với idempotency và optimistic locking.

## Kiến trúc

```
Frontend (Authenticated_User)
        │  (HTTP POST /exchange hoặc /topup, Authorization: Bearer <JWT>, Idempotency-Key: <UUID>)
Money Service (ECS, Private Subnet)
        │  (verify JWT từ Cognito)
        │  (check idempotency key → Idempotency Cache Redis)
        │  (get exchange rate → Exchange Rate Cache Redis)
        │  (execute transaction với optimistic locking → RDS PostgreSQL)
        │  (store result → Idempotency Cache Redis)
        │  (HTTP 200 + transaction result)
Frontend
```

**Deployment:** ECS Fargate trong Private Subnet (truy cập qua ALB)  
**JWT Verification:** JWKS public keys từ Cognito (cached 24h, thread-safe)  
**Idempotency:** ElastiCache Redis (noeviction policy)  
**Exchange Rate:** ElastiCache Redis (volatile-lru policy)  
**Database:** RDS PostgreSQL (optimistic locking via version column)

---

## Cấu trúc thư mục

```
services/money-service/
├── money_service.py     # Main service code
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── Dockerfile           # Multi-stage Docker build
├── .dockerignore        # Docker build exclusions
├── README.md            # This file
└── tests/
    └── ...              # Unit tests
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
python money_service.py
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

### `POST /exchange`

Trao đổi tiền tệ.

**Headers:**
- `Authorization: Bearer <JWT>` — JWT id_token từ Cognito (bắt buộc)
- `Idempotency-Key: <UUID>` — UUID để đảm bảo idempotency (bắt buộc)

**Request Body:**
```json
{
  "from_currency": "USD",
  "to_currency": "EUR",
  "amount": 100.0
}
```

**Responses:**

| Status | Mô tả |
|--------|-------|
| `200` | Transaction thành công (hoặc kết quả cached cho duplicate key) |
| `400` | Số dư không đủ hoặc request không hợp lệ |
| `401` | JWT thiếu, hết hạn, hoặc không hợp lệ |
| `409` | Optimistic lock conflict sau 3 lần retry |
| `503` | Tỉ giá không khả dụng |

**200 Response Example:**
```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "abc123",
  "type": "exchange",
  "from_currency": "USD",
  "to_currency": "EUR",
  "amount": 100.0,
  "rate_applied": 0.92,
  "received_amount": 92.0,
  "new_balance_vnd": 4500000.0,
  "idempotency_key": "your-uuid-here",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### `POST /topup`

Nạp tiền VND vào tài khoản (simulated).

**Headers:**
- `Authorization: Bearer <JWT>` — JWT id_token từ Cognito (bắt buộc)
- `Idempotency-Key: <UUID>` — UUID để đảm bảo idempotency (bắt buộc)

**Request Body:**
```json
{
  "amount": 1000000
}
```

**Responses:**

| Status | Mô tả |
|--------|-------|
| `200` | Top-up thành công (hoặc kết quả cached cho duplicate key) |
| `400` | Request không hợp lệ |
| `401` | JWT thiếu, hết hạn, hoặc không hợp lệ |
| `409` | Optimistic lock conflict sau 3 lần retry |

---

## Environment Variables

| Variable | Mô tả | Mặc định |
|---|---|---|
| `PORT` | Port service lắng nghe | `8080` |
| `AWS_REGION` | AWS region | `ap-southeast-1` |
| `COGNITO_USER_POOL_ID` | Cognito User Pool ID | _(bắt buộc)_ |
| `COGNITO_REGION` | Region của Cognito User Pool | `ap-southeast-1` |
| `JWKS_CACHE_TTL_SECONDS` | TTL cache JWKS public keys (giây) | `86400` |
| `DB_HOST` | RDS instance endpoint | _(bắt buộc)_ |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | `currency_exchange` |
| `DB_USER` | Database user | `postgres` |
| `DB_PASSWORD` | Database password | _(bắt buộc)_ |
| `EXCHANGE_RATE_REDIS_HOST` | ElastiCache endpoint cho exchange rate | _(bắt buộc)_ |
| `EXCHANGE_RATE_REDIS_PORT` | Redis port | `6379` |
| `EXCHANGE_RATE_REDIS_PASSWORD` | Redis AUTH password | _(trống)_ |
| `EXCHANGE_RATE_REDIS_SSL` | Bật TLS cho Redis connection | `true` |
| `IDEMPOTENCY_REDIS_HOST` | ElastiCache endpoint cho idempotency | _(bắt buộc)_ |
| `IDEMPOTENCY_REDIS_PORT` | Redis port | `6379` |
| `IDEMPOTENCY_REDIS_PASSWORD` | Redis AUTH password | _(trống)_ |
| `IDEMPOTENCY_REDIS_SSL` | Bật TLS cho Redis connection | `true` |
| `MAX_LOCK_RETRIES` | Số lần retry khi optimistic lock conflict | `3` |
| `CLEANUP_INTERVAL_SECONDS` | Tần suất chạy cleanup job (giây) | `86400` |
| `IDEMPOTENCY_TTL_DAYS` | Tuổi tối đa của idempotency keys (ngày) | `7` |

---

## Chạy tests

```bash
# Unit tests
python -m pytest tests/ -v
```

---

## Build Docker Image

```bash
# Build image locally
docker build -t money-service:latest .

# Chạy container locally (với .env file)
docker run --env-file .env -p 8080:8080 money-service:latest
```

---

## Deployment lên ECR

### Yêu cầu

- AWS CLI đã cài đặt và cấu hình (`aws configure`)
- Docker đang chạy
- Quyền truy cập ECR repository

### Các bước push image lên ECR

#### 1. Lấy thông tin ECR registry

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=ap-southeast-1
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPOSITORY="money-service"
IMAGE_TAG="latest"
```

#### 2. Đăng nhập vào ECR

```bash
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_REGISTRY}
```

#### 3. Build Docker image

```bash
docker build -t ${ECR_REPOSITORY}:${IMAGE_TAG} .
```

#### 4. Tag image với ECR URI

```bash
docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} \
  ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}
```

#### 5. Push image lên ECR

```bash
docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}
```

#### 6. (Tùy chọn) Tag với commit SHA để versioning

```bash
GIT_SHA=$(git rev-parse --short HEAD)

docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} \
  ${ECR_REGISTRY}/${ECR_REPOSITORY}:${GIT_SHA}

docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:${GIT_SHA}
```

### Script tổng hợp (one-liner)

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text) && \
AWS_REGION=ap-southeast-1 && \
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com" && \
ECR_REPOSITORY="money-service" && \
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY} && \
docker build -t ${ECR_REPOSITORY}:latest . && \
docker tag ${ECR_REPOSITORY}:latest ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest && \
docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest
```

---

## Deployment (ECS Fargate)

Service được containerize bằng Dockerfile và deploy lên ECS Fargate:

- **Private Subnet**: Không expose trực tiếp ra internet
- **ALB**: Nhận traffic từ ALB (port 8080)
- **desired_count = 2**: Multi-AZ deployment
- **Secrets**: `DB_PASSWORD`, `EXCHANGE_RATE_REDIS_PASSWORD`, `IDEMPOTENCY_REDIS_PASSWORD` được inject từ AWS Secrets Manager
- **IAM Task Role**: `Money_Service_Task_Role` với quyền đọc Secrets Manager

---

## Security

- JWT verification sử dụng RSA public keys (không cần round-trip đến Cognito)
- Idempotency key ngăn chặn duplicate transactions
- Optimistic locking ngăn chặn race conditions trên balance
- Container chạy với non-root user (`appuser`, uid/gid 1001)
- RDS connection sử dụng SSL (`sslmode=require`)
- Redis connections sử dụng TLS

---

## Logging

Service emit structured JSON logs ra stdout (CloudWatch Logs):

```json
{
  "level": "INFO",
  "message": "Exchange transaction committed",
  "service": "money-service",
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "abc123",
  "from_currency": "USD",
  "to_currency": "EUR"
}
```
