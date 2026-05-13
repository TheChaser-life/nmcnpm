# ── IAM Role cho Post-Confirmation Lambda ────────────────────────────────────

# Trust policy: chỉ Lambda service mới được assume role này
data "aws_iam_policy_document" "lambda_assume_role" {
    statement {
        effect  = "Allow"
        actions = ["sts:AssumeRole"]
        principals {
            type        = "Service"
            identifiers = ["lambda.amazonaws.com"]
        }
    }
}

resource "aws_iam_role" "post_confirmation_lambda_role" {
    name               = "post-confirmation-lambda-role"
    assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

# ── Policy: đọc RDS credentials từ Secrets Manager ───────────────────────────

data "aws_iam_policy_document" "lambda_secrets_policy" {
    statement {
        sid     = "ReadRDSSecret"
        effect  = "Allow"
        actions = ["secretsmanager:GetSecretValue"]
        # Giới hạn chỉ đúng secret RDS, không cho đọc secret khác (least privilege)
        resources = [var.rds_secret_arn]
    }
}

resource "aws_iam_policy" "lambda_secrets_policy" {
    name   = "post-confirmation-lambda-secrets-policy"
    policy = data.aws_iam_policy_document.lambda_secrets_policy.json
}

resource "aws_iam_role_policy_attachment" "lambda_secrets" {
    role       = aws_iam_role.post_confirmation_lambda_role.name
    policy_arn = aws_iam_policy.lambda_secrets_policy.arn
}

# ── Policy: ghi CloudWatch Logs ───────────────────────────────────────────────
# AWSLambdaBasicExecutionRole là managed policy chuẩn của AWS cho Lambda logging

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
    role       = aws_iam_role.post_confirmation_lambda_role.name
    policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ── Policy: tạo/xóa ENI khi Lambda chạy trong VPC ────────────────────────────
# Bắt buộc khi Lambda cần kết nối RDS trong Private Subnet

resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
    role       = aws_iam_role.post_confirmation_lambda_role.name
    policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# ── Lambda Function ───────────────────────────────────────────────────────────

resource "aws_lambda_function" "post_confirmation_function" {
    count         = var.cert_arn != "" ? 1 : 0
    function_name = "post-confirmation-lambda"
    package_type  = "Image"
    image_uri     = var.post_confirmation_function_image_uri
    role          = aws_iam_role.post_confirmation_lambda_role.arn

    # VPC config để Lambda kết nối được RDS trong Private Subnet (task 3.2.2)
    vpc_config {
        subnet_ids         = var.private_subnet_ids
        security_group_ids = [var.lambda_sg_id]
    }

    environment {
        variables = {
            DB_SECRET_ARN = var.rds_secret_arn
            DB_HOST       = var.db_host
            DB_PORT       = "5432"
            DB_NAME       = var.db_name
        }
    }

    # CI/CD pipeline sẽ update image_uri sau mỗi push — Terraform không ghi đè
    lifecycle {
        ignore_changes = [image_uri]
    }
}

# ── Cognito trigger permission ────────────────────────────────────────────────
# Cho phép Cognito User Pool gọi Lambda này (task 3.2.3)

resource "aws_lambda_permission" "allow_cognito" {
    count         = var.cert_arn != "" ? 1 : 0
    statement_id  = "AllowCognitoInvoke"
    action        = "lambda:InvokeFunction"
    function_name = var.cert_arn != "" ? aws_lambda_function.post_confirmation_function[0].function_name : "dummy"
    principal     = "cognito-idp.amazonaws.com"
    source_arn    = var.cognito_user_pool_arn
}


# ════════════════════════════════════════════════════════════════════════════════
# Model Promotion Lambda
# Task 5.3.1: So sánh metric của model mới với model hiện tại trong Registry
# ════════════════════════════════════════════════════════════════════════════════

# ── IAM Role cho Model Promotion Lambda ──────────────────────────────────────

resource "aws_iam_role" "model_promotion_lambda_role" {
    name               = "model-promotion-lambda-role"
    assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

# ── Policy: SageMaker Model Registry permissions ──────────────────────────────

data "aws_iam_policy_document" "model_promotion_sagemaker_policy" {
    # Đọc thông tin model package (để lấy metrics S3 URI và group name)
    statement {
        sid    = "DescribeModelPackage"
        effect = "Allow"
        actions = [
            "sagemaker:DescribeModelPackage",
            "sagemaker:ListModelPackages",
        ]
        resources = ["*"]
    }

    # Cập nhật trạng thái approval của model package (Approved / Rejected)
    statement {
        sid    = "UpdateModelPackage"
        effect = "Allow"
        actions = ["sagemaker:UpdateModelPackage"]
        resources = [
            "arn:aws:sagemaker:*:*:model-package/${var.model_package_group_name}/*"
        ]
    }

    # Đọc/cập nhật SageMaker Endpoint khi promote model mới
    statement {
        sid    = "ManageSageMakerEndpoint"
        effect = "Allow"
        actions = [
            "sagemaker:DescribeEndpoint",
            "sagemaker:UpdateEndpoint",
            "sagemaker:CreateEndpointConfig",
            "sagemaker:DescribeEndpointConfig",
        ]
        resources = [
            "arn:aws:sagemaker:*:*:endpoint/${var.sagemaker_endpoint_name}",
            "arn:aws:sagemaker:*:*:endpoint-config/forecast-endpoint-config-*",
        ]
    }

    # Tạo SageMaker Model resource để wrap model package khi promote
    statement {
        sid    = "CreateSageMakerModel"
        effect = "Allow"
        actions = [
            "sagemaker:CreateModel",
            "sagemaker:DescribeModel",
        ]
        resources = [
            "arn:aws:sagemaker:*:*:model/forecast-model-*",
        ]
    }

    # PassRole: Lambda cần pass SageMaker execution role khi tạo Model resource
    statement {
        sid    = "PassSageMakerExecutionRole"
        effect = "Allow"
        actions = ["iam:PassRole"]
        resources = [var.sagemaker_execution_role_arn]
    }
}

resource "aws_iam_policy" "model_promotion_sagemaker_policy" {
    name   = "model-promotion-lambda-sagemaker-policy"
    policy = data.aws_iam_policy_document.model_promotion_sagemaker_policy.json
}

resource "aws_iam_role_policy_attachment" "model_promotion_sagemaker" {
    role       = aws_iam_role.model_promotion_lambda_role.name
    policy_arn = aws_iam_policy.model_promotion_sagemaker_policy.arn
}

# ── Policy: đọc metrics.json từ S3 ───────────────────────────────────────────

data "aws_iam_policy_document" "model_promotion_s3_policy" {
    statement {
        sid    = "ReadModelArtifacts"
        effect = "Allow"
        actions = ["s3:GetObject"]
        resources = [
            "arn:aws:s3:::${var.model_artifact_bucket}/*"
        ]
    }
}

resource "aws_iam_policy" "model_promotion_s3_policy" {
    name   = "model-promotion-lambda-s3-policy"
    policy = data.aws_iam_policy_document.model_promotion_s3_policy.json
}

resource "aws_iam_role_policy_attachment" "model_promotion_s3" {
    role       = aws_iam_role.model_promotion_lambda_role.name
    policy_arn = aws_iam_policy.model_promotion_s3_policy.arn
}

# ── Policy: ghi CloudWatch Logs ───────────────────────────────────────────────

resource "aws_iam_role_policy_attachment" "model_promotion_basic_execution" {
    role       = aws_iam_role.model_promotion_lambda_role.name
    policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ── Lambda Function ───────────────────────────────────────────────────────────

resource "aws_lambda_function" "model_promotion_function" {
    count         = var.cert_arn != "" ? 1 : 0
    function_name = "model-promotion-lambda"
    package_type  = "Image"
    image_uri     = var.model_promotion_function_image_uri
    role          = aws_iam_role.model_promotion_lambda_role.arn

    # Timeout: so sánh metric có thể cần đọc file S3 lớn — 60s là đủ
    timeout     = 60
    memory_size = 256

    environment {
        variables = {
            APP_REGION                  = var.aws_region
            PRIMARY_METRIC              = "mean_rmse"
            MODEL_PACKAGE_GROUP         = var.model_package_group_name
            SAGEMAKER_ENDPOINT_NAME     = var.sagemaker_endpoint_name
            SAGEMAKER_EXECUTION_ROLE_ARN = var.sagemaker_execution_role_arn
        }
    }

    # CI/CD pipeline sẽ update image_uri sau mỗi push — Terraform không ghi đè
    lifecycle {
        ignore_changes = [image_uri]
    }
}

# ── Step Functions invoke permission ─────────────────────────────────────────
# Cho phép Step Functions gọi Lambda này (task 5.3.4)

resource "aws_lambda_permission" "allow_step_functions_model_promotion" {
    count         = var.cert_arn != "" ? 1 : 0
    statement_id  = "AllowStepFunctionsInvoke"
    action        = "lambda:InvokeFunction"
    function_name = var.cert_arn != "" ? aws_lambda_function.model_promotion_function[0].function_name : "dummy"
    principal     = "states.amazonaws.com"
    source_arn    = var.step_functions_state_machine_arn
}
