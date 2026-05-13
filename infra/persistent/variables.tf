# ── Core ──────────────────────────────────────────────────────────────────────

variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-southeast-2"
}

variable "account_id" {
  description = "AWS Account ID"
  type        = string
}

# ── S3 Buckets ────────────────────────────────────────────────────────────────

variable "s3_vpc_gateway_endpoint_id" {
  description = "ID của VPC Gateway Endpoint cho S3 — lấy từ main_infra outputs"
  type        = string
}

variable "admin_iam_arns" {
  description = "ARN của IAM users/roles được phép truy cập S3 từ ngoài VPC (Terraform, CI/CD)"
  type        = list(string)
  default     = []
}

# ── Secrets & Parameter Store ─────────────────────────────────────────────────

variable "travelpayouts_api_key" {
  description = "API key cho Travelpayouts API"
  type        = string
  sensitive   = true
}

variable "viator_api_key" {
  description = "API key cho Viator Partner API"
  type        = string
  sensitive   = true
}

variable "exchange_rate_api_key" {
  description = "API key cho Exchange Rate API"
  type        = string
  sensitive   = true
}

variable "premium_fee" {
  description = "Phí nâng cấp Premium (VND)"
  type        = string
  default     = "100000"
}

variable "private_subnet_ids" {
  description = "Private Subnet IDs — lấy từ main_infra outputs"
  type        = list(string)
}

variable "lambda_sg_id" {
  description = "Security Group ID cho Lambda — lấy từ main_infra outputs"
  type        = string
}

# ── ECR & ECS Cluster ─────────────────────────────────────────────────────────

variable "public_subnet_ids" {
  description = "Public Subnet IDs — lấy từ main_infra outputs"
  type        = list(string)
}

variable "public_subnet_1_id" {
  description = "Public Subnet AZ1 ID"
  type        = string
}

variable "public_subnet_2_id" {
  description = "Public Subnet AZ2 ID"
  type        = string
}

variable "ecs_services_sg_id" {
  description = "Security Group ID cho ECS services"
  type        = string
}

variable "producer_sg_id" {
  description = "Security Group ID cho Producer services"
  type        = string
}

variable "user_pool_id" {
  description = "Cognito User Pool ID — lấy từ main_infra outputs"
  type        = string
  default     = ""
}

variable "sagemaker_endpoint" {
  description = "SageMaker Endpoint name — lấy từ main_infra outputs"
  type        = string
  default     = "forecast-endpoint"
}

variable "exchange_rate_producer_image_uri" {
  description = "ECR image URI cho Exchange Rate Producer"
  type        = string
  default     = ""
}

variable "streaming_exchange_rate_image_uri" {
  description = "ECR image URI cho Streaming Service"
  type        = string
  default     = ""
}

variable "dataset_maker_image_uri" {
  description = "ECR image URI cho Dataset Maker"
  type        = string
  default     = ""
}

variable "forecast_exchange_rate_image_uri" {
  description = "ECR image URI cho Forecast Service"
  type        = string
  default     = ""
}

variable "money_image_uri" {
  description = "ECR image URI cho Money Service"
  type        = string
  default     = ""
}

variable "tour_producer_image_uri" {
  description = "ECR image URI cho Tour Producer"
  type        = string
  default     = ""
}

variable "tour_service_image_uri" {
  description = "ECR image URI cho Tour Service"
  type        = string
  default     = ""
}

variable "redis_host" {
  description = "Exchange Rate Redis primary endpoint"
  type        = string
  default     = ""
}

variable "exchange_rate_redis_host" {
  description = "Exchange Rate Redis primary endpoint"
  type        = string
  default     = ""
}

variable "idempotency_redis_host" {
  description = "Idempotency Redis primary endpoint"
  type        = string
  default     = ""
}

variable "exchange_api_url" {
  description = "Base URL của External Exchange Rate API"
  type        = string
  default     = "https://v6.exchangerate-api.com/v6"
}

variable "db_host" {
  description = "RDS PostgreSQL primary endpoint hostname"
  type        = string
  default     = ""
}

variable "step_functions_state_machine_arn" {
  description = "ARN của Step Functions State Machine"
  type        = string
  default     = ""
}

variable "eventbridge_sfn_policy_arn" {
  description = "ARN của IAM Policy cho phép EventBridge trigger Step Functions"
  type        = string
  default     = ""
}

variable "rotate_redis_password_lambda_function_name" {
  description = "Tên của Lambda function dùng để rotate ElastiCache password"
  type        = string
  default     = ""
}

variable "rotate_redis_password_lambda_function_arn" {
  description = "ARN của Lambda function dùng để rotate ElastiCache password"
  type        = string
  default     = ""
}

variable "frontend_image_uri" {
  description = "ECR image URI cho Frontend"
  type        = string
  default     = ""
}
