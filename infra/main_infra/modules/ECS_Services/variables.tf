variable "ecs_cluster_arn" {
  description = "ARN của ECS Cluster — lấy từ persistent outputs"
  type        = string
}

variable "ecs_cluster_name" {
  description = "Tên của ECS Cluster — dùng cho auto-scaling resource_id"
  type        = string
}

variable "exchange_rate_producer_task_definition_arn" {
  description = "ARN của Exchange Rate Producer ECS Task Definition"
  type        = string
}

variable "streaming_task_definition_arn" {
  description = "ARN của Streaming Exchange Rate ECS Task Definition"
  type        = string
}

variable "forecast_task_definition_arn" {
  description = "ARN của Forecast Exchange Rate ECS Task Definition"
  type        = string
}

variable "money_service_task_definition_arn" {
  description = "ARN của Money Service ECS Task Definition"
  type        = string
}

variable "tour_service_task_definition_arn" {
  description = "ARN của Tour Service ECS Task Definition"
  type        = string
}

# Networking
variable "public_subnet_1_id" {
  description = "Public Subnet AZ1 ID — cho Exchange Rate Producer AZ1"
  type        = string
}

variable "public_subnet_2_id" {
  description = "Public Subnet AZ2 ID — cho Exchange Rate Producer AZ2"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private Subnet IDs — cho các services chạy trong private subnets"
  type        = list(string)
}

variable "producer_sg_id" {
  description = "Security Group ID cho Producer services"
  type        = string
}

variable "ecs_services_sg_id" {
  description = "Security Group ID cho ECS services"
  type        = string
}

# ALB Target Groups
variable "streaming_target_group_arn" {
  description = "ARN của ALB Target Group cho Streaming Service"
  type        = string
}

variable "forecast_target_group_arn" {
  description = "ARN của ALB Target Group cho Forecast Service"
  type        = string
}

variable "update_money_target_group_arn" {
  description = "ARN của ALB Target Group cho Money Service"
  type        = string
}

variable "tour_service_target_group_arn" {
  description = "ARN của ALB Target Group cho Tour Service"
  type        = string
}

variable "money_service_desired_count" {
  description = "Số lượng Money Service ECS tasks (tối thiểu 2 cho Multi-AZ)"
  type        = number
  default     = 2
}

variable "frontend_task_definition_arn" {
  description = "ARN c?a Frontend ECS Task Definition"
  type        = string
}

variable "frontend_target_group_arn" {
  description = "ARN c?a ALB Target Group cho Frontend"
  type        = string
}

