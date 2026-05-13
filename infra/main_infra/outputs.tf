# ── VPC & Networking ────────────────────────────────────────────────────────
output "producer_sg_id" {
  description = "Security Group ID cho Producer tasks (cho phép outbound internet)"
  value       = module.VPC_and_Networking.producer_sg_id
}

output "ecs_services_sg_id" {
  description = "Security Group ID cho các ECS Services nội bộ"
  value       = module.VPC_and_Networking.ecs_services_sg_id
}

# ── ElastiCache (Redis/Valkey) ────────────────────────────────────────────────
output "redis_host" {
  description = "Redis host (trỏ về exchange rate cluster để tương thích code cũ)"
  value       = module.ElastiCache.exchange_rate_redis_primary_endpoint
}

output "exchange_rate_redis_host" {
  description = "Redis host cho Exchange Rate cache"
  value       = module.ElastiCache.exchange_rate_redis_primary_endpoint
}

output "idempotency_redis_host" {
  description = "Redis host cho Idempotency cache"
  value       = module.ElastiCache.idempotency_redis_primary_endpoint
}

# ── RDS PostgreSQL ────────────────────────────────────────────────────────────
output "db_host" {
  description = "RDS PostgreSQL Primary Endpoint hostname"
  value       = module.RDS_Postgre.db_endpoint
}

# ── Cognito ───────────────────────────────────────────────────────────────────
output "user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.Cognito.user_pool_id
}

output "user_pool_client_id" {
  description = "Cognito App Client ID (cho frontend)"
  value       = module.Cognito.user_pool_client_id
}

# ── Step Functions & EventBridge ─────────────────────────────────────────────
output "step_functions_state_machine_arn" {
  description = "ARN của Step Functions State Machine (ML Pipeline)"
  value       = module.StepFunctions.state_machine_arn
}

output "eventbridge_sfn_policy_arn" {
  description = "ARN của IAM Policy cấp quyền cho EventBridge trigger Step Functions"
  value       = module.StepFunctions.eventbridge_sfn_policy_arn
}

# ── ALB ───────────────────────────────────────────────────────────────────────
output "alb_dns_name" {
  description = "DNS name của Application Load Balancer"
  value       = module.ALB.alb_dns_name
}

# ── Lambda (Missing) ──────────────────────────────────────────────────────────
output "rotate_redis_password_lambda_function_name" {
  description = "Chưa được tạo trong main_infra (sẽ implement sau)"
  value       = ""
}

output "rotate_redis_password_lambda_function_arn" {
  description = "Chưa được tạo trong main_infra (sẽ implement sau)"
  value       = ""
}
