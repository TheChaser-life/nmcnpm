# Forecast Training Service

SageMaker-compatible container cho việc huấn luyện model dự báo tỉ giá tiền tệ. Sử dụng thuật toán **XGBoost** với **lag features** để train một model riêng cho từng currency_code, đánh giá bằng RMSE và MAE, và lưu artifacts theo SageMaker BYO container convention.

---

## Algorithm Choice Rationale

### Tại sao XGBoost?

| Tiêu chí | XGBoost ✅ | DeepAR | LSTM |
|---|---|---|---|
| Input format | CSV (tabular) | JSON Lines (time series) | Sequence arrays |
| Feature engineering | Sử dụng trực tiếp các features đã có | Cần reformatting | Cần reformatting |
| Dataset size | Tốt với small-medium dataset | Cần nhiều data hơn | Cần nhiều data hơn |
| Containerization | Đơn giản, pip install | Cần SageMaker built-in container | Cần TensorFlow/PyTorch |
| Interpretability | Feature importance có sẵn | Black box | Black box |
| Debug | Dễ debug locally | Khó debug | Khó debug |
| Training time | Nhanh | Chậm hơn | Chậm hơn |

**Lý do chọn XGBoost:**
- `Dataset_Maker` đã tạo sẵn time-based features (`hour`, `day_of_week`, `day_of_month`) → tabular regression là lựa chọn tự nhiên.
- Dataset có kích thước nhỏ-vừa (hourly data, ~24 rows/currency/ngày) → XGBoost phù hợp hơn deep learning models.
- Lag features (previous N days of rates) được tạo tự động trong training script.
- Dễ containerize và test locally với `pip install xgboost`.

### Multi-model approach

Thay vì train một model duy nhất cho tất cả currencies, service train **một model riêng cho từng currency_code**. Lý do:
- Mỗi currency có scale và volatility khác nhau (VD: USD vs JPY).
- Model riêng cho phép hyperparameter tuning per-currency trong tương lai.

---

## Cấu trúc thư mục

```
services/forecast-training/
├── train.py          # SageMaker training script
├── inference.py      # SageMaker inference handler + Flask server
├── requirements.txt  # Python dependencies
├── Dockerfile        # SageMaker BYO container
└── README.md         # This file
```

---

## SageMaker BYO Container Conventions

Container này tuân theo [SageMaker BYO container conventions](https://docs.aws.amazon.com/sagemaker/latest/dg/your-algorithms-training-algo.html):

| Convention | Implementation |
|---|---|
| Training entry point | `/opt/program/train` (bash script → `python train.py`) |
| Serving entry point | `/opt/program/serve` (bash script → gunicorn + Flask) |
| Health check | `GET /ping` → HTTP 200 |
| Inference | `POST /invocations` → forecast JSON |
| Inference port | 8080 |
| Model artifacts | `/opt/ml/model/` |
| Training data | `/opt/ml/input/data/training/` |
| Hyperparameters | `/opt/ml/input/config/hyperparameters.json` |
| Evaluation output | `/opt/ml/output/data/metrics.json` |
| Failure message | `/opt/ml/output/failure` |

---

## Input Data Format

Training data được đọc từ SageMaker input channel `training` (local path: `/opt/ml/input/data/training/`).

**CSV columns** (produced by Dataset_Maker):

| Column | Type | Description |
|---|---|---|
| `timestamp` | ISO 8601 string | Hourly bucket |
| `currency_code` | string | ISO 4217 code (e.g., USD, EUR) |
| `rate_to_vnd` | float | **Target variable** — exchange rate vs VND |
| `rate_normalized` | float (0.0–1.0) | Min-max normalized rate per currency |
| `transaction_volume` | float | Sum of exchange amounts in the hour |
| `transaction_count` | int | Number of exchange transactions in the hour |
| `hour` | int (0–23) | Hour of day |
| `day_of_week` | int (0–6) | 0=Monday … 6=Sunday |
| `day_of_month` | int (1–31) | Day of month |

**S3 path pattern:** `training-data/{YYYY}/{MM}/{DD}/rates_{YYYYMMDDTHHMMSSz}.csv`

---

## Output Format

### Model Artifacts (`/opt/ml/model/`)

Một file JSON per currency (XGBoost native format) + metadata:
```
/opt/ml/model/
├── USD_model.json       # XGBoost model
├── USD_metadata.json    # Feature columns, lag_days, forecast_horizon
├── EUR_model.json
├── EUR_metadata.json
└── ...
```

**Metadata format:**
```json
{
  "currency_code": "USD",
  "feature_columns": ["rate_normalized", "transaction_volume", ..., "rate_lag_1", ...],
  "lag_days": 7,
  "forecast_horizon": 1,
  "model_version": "1.0"
}
```

### Evaluation Metrics (`/opt/ml/output/data/metrics.json`)

```json
{
  "rmse_by_currency": {
    "USD": 0.0000012,
    "EUR": 0.0000018,
    "JPY": 0.0025
  },
  "mae_by_currency": {
    "USD": 0.0000010,
    "EUR": 0.0000015,
    "JPY": 0.0020
  },
  "mean_rmse": 0.0000015,
  "mean_mae": 0.0000012
}
```

`mean_rmse` là metric chính được Model Registry Lambda (task 5.3.1) dùng để so sánh với model hiện tại.

---

## Inference API

### Input (JSON)

```json
{
  "currency_code": "USD",
  "horizon": 7
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `currency_code` | string | ✅ | — | ISO 4217 currency code |
| `horizon` | int | ❌ | 7 | Number of days to forecast (1–365) |

### Output (JSON)

```json
{
  "currency_code": "USD",
  "forecast": [
    {"date": "2024-01-16", "predicted_rate": 0.0000432},
    {"date": "2024-01-17", "predicted_rate": 0.0000435},
    {"date": "2024-01-18", "predicted_rate": 0.0000431},
    ...
  ]
}
```

### Error Responses

| Tình huống | HTTP Status | Message |
|---|---|---|
| Unknown `currency_code` | 400 | `No model available for currency 'XYZ'` |
| Missing `currency_code` | 400 | `Missing required field: 'currency_code'` |
| Invalid `horizon` | 400 | `'horizon' must be >= 1, got 0` |
| Unsupported content type | 415 | `Unsupported content type: ...` |
| Internal error | 500 | `Internal server error` |

---

## Hyperparameters

Được đọc từ `/opt/ml/input/config/hyperparameters.json` (set bởi SageMaker Training Job configuration):

| Parameter | Type | Default | Description |
|---|---|---|---|
| `n_estimators` | int | `100` | Số lượng boosting rounds |
| `max_depth` | int | `6` | Độ sâu tối đa của mỗi tree |
| `learning_rate` | float | `0.1` | Step size shrinkage |
| `subsample` | float | `0.8` | Tỉ lệ subsample của training data |
| `colsample_bytree` | float | `0.8` | Tỉ lệ subsample của features |
| `objective` | string | `reg:squarederror` | Loss function |
| `lag_days` | int | `7` | Số ngày lag features (previous N days of rates) |
| `forecast_horizon` | int | `1` | Số bước dự báo trong training (target shift) |

**Ví dụ hyperparameters.json:**
```json
{
  "n_estimators": "100",
  "max_depth": "6",
  "learning_rate": "0.1",
  "subsample": "0.8",
  "colsample_bytree": "0.8",
  "objective": "reg:squarederror",
  "lag_days": "7",
  "forecast_horizon": "1"
}
```

> **Lưu ý:** SageMaker truyền tất cả hyperparameter values dưới dạng string — training script tự cast sang đúng type.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `SM_CHANNEL_TRAINING` | Path to training data (set by SageMaker) | `/opt/ml/input/data/training` |
| `SM_MODEL_DIR` | Path to save model artifacts (set by SageMaker) | `/opt/ml/model` |
| `SM_OUTPUT_DATA_DIR` | Path to save evaluation output (set by SageMaker) | `/opt/ml/output/data` |
| `SAGEMAKER_PROGRAM` | Training script name (set in Dockerfile) | `train.py` |

---

## Build và Push lên ECR

### 1. Build Docker image

```bash
cd services/forecast-training

docker build -t forecast-training:latest .
```

### 2. Authenticate với ECR

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=ap-southeast-1

aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

### 3. Tag và push image

```bash
ECR_REPO=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/forecast-training

docker tag forecast-training:latest $ECR_REPO:latest
docker push $ECR_REPO:latest
```

---

## Local Testing

### 1. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 2. Chuẩn bị test data

```bash
# Tạo thư mục SageMaker mock
mkdir -p /tmp/sagemaker/input/data/training
mkdir -p /tmp/sagemaker/input/config
mkdir -p /tmp/sagemaker/model
mkdir -p /tmp/sagemaker/output/data

# Tạo sample CSV (format từ Dataset_Maker)
cat > /tmp/sagemaker/input/data/training/sample.csv << 'EOF'
timestamp,currency_code,rate_to_vnd,rate_normalized,transaction_volume,transaction_count,hour,day_of_week,day_of_month
2024-01-01T00:00:00+00:00,USD,0.0000432,0.45,1500.0,42,0,0,1
2024-01-01T01:00:00+00:00,USD,0.0000433,0.46,1200.0,38,1,0,1
2024-01-01T02:00:00+00:00,USD,0.0000431,0.44,900.0,25,2,0,1
2024-01-01T03:00:00+00:00,USD,0.0000430,0.43,800.0,20,3,0,1
2024-01-01T04:00:00+00:00,USD,0.0000435,0.48,1100.0,30,4,0,1
2024-01-01T05:00:00+00:00,USD,0.0000436,0.49,1300.0,35,5,0,1
2024-01-01T06:00:00+00:00,USD,0.0000434,0.47,1600.0,45,6,0,1
2024-01-01T07:00:00+00:00,USD,0.0000437,0.50,1800.0,50,7,0,1
2024-01-01T08:00:00+00:00,USD,0.0000438,0.51,2000.0,55,8,0,1
2024-01-01T09:00:00+00:00,USD,0.0000440,0.53,2200.0,60,9,0,1
2024-01-01T10:00:00+00:00,USD,0.0000439,0.52,2100.0,58,10,0,1
2024-01-01T11:00:00+00:00,USD,0.0000441,0.54,2300.0,62,11,0,1
EOF

# Tạo hyperparameters.json
cat > /tmp/sagemaker/input/config/hyperparameters.json << 'EOF'
{
  "n_estimators": "50",
  "max_depth": "4",
  "learning_rate": "0.1",
  "subsample": "0.8",
  "colsample_bytree": "0.8",
  "objective": "reg:squarederror",
  "lag_days": "3",
  "forecast_horizon": "1"
}
EOF
```

### 3. Chạy training script

```bash
SM_CHANNEL_TRAINING=/tmp/sagemaker/input/data/training \
SM_MODEL_DIR=/tmp/sagemaker/model \
SM_OUTPUT_DATA_DIR=/tmp/sagemaker/output/data \
python train.py
```

### 4. Kiểm tra output

```bash
# Xem model artifacts
ls /tmp/sagemaker/model/

# Xem evaluation metrics
cat /tmp/sagemaker/output/data/metrics.json
```

### 5. Test inference server locally

```bash
# Start inference server
SM_MODEL_DIR=/tmp/sagemaker/model python inference.py
```

```bash
# Health check
curl http://localhost:8080/ping

# Forecast request
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"currency_code": "USD", "horizon": 7}'
```

### 6. Test với Docker

```bash
# Build image
docker build -t forecast-training:local .

# Run training
docker run --rm \
  -v /tmp/sagemaker:/opt/ml \
  -e SM_CHANNEL_TRAINING=/opt/ml/input/data/training \
  -e SM_MODEL_DIR=/opt/ml/model \
  -e SM_OUTPUT_DATA_DIR=/opt/ml/output/data \
  forecast-training:local train

# Run inference server
docker run --rm -p 8080:8080 \
  -v /tmp/sagemaker/model:/opt/ml/model \
  -e SM_MODEL_DIR=/opt/ml/model \
  forecast-training:local serve
```

---

## Logging

Service emit structured JSON logs ra stdout (CloudWatch Logs):

```json
{
  "level": "INFO",
  "message": "SageMaker training job completed successfully",
  "service": "forecast-training",
  "models_trained": 5,
  "rmse_by_currency": {
    "EUR": 0.0000018,
    "JPY": 0.0025,
    "USD": 0.0000012
  }
}
```

---

## Error Handling

| Tình huống | Hành vi |
|---|---|
| Không tìm thấy CSV files | Log ERROR, write `/opt/ml/output/failure`, exit code 1 |
| CSV thiếu required columns | Log ERROR, write `/opt/ml/output/failure`, exit code 1 |
| Currency có < 10 rows | Log WARN, bỏ qua currency đó |
| Tất cả currencies bị bỏ qua | Log ERROR, write `/opt/ml/output/failure`, exit code 1 |
| hyperparameters.json không tồn tại | Log WARN, dùng default values |
| Không thể save model | Log ERROR, write `/opt/ml/output/failure`, exit code 1 |
| Unexpected exception | Log ERROR, write `/opt/ml/output/failure`, exit code 1 |

---

## Integration với ML Pipeline

```
Dataset_Maker (ECS Task)
    │  (CSV files)
S3 (training-data/ prefix)
    │  (S3 event → EventBridge → Step Functions)
SageMaker Training Job
    │  (container: forecast-training ECR image)
    │  (calls: /opt/program/train)
    │  (reads: s3://bucket/training-data/)
    │  (writes: s3://bucket/model-artifacts/)
    │  (writes: metrics.json → Model Registry Lambda reads this)
Model_Registry Lambda (task 5.3.1)
    │  (compare mean_rmse with current model)
    ├── If better → approve + update SageMaker Endpoint
    └── Else → reject, keep current Endpoint
SageMaker Endpoint
    │  (calls: /opt/program/serve → gunicorn + Flask)
    │  (POST /invocations → forecast result)
Forecast_Service (ECS)
    │  (verify JWT premium claim)
    │  (call SageMaker Endpoint)
Frontend (Premium_User)
```
