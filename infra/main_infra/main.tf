terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "nmcnpm-tfstate"
    key            = "currency-exchange/main_infra.tfstate"
    region         = "ap-southeast-2"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

provider "aws" {
  region = var.region
}

# ── Remote State: đọc outputs từ persistent module ───────────────────────────
# Sau khi `infra/persistent` đã apply, main_infra đọc các outputs qua data source này

data "terraform_remote_state" "persistent" {
  backend = "s3"
  config = {
    bucket = var.backend_bucket
    key    = "currency-exchange/persistent.tfstate"
    region = var.region
  }
}

# ── Networking ────────────────────────────────────────────────────────────────

module "VPC_and_Networking" {
  source = "./modules/VPC_and_Networking"
}

# ── Load Balancer ─────────────────────────────────────────────────────────────

module "ALB" {
  source            = "./modules/ALB"
  public_subnet_ids = module.VPC_and_Networking.public_subnet_ids
  alb_sg_id         = module.VPC_and_Networking.alb_sg_id
  vpc_id            = module.VPC_and_Networking.vpc_id
  cert_arn          = var.cert_arn
}

# ── Security / WAF ────────────────────────────────────────────────────────────

module "WAF" {
  source  = "./modules/WAF"
  alb_arn = module.ALB.alb_arn
}

# ── Database ──────────────────────────────────────────────────────────────────

module "RDS_Postgre" {
  source             = "./modules/RDS_Postgre"
  az_1               = module.VPC_and_Networking.az_1
  az_2               = module.VPC_and_Networking.az_2
  private_subnet_ids = module.VPC_and_Networking.private_subnet_ids
  rds_sg_id          = module.VPC_and_Networking.rds_sg_id
  rds_password       = data.terraform_remote_state.persistent.outputs.rds_password
  elasticache_password = data.terraform_remote_state.persistent.outputs.elasticache_password
}

# ── Cache ─────────────────────────────────────────────────────────────────────

module "ElastiCache" {
  source             = "./modules/ElastiCache"
  private_subnet_ids = module.VPC_and_Networking.private_subnet_ids
  elasticache_sg_id  = module.VPC_and_Networking.elasticache_sg_id
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

  primary_db_instance_identifier       = module.RDS_Postgre.primary_db_instance_identifier
  replica_db_instance_identifier       = module.RDS_Postgre.replica_db_instance_identifier
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

# ── ML Pipeline ───────────────────────────────────────────────────────────────

module "SageMaker" {
  source = "./modules/SageMaker"

  region     = var.region
  account_id = var.account_id

  training_image            = var.training_image
  sagemaker_sg_id           = module.VPC_and_Networking.sagemaker_sg_id
  private_subnet_ids        = module.VPC_and_Networking.private_subnet_ids
  model_artifact_bucket     = data.terraform_remote_state.persistent.outputs.model_artifact_bucket_name
  training_data_bucket      = data.terraform_remote_state.persistent.outputs.training_data_bucket_name
  initial_model_package_arn = var.initial_model_package_arn
}

module "StepFunctions" {
  source = "./modules/StepFunctions"

  region     = var.region
  account_id = var.account_id

  ecs_cluster_arn                   = data.terraform_remote_state.persistent.outputs.ecs_cluster_arn
  dataset_maker_task_definition_arn = data.terraform_remote_state.persistent.outputs.dataset_maker_task_definition_arn
  dataset_maker_task_role_arn       = data.terraform_remote_state.persistent.outputs.dataset_maker_task_role_arn
  ecs_task_execution_role_arn       = data.terraform_remote_state.persistent.outputs.ecs_task_execution_role_arn
  private_subnet_ids                = module.VPC_and_Networking.private_subnet_ids
  ecs_services_sg_id                = module.VPC_and_Networking.ecs_services_sg_id

  sagemaker_training_role_arn = module.SageMaker.sagemaker_training_role_arn
  training_image              = var.training_image
  training_data_bucket        = data.terraform_remote_state.persistent.outputs.training_data_bucket_name
  model_artifact_bucket       = data.terraform_remote_state.persistent.outputs.model_artifact_bucket_name
  sagemaker_sg_id             = module.VPC_and_Networking.sagemaker_sg_id
  model_package_group_name    = module.SageMaker.model_package_group_name

  model_promotion_lambda_arn = module.Lambda.model_promotion_function_arn
}

# ── Lambda Functions ──────────────────────────────────────────────────────────

module "Lambda" {
  source = "./modules/Lambda"

  post_confirmation_function_image_uri = data.terraform_remote_state.persistent.outputs.post_confirmation_function_image_uri
  model_promotion_function_image_uri   = data.terraform_remote_state.persistent.outputs.model_promotion_function_image_uri

  rds_secret_arn        = data.terraform_remote_state.persistent.outputs.rds_secret_arn
  db_host               = module.RDS_Postgre.db_endpoint
  db_name               = "currency_exchange"
  private_subnet_ids    = module.VPC_and_Networking.private_subnet_ids
  lambda_sg_id          = module.VPC_and_Networking.lambda_sg_id
  cognito_user_pool_arn = module.Cognito.user_pool_arn

  model_package_group_name     = module.SageMaker.model_package_group_name
  model_artifact_bucket        = data.terraform_remote_state.persistent.outputs.model_artifact_bucket_name
  sagemaker_execution_role_arn = module.SageMaker.sagemaker_training_role_arn
  sagemaker_endpoint_name      = module.SageMaker.sagemaker_endpoint_name
  aws_region                   = var.region

  step_functions_state_machine_arn = module.StepFunctions.state_machine_arn
  cert_arn                         = var.cert_arn
}

# ── ECS Services ──────────────────────────────────────────────────────────────

module "ECS_Services" {
  source = "./modules/ECS_Services"

  # Từ persistent remote state
  ecs_cluster_arn                            = data.terraform_remote_state.persistent.outputs.ecs_cluster_arn
  ecs_cluster_name                           = data.terraform_remote_state.persistent.outputs.ecs_cluster_name
  exchange_rate_producer_task_definition_arn = data.terraform_remote_state.persistent.outputs.exchange_rate_producer_task_definition_arn
  streaming_task_definition_arn              = data.terraform_remote_state.persistent.outputs.streaming_task_definition_arn
  forecast_task_definition_arn               = data.terraform_remote_state.persistent.outputs.forecast_task_definition_arn
  money_service_task_definition_arn          = data.terraform_remote_state.persistent.outputs.money_service_task_definition_arn
  tour_service_task_definition_arn           = data.terraform_remote_state.persistent.outputs.tour_service_task_definition_arn
  frontend_task_definition_arn               = data.terraform_remote_state.persistent.outputs.frontend_task_definition_arn

  # Networking từ VPC module
  public_subnet_1_id  = module.VPC_and_Networking.public_subnet_1_id
  public_subnet_2_id  = module.VPC_and_Networking.public_subnet_2_id
  private_subnet_ids  = module.VPC_and_Networking.private_subnet_ids
  producer_sg_id      = module.VPC_and_Networking.producer_sg_id
  ecs_services_sg_id  = module.VPC_and_Networking.ecs_services_sg_id

  # ALB Target Groups
  streaming_target_group_arn    = module.ALB.streaming_exchange_rate_target_group_arn
  forecast_target_group_arn     = module.ALB.forecast_target_group_arn
  update_money_target_group_arn = module.ALB.update_money_target_group_arn
  tour_service_target_group_arn = module.ALB.tour_service_target_group_arn
  frontend_target_group_arn     = module.ALB.frontend_target_group_arn

  money_service_desired_count = 2
}
