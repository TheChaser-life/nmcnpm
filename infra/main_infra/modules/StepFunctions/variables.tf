variable "region" {
    description = "AWS region"
    type        = string
}

variable "account_id" {
    description = "AWS account ID"
    type        = string
}

# ECS — Dataset Maker
variable "ecs_cluster_arn" {
    description = "ARN của ECS Cluster chứa Dataset Maker task"
    type        = string
}

variable "dataset_maker_task_definition_arn" {
    description = "ARN của Dataset Maker ECS Task Definition"
    type        = string
}

variable "dataset_maker_task_role_arn" {
    description = "ARN của IAM Task Role của Dataset Maker (cần PassRole)"
    type        = string
}

variable "ecs_task_execution_role_arn" {
    description = "ARN của ECS Task Execution Role (cần PassRole)"
    type        = string
}

variable "private_subnet_ids" {
    description = "Private Subnet IDs để chạy Dataset Maker ECS task"
    type        = list(string)
}

variable "ecs_services_sg_id" {
    description = "Security Group ID cho ECS services"
    type        = string
}

# SageMaker — Training Job
variable "sagemaker_training_role_arn" {
    description = "ARN của IAM Role cho SageMaker Training Job"
    type        = string
}

variable "training_image" {
    description = "ECR URI của Docker image chứa training script"
    type        = string
}

variable "training_data_bucket" {
    description = "Tên S3 bucket chứa training data CSV từ Dataset Maker"
    type        = string
}

variable "model_artifact_bucket" {
    description = "Tên S3 bucket lưu model artifacts"
    type        = string
}

variable "sagemaker_sg_id" {
    description = "Security Group ID cho SageMaker Training Job"
    type        = string
}

variable "model_package_group_name" {
    description = "Tên của SageMaker Model Package Group — dùng để đăng ký model sau khi training"
    type        = string
}

variable "model_promotion_lambda_arn" {
    description = "ARN của model promotion Lambda function — được gọi sau khi Training Job hoàn thành để so sánh và promote model tốt nhất"
    type        = string
}
