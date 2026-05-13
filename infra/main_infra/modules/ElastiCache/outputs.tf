output "exchange_rate_elasticache_cluster_id" {
    value = aws_elasticache_replication_group.exchange_rate_valkey_cluster.id
}

output "idempotency_elasticache_cluster_id" {
    value = aws_elasticache_replication_group.idempotency_valkey_cluster.id
}

output "exchange_rate_redis_primary_endpoint" {
    description = "Primary endpoint hostname for the Exchange Rate ElastiCache cluster"
    value       = aws_elasticache_replication_group.exchange_rate_valkey_cluster.primary_endpoint_address
}

output "idempotency_redis_primary_endpoint" {
    description = "Primary endpoint hostname for the Idempotency ElastiCache cluster"
    value       = aws_elasticache_replication_group.idempotency_valkey_cluster.primary_endpoint_address
}
