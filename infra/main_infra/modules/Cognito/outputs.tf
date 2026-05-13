output "user_pool_id" {
  description = "ID của Cognito User Pool — dùng bởi ECR_and_ECS_Cluster và Lambda modules"
  value       = aws_cognito_user_pool.nmcnpm_user_pool.id
}

output "user_pool_arn" {
  description = "ARN của Cognito User Pool — dùng bởi Lambda module để cấp quyền invoke"
  value       = aws_cognito_user_pool.nmcnpm_user_pool.arn
}

output "user_pool_client_id" {
  description = "App Client ID cho frontend (Amplify)"
  value       = aws_cognito_user_pool_client.nmcnpm_frontend_client.id
}
