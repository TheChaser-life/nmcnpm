output "alb_arn" {
    value = aws_alb.alb.arn
}

output "alb_dns_name" {
    value = aws_alb.alb.dns_name
}

output "frontend_target_group_arn_suffix" {
    value = aws_alb_target_group.frontend_tg.arn_suffix
}

output "alb_arn_suffix" {
    value = aws_alb.alb.arn_suffix
}
output "streaming_exchange_rate_target_group_arn_suffix" {
    value = aws_alb_target_group.streaming_exchange_rate_tg.arn_suffix
}

output "update_user_money_target_group_arn_suffix" {
    value = aws_alb_target_group.update_money_tg.arn_suffix
}

output "forecast_exchange_rate_target_group_arn_suffix" {
    value = aws_alb_target_group.forecast_exchange_rate_tg.arn_suffix
}

output "tour_display_target_group_arn_suffix" {
    value = aws_alb_target_group.tour_display_tg.arn_suffix
}

output "streaming_exchange_rate_target_group_arn" {
    value = aws_alb_target_group.streaming_exchange_rate_tg.arn
}

output "update_money_target_group_arn" {
    description = "ARN of the ALB target group for the Money Service (update_money)"
    value       = aws_alb_target_group.update_money_tg.arn
}

output "forecast_target_group_arn" {
    description = "ARN of the ALB target group for the Forecast Service"
    value       = aws_alb_target_group.forecast_exchange_rate_tg.arn
}

output "tour_service_target_group_arn" {
    description = "ARN of the ALB target group for the Tour Service"
    value       = aws_alb_target_group.tour_display_tg.arn
}

output "frontend_target_group_arn" {
    description = "ARN of the ALB target group for the Frontend"
    value       = aws_alb_target_group.frontend_tg.arn
}
