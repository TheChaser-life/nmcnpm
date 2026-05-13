# ── Core ──────────────────────────────────────────────────────────────────────

variable "region" {
  description = "AWS region để deploy toàn bộ hệ thống"
  type        = string
  default     = "ap-southeast-1"
}

variable "project_name" {
  description = "Tên project — dùng để đặt tên resource"
  type        = string
}

variable "account_id" {
  description = "AWS Account ID"
  type        = string
}

# ── TLS / DNS ─────────────────────────────────────────────────────────────────

variable "cert_arn" {
  description = "ARN của ACM certificate cho HTTPS listener trên ALB (task 0.5.3)"
  type        = string
}

# ── ML / SageMaker ────────────────────────────────────────────────────────────

variable "training_image" {
  description = "ECR URI của Docker image chứa training script (forecast-training service)"
  type        = string
}

variable "initial_model_package_arn" {
  description = "ARN của model package ban đầu trong SageMaker Model Registry để deploy lên Endpoint lần đầu. Sau khi pipeline chạy lần đầu, model promotion Lambda sẽ tự động cập nhật."
  type        = string
}

# ── ECR Image URIs ────────────────────────────────────────────────────────────
# Điền sau khi build và push Docker images lần đầu (task 9.3.2 / 9.3.6)

variable "exchange_rate_producer_image_uri" {
  description = "ECR image URI cho Exchange Rate Producer service"
  type        = string
  default     = ""
}

variable "streaming_exchange_rate_image_uri" {
  description = "ECR image URI cho Streaming Service (WebSocket)"
  type        = string
  default     = ""
}

variable "dataset_maker_image_uri" {
  description = "ECR image URI cho Dataset Maker service"
  type        = string
  default     = ""
}

variable "tour_producer_image_uri" {
  description = "ECR image URI cho Tour Producer service"
  type        = string
  default     = ""
}

# ── External APIs ─────────────────────────────────────────────────────────────

variable "exchange_api_url" {
  description = "Base URL của External Exchange Rate API (ví dụ: https://v6.exchangerate-api.com/v6)"
  type        = string
}

variable "exchange_rate_api_key" {
  description = "API key cho External Exchange Rate API — lưu vào Secrets Manager"
  type        = string
  sensitive   = true
}

variable "travelpayouts_api_key" {
  description = "API key cho Travelpayouts API (tour data) — lưu vào Secrets Manager"
  type        = string
  sensitive   = true
}

# ── Business Config ───────────────────────────────────────────────────────────

variable "premium_fee" {
  description = "Phí nâng cấp Premium tính bằng VND giả lập — lưu vào SSM Parameter Store"
  type        = string
  default     = "100000"
}

# ── Alerting ──────────────────────────────────────────────────────────────────

variable "alert_email" {
  description = "Email nhận CloudWatch alarm notifications qua SNS"
  type        = string
}

# Backend
variable "backend_bucket" {
  type = string  
}

variable "backend_table" {
  type = string  
}