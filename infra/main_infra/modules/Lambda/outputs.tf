output "post_confirmation_function_arn" {
    description = "ARN của post-confirmation Lambda function"
    value       = length(aws_lambda_function.post_confirmation_function) > 0 ? aws_lambda_function.post_confirmation_function[0].arn : "arn:aws:lambda:${var.aws_region}:571832839909:function:dummy"
}

output "post_confirmation_function_name" {
    description = "Tên của post-confirmation Lambda function"
    value       = length(aws_lambda_function.post_confirmation_function) > 0 ? aws_lambda_function.post_confirmation_function[0].function_name : "dummy"
}

output "model_promotion_function_arn" {
    description = "ARN của model promotion Lambda function"
    value       = length(aws_lambda_function.model_promotion_function) > 0 ? aws_lambda_function.model_promotion_function[0].arn : "arn:aws:lambda:${var.aws_region}:571832839909:function:dummy"
}

output "model_promotion_function_name" {
    description = "Tên của model promotion Lambda function"
    value       = length(aws_lambda_function.model_promotion_function) > 0 ? aws_lambda_function.model_promotion_function[0].function_name : "dummy"
}
