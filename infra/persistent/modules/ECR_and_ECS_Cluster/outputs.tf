output "post_confirmation_function_image_uri" {
    value = "${aws_ecr_repository.post_confirmation_function.repository_url}:latest"
}

output "model_promotion_function_repository_url" {
    description = "ECR repository URL cho model-promotion Lambda — CI/CD push image vào đây"
    value       = aws_ecr_repository.model_promotion_function.repository_url
}

output "model_promotion_function_image_uri" {
    description = "ECR image URI ban đầu (tag :latest) — CI/CD sẽ update tag sau mỗi push"
    value       = "${aws_ecr_repository.model_promotion_function.repository_url}:latest"
}

output "ecs_cluster_arn" {
    description = "ARN của ECS Cluster"
    value       = aws_ecs_cluster.nmcnpm_cluster.arn
}

output "ecs_cluster_id" {
    description = "ID của ECS Cluster"
    value       = aws_ecs_cluster.nmcnpm_cluster.id
}

output "ecs_cluster_name" {
    description = "Tên của ECS Cluster — dùng cho auto-scaling resource_id"
    value       = aws_ecs_cluster.nmcnpm_cluster.name
}

output "dataset_maker_task_definition_arn" {
    description = "ARN của Dataset Maker ECS Task Definition"
    value       = aws_ecs_task_definition.Dataset_Maker_Task_Definition.arn
}

output "dataset_maker_task_role_arn" {
    description = "ARN của Dataset Maker IAM Task Role"
    value       = aws_iam_role.Dataset_Maker_Task_Role.arn
}

output "ecs_task_execution_role_arn" {
    description = "ARN của ECS Task Execution Role"
    value       = aws_iam_role.ecs_task_execution_role.arn
}

output "event_bridge_role_name" {
    description = "Tên của EventBridge IAM Role (để attach thêm policy)"
    value       = aws_iam_role.event_bridge_role.name
}

output "scheduled_dataset_maker_rule_name" {
    description = "Tên của EventBridge scheduled rule cho Dataset Maker"
    value       = aws_cloudwatch_event_rule.scheduled_dataset_maker_task.name
}

output "forecast_exchange_rate_repo_url" {
    description = "ECR repository URL cho Forecast Service — CI/CD push image vào đây"
    value       = aws_ecr_repository.forecast_exchange_rate_repo.repository_url
}

output "forecast_exchange_rate_image_uri" {
    description = "ECR image URI ban đầu (tag :latest)"
    value       = "${aws_ecr_repository.forecast_exchange_rate_repo.repository_url}:latest"
}

output "money_service_image_uri" {
    description = "ECR image URI cho Money Service (tag :latest)"
    value       = "${aws_ecr_repository.update_money_repo.repository_url}:latest"
}

output "money_service_task_definition_arn" {
    description = "ARN of the Money Service ECS Task Definition"
    value       = aws_ecs_task_definition.Money_Service_Task_Definition.arn
}

output "money_service_task_role_arn" {
    description = "ARN of the Money Service IAM Task Role"
    value       = aws_iam_role.Money_Service_Task_Role.arn
}

output "money_service_log_group_name" {
    description = "CloudWatch Log Group name for Money Service logs"
    value       = aws_cloudwatch_log_group.money_service_logs.name
}

output "tour_producer_repo_url" {
    description = "ECR repository URL cho Tour Producer"
    value       = aws_ecr_repository.tour_producer_repo.repository_url
}

output "tour_producer_image_uri" {
    description = "ECR image URI ban đầu (tag :latest)"
    value       = "${aws_ecr_repository.tour_producer_repo.repository_url}:latest"
}

output "tour_producer_task_definition_arn" {
    description = "ARN của Tour Producer ECS Task Definition"
    value       = aws_ecs_task_definition.Tour_Producer_Task_Definition.arn
}

output "tour_producer_task_role_arn" {
    description = "ARN của Tour Producer IAM Task Role"
    value       = aws_iam_role.Tour_Producer_Task_Role.arn
}

output "scheduled_tour_producer_rule_name" {
    description = "Tên của EventBridge scheduled rule cho Tour Producer"
    value       = aws_cloudwatch_event_rule.scheduled_tour_producer_task.name
}

output "tour_service_image_uri" {
    description = "ECR image URI for Tour Service (tag :latest)"
    value       = "${aws_ecr_repository.tour_display_repo.repository_url}:latest"
}

output "tour_service_task_definition_arn" {
    description = "ARN of the Tour Service ECS Task Definition"
    value       = aws_ecs_task_definition.Tour_Service_Task_Definition.arn
}

output "exchange_rate_producer_task_definition_arn" {
    description = "ARN của Exchange Rate Producer ECS Task Definition"
    value       = aws_ecs_task_definition.Exchange_Rate_Producer_Task_Definition.arn
}

output "streaming_task_definition_arn" {
    description = "ARN của Streaming Exchange Rate ECS Task Definition"
    value       = aws_ecs_task_definition.Streaming_Exchange_Rate_Task_Definition.arn
}

output "forecast_task_definition_arn" {
    description = "ARN của Forecast Exchange Rate ECS Task Definition"
    value       = aws_ecs_task_definition.Forecast_Exchange_Rate_Task_Definition.arn
}

output "exchange_rate_producer_az1_service_name" {
    description = "Tên ECS service AZ1"
    value       = "Exchange_Rate_Producer_Service_AZ_1"
}

output "exchange_rate_producer_az2_service_name" {
    description = "Tên ECS service AZ2"
    value       = "Exchange_Rate_Producer_Service_AZ_22"
}

output "frontend_image_uri" {
    description = "ECR image URI cho Frontend (tag :latest)"
    value       = "${aws_ecr_repository.frontend_repo.repository_url}:latest"
}

output "frontend_task_definition_arn" {
    description = "ARN của Frontend ECS Task Definition"
    value       = aws_ecs_task_definition.Frontend_Task_Definition.arn
}
