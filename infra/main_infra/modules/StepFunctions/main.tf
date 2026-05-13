# ── IAM Role cho Step Functions ───────────────────────────────────────────────

data "aws_iam_policy_document" "step_functions_trust_policy" {
    statement {
        effect  = "Allow"
        actions = ["sts:AssumeRole"]
        principals {
            type        = "Service"
            identifiers = ["states.amazonaws.com"]
        }
    }
}

resource "aws_iam_role" "step_functions_role" {
    name               = "step_functions_role"
    assume_role_policy = data.aws_iam_policy_document.step_functions_trust_policy.json
}

# Policy: cho phép Step Functions chạy ECS Task (Dataset Maker)
data "aws_iam_policy_document" "step_functions_ecs_policy_document" {
    # Chạy ECS Task
    statement {
        effect  = "Allow"
        actions = ["ecs:RunTask"]
        resources = [var.dataset_maker_task_definition_arn]
    }

    # Dừng ECS Task nếu cần (cleanup khi workflow fail)
    statement {
        effect  = "Allow"
        actions = ["ecs:StopTask", "ecs:DescribeTasks"]
        resources = ["*"]
    }

    # PassRole: Step Functions cần pass IAM roles cho ECS task
    statement {
        effect  = "Allow"
        actions = ["iam:PassRole"]
        resources = [
            var.ecs_task_execution_role_arn,
            var.dataset_maker_task_role_arn
        ]
    }

    # EventBridge integration: Step Functions dùng để sync với ECS task completion
    statement {
        effect  = "Allow"
        actions = [
            "events:PutTargets",
            "events:PutRule",
            "events:DescribeRule"
        ]
        resources = [
            "arn:aws:events:${var.region}:${var.account_id}:rule/StepFunctions*"
        ]
    }
}

resource "aws_iam_policy" "step_functions_ecs_policy" {
    name   = "nmcnpm-step-functions-ecs-policy"
    policy = data.aws_iam_policy_document.step_functions_ecs_policy_document.json
}

resource "aws_iam_role_policy_attachment" "step_functions_ecs_policy_attachment" {
    role       = aws_iam_role.step_functions_role.name
    policy_arn = aws_iam_policy.step_functions_ecs_policy.arn
}

# Policy: cho phép Step Functions trigger SageMaker Training Job
data "aws_iam_policy_document" "step_functions_sagemaker_policy_document" {
    statement {
        effect  = "Allow"
        actions = [
            "sagemaker:CreateTrainingJob",
            "sagemaker:DescribeTrainingJob",
            "sagemaker:StopTrainingJob",
            "sagemaker:AddTags"
        ]
        resources = [
            "arn:aws:sagemaker:${var.region}:${var.account_id}:training-job/*"
        ]
    }

    # PassRole: Step Functions cần pass SageMaker execution role
    statement {
        effect  = "Allow"
        actions = ["iam:PassRole"]
        resources = [var.sagemaker_training_role_arn]
    }

    # Quyền đăng ký model vào SageMaker Model Registry
    statement {
        effect  = "Allow"
        actions = [
            "sagemaker:CreateModelPackage",
            "sagemaker:DescribeModelPackage",
            "sagemaker:ListModelPackages",
            "sagemaker:UpdateModelPackage"
        ]
        resources = [
            "arn:aws:sagemaker:${var.region}:${var.account_id}:model-package-group/${var.model_package_group_name}",
            "arn:aws:sagemaker:${var.region}:${var.account_id}:model-package/${var.model_package_group_name}/*"
        ]
    }

    statement {
        effect = "Allow"
        actions = [
            "s3:GetObject",
            "s3:ListBucket"
        ]
        resources = [
            "arn:aws:s3:::${var.model_artifact_bucket}",
            "arn:aws:s3:::${var.model_artifact_bucket}/*"
        ]
    }

    statement {
        effect = "Allow"
        actions = [
            "ecr:BatchCheckLayerAvailability",
            "ecr:BatchGetImage",
            "ecr:DescribeImages",
            "ecr:GetDownloadUrlForLayer"
        ]
        resources = [
            "arn:aws:ecr:${var.region}:${var.account_id}:repository/forecast_training_repo"
        ]
    }

    statement {
        effect    = "Allow"
        actions   = ["ecr:GetAuthorizationToken"]
        resources = ["*"]
    }
}

resource "aws_iam_policy" "step_functions_sagemaker_policy" {
    name   = "nmcnpm-step-functions-sagemaker-policy"
    policy = data.aws_iam_policy_document.step_functions_sagemaker_policy_document.json
}

resource "aws_iam_role_policy_attachment" "step_functions_sagemaker_policy_attachment" {
    role       = aws_iam_role.step_functions_role.name
    policy_arn = aws_iam_policy.step_functions_sagemaker_policy.arn
}

# Policy: ghi execution logs vào CloudWatch
data "aws_iam_policy_document" "step_functions_logs_policy_document" {
    statement {
        effect  = "Allow"
        actions = [
            "logs:CreateLogDelivery",
            "logs:GetLogDelivery",
            "logs:UpdateLogDelivery",
            "logs:DeleteLogDelivery",
            "logs:ListLogDeliveries",
            "logs:PutResourcePolicy",
            "logs:DescribeResourcePolicies",
            "logs:DescribeLogGroups"
        ]
        resources = ["*"]
    }
}

resource "aws_iam_policy" "step_functions_logs_policy" {
    name   = "nmcnpm-step-functions-logs-policy"
    policy = data.aws_iam_policy_document.step_functions_logs_policy_document.json
}

resource "aws_iam_role_policy_attachment" "step_functions_logs_policy_attachment" {
    role       = aws_iam_role.step_functions_role.name
    policy_arn = aws_iam_policy.step_functions_logs_policy.arn
}

# Policy: cho phép Step Functions invoke model promotion Lambda
data "aws_iam_policy_document" "step_functions_lambda_policy_document" {
    statement {
        effect  = "Allow"
        actions = ["lambda:InvokeFunction"]
        resources = [var.model_promotion_lambda_arn]
    }
}

resource "aws_iam_policy" "step_functions_lambda_policy" {
    name   = "nmcnpm-step-functions-lambda-policy"
    policy = data.aws_iam_policy_document.step_functions_lambda_policy_document.json
}

resource "aws_iam_role_policy_attachment" "step_functions_lambda_policy_attachment" {
    role       = aws_iam_role.step_functions_role.name
    policy_arn = aws_iam_policy.step_functions_lambda_policy.arn
}

# ── CloudWatch Log Group cho Step Functions ───────────────────────────────────

resource "aws_cloudwatch_log_group" "step_functions_log_group" {
    name              = "/aws/states/nmcnpm-ml-pipeline"
    retention_in_days = 7
}

# ── Step Functions State Machine ──────────────────────────────────────────────
# Workflow: Dataset Maker (ECS) → SageMaker Training Job
# Task 5.2.4: Thiết lập Step Functions workflow

resource "aws_sfn_state_machine" "ml_training_pipeline" {
    name     = "nmcnpm-ml-training-pipeline"
    role_arn = aws_iam_role.step_functions_role.arn
    type     = "STANDARD"  # STANDARD hỗ trợ long-running jobs (SageMaker training có thể mất hàng giờ)

    # Amazon States Language (ASL) định nghĩa workflow
    definition = jsonencode({
        Comment = "ML Training Pipeline: Dataset Maker → SageMaker Training Job"
        StartAt = "RunDatasetMaker"

        States = {
            # ── State 1: Chạy Dataset Maker ECS Task ─────────────────────────
            RunDatasetMaker = {
                Type     = "Task"
                Resource = "arn:aws:states:::ecs:runTask.sync"
                Comment  = "Chạy Dataset Maker để thu thập và upload training data lên S3"

                Parameters = {
                    Cluster        = var.ecs_cluster_arn
                    TaskDefinition = var.dataset_maker_task_definition_arn
                    LaunchType     = "FARGATE"
                    NetworkConfiguration = {
                        AwsvpcConfiguration = {
                            Subnets        = var.private_subnet_ids
                            SecurityGroups = [var.ecs_services_sg_id]
                            AssignPublicIp = "DISABLED"
                        }
                    }
                }

                # Retry: tối đa 2 lần nếu ECS task fail do transient error
                Retry = [
                    {
                        ErrorEquals     = ["States.TaskFailed"]
                        IntervalSeconds = 30
                        MaxAttempts     = 2
                        BackoffRate     = 2.0
                    }
                ]

                # Catch: nếu Dataset Maker fail sau retry → chuyển sang FailState
                Catch = [
                    {
                        ErrorEquals = ["States.ALL"]
                        Next        = "DatasetMakerFailed"
                        ResultPath  = "$.error"
                    }
                ]

                Next = "StartSageMakerTrainingJob"
            }

            # ── State 2: Trigger SageMaker Training Job ───────────────────────
            StartSageMakerTrainingJob = {
                Type     = "Task"
                Resource = "arn:aws:states:::sagemaker:createTrainingJob.sync"
                Comment  = "Huấn luyện XGBoost model với training data vừa được tạo"

                Parameters = {
                    # Training job name <= 63 chars, only [a-zA-Z0-9-]
                    # Execution.Name đã có epoch timestamp → unique giữa các lần chạy
                    # State.RetryCount (0/1/2...) → unique giữa các retry trong cùng execution
                    "TrainingJobName.$" = "States.Format('fct-{}-r{}', States.UUID(), $$.State.RetryCount)"

                    RoleArn   = var.sagemaker_training_role_arn
                    AlgorithmSpecification = {
                        TrainingInputMode = "File"
                        TrainingImage     = var.training_image
                    }

                    # Hyperparameters — khớp với load_hyperparameters() trong train.py
                    HyperParameters = {
                        n_estimators     = "100"
                        max_depth        = "6"
                        learning_rate    = "0.1"
                        subsample        = "0.8"
                        colsample_bytree = "0.8"
                        objective        = "reg:squarederror"
                        lag_days         = "1"
                        forecast_horizon = "1"
                    }

                    InputDataConfig = [
                        {
                            ChannelName = "training"
                            DataSource = {
                                S3DataSource = {
                                    S3DataType             = "S3Prefix"
                                    S3Uri                  = "s3://${var.training_data_bucket}/training-data/"
                                    S3DataDistributionType = "FullyReplicated"
                                }
                            }
                            ContentType     = "text/csv"
                            CompressionType = "None"
                        }
                    ]

                    OutputDataConfig = {
                        S3OutputPath = "s3://${var.model_artifact_bucket}/model-artifacts/"
                    }

                    ResourceConfig = {
                        InstanceType   = "ml.m5.large"
                        InstanceCount  = 1
                        VolumeSizeInGB = 20
                    }

                    StoppingCondition = {
                        MaxRuntimeInSeconds = 3600
                    }

                    VpcConfig = {
                        SecurityGroupIds = [var.sagemaker_sg_id]
                        Subnets          = var.private_subnet_ids
                    }
                }

                # Retry: tối đa 1 lần nếu Training Job fail do transient error
                Retry = [
                    {
                        ErrorEquals     = ["States.TaskFailed"]
                        IntervalSeconds = 60
                        MaxAttempts     = 1
                        BackoffRate     = 2.0
                    }
                ]

                # Catch: nếu Training Job fail → chuyển sang FailState
                Catch = [
                    {
                        ErrorEquals = ["States.ALL"]
                        Next        = "TrainingJobFailed"
                        ResultPath  = "$.error"
                    }
                ]

                Next = "RegisterModelInRegistry"
            }

            # ── State 3: Đăng ký model vào SageMaker Model Registry ───────────
            # Task 5.2.5: Cấu hình Model Registry với evaluation metrics (RMSE/MAE)
            RegisterModelInRegistry = {
                Type     = "Task"
                Resource = "arn:aws:states:::aws-sdk:sagemaker:createModelPackage"
                Comment  = "Đăng ký model artifact vào Model Registry kèm evaluation metrics để so sánh và promote"

                Parameters = {
                    ModelPackageGroupName = var.model_package_group_name

                    # Model chờ Lambda (task 5.3) xét duyệt tự động dựa trên metric
                    ModelApprovalStatus = "PendingManualApproval"

                    ModelPackageDescription = "XGBoost forecast model — đăng ký tự động bởi Step Functions ML pipeline"

                    # Inference specification: container image dùng để serve model
                    InferenceSpecification = {
                        Containers = [
                            {
                                Image = var.training_image
                                # Đường dẫn S3 tới model artifact từ output của Training Job
                                "ModelDataUrl.$" = "States.Format('s3://${var.model_artifact_bucket}/model-artifacts/{}/output/model.tar.gz', $.TrainingJobName)"
                            }
                        ]
                        SupportedContentTypes     = ["text/csv"]
                        SupportedResponseMIMETypes = ["text/csv"]
                    }

                    # Evaluation metrics: RMSE là primary metric, MAE là secondary
                    # Giá trị thực tế được ghi bởi training script vào /opt/ml/output/metrics.json
                    # và được đọc bởi Lambda promotion function (task 5.3)
                    ModelMetrics = {
                        ModelQuality = {
                            Statistics = {
                                ContentType = "application/json"
                                # S3 URI tới file metrics.json do training script xuất ra
                                "S3Uri.$" = "States.Format('s3://${var.model_artifact_bucket}/model-artifacts/{}/output/metrics.json', $.TrainingJobName)"
                            }
                        }
                    }

                    # Metadata chứa tên training job để Lambda có thể tra cứu metrics chi tiết
                    MetadataProperties = {
                        "GeneratedBy.$" = "$.TrainingJobName"
                    }
                }

                # Retry: tối đa 2 lần nếu Model Registry API fail do transient error
                Retry = [
                    {
                        ErrorEquals     = ["States.TaskFailed"]
                        IntervalSeconds = 30
                        MaxAttempts     = 2
                        BackoffRate     = 2.0
                    }
                ]

                # Catch: nếu đăng ký model fail → chuyển sang FailState
                Catch = [
                    {
                        ErrorEquals = ["States.ALL"]
                        Next        = "ModelRegistrationFailed"
                        ResultPath  = "$.error"
                    }
                ]

                Next = "InvokeModelPromotion"
            }

            # ── State 4: Invoke Model Promotion Lambda ────────────────────────
            # Task 5.3.4: Gắn Lambda vào Step Functions workflow sau Training Job
            InvokeModelPromotion = {
                Type     = "Task"
                Resource = "arn:aws:states:::lambda:invoke"
                Comment  = "Gọi model promotion Lambda để so sánh RMSE và promote model tốt nhất lên SageMaker Endpoint"

                Parameters = {
                    FunctionName   = var.model_promotion_lambda_arn
                    "Payload.$"    = "$"
                }

                # Merge kết quả Lambda vào execution context (không ghi đè input)
                ResultPath = "$.promotionResult"

                # Retry: tối đa 2 lần nếu Lambda fail do transient error
                Retry = [
                    {
                        ErrorEquals     = ["States.TaskFailed", "Lambda.ServiceException", "Lambda.AWSLambdaException"]
                        IntervalSeconds = 30
                        MaxAttempts     = 2
                        BackoffRate     = 2.0
                    }
                ]

                # Catch: nếu Lambda fail sau retry → chuyển sang FailState
                Catch = [
                    {
                        ErrorEquals = ["States.ALL"]
                        Next        = "ModelPromotionFailed"
                        ResultPath  = "$.error"
                    }
                ]

                Next = "TrainingComplete"
            }

            # ── Terminal States ───────────────────────────────────────────────
            TrainingComplete = {
                Type    = "Succeed"
                Comment = "ML pipeline hoàn thành. Model artifact đã được lưu vào S3 và đăng ký vào Model Registry."
            }

            DatasetMakerFailed = {
                Type    = "Fail"
                Error   = "DatasetMakerFailed"
                Cause   = "Dataset Maker ECS task thất bại sau khi retry"
            }

            TrainingJobFailed = {
                Type    = "Fail"
                Error   = "TrainingJobFailed"
                Cause   = "SageMaker Training Job thất bại sau khi retry"
            }

            ModelRegistrationFailed = {
                Type    = "Fail"
                Error   = "ModelRegistrationFailed"
                Cause   = "Đăng ký model vào SageMaker Model Registry thất bại sau khi retry"
            }

            ModelPromotionFailed = {
                Type  = "Fail"
                Error = "ModelPromotionFailed"
                Cause = "Model promotion Lambda thất bại sau khi retry"
            }
        }
    })

    logging_configuration {
        log_destination        = "${aws_cloudwatch_log_group.step_functions_log_group.arn}:*"
        include_execution_data = true
        level                  = "ERROR"  # Chỉ log khi có lỗi để tiết kiệm chi phí
    }
}

# ── IAM: Cho phép EventBridge trigger Step Functions ─────────────────────────

data "aws_iam_policy_document" "eventbridge_sfn_policy_document" {
    statement {
        effect  = "Allow"
        actions = ["states:StartExecution"]
        resources = [aws_sfn_state_machine.ml_training_pipeline.arn]
    }
}

resource "aws_iam_policy" "eventbridge_sfn_policy" {
    name   = "nmcnpm-eventbridge-sfn-policy"
    policy = data.aws_iam_policy_document.eventbridge_sfn_policy_document.json
}

