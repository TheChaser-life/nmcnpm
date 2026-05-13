# infra/main_infra

Root module chứa tất cả các resource **có thể destroy/apply lại tự do** để tiết kiệm chi phí.

## Modules

| Module | Mô tả |
|--------|-------|
| `VPC_and_Networking` | VPC, Subnets, Security Groups, VPC Endpoints |
| `ALB` | Application Load Balancer, Target Groups, Listeners |
| `WAF` | Web Application Firewall (rate limiting, SQLi, XSS protection) |
| `RDS_Postgre` | PostgreSQL primary + read replica |
| `ElastiCache` | Valkey clusters (exchange rate cache + idempotency cache) |
| `SageMaker` | Training Job, Model Registry, Endpoint |
| `Lambda` | Post-confirmation Lambda, Model Promotion Lambda |
| `StepFunctions` | ML Training Pipeline state machine |
| `Cognito` | User Pool, App Client |
| `CloudWatch` | Log Groups, Metric Alarms |
| `SNS` | Alert topic + email subscription |
| `X-Ray` | Sampling rules |

## Cách sử dụng

```bash
cd infra/main_infra

# Khi cần dùng — apply toàn bộ infrastructure
terraform init
terraform apply

# Khi muốn tiết kiệm chi phí — destroy toàn bộ
terraform destroy
```

## Phụ thuộc vào persistent

Module này đọc outputs từ `infra/persistent` qua `terraform_remote_state`:

```hcl
data "terraform_remote_state" "persistent" {
  backend = "s3"
  config = {
    bucket = var.backend_bucket
    key    = "currency-exchange/persistent.tfstate"
    region = var.region
  }
}
```

Các giá trị được đọc từ persistent:
- `rds_password`, `elasticache_password` — để tạo RDS và ElastiCache
- `rds_secret_arn`, `elasticache_secret_arn`, `premium_fee_parameter_arn` — cho ECS tasks
- `training_data_bucket_name`, `model_artifact_bucket_name`, `tour_bucket_name` — cho SageMaker và ECS
- `ecs_cluster_arn`, `dataset_maker_task_definition_arn`, v.v. — cho StepFunctions
- `post_confirmation_function_image_uri`, `model_promotion_function_image_uri` — cho Lambda

## Thứ tự apply

1. `infra/persistent` phải được apply trước
2. Sau đó mới apply `infra/main_infra`

## Backend

State được lưu tại: `s3://nmcnpm-tfstate/currency-exchange/main_infra.tfstate`
