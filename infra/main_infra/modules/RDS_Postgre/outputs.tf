output "primary_db_instance_identifier" {
  value = aws_db_instance.rds_postgres_primary.identifier
}

# output "replica_db_instance_identifier" {
#   value = aws_db_instance.rds_postgres_read_replica.identifier
# }

output "db_endpoint" {
  description = "Hostname của RDS primary instance — dùng bởi ECS services và Lambda"
  value       = aws_db_instance.rds_postgres_primary.address
}