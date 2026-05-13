# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — Root module này đã được tái cấu trúc thành 2 module riêng:   ║
# ║                                                                              ║
# ║  infra/persistent/   — S3, ECR, Secrets Manager (apply một lần)             ║
# ║  infra/main_infra/   — VPC, ALB, RDS, ECS, v.v. (destroy/apply tự do)      ║
# ║                                                                              ║
# ║  Xem README trong mỗi thư mục để biết cách sử dụng.                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state backend — cần bootstrap S3 bucket + DynamoDB table trước
  # (xem infra/bootstrap/ để tạo các resource này)
  # Bỏ comment block này sau khi đã chạy bootstrap:
  #
  backend "s3" {
    bucket         = "nmcnpm-tfstate"
    key            = "currency-exchange/terraform.tfstate"
    region         = var.region
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

provider "aws" {
  region = var.region
  # Credentials được đọc từ env vars (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
  # hoặc IAM Role (OIDC) khi chạy trong CI/CD — không hardcode ở đây.
}

# ── Networking ────────────────────────────────────────────────────────────────

module "VPC_and_Networking" {
  source = "./modules/VPC_and_Networking"
}

# ── Security / WAF ────────────────────────────────────────────────────────────

module "WAF" {
  source  = "./modules/WAF"
  alb_arn = module.ALB.alb_arn
}

# ── Load Balancer ─────────────────────────────────────────────────────────────

module "ALB" {
  source            = "./modules/ALB"
  public_subnet_ids = module.VPC_and_Networking.public_subnet_ids
  alb_sg_id         = module.VPC_and_Networking.alb_sg_id
  vpc_id            = module.VPC_and_Networking.vpc_id
  cert_arn          = var.cert_arn
}

# ── Storage ───────────────────────────────────────────────────────────────────

module "S3_Buckets" {
  source                    = "./modules/S3_Buckets"
  account_id                = var.account_id
  s3_vpc_gateway_endpoint_id = module.VPC_and_Networking.s3_gateway_endpoint_id
}

# ── Secrets & Parameter Store ─────────────────────────────────────────────────
# Phải tạo trước RDS và ElastiCache vì chúng cần password từ đây.

module "Secrets_Manager_and_Parameter_Store" {
  source             = "./modules/Secrets_Manager_and_Parameter_Store"
  region             = var.region
  private_subnet_ids = module.VPC_and_Networking.private_subnet_ids
  lambda_sg_id       = module.VPC_and_Networking.lambda_sg_id

  # Lambda dùng để rotate ElastiCache password (tạo bởi ECR_and_ECS_Cluster)
  rotate_redis_password_lambda_function_name = module.ECR_and_ECS_Cluster.rotate_redis_lambda_function_name
  rotate_redis_password_lambda_function_arn  = module.ECR_and_ECS_Cluster.rotate_redis_lambda_function_arn

  travelpayouts_api_key = var.travelpayouts_api_key
  exchange_rate_api_key = var.exchange_rate_api_key
  premium_fee           = var.premium_fee
}

# ── Database ──────────────────────────────────────────────────────────────────

module "RDS_Postgre" {
  source             = "./modules/RDS_Postgre"
  az_1               = module.VPC_and_Networking.az_1
  az_2               = module.VPC_and_Networking.az_2
  private_subnet_ids = module.VPC_and_Networking.private_subnet_ids
  rds_password       = module.Secrets_Manager_and_Parameter_Store.rds_password
  elasticache_password = module.Secrets_Manager_and_Parameter_Store.elasticache_password
}

# ── Cache ─────────────────────────────────────────────────────────────────────

module "ElastiCache" {
  source             = "./modules/ElastiCache"
  private_subnet_ids = module.VPC_and_Networking.private_subnet_ids
}

# ── Observability ─────────────────────────────────────────────────────────────

module "SNS" {
  source      = "./modules/SNS"
  alert_email = var.alert_email
}

module "CloudWatch" {
  source = "./modules/CloudWatch"

  alb_arn_suffix                                  = module.ALB.alb_arn_suffix
  frontend_target_group_arn_suffix                = module.ALB.frontend_target_group_arn_suffix
  streaming_exchange_rate_target_group_arn_suffix = module.ALB.streaming_exchange_rate_target_group_arn_suffix
  update_user_money_target_group_arn_suffix       = module.ALB.update_user_money_target_group_arn_suffix
  forecast_exchange_rate_target_group_arn_suffix  = module.ALB.forecast_exchange_rate_target_group_arn_suffix
  tour_display_target_group_arn_suffix            = module.ALB.tour_display_target_group_arn_suffix

  sns_topic_arn = module.SNS.sns_topic_arn

  primary_db_instance_identifier  = module.RDS_Postgre.primary_db_instance_identifier
  replica_db_instance_identifier  = module.RDS_Postgre.replica_db_instance_identifier
  exchange_rate_elasticache_cluster_id = module.ElastiCache.exchange_rate_elasticache_cluster_id
  idempotency_elasticache_cluster_id   = module.ElastiCache.idempotency_elasticache_cluster_id
}

module "X-Ray" {
  source = "./modules/X-Ray"
}

# ── Authentication ────────────────────────────────────────────────────────────

module "Cognito" {
  source                         = "./modules/Cognito"
  post_confirmation_function_arn = module.Lambda.post_confirmation_function_arn
}

# ── Container Registry & ECS Cluster ─────────────────────────────────────────

module "ECR_and_ECS_Cluster" {
  source     = "./modules/ECR_and_ECS_Cluster"
  region     = var.region
  account_id = var.account_id

  # Networking
  public_subnet_ids   = module.VPC_and_Networking.public_subnet_ids
  public_subnet_1_id  = module.VPC_and_Networking.public_subnet_1_id
  public_subnet_2_id  = module.VPC_and_Networking.public_subnet_2_id
  private_subnet_ids  = module.VPC_and_Networking.private_subnet_ids
  private_subnet_1_id = module.VPC_and_Networking.private_subnet_1_id
  ecs_services_sg_id  = module.VPC_and_Networking.ecs_services_sg_id
  producer_sg_id      = module.VPC_and_Networking.producer_sg_id

  # Cognito
  user_pool_id = module.Cognito.user_pool_id

  # SageMaker
  sagemaker_endpoint = module.SageMaker.sagemaker_endpoint_name

  # S3
  s3_tour_bucket_name    = module.S3_Buckets.tour_bucket_name
  s3_dataset_bucket_name = module.S3_Buckets.training_data_bucket_name

  # ECR image URIs (điền sau khi build và push lần đầu)
  Exchange_Rate_Producer_Image_URI  = var.exchange_rate_producer_image_uri
  Streaming_Exchange_Rate_Image_URI = var.streaming_exchange_rate_image_uri
  Dataset_Maker_Image_URI           = var.dataset_maker_image_uri

  # ElastiCache
  redis_host               = module.ElastiCache.exchange_rate_redis_primary_endpoint
  exchange_rate_redis_host = module.ElastiCache.exchange_rate_redis_primary_endpoint
  idempotency_redis_host   = module.ElastiCache.idempotency_redis_primary_endpoint
  exchange_api_url         = var.exchange_api_url

  # ALB Target Groups
  streaming_target_group_arn    = module.ALB.streaming_target_group_arn
  forecast_target_group_arn     = module.ALB.forecast_target_group_arn
  update_money_target_group_arn = module.ALB.update_money_target_group_arn
  tour_service_target_group_arn = module.ALB.tour_service_target_group_arn

  # Secrets & Parameter Store
  rds_secret_arn            = module.Secrets_Manager_and_Parameter_Store.rds_secret_arn
  elasticache_secret_arn    = module.Secrets_Manager_and_Parameter_Store.elasticache_secret_arn
  premium_fee_parameter_arn = module.Secrets_Manager_and_Parameter_Store.premium_fee_parameter_arn

  # RDS — endpoint lấy từ module output, không hardcode
  db_host = module.RDS_Postgre.db_endpoint

  # Money Service
  money_service_desired_count = 2

  # EventBridge / Step Functions
  step_functions_state_machine_arn = module.StepFunctions.state_machine_arn
  eventbridge_sfn_policy_arn       = module.StepFunctions.eventbridge_sfn_policy_arn
}

# ── ML Pipeline ───────────────────────────────────────────────────────────────

module "SageMaker" {
  source = "./modules/SageMaker"

  region     = var.region
  account_id = var.account_id

  training_image            = var.training_image
  sagemaker_sg_id           = module.VPC_and_Networking.sagemaker_sg_id
  private_subnet_ids        = module.VPC_and_Networking.private_subnet_ids
  model_artifact_bucket     = module.S3_Buckets.model_artifact_bucket_name
  training_data_bucket      = module.S3_Buckets.training_data_bucket_name
  initial_model_package_arn = var.initial_model_package_arn
}

module "StepFunctions" {
  source = "./modules/StepFunctions"

  region     = var.region
  account_id = var.account_id

  ecs_cluster_arn                   = module.ECR_and_ECS_Cluster.ecs_cluster_arn
  dataset_maker_task_definition_arn = module.ECR_and_ECS_Cluster.dataset_maker_task_definition_arn
  dataset_maker_task_role_arn       = module.ECR_and_ECS_Cluster.dataset_maker_task_role_arn
  ecs_task_execution_role_arn       = module.ECR_and_ECS_Cluster.ecs_task_execution_role_arn
  private_subnet_ids                = module.VPC_and_Networking.private_subnet_ids
  ecs_services_sg_id                = module.VPC_and_Networking.ecs_services_sg_id

  sagemaker_training_role_arn = module.SageMaker.sagemaker_training_role_arn
  training_image              = var.training_image
  training_data_bucket        = module.S3_Buckets.training_data_bucket_name
  model_artifact_bucket       = module.S3_Buckets.model_artifact_bucket_name
  sagemaker_sg_id             = module.VPC_and_Networking.sagemaker_sg_id
  model_package_group_name    = module.SageMaker.model_package_group_name

  model_promotion_lambda_arn = module.Lambda.model_promotion_function_arn
}

# ── Lambda Functions ──────────────────────────────────────────────────────────

module "Lambda" {
  source = "./modules/Lambda"

  post_confirmation_function_image_uri = module.ECR_and_ECS_Cluster.post_confirmation_function_image_uri
  model_promotion_function_image_uri   = module.ECR_and_ECS_Cluster.model_promotion_function_image_uri

  rds_secret_arn        = module.Secrets_Manager_and_Parameter_Store.rds_secret_arn
  db_host               = module.RDS_Postgre.db_endpoint
  db_name               = "currency_exchange"
  private_subnet_ids    = module.VPC_and_Networking.private_subnet_ids
  lambda_sg_id          = module.VPC_and_Networking.lambda_sg_id
  cognito_user_pool_arn = module.Cognito.user_pool_arn

  model_package_group_name     = module.SageMaker.model_package_group_name
  model_artifact_bucket        = module.S3_Buckets.model_artifact_bucket_name
  sagemaker_execution_role_arn = module.SageMaker.sagemaker_training_role_arn
  sagemaker_endpoint_name      = module.SageMaker.sagemaker_endpoint_name
  aws_region                   = var.region

  step_functions_state_machine_arn = module.StepFunctions.state_machine_arn
}
