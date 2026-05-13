Dưới đây là toàn bộ các bước theo đúng thứ tự phụ thuộc:

---

## Bước 1 — Bootstrap Terraform Backend

```bash
bash initiate_terraform_backend.sh
```

Sau khi chạy xong, copy bucket name từ output và bật backend trong `infra/persistent/main.tf` và `infra/main_infra/main.tf`.

---

## Bước 2 — Apply `persistent` lần 1

Tạo S3, ECR repos, ECS Cluster, Task Definitions, Secrets Manager.

```bash
cd infra/persistent
terraform init
terraform apply
```

Lấy outputs:
```bash
terraform output
```

---

## Bước 3 — Apply `main_infra` lần 1

Tạo VPC, ALB, RDS, ElastiCache, Cognito, Lambda, SageMaker, StepFunctions, ECS Services.

Trước tiên điền vào `infra/main_infra/terraform.tfvars`:
```
cert_arn = ""   # để trống, điền sau khi có ACM cert
```

```bash
cd infra/main_infra
terraform init
terraform apply
```

Lấy outputs:
```bash
terraform output
```

---

## Bước 4 — Điền networking outputs vào `persistent/terraform.tfvars`

```bash
# Lấy từ main_infra outputs
cd infra/main_infra
terraform output vpc_id
terraform output public_subnet_ids
terraform output private_subnet_ids
# ... v.v.
```

Điền vào `infra/persistent/terraform.tfvars`:
```hcl
s3_vpc_gateway_endpoint_id = "vpce-xxx"
private_subnet_ids          = ["subnet-xxx", "subnet-yyy"]
lambda_sg_id                = "sg-xxx"
public_subnet_ids           = ["subnet-aaa", "subnet-bbb"]
public_subnet_1_id          = "subnet-aaa"
public_subnet_2_id          = "subnet-bbb"
ecs_services_sg_id          = "sg-yyy"
producer_sg_id              = "sg-zzz"
redis_host                  = "xxx.cache.amazonaws.com"
exchange_rate_redis_host    = "xxx.cache.amazonaws.com"
idempotency_redis_host      = "yyy.cache.amazonaws.com"
db_host                     = "xxx.rds.amazonaws.com"
user_pool_id                = "ap-southeast-1_xxx"
step_functions_state_machine_arn = "arn:aws:states:..."
eventbridge_sfn_policy_arn       = "arn:aws:iam::..."
rotate_redis_password_lambda_function_name = "nmcnpm-rotate-redis"
rotate_redis_password_lambda_function_arn  = "arn:aws:lambda:..."
```

Apply lại persistent để bật rotation:
```bash
cd infra/persistent
terraform apply
```

---

## Bước 5 — DNS và TLS Certificate

**5.1** Lấy ALB DNS name:
```bash
cd infra/main_infra
terraform output alb_dns_name
```

**5.2** Vào Cloudflare → tạo CNAME record trỏ domain về ALB DNS name (tắt proxy)

**5.3** Vào AWS ACM → request certificate → DNS validation → thêm CNAME vào Cloudflare

**5.4** Chờ certificate `ISSUED`, điền vào `main_infra/terraform.tfvars`:
```hcl
cert_arn = "arn:aws:acm:ap-southeast-1:..."
```

```bash
cd infra/main_infra
terraform apply
```

---

## Bước 6 — Chạy DB Migrations

```bash
# Kết nối qua AWS Systems Manager Session Manager hoặc bastion
psql -h <rds-endpoint> -U postgres -d currency_exchange \
  -f db/migrations/V1__create_users_table.sql \
  -f db/migrations/V2__create_transactions_table.sql \
  -f db/migrations/V3__create_indexes.sql \
  -f db/migrations/V4__add_premium_deducted_column.sql
```

---

## Bước 7 — Build và Push Docker Images lần đầu

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="ap-southeast-1"
REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# Login ECR
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $REGISTRY

# Build và push từng service
for SERVICE in exchange-rate-producer streaming-service money-service \
               forecast-service tour-producer tour-service dataset-maker frontend; do
  docker build -t "$REGISTRY/${SERVICE}-repo:latest" "services/$SERVICE"
  docker push "$REGISTRY/${SERVICE}-repo:latest"
done

# forecast-training (SageMaker training image)
docker build -t "$REGISTRY/forecast-training:latest" services/forecast-training
docker push "$REGISTRY/forecast-training:latest"
```

---

## Bước 8 — Điền Image URIs và Apply lại

Điền vào `persistent/terraform.tfvars`:
```hcl
exchange_rate_producer_image_uri  = "<account>.dkr.ecr.ap-southeast-1.amazonaws.com/exchange-rate-producer-repo:latest"
streaming_exchange_rate_image_uri = "<account>.dkr.ecr.ap-southeast-1.amazonaws.com/streaming-service-repo:latest"
dataset_maker_image_uri           = "<account>.dkr.ecr.ap-southeast-1.amazonaws.com/dataset-maker-repo:latest"
forecast_exchange_rate_image_uri  = "<account>.dkr.ecr.ap-southeast-1.amazonaws.com/forecast-service-repo:latest"
money_image_uri                   = "<account>.dkr.ecr.ap-southeast-1.amazonaws.com/money-service-repo:latest"
tour_producer_image_uri           = "<account>.dkr.ecr.ap-southeast-1.amazonaws.com/tour-producer-repo:latest"
tour_service_image_uri            = "<account>.dkr.ecr.ap-southeast-1.amazonaws.com/tour-service-repo:latest"
```

Điền `training_image` vào `main_infra/terraform.tfvars`:
```hcl
training_image = "<account>.dkr.ecr.ap-southeast-1.amazonaws.com/forecast-training:latest"
```

```bash
cd infra/persistent && terraform apply
cd infra/main_infra && terraform apply
```

---

## Bước 9 — Chạy ML Pipeline lần đầu

```bash
STATE_MACHINE_ARN=$(cd infra/main_infra && terraform output -raw step_functions_state_machine_arn)

aws stepfunctions start-execution \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --name "initial-training-$(date +%s)"
```

Chờ Training Job hoàn thành (~30-60 phút), lấy model ARN:
```bash
aws sagemaker list-model-packages \
  --model-package-group-name forecast-model-registry \
  --sort-by CreationTime --sort-order Descending \
  --query 'ModelPackageSummaryList[0].ModelPackageArn' \
  --output text
```

Điền vào `main_infra/terraform.tfvars`:
```hcl
initial_model_package_arn = "arn:aws:sagemaker:..."
```

```bash
cd infra/main_infra && terraform apply
```

---

## Bước 10 — Cấu hình GitHub Actions

Thêm secrets vào GitHub repo → Settings → Secrets:

| Secret | Giá trị |
|---|---|
| `AWS_OIDC_ROLE_ARN` | ARN IAM Role OIDC |
| `AWS_REGION` | `ap-southeast-1` |
| `ECS_CLUSTER_NAME` | Tên ECS Cluster |
| `SONAR_TOKEN` | Token SonarCloud |
| `SONAR_HOST_URL` | URL SonarQube |
| `ORGANIZATION` | Org key SonarCloud |
| `PROJECT_KEY` | Project key SonarCloud |
| `PAT_TOKEN` | GitHub Personal Access Token |
| `TF_VAR_EXCHANGE_RATE_API_KEY` | API key ExchangeRate-API |
| `TF_VAR_TRAVELPAYOUTS_API_KEY` | API key Travelpayouts |

Bật branch protection trên `main`: yêu cầu `build-test-scan` pass trước khi merge.

---

## Tóm tắt thứ tự

```
Bootstrap S3/DynamoDB
    ↓
persistent apply (lần 1) — S3, ECR, Secrets, ECS Cluster
    ↓
main_infra apply (lần 1) — VPC, RDS, ElastiCache, Lambda, Cognito...
    ↓
persistent apply (lần 2) — bật rotation với Lambda ARN
    ↓
DNS + ACM cert → main_infra apply (lần 2) — gắn cert vào ALB
    ↓
DB migrations
    ↓
Build & push Docker images
    ↓
persistent + main_infra apply (lần 3) — Task Definitions với image URIs thật
    ↓
Chạy ML pipeline lần đầu → lấy model ARN
    ↓
main_infra apply (lần 4) — deploy SageMaker Endpoint
    ↓
Cấu hình GitHub secrets + branch protection
    ↓
CI/CD tự động từ đây
```