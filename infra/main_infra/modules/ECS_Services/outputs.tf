output "money_service_name" {
  description = "Tên của Money Service ECS service"
  value       = aws_ecs_service.Money_Service.name
}

output "streaming_service_name" {
  description = "Tên của Streaming Exchange Rate ECS service"
  value       = aws_ecs_service.Streaming_Exchange_Rate_Service.name
}

output "tour_service_name" {
  description = "Tên của Tour Service ECS service"
  value       = aws_ecs_service.Tour_Service.name
}

output "forecast_service_name" {
  description = "Tên của Forecast Exchange Rate ECS service"
  value       = aws_ecs_service.Forecast_Exchange_Rate_Service.name
}
