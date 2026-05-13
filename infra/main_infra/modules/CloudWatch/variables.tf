variable "frontend_target_group_arn_suffix" {
    type = string
}

variable "alb_arn_suffix" {
    type = string
}

variable "sns_topic_arn" {
    type = string
}

variable "streaming_exchange_rate_target_group_arn_suffix" {
    type = string
}

variable "update_user_money_target_group_arn_suffix" {
    type = string
}

variable "forecast_exchange_rate_target_group_arn_suffix" {
    type = string
}

variable "tour_display_target_group_arn_suffix" {
    type = string
}

variable "primary_db_instance_identifier" {
    type = string
}

variable "replica_db_instance_identifier" {
    type = string
}

variable "exchange_rate_elasticache_cluster_id" {
    type = string
}

variable "idempotency_elasticache_cluster_id" {
    type = string
}