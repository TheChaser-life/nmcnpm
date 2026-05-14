resource "aws_elasticache_subnet_group" "cache_private_subnet_group" {
    name = "cache-private-subnet-group"
    subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_parameter_group" "exchange_rate_valkey_parameter_group" {
    name = "exchange-rate-valkey-parameter-group"
    family = "valkey7"
    parameter {
      name = "maxmemory-policy"
      value = "volatile-lru" # xóa data có mục ttl và ít được sử dụng gần đây nhất
    }
}

resource "aws_elasticache_replication_group" "exchange_rate_valkey_cluster" {
    replication_group_id = "exchange-rate-valkey-cluster"
    description = "valkey cluster for exchange rate cache"
    engine = "valkey"
    engine_version = "7.2"
    node_type = "cache.t4g.micro"
    num_cache_clusters = 1
    parameter_group_name = aws_elasticache_parameter_group.exchange_rate_valkey_parameter_group.name
    automatic_failover_enabled = false
    multi_az_enabled = false
    apply_immediately = true
    subnet_group_name = aws_elasticache_subnet_group.cache_private_subnet_group.name
    security_group_ids = [var.elasticache_sg_id]
    at_rest_encryption_enabled = false
    transit_encryption_enabled = false
}

resource "aws_elasticache_parameter_group" "idempotency_valkey_parameter_group" {
    name = "idempotency-valkey-parameter-group"
    family = "valkey7"
    parameter {
      name = "maxmemory-policy"
      value = "noeviction" # nếu RAM đầy sẽ chặn không cho ghi thay vì xóa bớt data
    }
}

resource "aws_elasticache_replication_group" "idempotency_valkey_cluster" {
    replication_group_id = "idempotency-valkey-cluster"
    description = "valkey cluster for idempotency cache"
    engine = "valkey"
    engine_version = "7.2"
    node_type = "cache.t4g.micro"
    num_cache_clusters = 1
    parameter_group_name = aws_elasticache_parameter_group.idempotency_valkey_parameter_group.name
    automatic_failover_enabled = false
    multi_az_enabled = false
    apply_immediately = true
    subnet_group_name = aws_elasticache_subnet_group.cache_private_subnet_group.name
    security_group_ids = [var.elasticache_sg_id]
    at_rest_encryption_enabled = true
    transit_encryption_enabled = true
}
