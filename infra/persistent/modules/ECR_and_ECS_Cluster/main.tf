# ECR
resource "aws_ecr_repository" "frontend_repo" {
    name                 = "frontend_repo"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_lifecycle_policy" "frontend_repo_cleanup" {
    repository = aws_ecr_repository.frontend_repo.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus = "any"
                countType = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

resource "aws_ecr_repository" "streaming_exchange_rate_repo" {
    name                 = "streaming_exchange_rate_repo"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_lifecycle_policy" "streaming_exchange_rate_repo_cleanup" {
    repository = aws_ecr_repository.streaming_exchange_rate_repo.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus = "any"
                countType = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

resource "aws_ecr_repository" "update_money_repo" {
    name                 = "update_money_repo"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_lifecycle_policy" "update_money_repo_cleanup" {
    repository = aws_ecr_repository.update_money_repo.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus = "any"
                countType = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

resource "aws_ecr_repository" "forecast_exchange_rate_repo" {
    name                 = "forecast_exchange_rate_repo"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_lifecycle_policy" "forecast_exchange_rate_repo_cleanup" {
    repository = aws_ecr_repository.forecast_exchange_rate_repo.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus = "any"
                countType = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

resource "aws_ecr_repository" "tour_display_repo" {
    name                 = "tour_display_repo"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_lifecycle_policy" "tour_display_repo_cleanup" {
    repository = aws_ecr_repository.tour_display_repo.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus = "any"
                countType = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

resource "aws_ecr_repository" "exchange_rate_producer_repo" {
    name                 = "exchange_rate_producer_repo"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_lifecycle_policy" "exchange_rate_producer_repo_cleanup" {
    repository = aws_ecr_repository.exchange_rate_producer_repo.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus = "any"
                countType = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

resource "aws_ecr_repository" "tour_producer_repo" {
    name                 = "tour_producer_repo"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_lifecycle_policy" "tour_producer_repo_cleanup" {
    repository = aws_ecr_repository.tour_producer_repo.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus = "any"
                countType = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

resource "aws_ecr_repository" "dataset_maker_repo" {
    name                 = "dataset_maker_repo"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_lifecycle_policy" "dataset_maker_repo_cleanup" {
    repository = aws_ecr_repository.dataset_maker_repo.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus = "any"
                countType = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

resource "aws_ecr_repository" "post_confirmation_function" {
    name                 = "post_confirmation_function"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_lifecycle_policy" "post_confirmation_function_cleanup" {
    repository = aws_ecr_repository.post_confirmation_function.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus = "any"
                countType = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

resource "aws_ecr_repository" "model_promotion_function" {
    name                 = "model_promotion_function"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_lifecycle_policy" "model_promotion_function_cleanup" {
    repository = aws_ecr_repository.model_promotion_function.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description  = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus   = "any"
                countType   = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

resource "aws_ecr_repository" "forecast_training_repo" {
    name                 = "forecast_training_repo"
    image_tag_mutability = "MUTABLE"
    force_delete         = true
    image_scanning_configuration {
        scan_on_push = true
    }
}

resource "aws_ecr_repository_policy" "forecast_training_repo_pull_policy" {
    repository = aws_ecr_repository.forecast_training_repo.name
    policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Sid    = "AllowSageMakerServicePull"
                Effect = "Allow"
                Principal = {
                    Service = "sagemaker.amazonaws.com"
                }
                Action = [
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:BatchGetImage",
                    "ecr:DescribeImages",
                    "ecr:GetDownloadUrlForLayer"
                ]
                Condition = {
                    StringEquals = {
                        "aws:SourceAccount" = var.account_id
                    }
                }
            },
            {
                Sid    = "AllowMLPipelineRolesPull"
                Effect = "Allow"
                Principal = {
                    AWS = "arn:aws:iam::${var.account_id}:root"
                }
                Action = [
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:BatchGetImage",
                    "ecr:DescribeImages",
                    "ecr:GetDownloadUrlForLayer"
                ]
                Condition = {
                    StringLike = {
                        "aws:PrincipalArn" = [
                            "arn:aws:iam::${var.account_id}:role/sagemaker_training_role",
                            "arn:aws:iam::${var.account_id}:role/step_functions_role",
                            "arn:aws:iam::${var.account_id}:role/model-promotion-lambda-role"
                        ]
                    }
                }
            }
        ]
    })
}

resource "aws_ecr_lifecycle_policy" "forecast_training_repo_cleanup" {
    repository = aws_ecr_repository.forecast_training_repo.name
    policy = jsonencode({
        rules = [{
            rulePriority = 1
            description  = "Giu lai 3 image gan nhat"
            selection = {
                tagStatus   = "any"
                countType   = "imageCountMoreThan"
                countNumber = 3
            }
            action = {
                type = "expire"
            }
        }]
    })
}

# ECS Cluster
resource "aws_ecs_cluster" "nmcnpm_cluster" {
    name = "nmcnpm_cluster"

    setting {
        name = "containerInsights"
        value = "enabled"
    }
} 

resource "aws_ecs_cluster_capacity_providers" "nmcnpm_cluster_providers" {
    cluster_name = aws_ecs_cluster.nmcnpm_cluster.name

    capacity_providers = ["FARGATE", "FARGATE_SPOT"]

    default_capacity_provider_strategy {
      base = 12
      weight = 100
      capacity_provider = "FARGATE"
    }
}

# IAM Role for ECS Task Execution
# Trust Policy chỉ định các service được sử dụng
data "aws_iam_policy_document" "ecs_task_execution_trust_policy" {
    statement {
      actions = ["sts:AssumeRole"]
      principals {
        type = "Service"
        identifiers = ["ecs-tasks.amazonaws.com"]    
      }
    }
}

# Tạo Role
resource "aws_iam_role" "ecs_task_execution_role" {
    name = "nmcnpm-task-execution-role"
    assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_trust_policy.json
}

# Policy có sẵn do AWS quản lý cho phép tạo và ghi log vào CloudWatch và pull image từ ECR
resource "aws_iam_role_policy_attachment" "Attach_CloudWatch_and_ECR_Policy_to_IAM_Role" {
    role = aws_iam_role.ecs_task_execution_role.name
    policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Tạo document cho phép đọc secret từ Secret Manager
data "aws_iam_policy_document" "ECS_Read_Secret_Policy" {
    statement {
      effect = "Allow"
      actions = [
        "secretsmanager:GetSecretValue"
      ]

      resources = ["arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:nmcnpm/*"]
    }    
}

# Tạo poilicy từ document ở trên
resource "aws_iam_policy" "IAM_Policy_for_read_secret_from_ASM" {
    name = "IAM_Policy_for_read_secret_from_ASM"
    policy = data.aws_iam_policy_document.ECS_Read_Secret_Policy.json
}

# Gán policy trên vào IAM Role đã tạo
resource "aws_iam_role_policy_attachment" "Attach_Secret_Manager_Policy_to_IAM_Role" {
    role = aws_iam_role.ecs_task_execution_role.name
    policy_arn = aws_iam_policy.IAM_Policy_for_read_secret_from_ASM.arn
}

# IAM Role cho Update User Money Task, cần truy cập vào Cognito User Pool để thay đổi user attribute từ Standard -> Premium
data "aws_iam_policy_document" "Update_User_Money_Task_Document_To_Access_Cognito" {
    statement {
      effect = "Allow"
      actions = [
        "cognito-idp:AdminUpdateUserAttribute"
      ]
      resources = [
        "arn:aws:cognito-idp:${var.region}:${var.account_id}:userpool/${var.user_pool_id}"
      ]
    }
}

resource "aws_iam_policy" "IAM_Policy_for_update_user_attribute_in_Cognito" {
    name = "IAM_Policy_for_update_user_attribute_in_Cognito"
    policy = data.aws_iam_policy_document.Update_User_Money_Task_Document_To_Access_Cognito.json
}

data "aws_iam_policy_document" "Update_User_Money_Task_Document_To_Access_Parameter_Store" {
    statement {
      effect = "Allow"
      actions = [
        "ssm:GetParameter"
      ]
      resources = [
        "arn:aws:ssm:${var.region}:${var.account_id}:parameter/nmcnpm/*"
      ]
    }
}

resource "aws_iam_policy" "IAM_Policy_for_read_Parameter_Store" {
    name = "IAM_Policy_for_read_Parameter_Store"
    policy = data.aws_iam_policy_document.Update_User_Money_Task_Document_To_Access_Parameter_Store.json
}

resource "aws_iam_role" "Update_User_Money_Task_Role" {
    name = "Update_User_Money_Task_Role"
    assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_trust_policy.json
}

resource "aws_iam_role_policy_attachment" "Attach_update_user_attribute_in_Cognito_Policy_To_Update_User_Money_Task" {
    role = aws_iam_role.Update_User_Money_Task_Role.name
    policy_arn = aws_iam_policy.IAM_Policy_for_update_user_attribute_in_Cognito.arn
}

resource "aws_iam_role_policy_attachment" "Attach_read_Parameter_Store_Policy_To_Update_User_Money_Task" {
    role = aws_iam_role.Update_User_Money_Task_Role.name
    policy_arn = aws_iam_policy.IAM_Policy_for_read_Parameter_Store.arn
}

# IAM Role cho Forecast Exchange Rate Task để truy cập sagemaker endpoint
data "aws_iam_policy_document" "Forecast_Exchange_Rate_Task_Document_To_Access_SageMaker_Endpoint" {
    statement {
      effect = "Allow"
      actions = [
        "sagemaker:InvokeEndpoint"
      ]

      resources = [
        "arn:aws:sagemaker:${var.region}:${var.account_id}:endpoint/${var.sagemaker_endpoint}"
      ]
    }
}

resource "aws_iam_policy" "IAM_Policy_for_invoke_SageMaker_Endpoint" {
    name = "IAM_Policy_for_invoke_SageMaker_Endpoint"
    policy = data.aws_iam_policy_document.Forecast_Exchange_Rate_Task_Document_To_Access_SageMaker_Endpoint.json
}

resource "aws_iam_role" "Forecast_Exchange_Rate_Task_Role" {
    name = "Forecast_Exchange_Rate_Task_Role"
    assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_trust_policy.json
}

resource "aws_iam_role_policy_attachment" "Attach_Invoke_SageMaker_Endpoint_Policy_To_Forecast_Exchange_Rate_Task_Role" {
    role = aws_iam_role.Forecast_Exchange_Rate_Task_Role.name
    policy_arn = aws_iam_policy.IAM_Policy_for_invoke_SageMaker_Endpoint.arn
}

# IAM Role cho Tour Display Task để truy cập S3 bucket 
data "aws_iam_policy_document" "Tour_Display_Task_Document_To_Access_S3" {
    statement {
      effect = "Allow"
      actions = [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ]

      resources = [
        "arn:aws:s3:::${var.s3_tour_bucket_name}"
      ]
    }

    statement {
      effect = "Allow"
      actions = [
        "s3:GetObject"
      ]
      resources = [
        "arn:aws:s3:::${var.s3_tour_bucket_name}/*"
      ]
    }
}

resource "aws_iam_policy" "IAM_Policy_for_Access_S3_Tour_Bucket" {
    name = "IAM_Policy_for_Access_S3_Tour_Bucket"
    policy = data.aws_iam_policy_document.Tour_Display_Task_Document_To_Access_S3.json
}

resource "aws_iam_role" "Tour_Display_Task_Role" {
    name = "Tour_Display_Task_Role"
    assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_trust_policy.json
}

resource "aws_iam_role_policy_attachment" "Attach_Access_S3_Tour_Bucket_To_Tour_Display_Task_Role" {
    role = aws_iam_role.Tour_Display_Task_Role.name
    policy_arn = aws_iam_policy.IAM_Policy_for_Access_S3_Tour_Bucket.arn
}

# IAM Role cho Tour Producer Task để put object vào S3 
data "aws_iam_policy_document" "Tour_Producer_Task_Document_To_Put_To_S3" {
    statement {
      effect = "Allow"
      actions = [
        "s3:PutObject"
      ]

      resources = [
        "arn:aws:s3:::${var.s3_tour_bucket_name}/*"
      ]
    }
}

resource "aws_iam_policy" "IAM_Policy_for_Put_Tour_Object_To_S3" {
    name = "IAM_Policy_for_Put_Tour_Object_To_S3"
    policy = data.aws_iam_policy_document.Tour_Producer_Task_Document_To_Put_To_S3.json
}

resource "aws_iam_role" "Tour_Producer_Task_Role" {
    name = "Tour_Producer_Task_Role"
    assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_trust_policy.json
}

resource "aws_iam_role_policy_attachment" "Attach_Put_Tour_Object_Policy_To_Tour_Producer_Task_Role" {
    role = aws_iam_role.Tour_Producer_Task_Role.name
    policy_arn = aws_iam_policy.IAM_Policy_for_Put_Tour_Object_To_S3.arn
}

# IAM Role cho Dataset Maker Task để put object vào S3 
data "aws_iam_policy_document" "Dataset_Maker_Task_Document_To_Put_To_S3" {
    statement {
      effect = "Allow"
      actions = [
        "s3:PutObject"
      ]

      resources = [
        "arn:aws:s3:::${var.s3_dataset_bucket_name}/*"
      ]
    }
}

resource "aws_iam_policy" "IAM_Policy_for_Put_Dataset_To_S3" {
    name = "IAM_Policy_for_Put_Dataset_To_S3"
    policy = data.aws_iam_policy_document.Dataset_Maker_Task_Document_To_Put_To_S3.json
}

resource "aws_iam_role" "Dataset_Maker_Task_Role" {
    name = "Dataset_Maker_Task_Role"
    assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_trust_policy.json
}

resource "aws_iam_role_policy_attachment" "Attach_Put_Dataset_Policy_To_Dataset_Maker_Task_Role" {
    role = aws_iam_role.Dataset_Maker_Task_Role.name
    policy_arn = aws_iam_policy.IAM_Policy_for_Put_Dataset_To_S3.arn
}

data "aws_iam_policy_document" "nmcnpm_xray_policy_document" {
  statement {
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",      # gửi trace segments
      "xray:PutTelemetryRecords",   # gửi telemetry (sampling stats)
      "xray:GetSamplingRules",      # đọc sampling rules
      "xray:GetSamplingTargets"     # đọc sampling targets
    ]
    resources = ["*"]  # X-Ray không hỗ trợ resource-level restriction
  }
}

resource "aws_iam_role" "Frontend_Task_Role" {
    name = "Frontend_Task_Role"
    assume_role_policy =  data.aws_iam_policy_document.ecs_task_execution_trust_policy.json
}

resource "aws_iam_role" "Streaming_Exchange_Rate_Task_Role" {
    name = "streaming_exchange_rate_Task_Role"
    assume_role_policy =  data.aws_iam_policy_document.ecs_task_execution_trust_policy.json
}

resource "aws_iam_policy" "nmcnpm_xray_policy" {
  name   = "nmcnpm_xray_policy"
  policy = data.aws_iam_policy_document.nmcnpm_xray_policy_document.json
}

resource "aws_iam_role_policy_attachment" "xray_money_task" {
  role       = aws_iam_role.Update_User_Money_Task_Role.name
  policy_arn = aws_iam_policy.nmcnpm_xray_policy.arn
}

resource "aws_iam_role_policy_attachment" "xray_forecast_task" {
  role       = aws_iam_role.Forecast_Exchange_Rate_Task_Role.name
  policy_arn = aws_iam_policy.nmcnpm_xray_policy.arn
}

resource "aws_iam_role_policy_attachment" "xray_tour_display_task" {
  role       = aws_iam_role.Tour_Display_Task_Role.name
  policy_arn = aws_iam_policy.nmcnpm_xray_policy.arn
}

resource "aws_iam_role_policy_attachment" "xray_tour_producer_task" {
  role       = aws_iam_role.Tour_Producer_Task_Role.name
  policy_arn = aws_iam_policy.nmcnpm_xray_policy.arn
}

resource "aws_iam_role_policy_attachment" "xray_dataset_maker_task" {
  role       = aws_iam_role.Dataset_Maker_Task_Role.name
  policy_arn = aws_iam_policy.nmcnpm_xray_policy.arn
}

resource "aws_iam_role_policy_attachment" "xray_frontend_task" {
  role       = aws_iam_role.Frontend_Task_Role.name
  policy_arn = aws_iam_policy.nmcnpm_xray_policy.arn
}

resource "aws_iam_role_policy_attachment" "xray_streaming_exchange_rate_task" {
  role       = aws_iam_role.Streaming_Exchange_Rate_Task_Role.name
  policy_arn = aws_iam_policy.nmcnpm_xray_policy.arn
}

# CloudWatch Metrics Policy
data "aws_iam_policy_document" "nmcnpm_metrics_policy_document" {
  statement {
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "nmcnpm_metrics_policy" {
  name   = "nmcnpm_metrics_policy"
  policy = data.aws_iam_policy_document.nmcnpm_metrics_policy_document.json
}

# Attach metrics policy to roles that emit metrics
resource "aws_iam_role_policy_attachment" "metrics_producer_task" {
  role       = aws_iam_role.Exchange_Rate_Producer_Task_Role.name
  policy_arn = aws_iam_policy.nmcnpm_metrics_policy.arn
}

resource "aws_iam_role_policy_attachment" "metrics_streaming_task" {
  role       = aws_iam_role.Streaming_Exchange_Rate_Task_Role.name
  policy_arn = aws_iam_policy.nmcnpm_metrics_policy.arn
}

resource "aws_iam_role_policy_attachment" "metrics_dataset_maker_task" {
  role       = aws_iam_role.Dataset_Maker_Task_Role.name
  policy_arn = aws_iam_policy.nmcnpm_metrics_policy.arn
}

resource "aws_iam_role" "Exchange_Rate_Producer_Task_Role" {
    name = "Exchange_Rate_Producer_Task_Role"
    assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_trust_policy.json
}

# Task Definition
# Exchange Rate Producer Task Definition
resource "aws_ecs_task_definition" "Exchange_Rate_Producer_Task_Definition" {
    family = "Exchange_Rate_Producer_Task"
    network_mode = "awsvpc" #Docker networking mode to use for the containers in the task.
    requires_compatibilities = ["FARGATE"]
    cpu = "256"
    memory = "512"
    execution_role_arn = aws_iam_role.ecs_task_execution_role.arn
    task_role_arn      = aws_iam_role.Exchange_Rate_Producer_Task_Role.arn

    container_definitions = jsonencode([
        {
            name = "Exchange_Rate_Producer_Container"
            image = var.Exchange_Rate_Producer_Image_URI != "" ? var.Exchange_Rate_Producer_Image_URI : "nginx:latest"
            essential = true

            environment = [
                { name = "POLLING_INTERVAL_SECONDS", value = "2100" },
                { name = "CACHE_TTL_SECONDS",        value = "2160" },
                { name = "REDIS_PORT",               value = "6379" },
                { name = "REDIS_SSL",                value = "false" },
                { name = "REDIS_HOST",               value = var.redis_host },
                { name = "EXCHANGE_API_URL",         value = var.exchange_api_url },
                { name = "SUPPORTED_CURRENCIES",     value = "USD,EUR,GBP,JPY,CNY,KRW,THB,SGD,MYR,IDR,PHP,AUD" },
                { name = "AWS_REGION",               value = var.region },
                { name = "ENABLE_CLOUDWATCH_METRICS", value = "true" }
            ]

            secrets = [
                {
                    name      = "EXCHANGE_API_KEY"
                    valueFrom = "arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:nmcnpm/exchange_rate_api_key"
                }
            ]

            logConfiguration = {
                logDriver = "awslogs"
                options = {
                "awslogs-group"         = "/ecs/exchange-rate-producer"
                "awslogs-region"        = var.region
                "awslogs-stream-prefix" = "ecs"
                }
            }
        }
    ])
}

#  Streaming Exchange Rate Task Definition
resource "aws_ecs_task_definition" "Streaming_Exchange_Rate_Task_Definition" {
    family = "Streaming_Exchange_Rate_Task"
    network_mode = "awsvpc" #Docker networking mode to use for the containers in the task.
    requires_compatibilities = ["FARGATE"]
    cpu = "256"
    memory = "512"
    execution_role_arn = aws_iam_role.ecs_task_execution_role.arn
    task_role_arn = aws_iam_role.Streaming_Exchange_Rate_Task_Role.arn
    container_definitions = jsonencode([
        {
            name = "Streaming_Exchange_Rate_Container"
            image = var.Streaming_Exchange_Rate_Image_URI != "" ? var.Streaming_Exchange_Rate_Image_URI : "nginx:latest"
            essential = true

            portMappings = [
                {
                    containerPort = 4000
                    hostPort      = 4000
                    protocol      = "tcp"
                }
            ]

            environment = [
                { name = "POLLING_INTERVAL_SECONDS", value = "30" },
                { name = "REDIS_PORT",               value = "6379" },
                { name = "REDIS_SSL",                value = "false" },
                { name = "REDIS_HOST",               value = var.redis_host },
                { name = "AWS_REGION",               value = var.region },
                { name = "ENABLE_CLOUDWATCH_METRICS", value = "true" },
                { name = "PORT",                     value = "4000" }
            ]

            secrets = []

            logConfiguration = {
                logDriver = "awslogs"
                options = {
                "awslogs-group"         = "/ecs/streaming_exchange_rate"
                "awslogs-region"        = var.region
                "awslogs-stream-prefix" = "ecs"
                }
            }
        }
    ])
}

# Dataset Maker Task Definition
resource "aws_ecs_task_definition" "Dataset_Maker_Task_Definition" {
    family = "Dataset_Maker_Task_Definition"
    network_mode = "awsvpc" #Docker networking mode to use for the containers in the task.
    requires_compatibilities = ["FARGATE"]
    cpu = "256"
    memory = "512"
    execution_role_arn = aws_iam_role.ecs_task_execution_role.arn
    task_role_arn = aws_iam_role.Dataset_Maker_Task_Role.arn
    container_definitions = jsonencode([
        {
            name = "Dataset_Maker_Container"
            image = var.Dataset_Maker_Image_URI != "" ? var.Dataset_Maker_Image_URI : "nginx:latest"
            essential = true

            environment = [
                { name = "REDIS_PORT",               value = "6379" },
                { name = "REDIS_SSL",                value = "false" },
                { name = "REDIS_HOST",               value = var.redis_host },
                { name = "AWS_REGION",               value = var.region },
                { name = "ENABLE_CLOUDWATCH_METRICS", value = "true" },
                { name = "S3_BUCKET",                value = var.s3_dataset_bucket_name },
                { name = "DB_HOST",                  value = var.db_host },
                { name = "DB_PORT",                  value = "5432" },
                { name = "DB_NAME",                  value = "currency_exchange" }
            ]

            secrets = [
                {
                    name      = "DB_USER"
                    valueFrom = "${var.rds_secret_arn}:username::"
                },
                {
                    name      = "DB_PASSWORD"
                    valueFrom = "${var.rds_secret_arn}:password::"
                }
            ]

            logConfiguration = {
                logDriver = "awslogs"
                options = {
                "awslogs-group"         = "/ecs/dataset_maker"
                "awslogs-region"        = var.region
                "awslogs-stream-prefix" = "ecs"
                }
            }
        }
    ])
}

# IAM Role cho EventBridge để có quyền trigger ECS RunTask
data "aws_iam_policy_document" "event_bridge_trust_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "event_bridge_role" {
  name               = "nmcnpm-eventbridge-ecs-role"
  assume_role_policy = data.aws_iam_policy_document.event_bridge_trust_policy.json
}

# AWS managed policy cho phép EventBridge gọi ECS RunTask
resource "aws_iam_role_policy_attachment" "event_bridge_ecs_policy" {
  role       = aws_iam_role.event_bridge_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceEventsRole"
}

# Policy cho phép EventBridge trigger Step Functions
# count = 0 khi StepFunctions chưa được tạo (lần apply đầu)
resource "aws_iam_role_policy_attachment" "event_bridge_sfn_policy" {
  count      = var.eventbridge_sfn_policy_arn != "" ? 1 : 0
  role       = aws_iam_role.event_bridge_role.name
  policy_arn = var.eventbridge_sfn_policy_arn
}

# EventBridge Scheduled Rule: trigger ML Pipeline hàng ngày lúc 00:00 ICT (17:00 UTC)
resource "aws_cloudwatch_event_rule" "scheduled_dataset_maker_task" {
    name                = "scheduled_dataset_maker_task"
    description         = "Trigger ML Training Pipeline (Dataset Maker → SageMaker) daily at 00:00 ICT (17:00 UTC)"
    schedule_expression = "cron(0 17 * * ? *)"
}

# Target: Step Functions State Machine
# count = 0 khi StepFunctions chưa được tạo (lần apply đầu)
resource "aws_cloudwatch_event_target" "scheduled_dataset_maker_task_target" {
  count     = var.step_functions_state_machine_arn != "" ? 1 : 0
  target_id = "scheduled_ml_pipeline_target"
  arn       = var.step_functions_state_machine_arn
  rule      = aws_cloudwatch_event_rule.scheduled_dataset_maker_task.name
  role_arn  = aws_iam_role.event_bridge_role.arn
}

# ── Forecast Exchange Rate Task Definition (Task 5.5.9) ───────────────────────
resource "aws_ecs_task_definition" "Forecast_Exchange_Rate_Task_Definition" {
    family                   = "Forecast_Exchange_Rate_Task"
    network_mode             = "awsvpc"
    requires_compatibilities = ["FARGATE"]
    cpu                      = "256"
    memory                   = "512"
    execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
    task_role_arn            = aws_iam_role.Forecast_Exchange_Rate_Task_Role.arn

    container_definitions = jsonencode([
        {
            name      = "Forecast_Exchange_Rate_Container"
            image     = var.Forecast_Exchange_Rate_Image_URI != "" ? var.Forecast_Exchange_Rate_Image_URI : "nginx:latest"
            essential = true

            portMappings = [
                {
                    containerPort = 6000
                    protocol      = "tcp"
                }
            ]

            environment = [
                { name = "PORT",                    value = "6000" },
                { name = "AWS_REGION",              value = var.region },
                { name = "SAGEMAKER_ENDPOINT_NAME", value = var.sagemaker_endpoint },
                { name = "SAGEMAKER_CONNECT_TIMEOUT_SECONDS", value = "3" },
                { name = "SAGEMAKER_READ_TIMEOUT_SECONDS",    value = "8" },
                { name = "COGNITO_USER_POOL_ID",    value = var.user_pool_id },
                { name = "COGNITO_REGION",          value = var.region },
                { name = "JWKS_CACHE_TTL_SECONDS",  value = "86400" }
            ]

            logConfiguration = {
                logDriver = "awslogs"
                options = {
                    "awslogs-group"         = "/ecs/forecast-service"
                    "awslogs-region"        = var.region
                    "awslogs-stream-prefix" = "ecs"
                }
            }
        }
    ])
}

# ── Money Service (Task 6.1.12) ───────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "money_service_logs" {
    name              = "/ecs/money-service"
    retention_in_days = 7
}

# IAM Task Role cho Money Service (least privilege)
resource "aws_iam_role" "Money_Service_Task_Role" {
    name               = "Money_Service_Task_Role"
    assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_trust_policy.json
}

# Cognito Admin API — set custom:premium = true on upgrade
data "aws_iam_policy_document" "money_service_cognito_policy_doc" {
    statement {
        effect  = "Allow"
        actions = ["cognito-idp:AdminUpdateUserAttributes"]
        resources = [
            "arn:aws:cognito-idp:${var.region}:${var.account_id}:userpool/${var.user_pool_id}"
        ]
    }
}

resource "aws_iam_policy" "Money_Service_Cognito_Policy" {
    name   = "Money_Service_Cognito_Policy"
    policy = data.aws_iam_policy_document.money_service_cognito_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "money_service_cognito" {
    role       = aws_iam_role.Money_Service_Task_Role.name
    policy_arn = aws_iam_policy.Money_Service_Cognito_Policy.arn
}

# SSM Parameter Store — read premium_fee
data "aws_iam_policy_document" "money_service_ssm_policy_doc" {
    statement {
        effect    = "Allow"
        actions   = ["ssm:GetParameter"]
        resources = [var.premium_fee_parameter_arn]
    }
}

resource "aws_iam_policy" "Money_Service_SSM_Policy" {
    name   = "Money_Service_SSM_Policy"
    policy = data.aws_iam_policy_document.money_service_ssm_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "money_service_ssm" {
    role       = aws_iam_role.Money_Service_Task_Role.name
    policy_arn = aws_iam_policy.Money_Service_SSM_Policy.arn
}

# Secrets Manager — read RDS credentials and ElastiCache password
data "aws_iam_policy_document" "money_service_secrets_policy_doc" {
    statement {
        effect  = "Allow"
        actions = ["secretsmanager:GetSecretValue"]
        resources = [
            var.rds_secret_arn,
            var.elasticache_secret_arn
        ]
    }
}

resource "aws_iam_policy" "Money_Service_Secrets_Policy" {
    name   = "Money_Service_Secrets_Policy"
    policy = data.aws_iam_policy_document.money_service_secrets_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "money_service_secrets" {
    role       = aws_iam_role.Money_Service_Task_Role.name
    policy_arn = aws_iam_policy.Money_Service_Secrets_Policy.arn
}

# CloudWatch Logs — write structured JSON logs
data "aws_iam_policy_document" "money_service_logs_policy_doc" {
    statement {
        effect = "Allow"
        actions = [
            "logs:CreateLogStream",
            "logs:PutLogEvents"
        ]
        resources = ["${aws_cloudwatch_log_group.money_service_logs.arn}:*"]
    }
}

resource "aws_iam_policy" "Money_Service_Logs_Policy" {
    name   = "Money_Service_Logs_Policy"
    policy = data.aws_iam_policy_document.money_service_logs_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "money_service_logs" {
    role       = aws_iam_role.Money_Service_Task_Role.name
    policy_arn = aws_iam_policy.Money_Service_Logs_Policy.arn
}

# X-Ray — reuse shared xray policy
resource "aws_iam_role_policy_attachment" "xray_money_service_task" {
    role       = aws_iam_role.Money_Service_Task_Role.name
    policy_arn = aws_iam_policy.nmcnpm_xray_policy.arn
}

# ECS Task Definition
resource "aws_ecs_task_definition" "Money_Service_Task_Definition" {
    family                   = "Money_Service_Task"
    network_mode             = "awsvpc"
    requires_compatibilities = ["FARGATE"]
    cpu                      = "512"
    memory                   = "1024"
    execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
    task_role_arn            = aws_iam_role.Money_Service_Task_Role.arn

    container_definitions = jsonencode([
        {
            name      = "Money_Service_Container"
            image     = var.Money_Image_URI != "" ? var.Money_Image_URI : "nginx:latest"
            essential = true

            portMappings = [
                {
                    containerPort = 5000
                    protocol      = "tcp"
                }
            ]

            environment = [
                { name = "PORT",                       value = "5000" },
                { name = "AWS_REGION",                 value = var.region },
                { name = "COGNITO_USER_POOL_ID",       value = var.user_pool_id },
                { name = "COGNITO_REGION",             value = var.region },
                { name = "JWKS_CACHE_TTL_SECONDS",     value = "86400" },
                { name = "DB_HOST",                    value = var.db_host },
                { name = "DB_PORT",                    value = "5432" },
                { name = "DB_NAME",                    value = "currency_exchange" },
                { name = "EXCHANGE_RATE_REDIS_HOST",   value = var.exchange_rate_redis_host },
                { name = "EXCHANGE_RATE_REDIS_PORT",   value = "6379" },
                { name = "EXCHANGE_RATE_REDIS_SSL",    value = "false" },
                { name = "IDEMPOTENCY_REDIS_HOST",     value = var.idempotency_redis_host },
                { name = "IDEMPOTENCY_REDIS_PORT",     value = "6379" },
                { name = "IDEMPOTENCY_REDIS_SSL",      value = "true" },
                { name = "MAX_LOCK_RETRIES",           value = "3" },
                { name = "CLEANUP_INTERVAL_SECONDS",   value = "86400" },
                { name = "IDEMPOTENCY_TTL_DAYS",       value = "7" },
                { name = "AWS_XRAY_DAEMON_ADDRESS",    value = "127.0.0.1:2000" }
            ]

            secrets = [
                {
                    name      = "DB_USER"
                    valueFrom = "${var.rds_secret_arn}:username::"
                },
                {
                    name      = "DB_PASSWORD"
                    valueFrom = "${var.rds_secret_arn}:password::"
                }
            ]

            healthCheck = {
                command     = ["CMD-SHELL", "curl -f http://localhost:5000/health || exit 1"]
                interval    = 30
                timeout     = 5
                retries     = 3
                startPeriod = 60
            }

            logConfiguration = {
                logDriver = "awslogs"
                options = {
                    "awslogs-group"         = aws_cloudwatch_log_group.money_service_logs.name
                    "awslogs-region"        = var.region
                    "awslogs-stream-prefix" = "ecs"
                }
            }
        },

        # AWS X-Ray Daemon sidecar
        {
            name      = "xray-daemon"
            image     = "571832839909.dkr.ecr.ap-southeast-2.amazonaws.com/xray-daemon:latest"
            essential = false

            portMappings = [
                {
                    containerPort = 2000
                    protocol      = "udp"
                }
            ]

            logConfiguration = {
                logDriver = "awslogs"
                options = {
                    "awslogs-group"         = aws_cloudwatch_log_group.money_service_logs.name
                    "awslogs-region"        = var.region
                    "awslogs-stream-prefix" = "xray"
                }
            }
        }
    ])
}

# ── Tour Producer Task Definition & EventBridge Rule (Task 7.1.7 / 7.1.8) ────

resource "aws_cloudwatch_log_group" "tour_producer_logs" {
    name              = "/ecs/tour-producer"
    retention_in_days = 7
}

resource "aws_ecs_task_definition" "Tour_Producer_Task_Definition" {
    family                   = "Tour_Producer_Task"
    network_mode             = "awsvpc"
    requires_compatibilities = ["FARGATE"]
    cpu                      = "256"
    memory                   = "512"
    execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
    task_role_arn            = aws_iam_role.Tour_Producer_Task_Role.arn

    container_definitions = jsonencode([
        {
            name      = "Tour_Producer_Container"
            image     = var.Tour_Producer_Image_URI != "" ? var.Tour_Producer_Image_URI : "nginx:latest"
            essential = true

            environment = [
                { name = "SUPPORTED_CURRENCIES",    value = "USD,EUR,GBP,JPY,CNY,KRW,THB,SGD,MYR,IDR,PHP,AUD" },
                { name = "MAX_TOURS_PER_CURRENCY",  value = "10" },
                { name = "S3_TOUR_BUCKET",          value = var.s3_tour_bucket_name },
                { name = "S3_TOURS_PREFIX",         value = "tours" },
                { name = "S3_IMAGES_PREFIX",        value = "tours/images" },
                { name = "AWS_REGION",              value = var.region },
                { name = "IMAGE_DOWNLOAD_TIMEOUT",  value = "10" },
                { name = "MAX_IMAGE_SIZE_BYTES",    value = "5242880" },
                { name = "VIATOR_API_BASE_URL",       value = "https://api.viator.com/partner" },
                { name = "VIATOR_API_TIMEOUT",        value = "15" }
            ]

            secrets = [
                {
                    name      = "VIATOR_API_KEY"
                    valueFrom = var.viator_api_key_secret_arn
                }
            ]

            logConfiguration = {
                logDriver = "awslogs"
                options = {
                    "awslogs-group"         = "/ecs/tour-producer"
                    "awslogs-region"        = var.region
                    "awslogs-stream-prefix" = "ecs"
                }
            }
        }
    ])

    depends_on = [aws_cloudwatch_log_group.tour_producer_logs]
}

# EventBridge Scheduled Rule: trigger Tour Producer every 24h at 01:00 ICT (18:00 UTC)
# Offset from Dataset Maker (17:00 UTC) to avoid resource contention
resource "aws_cloudwatch_event_rule" "scheduled_tour_producer_task" {
    name                = "scheduled_tour_producer_task"
    description         = "Trigger Tour Producer ECS task every 24h at 00:00 ICT (17:00 UTC)"
    schedule_expression = "cron(0 17 * * ? *)"
}

# EventBridge target: run the Tour Producer ECS task directly (no Step Functions needed)
resource "aws_cloudwatch_event_target" "scheduled_tour_producer_task_target" {
    count     = length(var.public_subnet_ids) > 0 ? 1 : 0
    target_id = "scheduled_tour_producer_target"
    arn       = aws_ecs_cluster.nmcnpm_cluster.arn
    rule      = aws_cloudwatch_event_rule.scheduled_tour_producer_task.name
    role_arn  = aws_iam_role.event_bridge_role.arn

    ecs_target {
        task_definition_arn = aws_ecs_task_definition.Tour_Producer_Task_Definition.arn
        task_count          = 1
        launch_type         = "FARGATE"

        # Tour Producer runs in Public Subnet — needs internet access to call Travelpayouts API
        network_configuration {
            subnets          = var.public_subnet_ids
            security_groups  = [var.producer_sg_id]
            assign_public_ip = true
        }
    }
}

# ── Tour Service Task Definition & ECS Service (Task 7.2.6) ──────────────────

resource "aws_cloudwatch_log_group" "tour_service_logs" {
    name              = "/ecs/tour-service"
    retention_in_days = 7
}

resource "aws_ecs_task_definition" "Tour_Service_Task_Definition" {
    family                   = "Tour_Service_Task"
    network_mode             = "awsvpc"
    requires_compatibilities = ["FARGATE"]
    cpu                      = "256"
    memory                   = "512"
    execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
    task_role_arn            = aws_iam_role.Tour_Display_Task_Role.arn

    container_definitions = jsonencode([
        {
            name      = "Tour_Service_Container"
            image     = var.Tour_Service_Image_URI != "" ? var.Tour_Service_Image_URI : "nginx:latest"
            essential = true

            portMappings = [
                {
                    containerPort = 7000
                    protocol      = "tcp"
                }
            ]

            environment = [
                { name = "PORT",                         value = "7000" },
                { name = "AWS_REGION",                   value = var.region },
                { name = "S3_TOUR_BUCKET",               value = var.s3_tour_bucket_name },
                { name = "S3_TOURS_PREFIX",              value = "tours" },
                { name = "S3_IMAGES_PREFIX",             value = "tours/images" },
                { name = "PRESIGNED_URL_EXPIRY_SECONDS", value = "3600" }
            ]

            healthCheck = {
                command     = ["CMD-SHELL", "curl -f http://localhost:7000/health || exit 1"]
                interval    = 30
                timeout     = 5
                retries     = 3
                startPeriod = 30
            }

            logConfiguration = {
                logDriver = "awslogs"
                options = {
                    "awslogs-group"         = "/ecs/tour-service"
                    "awslogs-region"        = var.region
                    "awslogs-stream-prefix" = "ecs"
                }
            }
        }
    ])

    depends_on = [aws_cloudwatch_log_group.tour_service_logs]
}

# ── Frontend Task Definition ──────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "frontend_logs" {
    name              = "/ecs/frontend"
    retention_in_days = 7
}

variable "Frontend_Image_URI" {
    description = "ECR image URI cho Frontend service"
    type        = string
    default     = ""
}

resource "aws_ecs_task_definition" "Frontend_Task_Definition" {
    family                   = "Frontend_Task"
    network_mode             = "awsvpc"
    requires_compatibilities = ["FARGATE"]
    cpu                      = "256"
    memory                   = "512"
    execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
    task_role_arn            = aws_iam_role.Frontend_Task_Role.arn

    container_definitions = jsonencode([
        {
            name      = "Frontend_Container"
            image     = var.Frontend_Image_URI != "" ? var.Frontend_Image_URI : "nginx:latest"
            essential = true

            portMappings = [
                {
                    containerPort = 3000
                    protocol      = "tcp"
                }
            ]

            environment = [
                { name = "PORT",       value = "3000" },
                { name = "AWS_REGION", value = var.region }
            ]

            logConfiguration = {
                logDriver = "awslogs"
                options = {
                    "awslogs-group"         = "/ecs/frontend"
                    "awslogs-region"        = var.region
                    "awslogs-stream-prefix" = "ecs"
                }
            }
        }
    ])

    depends_on = [aws_cloudwatch_log_group.frontend_logs]
}
