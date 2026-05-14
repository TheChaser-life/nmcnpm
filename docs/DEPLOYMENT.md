# Deployment Guide

Tài liệu này hướng dẫn triển khai hệ thống lên AWS bằng Terraform và GitHub Actions.

## Điều kiện tiên quyết

- AWS CLI v2 đã đăng nhập đúng account.
- Terraform 1.6+.
- Docker Desktop.
- ECR/ECS permissions, IAM permissions để tạo hạ tầng.
- ACM certificate ARN cho HTTPS listener.
- S3 backend bucket và DynamoDB lock table cho Terraform state.
- GitHub repository secrets cho CI/CD.

## Thứ tự triển khai tổng quát

1. Chuẩn bị Terraform backend.
2. Apply `infra/persistent`.
3. Build/push image lần đầu cho các service cần image URI ban đầu.
4. Apply `infra/main_infra`.
5. Cập nhật frontend env/API URL từ output hạ tầng.
6. Dùng GitHub Actions để build, scan, push và rolling deploy các lần sau.

## 1. Terraform backend

Tạo S3 bucket và DynamoDB table cho state locking. Ví dụ tên state hiện được tài liệu hóa trong Terraform README:

```text
s3://nmcnpm-tfstate/currency-exchange/persistent.tfstate
s3://nmcnpm-tfstate/currency-exchange/main_infra.tfstate
```

Điền các biến như `backend_bucket`, `backend_table`, `region`, `account_id` vào `terraform.tfvars` tương ứng. Không commit file tfvars chứa secret thật.

## 2. Persistent layer

`infra/persistent` chứa resource ít destroy: S3 buckets, ECR repositories, ECS cluster, Secrets Manager/Parameter Store.

```bash
cd infra/persistent
terraform init
terraform plan
terraform apply
terraform output
```

Sau bước này, ghi lại các output quan trọng như ECR repository URI, S3 bucket names, secret ARNs và ECS cluster ARN.

## 3. Build image lần đầu

Một số resource ở `main_infra` cần image URI để tạo task definition/Lambda. Có thể build/push thủ công lần đầu hoặc để workflow chạy sau khi ECR repo đã tồn tại.

Ví dụ build/push một service:

```bash
AWS_REGION=ap-southeast-2
AWS_ACCOUNT_ID=<your-account-id>
ECR_REGISTRY="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

cd services/money-service
docker build -t money-service:latest .
docker tag money-service:latest "$ECR_REGISTRY/update_money_repo:latest"
docker push "$ECR_REGISTRY/update_money_repo:latest"
```

Lặp lại với các service cần deploy: frontend, streaming-service, exchange-rate-producer, money-service, forecast-service, tour-producer, tour-service, dataset-maker và các Lambda image.

## 4. Main infrastructure

`infra/main_infra` tạo network, ALB, WAF, RDS, Redis, Cognito, ECS services, Lambda, Step Functions, SageMaker, CloudWatch/SNS.

```bash
cd infra/main_infra
terraform init
terraform plan
terraform apply
terraform output
```

Các biến quan trọng thường cần có:

| Biến | Mô tả |
|---|---|
| `region` | AWS region triển khai. |
| `account_id` | AWS Account ID. |
| `cert_arn` | ACM certificate ARN cho HTTPS. |
| `training_image` | ECR URI của image training. |
| `initial_model_package_arn` | Model package ban đầu cho SageMaker. |
| `alert_email` | Email nhận SNS alarm. |
| `backend_bucket` | S3 bucket chứa remote state. |
| `backend_table` | DynamoDB table cho state locking. |

## 5. Cấu hình frontend

Frontend Vite nhận biến môi trường lúc build image. Cần cấu hình các secret trong GitHub Actions hoặc `.env.local` khi chạy local:

```text
VITE_COGNITO_USER_POOL_ID=<user-pool-id>
VITE_COGNITO_CLIENT_ID=<app-client-id>
VITE_AWS_REGION=ap-southeast-2
VITE_API_BASE_URL=https://<alb-or-domain>
VITE_STREAMING_SERVICE_URL=https://<alb-or-domain>/stream
VITE_MONEY_SERVICE_URL=https://<alb-or-domain>
VITE_FORECAST_SERVICE_URL=https://<alb-or-domain>
VITE_TOUR_SERVICE_URL=https://<alb-or-domain>
```

## 6. Database migration

Các file SQL nằm trong `db/db_initiate/`:

```text
V0__create_database.sql
V1__create_users_table.sql
V2__create_transactions_table.sql
V3__create_indexes.sql
V4__add_premium_deducted_column.sql
```

Chạy migration bằng công cụ bạn chọn như Flyway, psql hoặc workflow riêng. Thứ tự version phải được giữ nguyên.

## 7. GitHub Actions secrets

Các workflow hiện cần nhóm secrets sau:

| Secret | Dùng cho |
|---|---|
| `PAT` | SonarQube scan workflow. |
| `SONAR_TOKEN` | SonarQube/SonarCloud authentication. |
| `ORGANIZATION` | Sonar organization. |
| `PROJECT_KEY` | Sonar project key. |
| `AWS_OIDC_ROLE_ARN` | GitHub OIDC role để deploy AWS. |
| `AWS_REGION` | AWS region deploy. |
| `ECS_CLUSTER_NAME` | ECS cluster cho rolling deploy. |
| `VITE_*` | Build-time config cho frontend. |

## 8. Rollback

Workflow deploy tag image bằng commit SHA và `latest`. Để rollback:

1. Tìm image SHA ổn định trước đó trong ECR.
2. Register task definition revision mới trỏ về image đó.
3. Update ECS service về task definition revision mới.
4. Chờ `aws ecs wait services-stable`.

## 9. Destroy để tiết kiệm chi phí

`main_infra` có thể destroy khi không dùng demo:

```bash
cd infra/main_infra
terraform destroy
```

Cẩn thận với `infra/persistent`: layer này chứa bucket, repo, secrets và state liên quan. Chỉ destroy khi chắc chắn không cần giữ artifact/data.
