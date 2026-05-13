variable "training_image" {
    description = "ECR URI của Docker image chứa training script (forecast-training)"
    type        = string
}

variable "sagemaker_sg_id" {
    description = "Security Group ID cho SageMaker Training Job và Endpoint"
    type        = string
}

variable "private_subnet_ids" {
    description = "Danh sách Private Subnet IDs để SageMaker chạy trong VPC"
    type        = list(string)
}

variable "model_artifact_bucket" {
    description = "Tên S3 bucket lưu model artifacts (output của Training Job)"
    type        = string
}

variable "training_data_bucket" {
    description = "Tên S3 bucket chứa training data CSV từ Dataset Maker"
    type        = string
}

# ── Variables cho SageMaker Endpoint (task 5.4) ───────────────────────────────

variable "region" {
    description = "AWS region — dùng để xây dựng ARN của model package"
    type        = string
}

variable "account_id" {
    description = "AWS Account ID — dùng để xây dựng ARN của model package"
    type        = string
}

variable "initial_model_package_arn" {
    description = "ARN của model package ban đầu trong Model Registry để deploy lên Endpoint lần đầu. Sau khi hệ thống chạy, model promotion Lambda sẽ tự động cập nhật Endpoint khi có model tốt hơn."
    type        = string
}
