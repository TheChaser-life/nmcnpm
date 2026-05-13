variable "post_confirmation_function_image_uri" {
    description = "ECR image URI cho post-confirmation Lambda (tag ban đầu, CI/CD sẽ update sau)"
    type        = string
}

variable "cert_arn" {
    type    = string
    default = ""
}

variable "rds_secret_arn" {
    description = "ARN của Secrets Manager secret chứa RDS credentials {username, password}"
    type        = string
}

variable "db_host" {
    description = "RDS endpoint hostname"
    type        = string
}

variable "db_name" {
    description = "Tên database PostgreSQL"
    type        = string
    default     = "currency_exchange"
}

variable "private_subnet_ids" {
    description = "Danh sách Private Subnet IDs để Lambda chạy trong VPC"
    type        = list(string)
}

variable "lambda_sg_id" {
    description = "Security Group ID cho Lambda (cần outbound đến RDS port 5432 và Secrets Manager 443)"
    type        = string
}

variable "cognito_user_pool_arn" {
    description = "ARN của Cognito User Pool để cấp quyền invoke Lambda"
    type        = string
}

# ── Model Promotion Lambda variables ─────────────────────────────────────────

variable "model_promotion_function_image_uri" {
    description = "ECR image URI cho model-promotion Lambda (tag ban đầu, CI/CD sẽ update sau)"
    type        = string
}

variable "model_package_group_name" {
    description = "Tên SageMaker Model Package Group — dùng để giới hạn quyền UpdateModelPackage"
    type        = string
    default     = "forecast_model_registry"
}

variable "model_artifact_bucket" {
    description = "Tên S3 bucket chứa model artifacts và metrics.json"
    type        = string
}

variable "sagemaker_endpoint_name" {
    description = "Tên SageMaker Endpoint mà model promotion Lambda có thể update"
    type        = string
    default     = "forecast-endpoint"
}

variable "step_functions_state_machine_arn" {
    description = "ARN của Step Functions State Machine được phép invoke model promotion Lambda"
    type        = string
}

variable "aws_region" {
    description = "AWS region cho Lambda environment variable"
    type        = string
    default     = "ap-southeast-2"
}

variable "sagemaker_execution_role_arn" {
    description = "ARN của IAM Role mà SageMaker dùng để tạo Model resource (cần PassRole từ Lambda)"
    type        = string
}
