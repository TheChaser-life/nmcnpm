data "aws_region" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

# ─── VPC ────────────────────────────────────────────────────────────────────

resource "aws_vpc" "nmcnpm" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
}

# ─── Subnets ─────────────────────────────────────────────────────────────────

resource "aws_subnet" "public_subnet_1" {
  vpc_id            = aws_vpc.nmcnpm.id
  cidr_block        = "10.0.0.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
}

resource "aws_subnet" "public_subnet_2" {
  vpc_id            = aws_vpc.nmcnpm.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]
}

resource "aws_subnet" "private_subnet_1" {
  vpc_id            = aws_vpc.nmcnpm.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
}

resource "aws_subnet" "private_subnet_2" {
  vpc_id            = aws_vpc.nmcnpm.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]
}

# ─── Internet Gateway & Route Tables ─────────────────────────────────────────

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.nmcnpm.id
}

resource "aws_route_table" "public_subnet_route_table" {
  vpc_id = aws_vpc.nmcnpm.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
}

resource "aws_route_table" "private_subnet_route_table" {
  vpc_id = aws_vpc.nmcnpm.id
}

resource "aws_route_table_association" "public_subnet_1" {
  route_table_id = aws_route_table.public_subnet_route_table.id
  subnet_id      = aws_subnet.public_subnet_1.id
}

resource "aws_route_table_association" "public_subnet_2" {
  route_table_id = aws_route_table.public_subnet_route_table.id
  subnet_id      = aws_subnet.public_subnet_2.id
}

resource "aws_route_table_association" "private_subnet_1" {
  route_table_id = aws_route_table.private_subnet_route_table.id
  subnet_id      = aws_subnet.private_subnet_1.id
}

resource "aws_route_table_association" "private_subnet_2" {
  route_table_id = aws_route_table.private_subnet_route_table.id
  subnet_id      = aws_subnet.private_subnet_2.id
}

# ─── Security Groups ─────────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  vpc_id = aws_vpc.nmcnpm.id
}

resource "aws_security_group_rule" "allow_tls_ipv4_from_internet" {
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.alb.id
}

resource "aws_security_group_rule" "allow_http_ipv4_from_internet" {
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.alb.id
}

resource "aws_security_group_rule" "allow_egress_traffic_to_private_subnet" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.alb.id
}

resource "aws_security_group" "ecs_services" {
  vpc_id = aws_vpc.nmcnpm.id
}

resource "aws_security_group_rule" "allow_inbound_from_alb" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 0
  protocol                 = "-1"
  source_security_group_id = aws_security_group.alb.id
  security_group_id        = aws_security_group.ecs_services.id
}

resource "aws_security_group_rule" "allow_egress_traffic" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.ecs_services.id
}

resource "aws_security_group" "rds" {
  vpc_id = aws_vpc.nmcnpm.id
}

resource "aws_security_group_rule" "allow_inbound_from_ecs_services_to_rds" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_services.id
  security_group_id        = aws_security_group.rds.id
}

resource "aws_security_group_rule" "allow_inbound_from_lambda_to_rds" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.lambda.id
  security_group_id        = aws_security_group.rds.id
}

resource "aws_security_group" "lambda" {
  vpc_id = aws_vpc.nmcnpm.id  
}

resource "aws_security_group_rule" "allow_outbound_from_lambda_to_rds" {
  type = "egress"
  from_port = 5432
  to_port = 5432
  protocol = "tcp"
  source_security_group_id = aws_security_group.rds.id
  security_group_id = aws_security_group.lambda.id
}

resource "aws_security_group_rule" "allow_outbound_from_lambda_to_interface_endpoint_to_get_rds_secret" {
  type = "egress"
  from_port = 443
  to_port = 443
  protocol = "tcp"
  source_security_group_id = aws_security_group.interface_endpoint.id
  security_group_id = aws_security_group.lambda.id
}

resource "aws_security_group" "elasticache" {
  vpc_id = aws_vpc.nmcnpm.id
}

resource "aws_security_group_rule" "allow_inbound_from_ecs_services_to_elasticache" {
  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_services.id
  security_group_id        = aws_security_group.elasticache.id
}

# Exchange Rate Producer dùng producer SG riêng — cho phép kết nối tới ElastiCache
resource "aws_security_group_rule" "allow_inbound_from_producer_to_elasticache" {
  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.producer.id
  security_group_id        = aws_security_group.elasticache.id
}

resource "aws_security_group" "sagemaker" {
  vpc_id = aws_vpc.nmcnpm.id
}

resource "aws_security_group_rule" "allow_inbound_from_ecs_services_to_sagemaker" {
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  source_security_group_id = aws_security_group.ecs_services.id
  security_group_id = aws_security_group.sagemaker.id
}

resource "aws_security_group_rule" "allow_outbound_from_sagemaker_to_interface_endpoint" {
  type                     = "egress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.interface_endpoint.id
  security_group_id        = aws_security_group.sagemaker.id
}

# SageMaker training cần truy cập S3 (Gateway Endpoint) và ECR qua HTTPS
resource "aws_security_group_rule" "allow_outbound_from_sagemaker_to_s3_and_ecr" {
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.sagemaker.id
}

resource "aws_security_group" "producer" {
  vpc_id = aws_vpc.nmcnpm.id
}

resource "aws_security_group_rule" "allow_outbound_from_producer_to_internet" {
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.producer.id
}

resource "aws_security_group_rule" "allow_outbound_from_producer_to_elasticache" {
  type              = "egress"
  from_port         = 6379
  to_port           = 6379
  protocol          = "tcp"
  source_security_group_id = aws_security_group.elasticache.id
  security_group_id = aws_security_group.producer.id
}

resource "aws_security_group" "interface_endpoint" {
  vpc_id = aws_vpc.nmcnpm.id
}

resource "aws_security_group_rule" "allow_inbound_from_vpc" {
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = [aws_vpc.nmcnpm.cidr_block]
  security_group_id = aws_security_group.interface_endpoint.id
}

# ─── VPC Endpoints ───────────────────────────────────────────────────────────

resource "aws_vpc_endpoint" "gateway_endpoint" {
  vpc_id            = aws_vpc.nmcnpm.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private_subnet_route_table.id]
}

locals {
  interface_endpoints = {
    "ecr-api"           = "ecr.api"
    "ecr-dkr"           = "ecr.dkr"
    "sagemaker"         = "sagemaker.api"
    "sagemaker-runtime" = "sagemaker.runtime"
    "cognito-idp"       = "cognito-idp"
    "secretsmanager"    = "secretsmanager"
    "logs"              = "logs"
    "ssm"               = "ssm"
  }
}

resource "aws_vpc_endpoint" "interface_endpoint" {
  for_each          = local.interface_endpoints
  vpc_id            = aws_vpc.nmcnpm.id
  vpc_endpoint_type = "Interface"
  service_name      = "com.amazonaws.${data.aws_region.current.name}.${each.value}"
  subnet_ids        = [aws_subnet.private_subnet_1.id, aws_subnet.private_subnet_2.id]
  security_group_ids = [aws_security_group.interface_endpoint.id]
  private_dns_enabled = true
}
