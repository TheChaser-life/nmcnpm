# Dataset Maker

Service ECS one-shot thu thập dữ liệu tỉ giá lịch sử từ Exchange Rate Cache (Redis) và transaction log (RDS PostgreSQL), xử lý thành CSV, và upload lên S3 để SageMaker Training Job sử dụng.

## Kiến trúc

```
Exchange Rate Cache (ElastiCache Redis)
        │  (SCAN exchange_rate:* keys)
        ├──────────────────────────────┐
User_DB (RDS PostgreSQL)              │
        │  (SELECT transactions)       │
        └──────────────────────────────┤
                                Dataset Maker (ECS Task, Private Subnet)
                                       │  (CSV, partitioned by date)
                                S3 (training-data/ prefix)
                                       │  (S3 event / EventBridge)
                                SageMaker Training Job
```

**Deployment:** ECS Task (không phải long-running service) trong Private Subnet.  
**Trigger:** EventBridge scheduled rule (mặc định: hàng ngày lúc 00:00 UTC).  
**S3 access:** VPC Gateway Endpoint — không qua internet, không tốn NAT Gateway.

---

## Cấu trúc thư mục

```
services/dataset-maker/
├── dataset_maker.py     # Main service script (one-shot)
├── requirements.txt     # Python dependencies
├── Dockerfile
├── .env.example         # Environment variable template
├── .dockerignore
├── README.md            # This file
└── tests/
    ├── __init__.py
    └── test_dataset_maker.py
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

### 3. Chạy job

```bash
python dataset_maker.py
```

Script chạy một lần rồi thoát (exit code 0 = thành công, exit code 1 = lỗi).

---

## Environment Variables

| Variable | Mô tả | Mặc định |
|---|---|---|
| `REDIS_HOST` | ElastiCache primary endpoint | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `REDIS_DB` | Redis database index | `0` |
| `REDIS_PASSWORD` | Redis AUTH password | _(trống)_ |
| `REDIS_SSL` | Bật TLS cho Redis connection | `true` |
| `DB_HOST` | RDS instance endpoint | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | `currency_exchange` |
| `DB_USER` | Database user | `postgres` |
| `DB_PASSWORD` | Database password | _(trống)_ |
| `S3_BUCKET` | S3 bucket name cho training data | _(bắt buộc)_ |
| `S3_PREFIX` | S3 key prefix | `training-data` |
| `LOOKBACK_HOURS` | Số giờ lịch sử transaction cần thu thập | `24` |
| `AWS_REGION` | AWS region cho S3 client | `ap-southeast-1` |

---

## CSV Format

File CSV được upload lên S3 với đường dẫn:

```
{S3_PREFIX}/{YYYY}/{MM}/{DD}/rates_{YYYYMMDDTHHMMSSz}.csv
```

**Ví dụ:** `training-data/2024/01/15/rates_20240115T000000Z.csv`

**Columns:**

| Column | Kiểu | Mô tả |
|---|---|---|
| `timestamp` | ISO 8601 | Hourly bucket của dữ liệu |
| `currency_code` | string | Mã tiền tệ ISO 4217 (VD: USD, EUR) |
| `rate_to_vnd` | float | Tỉ giá (1 VND = X đơn vị currency) |
| `transaction_volume` | float | Tổng khối lượng giao dịch trong giờ đó |
| `transaction_count` | int | Số lượng giao dịch trong giờ đó |

**Ví dụ:**

```csv
timestamp,currency_code,rate_to_vnd,transaction_volume,transaction_count
2024-01-15T00:00:00+00:00,EUR,0.000039,15000.5,42
2024-01-15T00:00:00+00:00,USD,0.000043,28000.0,87
```

---

## Redis Key Format

Dataset Maker đọc các key theo format được tạo bởi Exchange Rate Producer:

```
exchange_rate:{CURRENCY_CODE}
```

**Ví dụ:** `exchange_rate:USD`, `exchange_rate:EUR`

**Value (JSON string):**
```json
{
  "currency": "USD",
  "rate": 0.000043,
  "timestamp": 1700000000.123
}
```

---

## Error Handling

| Tình huống | Hành vi |
|---|---|
| Redis không có dữ liệu | Log WARN, tiếp tục với transaction data |
| PostgreSQL query fail | Log ERROR, exit code 1 (ECS báo task failed) |
| S3 upload fail | Log ERROR, exit code 1 |
| CSV không có data rows | Log WARN, bỏ qua upload, exit code 0 |
| Config thiếu biến bắt buộc | Log ERROR, exit code 1 |

---

## Logging

Service emit structured JSON logs ra stdout (CloudWatch Logs):

```json
{
  "level": "INFO",
  "message": "Dataset Maker job completed successfully",
  "service": "dataset-maker",
  "s3_key": "training-data/2024/01/15/rates_20240115T000000Z.csv",
  "run_time": "2024-01-15T00:00:00+00:00"
}
```

---

## Chạy tests

```bash
python -m pytest tests/ -v
```

---

## Build Docker Image và Push lên ECR

### Yêu cầu

- [Docker](https://docs.docker.com/get-docker/) đã được cài đặt và đang chạy
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) đã được cấu hình (`aws configure`)
- IAM user/role có quyền `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`

### Environment Variables

| Biến | Mô tả | Mặc định |
|---|---|---|
| `AWS_ACCOUNT_ID` | AWS Account ID (12 chữ số) | Tự động detect qua `aws sts get-caller-identity` |
| `AWS_REGION` | AWS Region chứa ECR repository | `ap-southeast-1` |
| `IMAGE_TAG` | Tag cho Docker image | `latest` |

> **ECR Repository name:** `dataset_maker_repo` (được định nghĩa trong Terraform tại `infra/modules/ECR_and_ECS_Cluster/main.tf`)

### Cách push lên ECR

**Bước 1:** Đảm bảo ECR repository đã được tạo bằng Terraform:

```bash
cd infra
terraform apply
```

**Bước 2:** Chạy script push từ thư mục `services/dataset-maker/`:

```bash
# Sử dụng tag mặc định (latest), tự động detect AWS Account ID
AWS_ACCOUNT_ID=123456789012 ./push_to_ecr.sh

# Hoặc chỉ định đầy đủ
AWS_ACCOUNT_ID=123456789012 \
AWS_REGION=ap-southeast-1 \
IMAGE_TAG=v1.0.0 \
./push_to_ecr.sh
```

**Bước 3 (thủ công, nếu không dùng script):**

```bash
# 1. Build image
docker build --platform linux/amd64 -t dataset-maker:latest .

# 2. Đăng nhập ECR
aws ecr get-login-password --region ap-southeast-1 \
  | docker login \
      --username AWS \
      --password-stdin \
      123456789012.dkr.ecr.ap-southeast-1.amazonaws.com

# 3. Tag image
docker tag dataset-maker:latest \
  123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/dataset_maker_repo:latest

# 4. Push image
docker push \
  123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/dataset_maker_repo:latest
```

> **Lưu ý:** Thay `123456789012` bằng AWS Account ID thực tế của bạn.

### Sau khi push

Cập nhật biến `Dataset_Maker_Image_URI` trong Terraform (`infra/terraform.tfvars`) với URI của image vừa push:

```
Dataset_Maker_Image_URI = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/dataset_maker_repo:latest"
```

Sau đó chạy `terraform apply` để ECS Task Definition sử dụng image mới.

---

## Deployment (ECS Task)

Service được containerize bằng Dockerfile và deploy lên ECS như một **Task** (không phải Service):

- **Private Subnet**: Truy cập Redis và RDS qua VPC internal routing
- **S3 access**: Qua VPC Gateway Endpoint (không cần NAT Gateway)
- **Trigger**: EventBridge scheduled rule (daily at 00:00 UTC)
- **Secrets**: `DB_PASSWORD` và `REDIS_PASSWORD` được inject từ AWS Secrets Manager
- **Exit code**: 0 = thành công, 1 = lỗi (ECS sẽ báo task failed cho CloudWatch)
