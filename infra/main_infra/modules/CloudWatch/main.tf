#CloudWatch Logs Group cho các services
resource "aws_cloudwatch_log_group" "frontend_logs_group" {
    name = "/ecs/frontend"
    retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "streaming_exchange_rate_logs_group" {
    name = "/ecs/streaming_exchange_rate"
    retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "update_user_money_logs_group" {
    name = "/ecs/update_user_money"
    retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "forecast_exchange_rate_logs_group" {
    name = "/ecs/forecast_exchange_rate"
    retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "tour_display_logs_group" {
    name = "/ecs/tour_display"
    retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "exchange_rate_producer_logs_group" {
    name = "/ecs/exchange_rate_producer"
    retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "tour_producer_logs_group" {
    name = "/ecs/tour_producer"
    retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "dataset_maker_logs_group" {
    name = "/ecs/dataset_maker"
    retention_in_days = 7
}

# CloudWatch Alarm cho các services
resource "aws_cloudwatch_metric_alarm" "frontend_5xx_error_rate_alarm" {
    alarm_name = "frontend_5xx_error_rate_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 2
    threshold = 3

    metric_query {
      id = "error_rate"
      expression = "errors / requests * 100"
      label = "5XX Error Rate (%)"
      return_data = true
    }

    metric_query {
      id = "errors"
      metric {
        namespace = "AWS/ApplicationELB"
        metric_name = "HTTPCode_Target_5XX_Count"
        dimensions = {
          TargetGroup = var.frontend_target_group_arn_suffix
          LoadBalancer = var.alb_arn_suffix
        }
        period = 60
        stat = "Sum"
      }
    }

    metric_query {
      id = "requests"
      metric {
        namespace = "AWS/ApplicationELB"
        metric_name = "RequestCount"
        dimensions = {
          TargetGroup = var.frontend_target_group_arn_suffix
          LoadBalancer = var.alb_arn_suffix
        }
        period = 60
        stat = "Sum"
      }
    }

    alarm_actions = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "streaming_exchange_rate_5xx_error_rate_alarm" {
    alarm_name = "streaming_exchange_rate_5xx_error_rate_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 2
    threshold = 3

    metric_query {
      id = "error_rate"
      expression = "errors / requests * 100"
      label = "5XX Error Rate (%)"
      return_data = true
    }

    metric_query {
      id = "errors"
      metric {
        namespace = "AWS/ApplicationELB"
        metric_name = "HTTPCode_Target_5XX_Count"
        dimensions = {
          TargetGroup = var.streaming_exchange_rate_target_group_arn_suffix
          LoadBalancer = var.alb_arn_suffix
        }
        period = 60
        stat = "Sum"
      }
    }

    metric_query {
      id = "requests"
      metric {
        namespace = "AWS/ApplicationELB"
        metric_name = "RequestCount"
        dimensions = {
          TargetGroup = var.streaming_exchange_rate_target_group_arn_suffix
          LoadBalancer = var.alb_arn_suffix
        }
        period = 60
        stat = "Sum"
      }
    }

    alarm_actions = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "update_user_money_5xx_error_rate_alarm" {
    alarm_name = "update_user_money_5xx_error_rate_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 2
    threshold = 3

    metric_query {
      id = "error_rate"
      expression = "errors / requests * 100"
      label = "5XX Error Rate (%)"
      return_data = true
    }

    metric_query {
      id = "errors"
      metric {
        namespace = "AWS/ApplicationELB"
        metric_name = "HTTPCode_Target_5XX_Count"
        dimensions = {
          TargetGroup = var.update_user_money_target_group_arn_suffix
          LoadBalancer = var.alb_arn_suffix
        }
        period = 60
        stat = "Sum"
      }
    }

    metric_query {
      id = "requests"
      metric {
        namespace = "AWS/ApplicationELB"
        metric_name = "RequestCount"
        dimensions = {
          TargetGroup = var.update_user_money_target_group_arn_suffix
          LoadBalancer = var.alb_arn_suffix
        }
        period = 60
        stat = "Sum"
      }
    }

    alarm_actions = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "forecast_exchange_rate_5xx_error_rate_alarm" {
    alarm_name = "forecast_exchange_rate_5xx_error_rate_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 2
    threshold = 3

    metric_query {
      id = "error_rate"
      expression = "errors / requests * 100"
      label = "5XX Error Rate (%)"
      return_data = true
    }

    metric_query {
      id = "errors"
      metric {
        namespace = "AWS/ApplicationELB"
        metric_name = "HTTPCode_Target_5XX_Count"
        dimensions = {
          TargetGroup = var.forecast_exchange_rate_target_group_arn_suffix
          LoadBalancer = var.alb_arn_suffix
        }
        period = 60
        stat = "Sum"
      }
    }

    metric_query {
      id = "requests"
      metric {
        namespace = "AWS/ApplicationELB"
        metric_name = "RequestCount"
        dimensions = {
          TargetGroup = var.forecast_exchange_rate_target_group_arn_suffix
          LoadBalancer = var.alb_arn_suffix
        }
        period = 60
        stat = "Sum"
      }
    }

    alarm_actions = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "tour_display_5xx_error_rate_alarm" {
    alarm_name = "tour_display_5xx_error_rate_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 2
    threshold = 3

    metric_query {
      id = "error_rate"
      expression = "errors / requests * 100"
      label = "5XX Error Rate (%)"
      return_data = true
    }

    metric_query {
      id = "errors"
      metric {
        namespace = "AWS/ApplicationELB"
        metric_name = "HTTPCode_Target_5XX_Count"
        dimensions = {
          TargetGroup = var.tour_display_target_group_arn_suffix
          LoadBalancer = var.alb_arn_suffix
        }
        period = 60
        stat = "Sum"
      }
    }

    metric_query {
      id = "requests"
      metric {
        namespace = "AWS/ApplicationELB"
        metric_name = "RequestCount"
        dimensions = {
          TargetGroup = var.tour_display_target_group_arn_suffix
          LoadBalancer = var.alb_arn_suffix
        }
        period = 60
        stat = "Sum"
      }
    }

    alarm_actions = [var.sns_topic_arn]
}

# CloudWatch Alarm cho RDS và read replica
resource "aws_cloudwatch_metric_alarm" "primary_rds_cpuutilization_alarm" {
    alarm_name = "primary_rds_cpuutilization_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 1
    threshold = 80

    namespace = "AWS/RDS"
    metric_name = "CPUUtilization"
    statistic = "Average"
    period = 300

    dimensions = {
        DBInstanceIdentifier = var.primary_db_instance_identifier
    }

    alarm_actions = [var.sns_topic_arn]
}

# resource "aws_cloudwatch_metric_alarm" "replica_rds_cpuutilization_alarm" {
#     alarm_name = "replica_rds_cpuutilization_alarm"
#     comparison_operator = "GreaterThanThreshold"
#     evaluation_periods = 1
#     threshold = 80

#     namespace = "AWS/RDS"
#     metric_name = "CPUUtilization"
#     statistic = "Average"
#     period = 300

#     dimensions = {
#         DBInstanceIdentifier = var.replica_db_instance_identifier
#     }

#     alarm_actions = [var.sns_topic_arn]
# }

# resource "aws_cloudwatch_metric_alarm" "replica_rds_replica_lag_alarm" {
#     alarm_name = "replica_rds_replica_lag_alarm"
#     comparison_operator = "GreaterThanThreshold"
#     evaluation_periods = 1
#     threshold = 60

#     namespace = "AWS/RDS"
#     metric_name = "ReplicaLag"
#     statistic = "Maximum"
#     period = 60

#     dimensions = {
#         DBInstanceIdentifier = var.replica_db_instance_identifier
#     }

#     alarm_actions = [var.sns_topic_arn]
# }

# CloudWatch Alarm cho ElastiCache và Read Replica
resource "aws_cloudwatch_metric_alarm" "exchange_rate_elasticache_memory_usage_percentage_alarm" {
    alarm_name = "exchange_rate_elasticache_memory_usage_percentage_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 1
    threshold = 80

    namespace = "AWS/ElastiCache"
    metric_name = "DatabaseMemoryUsagePercentage"
    statistic = "Average"
    period = 60

    dimensions = {
        CacheClusterId = var.exchange_rate_elasticache_cluster_id
    }

    alarm_actions     = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "exchange_rate_elasticache_cpu_usage_percentage_alarm" {
    alarm_name = "exchange_rate_elasticache_cpu_usage_percentage_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 2
    threshold = 80

    namespace = "AWS/ElastiCache"
    metric_name = "EngineCPUUtilization"
    statistic = "Average"
    period = 60

    dimensions = {
        CacheClusterId = var.exchange_rate_elasticache_cluster_id
    }

    alarm_actions     = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "idempotency_elasticache_memory_usage_percentage_alarm" {
    alarm_name = "idempotency_elasticache_memory_usage_percentage_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 1
    threshold = 80

    namespace = "AWS/ElastiCache"
    metric_name = "DatabaseMemoryUsagePercentage"
    statistic = "Average"
    period = 60

    dimensions = {
        CacheClusterId = var.idempotency_elasticache_cluster_id
    }

    alarm_actions     = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "idempotency_elasticache_cpu_usage_percentage_alarm" {
    alarm_name = "idempotency_elasticache_cpu_usage_percentage_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 2
    threshold = 80

    namespace = "AWS/ElastiCache"
    metric_name = "EngineCPUUtilization"
    statistic = "Average"
    period = 60

    dimensions = {
        CacheClusterId = var.idempotency_elasticache_cluster_id
    }

    alarm_actions     = [var.sns_topic_arn]
}

# CloudWatch Alarm cho ALB
resource "aws_cloudwatch_metric_alarm" "alb_5xx_error_rate_alarm" {
    alarm_name = "alb_5xx_error_rate_alarm"
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods = 1
    threshold = 3
    
    metric_query {
    id          = "error_rate"
    expression  = "errors / requests * 100"
    label       = "5XX Error Rate (%)"
    return_data = true
  }

  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_ELB_5XX_Count"
      dimensions = {
        LoadBalancer = var.alb_arn_suffix
      }
      period = 60
      stat   = "Sum"
    }
  }

  metric_query {
    id = "requests"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "RequestCount"
      dimensions = {
        LoadBalancer = var.alb_arn_suffix
      }
      period = 60
      stat   = "Sum"
    }
  }

  alarm_actions = [var.sns_topic_arn]
}

# Tạo CloudWatch Alarm cho producer custom metric
resource "aws_cloudwatch_metric_alarm" "exchange_rate_cache_stale" {
    alarm_name = "exchange_rate_cache_stale"
    namespace = "NMCNPM/ExchangeRate"
    metric_name = "ExchangeRateCacheAge"
    comparison_operator = "LessThanThreshold"
    evaluation_periods = 1
    threshold = 1
    period = 120
    statistic = "SampleCount"
    treat_missing_data  = "breaching"
    alarm_actions = [var.sns_topic_arn]
}
