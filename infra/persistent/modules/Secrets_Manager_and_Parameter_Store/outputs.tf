output "rds_password" {
    value = random_password.db_generate_pass.result
}

output "elasticache_password" {
    value = random_password.elasticache_generate_pass.result
}

output "rds_secret_arn" {
    description = "ARN của Secrets Manager secret chứa RDS credentials (JSON format)"
    value       = aws_secretsmanager_secret.rds_password.arn
}

output "elasticache_secret_arn" {
    description = "ARN của Secrets Manager secret chứa ElastiCache password"
    value       = aws_secretsmanager_secret.elasticache_password.arn
}

output "premium_fee_parameter_arn" {
    description = "ARN của SSM Parameter Store parameter cho premium_fee"
    value       = aws_ssm_parameter.premium_fee.arn
}
