output "state_machine_arn" {
    description = "ARN của Step Functions State Machine (ML Training Pipeline)"
    value       = aws_sfn_state_machine.ml_training_pipeline.arn
}

output "eventbridge_sfn_policy_arn" {
    description = "ARN của IAM Policy cho phép EventBridge trigger Step Functions"
    value       = aws_iam_policy.eventbridge_sfn_policy.arn
}
