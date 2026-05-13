variable "region" {
    type = string
}

variable "account_id" {
    type = string
}

variable "user_pool_id" {
    type    = string
    default = ""
}

variable "sagemaker_endpoint" {
    type    = string
    default = ""
}

variable "s3_tour_bucket_name" {
    type = string
}

variable "s3_dataset_bucket_name" {
    type = string
}

variable "Exchange_Rate_Producer_Image_URI" {
    type = string
}

variable "public_subnet_ids" {
    type = list(string)
}

variable "producer_sg_id" {
    type = string
}

variable "redis_host" {
    type    = string
    default = ""
}

variable "exchange_api_url" {
    type    = string
    default = "https://v6.exchangerate-api.com/v6"
}

variable "public_subnet_1_id" {
    type = string
}

variable "public_subnet_2_id" {
    type = string
}

variable "Streaming_Exchange_Rate_Image_URI" {
    type = string
}

variable "private_subnet_ids" {
    type = list(string)
}

variable "ecs_services_sg_id" {
    type = string
}

variable "Dataset_Maker_Image_URI" {
    type = string
}

variable "step_functions_state_machine_arn" {
    description = "ARN của Step Functions State Machine (ML Training Pipeline) — EventBridge target"
    type        = string
}

variable "eventbridge_sfn_policy_arn" {
    description = "ARN của IAM Policy cho phép EventBridge trigger Step Functions"
    type        = string
}

# ── Money Service variables ───────────────────────────────────────────────────

variable "db_host" {
    description = "RDS PostgreSQL primary endpoint hostname"
    type        = string
    default     = ""
}

variable "rds_secret_arn" {
    description = "ARN of the Secrets Manager secret containing RDS credentials"
    type        = string
    default     = ""
}

variable "elasticache_secret_arn" {
    description = "ARN of the Secrets Manager secret containing the ElastiCache password"
    type        = string
    default     = ""
}

variable "exchange_rate_redis_host" {
    description = "Primary endpoint hostname of the Exchange Rate ElastiCache cluster"
    type        = string
    default     = ""
}

variable "idempotency_redis_host" {
    description = "Primary endpoint hostname of the Idempotency ElastiCache cluster"
    type        = string
    default     = ""
}

variable "premium_fee_parameter_arn" {
    description = "ARN of the SSM Parameter Store parameter for premium_fee"
    type        = string
    default     = ""
}

variable "Forecast_Exchange_Rate_Image_URI" {
    type    = string
    default = ""
}

variable "Money_Image_URI" {
    type    = string
    default = ""
}

variable "Tour_Producer_Image_URI" {
    type    = string
    default = ""
}

variable "Tour_Service_Image_URI" {
    type    = string
    default = ""
}