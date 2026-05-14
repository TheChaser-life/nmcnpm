# API Documentation

Project hiện chưa có OpenAPI/Swagger tập trung ở root. Tài liệu này tổng hợp các endpoint chính từ từng service. Khi mở rộng project, nên bổ sung OpenAPI spec hoặc Postman Collection.

## Authentication

Các endpoint nghiệp vụ dùng Cognito JWT trong header:

```http
Authorization: Bearer <id_token_or_access_token>
```

Các endpoint ghi tiền cần thêm:

```http
Idempotency-Key: <uuid>
```

## Money Service

Mặc định service nghe `PORT=8080`. Khi chạy nhiều service cùng lúc ở local, có thể override thành `PORT=5000` và dùng base URL `http://localhost:5000`.

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/health` | Không | Health check. |
| GET | `/balance` | Có | Lấy số dư user hiện tại. |
| GET | `/premium/fee` | Có | Lấy phí nâng cấp Premium. |
| POST | `/exchange` | Có | Đổi tiền giữa hai currency. |
| POST | `/topup` | Có | Nạp tiền giả lập. |
| POST | `/premium/upgrade` | Có | Trừ tiền và nâng cấp Premium. |

### POST `/exchange`

Headers:

```http
Authorization: Bearer <jwt>
Idempotency-Key: <uuid>
Content-Type: application/json
```

Body:

```json
{
  "from_currency": "USD",
  "to_currency": "EUR",
  "amount": 100
}
```

Response thành công trả về thông tin transaction, rate áp dụng, số tiền nhận và balance mới.

### POST `/topup`

```json
{
  "amount": 1000000
}
```

### POST `/premium/upgrade`

Request dùng JWT và idempotency key. Service kiểm tra balance, trừ premium fee và cập nhật Cognito custom claim.

## Forecast Service

Mặc định service nghe `PORT=8080`. Khi chạy nhiều service cùng lúc ở local, có thể override thành `PORT=6000` và dùng base URL `http://localhost:6000`.

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/health` | Không | Health check. |
| GET | `/forecast/{currency_code}` | Premium JWT | Dự báo tỷ giá cho một currency. |

### GET `/forecast/USD`

Response ví dụ:

```json
{
  "currency_code": "USD",
  "forecast": [0.000043, 0.000044, 0.000042],
  "model_version": "v1.2.3"
}
```

Status quan trọng:

| Status | Ý nghĩa |
|---|---|
| 401 | Thiếu hoặc sai JWT. |
| 403 | User không phải Premium. |
| 503 | SageMaker Endpoint không khả dụng. |

## Tour Service

Base URL local gợi ý: `http://localhost:7000`.

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/health` | Không | Health check. |
| GET | `/tours/{currency_code}` | Không hoặc tùy ALB policy | Lấy danh sách tour theo currency. |

### GET `/tours/JPY`

Response ví dụ:

```json
{
  "tours": [
    {
      "id": "abc123def456abcd",
      "name": "Tokyo City Tour",
      "description": "Explore the heart of Tokyo...",
      "image_url": "https://original-source.com/image.jpg",
      "image_key": "tours/images/JPY/abc123def456abcd.jpg",
      "image_presigned_url": "https://s3.amazonaws.com/bucket/...",
      "affiliate_url": "https://travelpayouts.com/...",
      "currency_code": "JPY",
      "country_code": "JP",
      "country_name": "Japan",
      "collected_at": "2026-05-14T00:00:00+00:00"
    }
  ],
  "count": 1,
  "currency_code": "JPY"
}
```

## Streaming Service

Mặc định service nghe `PORT=3001`. Khi chạy song song với frontend, có thể override thành `PORT=4000` và dùng `http://localhost:4000`.

| Giao thức | Path/Event | Mô tả |
|---|---|---|
| HTTP GET | `/health` | Health check. |
| WebSocket Socket.IO | `connection` | Client kết nối realtime. |
| WebSocket event | exchange-rate update events | Server push dữ liệu tỷ giá đọc từ Redis. |

Frontend sử dụng `VITE_STREAMING_SERVICE_URL` để kết nối Socket.IO.

## SageMaker Inference Container

Container trong `services/forecast-training` phục vụ SageMaker contract:

| Method | Path | Mô tả |
|---|---|---|
| GET | `/ping` | Health check cho SageMaker. |
| POST | `/invocations` | Inference request từ SageMaker Endpoint. |

## Service README chi tiết

- [Money Service](../services/money-service/README.md)
- [Forecast Service](../services/forecast-service/README.md)
- [Tour Service](../services/tour-service/README.md)
- [Streaming Service](../services/streaming-service/README.md)
- [Dataset Maker](../services/dataset-maker/README.md)
- [Post-confirmation Lambda](../services/post-confirmation-lambda/README.md)
