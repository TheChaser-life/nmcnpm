# ── S3 Buckets ────────────────────────────────────────────────────────────────

output "training_data_bucket_name" {
  description = "Tên S3 bucket chứa training data CSV"
  value       = module.S3_Buckets.training_data_bucket_name
}

output "model_artifact_bucket_name" {
  description = "Tên S3 bucket lưu model artifacts"
  value       = module.S3_Buckets.model_artifact_bucket_name
}

output "tour_bucket_name" {
  description = "Tên S3 bucket chứa tour data"
  value       = module.S3_Buckets.tour_bucket_name
}

# ── Secrets Manager ───────────────────────────────────────────────────────────

output "rds_secret_arn" {
  description = "ARN của Secrets Manager secret chứa RDS credentials"
  value       = module.Secrets_Manager_and_Parameter_Store.rds_secret_arn
}

output "elasticache_secret_arn" {
  description = "ARN của Secrets Manager secret chứa ElastiCache password"
  value       = module.Secrets_Manager_and_Parameter_Store.elasticache_secret_arn
}

output "premium_fee_parameter_arn" {
  description = "ARN của SSM Parameter Store parameter cho premium_fee"
  value       = module.Secrets_Manager_and_Parameter_Store.premium_fee_parameter_arn
}

output "rds_password" {
  description = "RDS password (generated) — dùng bởi main_infra RDS module"
  value       = module.Secrets_Manager_and_Parameter_Store.rds_password
  sensitive   = true
}

output "elasticache_password" {
  description = "ElastiCache password (generated) — dùng bởi main_infra ElastiCache module"
  value       = module.Secrets_Manager_and_Parameter_Store.elasticache_password
  sensitive   = true
}

# ── ECR & ECS Cluster ─────────────────────────────────────────────────────────

output "ecs_cluster_arn" {
  description = "ARN của ECS Cluster"
  value       = module.ECR_and_ECS_Cluster.ecs_cluster_arn
}

output "ecs_cluster_id" {
  description = "ID của ECS Cluster"
  value       = module.ECR_and_ECS_Cluster.ecs_cluster_id
}

output "dataset_maker_task_definition_arn" {
  description = "ARN của Dataset Maker ECS Task Definition"
  value       = module.ECR_and_ECS_Cluster.dataset_maker_task_definition_arn
}

output "dataset_maker_task_role_arn" {
  description = "ARN của Dataset Maker IAM Task Role"
  value       = module.ECR_and_ECS_Cluster.dataset_maker_task_role_arn
}

output "ecs_task_execution_role_arn" {
  description = "ARN của ECS Task Execution Role"
  value       = module.ECR_and_ECS_Cluster.ecs_task_execution_role_arn
}

output "event_bridge_role_name" {
  description = "Tên của EventBridge IAM Role"
  value       = module.ECR_and_ECS_Cluster.event_bridge_role_name
}

output "post_confirmation_function_image_uri" {
  description = "ECR image URI cho post-confirmation Lambda"
  value       = module.ECR_and_ECS_Cluster.post_confirmation_function_image_uri
}

output "model_promotion_function_image_uri" {
  description = "ECR image URI cho model-promotion Lambda"
  value       = module.ECR_and_ECS_Cluster.model_promotion_function_image_uri
}

output "model_promotion_function_repository_url" {
  description = "ECR repository URL cho model-promotion Lambda"
  value       = module.ECR_and_ECS_Cluster.model_promotion_function_repository_url
}

output "forecast_exchange_rate_repo_url" {
  description = "ECR repository URL cho Forecast Service"
  value       = module.ECR_and_ECS_Cluster.forecast_exchange_rate_repo_url
}

output "tour_producer_repo_url" {
  description = "ECR repository URL cho Tour Producer"
  value       = module.ECR_and_ECS_Cluster.tour_producer_repo_url
}

output "scheduled_dataset_maker_rule_name" {
  description = "Tên của EventBridge scheduled rule cho Dataset Maker"
  value       = module.ECR_and_ECS_Cluster.scheduled_dataset_maker_rule_name
}

# ── ECS Task Definitions (cho ECS_Services module trong main_infra) ────────────

output "ecs_cluster_name" {
  description = "Tên của ECS Cluster"
  value       = module.ECR_and_ECS_Cluster.ecs_cluster_name
}

output "exchange_rate_producer_task_definition_arn" {
  description = "ARN của Exchange Rate Producer ECS Task Definition"
  value       = module.ECR_and_ECS_Cluster.exchange_rate_producer_task_definition_arn
}

output "streaming_task_definition_arn" {
  description = "ARN của Streaming Exchange Rate ECS Task Definition"
  value       = module.ECR_and_ECS_Cluster.streaming_task_definition_arn
}

output "forecast_task_definition_arn" {
  description = "ARN của Forecast Exchange Rate ECS Task Definition"
  value       = module.ECR_and_ECS_Cluster.forecast_task_definition_arn
}

output "money_service_task_definition_arn" {
  description = "ARN của Money Service ECS Task Definition"
  value       = module.ECR_and_ECS_Cluster.money_service_task_definition_arn
}

output "tour_service_task_definition_arn" {
  description = "ARN của Tour Service ECS Task Definition"
  value       = module.ECR_and_ECS_Cluster.tour_service_task_definition_arn
}

output "frontend_task_definition_arn" {
  description = "ARN cua Frontend ECS Task Definition"
  value       = module.ECR_and_ECS_Cluster.frontend_task_definition_arn
}

