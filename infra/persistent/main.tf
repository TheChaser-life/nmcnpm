terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  backend "s3" {
    bucket         = "nmcnpm-tfstate"
    key            = "currency-exchange/persistent.tfstate"
    region         = "ap-southeast-2"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

provider "aws" {
  region = var.region
}

# ── S3 Buckets ────────────────────────────────────────────────────────────────
# force_destroy = true cho phép xóa bucket kể cả khi còn objects

module "S3_Buckets" {
  source = "./modules/S3_Buckets"

  account_id                 = var.account_id
  s3_vpc_gateway_endpoint_id = var.s3_vpc_gateway_endpoint_id
  admin_iam_arns             = var.admin_iam_arns
}

# ── ECR Repositories & ECS Cluster ───────────────────────────────────────────
# force_delete = true cho phép xóa ECR repo kể cả khi còn images
# Lưu ý: module này cần nhiều biến từ main_infra (networking, secrets, v.v.)
# Khi apply lần đầu, truyền giá trị placeholder cho các biến chưa có

module "ECR_and_ECS_Cluster" {
  source     = "./modules/ECR_and_ECS_Cluster"
  region     = var.region
  account_id = var.account_id

  # Networking — lấy từ main_infra sau khi apply
  public_subnet_ids   = var.public_subnet_ids
  public_subnet_1_id  = var.public_subnet_1_id
  public_subnet_2_id  = var.public_subnet_2_id
  private_subnet_ids  = var.private_subnet_ids
  ecs_services_sg_id  = var.ecs_services_sg_id
  producer_sg_id      = var.producer_sg_id

  # Cognito
  user_pool_id = var.user_pool_id

  # SageMaker
  sagemaker_endpoint = var.sagemaker_endpoint

  # S3
  s3_tour_bucket_name    = module.S3_Buckets.tour_bucket_name
  s3_dataset_bucket_name = module.S3_Buckets.training_data_bucket_name

  # ECR image URIs
  Exchange_Rate_Producer_Image_URI  = var.exchange_rate_producer_image_uri
  Streaming_Exchange_Rate_Image_URI = var.streaming_exchange_rate_image_uri
  Dataset_Maker_Image_URI           = var.dataset_maker_image_uri
  Forecast_Exchange_Rate_Image_URI  = var.forecast_exchange_rate_image_uri
  Money_Image_URI                   = var.money_image_uri
  Tour_Producer_Image_URI           = var.tour_producer_image_uri
  Tour_Service_Image_URI            = var.tour_service_image_uri
  Frontend_Image_URI                = var.frontend_image_uri

  # ElastiCache
  redis_host               = var.redis_host
  exchange_rate_redis_host = var.exchange_rate_redis_host
  idempotency_redis_host   = var.idempotency_redis_host
  exchange_api_url         = var.exchange_api_url

  # ALB Target Groups — đã chuyển sang ECS_Services module trong main_infra

  # Secrets & Parameter Store
  rds_secret_arn            = module.Secrets_Manager_and_Parameter_Store.rds_secret_arn
  elasticache_secret_arn    = module.Secrets_Manager_and_Parameter_Store.elasticache_secret_arn
  premium_fee_parameter_arn = module.Secrets_Manager_and_Parameter_Store.premium_fee_parameter_arn
  viator_api_key_secret_arn = module.Secrets_Manager_and_Parameter_Store.viator_api_key_secret_arn

  # RDS
  db_host = var.db_host

  # EventBridge / Step Functions
  step_functions_state_machine_arn = var.step_functions_state_machine_arn
  eventbridge_sfn_policy_arn       = var.eventbridge_sfn_policy_arn
}

# ── Secrets Manager & Parameter Store ────────────────────────────────────────
# recovery_window_in_days = 0 cho phép xóa secret ngay lập tức

module "Secrets_Manager_and_Parameter_Store" {
  source = "./modules/Secrets_Manager_and_Parameter_Store"

  region             = var.region
  private_subnet_ids = var.private_subnet_ids
  lambda_sg_id       = var.lambda_sg_id

  rotate_redis_password_lambda_function_name = var.rotate_redis_password_lambda_function_name
  rotate_redis_password_lambda_function_arn  = var.rotate_redis_password_lambda_function_arn

  travelpayouts_api_key = var.travelpayouts_api_key
  viator_api_key        = var.viator_api_key
  exchange_rate_api_key = var.exchange_rate_api_key
  premium_fee           = var.premium_fee
}
