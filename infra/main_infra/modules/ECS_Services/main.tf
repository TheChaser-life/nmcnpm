# ── Exchange Rate Producer Services ──────────────────────────────────────────

resource "aws_ecs_service" "Exchange_Rate_Producer_Service_AZ_1" {
  name            = "Exchange_Rate_Producer_Service_AZ_1"
  cluster         = var.ecs_cluster_arn
  task_definition = var.exchange_rate_producer_task_definition_arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = [var.public_subnet_1_id]
    security_groups  = [var.producer_sg_id]
    assign_public_ip = true
  }
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
}

resource "aws_ecs_service" "Exchange_Rate_Producer_Service_AZ_2" {
  name            = "Exchange_Rate_Producer_Service_AZ_22"
  cluster         = var.ecs_cluster_arn
  task_definition = var.exchange_rate_producer_task_definition_arn
  desired_count   = 0
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = [var.public_subnet_2_id]
    security_groups  = [var.producer_sg_id]
    assign_public_ip = true
  }
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
}

# Auto-scaling cho AZ2 producer
resource "aws_appautoscaling_target" "producer_az2_scaling_target" {
  max_capacity       = 1
  min_capacity       = 0
  resource_id        = "service/${var.ecs_cluster_name}/${aws_ecs_service.Exchange_Rate_Producer_Service_AZ_2.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "producer_az2_scale_up" {
  name               = "producer-az2-scale-up"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.producer_az2_scaling_target.resource_id
  scalable_dimension = aws_appautoscaling_target.producer_az2_scaling_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.producer_az2_scaling_target.service_namespace
  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"
    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 1
    }
  }
}

resource "aws_appautoscaling_policy" "producer_az2_scale_down" {
  name               = "producer-az2-scale-down"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.producer_az2_scaling_target.resource_id
  scalable_dimension = aws_appautoscaling_target.producer_az2_scaling_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.producer_az2_scaling_target.service_namespace
  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 120
    metric_aggregation_type = "Maximum"
    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = 0
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "producer_az1_down" {
  alarm_name          = "exchange-rate-producer-az1-down"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "RunningTaskCount"
  namespace           = "ECS/ContainerInsights"
  period              = 30
  statistic           = "Maximum"
  threshold           = 1
  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = aws_ecs_service.Exchange_Rate_Producer_Service_AZ_1.name
  }
  alarm_description = "AZ1 Exchange Rate Producer has no running tasks — activate AZ2 standby"
  alarm_actions     = [aws_appautoscaling_policy.producer_az2_scale_up.arn]
  ok_actions        = [aws_appautoscaling_policy.producer_az2_scale_down.arn]
}

# ── Streaming Service ─────────────────────────────────────────────────────────

resource "aws_ecs_service" "Streaming_Exchange_Rate_Service" {
  name            = "Streaming_Exchange_Rate_Service"
  cluster         = var.ecs_cluster_arn
  task_definition = var.streaming_task_definition_arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_services_sg_id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = var.streaming_target_group_arn
    container_name   = "Streaming_Exchange_Rate_Container"
    container_port   = 4000
  }
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
}

resource "aws_appautoscaling_target" "Streaming_Exchange_Rate_Scaling_Target" {
  max_capacity       = 4
  min_capacity       = 1
  resource_id        = "service/${var.ecs_cluster_name}/${aws_ecs_service.Streaming_Exchange_Rate_Service.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "Streaming_Exchange_Rate_Scale_Up" {
  name               = "Streaming_Exchange_Rate_Scale_Up"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.Streaming_Exchange_Rate_Scaling_Target.resource_id
  scalable_dimension = aws_appautoscaling_target.Streaming_Exchange_Rate_Scaling_Target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.Streaming_Exchange_Rate_Scaling_Target.service_namespace
  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"
    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 1
    }
  }
}

resource "aws_appautoscaling_policy" "Streaming_Exchange_Rate_Scale_Down" {
  name               = "Streaming_Exchange_Rate_Scale_Down"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.Streaming_Exchange_Rate_Scaling_Target.resource_id
  scalable_dimension = aws_appautoscaling_target.Streaming_Exchange_Rate_Scaling_Target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.Streaming_Exchange_Rate_Scaling_Target.service_namespace
  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 120
    metric_aggregation_type = "Maximum"
    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = -1
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "Streaming_Exchange_Rate_Scale_Up_Alarm" {
  alarm_name          = "Streaming_Exchange_Rate_Scale_Up_Alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "ECS/ContainerInsights"
  period              = 30
  statistic           = "Maximum"
  threshold           = 80
  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = aws_ecs_service.Streaming_Exchange_Rate_Service.name
  }
  alarm_description = "Streaming Service CPUUtilization is high - Scale Up"
  alarm_actions     = [aws_appautoscaling_policy.Streaming_Exchange_Rate_Scale_Up.arn]
  ok_actions        = [aws_appautoscaling_policy.Streaming_Exchange_Rate_Scale_Down.arn]
}

# ── Forecast Service ──────────────────────────────────────────────────────────

resource "aws_ecs_service" "Forecast_Exchange_Rate_Service" {
  name            = "Forecast_Exchange_Rate_Service"
  cluster         = var.ecs_cluster_arn
  task_definition = var.forecast_task_definition_arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_services_sg_id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = var.forecast_target_group_arn
    container_name   = "Forecast_Exchange_Rate_Container"
    container_port   = 6000
  }
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
}

# ── Money Service ─────────────────────────────────────────────────────────────

resource "aws_ecs_service" "Money_Service" {
  name            = "Money_Service"
  cluster         = var.ecs_cluster_arn
  task_definition = var.money_service_task_definition_arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_services_sg_id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = var.update_money_target_group_arn
    container_name   = "Money_Service_Container"
    container_port   = 5000
  }
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
}

# ── Tour Service ──────────────────────────────────────────────────────────────

resource "aws_ecs_service" "Tour_Service" {
  name            = "Tour_Service"
  cluster         = var.ecs_cluster_arn
  task_definition = var.tour_service_task_definition_arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_services_sg_id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = var.tour_service_target_group_arn
    container_name   = "Tour_Service_Container"
    container_port   = 7000
  }
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
}

# ── Frontend Service ──────────────────────────────────────────────────

resource "aws_ecs_service" "Frontend_Service" {
  name            = "Frontend_Service"
  cluster         = var.ecs_cluster_arn
  task_definition = var.frontend_task_definition_arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_services_sg_id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = var.frontend_target_group_arn
    container_name   = "Frontend_Container"
    container_port   = 3000
  }
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
}
