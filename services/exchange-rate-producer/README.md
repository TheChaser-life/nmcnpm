# Exchange Rate Producer

Service ECS định kỳ polling External Exchange API để lấy tỉ giá tiền tệ so với VND, sau đó lưu vào Exchange Rate Cache (ElastiCache Redis) với TTL=30s.

## Kiến trúc

```
External Exchange API
        │  (HTTP GET, mỗi 30s)
Exchange Rate Producer (ECS, Public Subnet)
        │  (SET với TTL=30s)
Exchange Rate Cache (ElastiCache Redis, Private Subnet)
        │
Streaming Service → Frontend (WebSocket)
```

**Deployment:** ECS Fargate trong Public Subnet (cần internet access để gọi external API)  
**Multi-AZ:** AZ 1 active, AZ 2 standby (auto-activate khi AZ 1 fail)

---

## Cấu trúc thư mục

```
services/exchange-rate-producer/
├── producer.py          # Main service code
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── README.md            # This file
└── tests/
    ├── __init__.py
    └── test_producer.py # Unit tests
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
python producer.py
```

Service sẽ bắt đầu polling ngay lập tức và lặp lại mỗi `POLLING_INTERVAL_SECONDS` giây.

---

## Environment Variables

| Variable | Mô tả | Mặc định |
|---|---|---|
| `EXCHANGE_API_URL` | URL của external exchange rate API (base: VND) | `https://api.exchangerate-api.com/v4/latest/VND` |
| `EXCHANGE_API_KEY` | API key (nếu provider yêu cầu) | _(trống)_ |
| `EXCHANGE_API_TIMEOUT` | Timeout cho mỗi API request (giây) | `10` |
| `REDIS_HOST` | ElastiCache primary endpoint | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `REDIS_DB` | Redis database index | `0` |
| `REDIS_PASSWORD` | Redis AUTH password | _(trống)_ |
| `REDIS_SSL` | Bật TLS cho Redis connection | `true` |
| `POLLING_INTERVAL_SECONDS` | Tần suất polling (giây, tối đa 60) | `30` |
| `CACHE_TTL_SECONDS` | TTL cho mỗi key trong Redis (giây) | `30` |
| `SUPPORTED_CURRENCIES` | Danh sách currency codes (phân cách bằng dấu phẩy) | `USD,EUR,GBP,JPY,CNY,KRW,THB,SGD,MYR,IDR,PHP,AUD` |

---

## Redis Cache Format

Mỗi tỉ giá được lưu với key format: `exchange_rate:{CURRENCY_CODE}`

**Ví dụ key:** `exchange_rate:USD`

**Value (JSON string):**
```json
{
  "currency": "USD",
  "rate": 0.000043,
  "timestamp": 1700000000.123
}
```

- `currency`: Mã tiền tệ (ISO 4217)
- `rate`: Tỉ giá so với VND (1 VND = rate đơn vị currency)
- `timestamp`: Unix timestamp lúc lấy dữ liệu

---

## Error Handling

| Tình huống | Hành vi |
|---|---|
| API timeout | Log lỗi, giữ nguyên cache hiện tại, tiếp tục polling |
| API trả về HTTP error (4xx/5xx) | Log lỗi với status code, giữ nguyên cache |
| API trả về JSON không hợp lệ | Log lỗi, giữ nguyên cache |
| Redis connection error | Log lỗi, service tiếp tục chạy |
| Currency không có trong API response | Log warning, bỏ qua currency đó |

**Nguyên tắc quan trọng:** Khi API fail, service **không ghi đè** cache hiện tại. Cache sẽ tự hết hạn theo TTL, cho phép Streaming Service phát hiện dữ liệu stale.

---

## Logging

Service emit structured JSON logs ra stdout (CloudWatch Logs):

```json
{
  "level": "INFO",
  "message": "Polling cycle completed",
  "service": "exchange-rate-producer",
  "cycle": 42,
  "success": true,
  "duration_seconds": 0.85,
  "sleep_seconds": 29.15
}
```

---

## Chạy tests

```bash
python -m unittest tests.test_producer -v
```

Tests bao gồm:
- Filtering currencies từ API response
- Cache update logic (key format, TTL, JSON value)
- Error handling khi API fail (không ghi đè cache)
- Error handling khi Redis fail (tiếp tục xử lý các currency khác)
- API response parsing (timeout, HTTP error, invalid JSON, missing fields)
- Config validation

---

## Deployment (ECS Fargate)

Service được containerize bằng Dockerfile (task 4.1.5) và deploy lên ECS Fargate:

- **Public Subnet**: Cần internet access để gọi external API
- **AZ 1**: `desired_count = 1` (active)
- **AZ 2**: `desired_count = 0` (standby, auto-scale khi AZ 1 fail)
- **Secrets**: `EXCHANGE_API_KEY` và `REDIS_PASSWORD` được inject từ AWS Secrets Manager

---

## Supported Currencies

Mặc định service theo dõi 12 loại tiền tệ so với VND:

| Code | Tên |
|---|---|
| USD | US Dollar |
| EUR | Euro |
| GBP | British Pound |
| JPY | Japanese Yen |
| CNY | Chinese Yuan |
| KRW | South Korean Won |
| THB | Thai Baht |
| SGD | Singapore Dollar |
| MYR | Malaysian Ringgit |
| IDR | Indonesian Rupiah |
| PHP | Philippine Peso |
| AUD | Australian Dollar |

Danh sách này có thể thay đổi qua environment variable `SUPPORTED_CURRENCIES`.
