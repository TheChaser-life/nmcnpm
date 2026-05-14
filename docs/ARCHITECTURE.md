# Architecture

Tài liệu này mô tả kiến trúc logic và hạ tầng của hệ thống Currency Exchange Platform. Sơ đồ trực quan có trong [Architecture_Diagram.drawio](../Architecture_Diagram.drawio).

## Tổng quan

Hệ thống được thiết kế theo mô hình microservices chạy trên AWS ECS Fargate. Frontend đi qua Application Load Balancer, các service xử lý nghiệp vụ nằm trong private subnet, dữ liệu nằm ở RDS/ElastiCache/S3, còn xác thực do Cognito đảm nhiệm.

```text
User
  |
Route 53 / Domain
  |
AWS WAF
  |
Application Load Balancer
  |
  +-- Frontend ECS Service
  +-- Streaming Service
  +-- Money Service
  +-- Forecast Service
  +-- Tour Service

Private Data Plane:
  RDS PostgreSQL
  ElastiCache Redis/Valkey
  S3 Buckets
  SageMaker Endpoint
  Cognito
```

## Thành phần chính

| Thành phần | Vai trò |
|---|---|
| Frontend | Giao diện React cho dashboard tỷ giá, exchange/top-up, forecast, tour và auth. |
| Exchange Rate Producer | Gọi external exchange-rate API định kỳ, chuẩn hóa dữ liệu và ghi vào Redis. |
| Streaming Service | Đọc Redis và push tỷ giá realtime cho browser qua Socket.IO. |
| Money Service | Quản lý balance, top-up, exchange, premium upgrade, idempotency và optimistic locking. |
| Forecast Service | Kiểm tra JWT/Premium claim rồi gọi SageMaker Endpoint để lấy dự báo. |
| Dataset Maker | ECS one-shot task tạo training CSV từ Redis/RDS và upload S3. |
| Forecast Training | Container training/inference cho SageMaker. |
| Model Promotion Lambda | So sánh metric và promote model tốt hơn vào endpoint/registry. |
| Tour Producer | Thu thập tour từ external provider và lưu JSON/ảnh vào S3. |
| Tour Service | Đọc tour từ S3 và trả về tour kèm pre-signed image URL. |
| Post-confirmation Lambda | Cognito trigger tạo record user trong PostgreSQL sau khi xác nhận email. |

## Luồng tỷ giá realtime

```text
External Exchange Rate API
  -> Exchange Rate Producer
  -> ElastiCache exchange-rate cache
  -> Streaming Service
  -> Frontend WebSocket dashboard
```

Redis được dùng làm cache tốc độ cao. Streaming service poll Redis theo interval ngắn và phát event cho client qua Socket.IO. ALB có thể route traffic WebSocket đến streaming service.

## Luồng exchange/top-up

```text
Frontend
  -> Money Service
  -> verify Cognito JWT
  -> check Idempotency-Key in Redis
  -> read exchange rate from Redis
  -> update RDS PostgreSQL with optimistic locking
  -> save idempotent result
  -> Frontend
```

Hai cơ chế quan trọng:

- `Idempotency-Key`: tránh xử lý trùng khi client retry.
- `version` column trong DB: tránh race condition khi nhiều request cùng cập nhật balance.

## Luồng forecast Premium

```text
Frontend
  -> Forecast Service
  -> verify JWT and custom:premium
  -> SageMaker Endpoint
  -> Forecast result
```

Forecast chỉ mở cho user có `custom:premium = true` trong Cognito token.

## Luồng ML training

```text
Redis + RDS
  -> Dataset Maker ECS Task
  -> S3 training-data bucket
  -> Step Functions / SageMaker Training Job
  -> S3 model artifact bucket
  -> Model Registry
  -> Model Promotion Lambda
  -> SageMaker Endpoint
```

Dataset Maker là task chạy theo lịch. SageMaker Training Job tạo model artifact. Lambda promotion chịu trách nhiệm chọn model có metric tốt hơn trước khi đưa vào endpoint.

## Luồng tour

```text
Travel/Tour External API
  -> Tour Producer
  -> S3 tour bucket
  -> Tour Service
  -> Frontend
  -> Affiliate redirect
```

Tour data và ảnh là dạng static/semi-static nên S3 phù hợp hơn database quan hệ về chi phí và khả năng scale.

## Hạ tầng AWS

| Lớp | Dịch vụ |
|---|---|
| Network | VPC, public/private subnets, route tables, security groups, VPC endpoints |
| Edge | Route 53, ALB, WAF, ACM certificate |
| Compute | ECS Fargate, Lambda |
| Data | RDS PostgreSQL, ElastiCache Redis/Valkey, S3 |
| ML | SageMaker Training Job, Model Registry, Endpoint |
| Auth | Cognito User Pool, App Client |
| Automation | EventBridge, Step Functions |
| Observability | CloudWatch Logs, CloudWatch Alarms, SNS, X-Ray |

## Multi-AZ và resilience

- ECS service chạy desired count nhiều hơn 1 và trải trên nhiều subnet/AZ khi cấu hình hạ tầng đầy đủ.
- RDS có primary và read replica/failover strategy theo module Terraform.
- ElastiCache có cache riêng cho tỷ giá và idempotency.
- ALB health check giúp route khỏi task unhealthy.
- CloudWatch/SNS gửi cảnh báo khi service hoặc resource có vấn đề.

## Bảo mật

- WAF đứng trước ALB để giảm rủi ro request độc hại phổ biến.
- Backend/data service chạy trong private subnet.
- JWT được verify bằng JWKS public keys từ Cognito.
- Secret được đưa qua AWS Secrets Manager/SSM, không hardcode trong code.
- S3 access từ service đi qua IAM task role và VPC Gateway Endpoint.
- Container nên chạy non-root theo Dockerfile của từng service.
