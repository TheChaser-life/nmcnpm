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

# ── TLS / DNS ─────────────────────────────────────────────────────────────────

variable "cert_arn" {
  description = "ARN của ACM certificate cho HTTPS listener trên ALB"
  type        = string
}

# ── ML / SageMaker ────────────────────────────────────────────────────────────

variable "training_image" {
  description = "ECR URI của Docker image chứa training script"
  type        = string
}

variable "initial_model_package_arn" {
  description = "ARN của model package ban đầu trong SageMaker Model Registry"
  type        = string
}

# ── Alerting ──────────────────────────────────────────────────────────────────

variable "alert_email" {
  description = "Email nhận CloudWatch alarm notifications qua SNS"
  type        = string
}

# ── Backend ───────────────────────────────────────────────────────────────────

variable "backend_bucket" {
  description = "S3 bucket chứa Terraform state — dùng để đọc persistent remote state"
  type        = string
}

variable "backend_table" {
  description = "DynamoDB table cho Terraform state locking"
  type        = string
}
