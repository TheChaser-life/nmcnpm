output "vpc_id" {
  value = aws_vpc.nmcnpm.id
}

output "public_subnet_ids" {
  value = [aws_subnet.public_subnet_1.id, aws_subnet.public_subnet_2.id]
}

output "private_subnet_ids" {
  value = [aws_subnet.private_subnet_1.id, aws_subnet.private_subnet_2.id]
}

output "alb_sg_id" {
  value = aws_security_group.alb.id
}

output "ecs_services_sg_id" {
  value = aws_security_group.ecs_services.id
}

output "rds_sg_id" {
  value = aws_security_group.rds.id
}

output "elasticache_sg_id" {
  value = aws_security_group.elasticache.id
}

output "producer_sg_id" {
  value = aws_security_group.producer.id
}

output "interface_endpoint_sg_id" {
  value = aws_security_group.interface_endpoint.id
}

output "lambda_sg_id" {
  value = aws_security_group.lambda.id
}

output "az_1" {
  value = data.aws_availability_zones.available.names[0]   
}

output "az_2" {
  value = data.aws_availability_zones.available.names[1]   
}

output "sagemaker_sg_id" {
  value = aws_security_group.sagemaker.id
}

output "public_subnet_1_id" {
  description = "ID của Public Subnet AZ 1"
  value       = aws_subnet.public_subnet_1.id
}

output "public_subnet_2_id" {
  description = "ID của Public Subnet AZ 2"
  value       = aws_subnet.public_subnet_2.id
}

output "private_subnet_1_id" {
  description = "ID của Private Subnet AZ 1"
  value       = aws_subnet.private_subnet_1.id
}

output "private_subnet_2_id" {
  description = "ID của Private Subnet AZ 2"
  value       = aws_subnet.private_subnet_2.id
}

output "s3_gateway_endpoint_id" {
  description = "ID của VPC Gateway Endpoint cho S3 — dùng bởi S3_Buckets module để tạo bucket policy"
  value       = aws_vpc_endpoint.gateway_endpoint.id
}