output "sagemaker_training_role_arn" {
    description = "ARN của IAM Role cho SageMaker Training Job — dùng bởi Step Functions"
    value       = aws_iam_role.sagemaker_training_role.arn
}

output "model_package_group_name" {
    description = "Tên của SageMaker Model Package Group (Model Registry)"
    value       = aws_sagemaker_model_package_group.forecast_model_registry.model_package_group_name
}

output "model_package_group_arn" {
    description = "ARN của SageMaker Model Package Group (Model Registry)"
    value       = aws_sagemaker_model_package_group.forecast_model_registry.arn
}

output "sagemaker_endpoint_name" {
    description = "Tên của SageMaker Endpoint — dùng bởi Forecast Service và model promotion Lambda"
    value       = "forecast-endpoint"
}
