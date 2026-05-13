# ── IAM Role cho SageMaker ────────────────────────────────────────────────────

data "aws_iam_policy_document" "sagemaker_trust_policy" {
    statement {
        effect  = "Allow"
        actions = ["sts:AssumeRole"]
        principals {
            type        = "Service"
            identifiers = ["sagemaker.amazonaws.com"]
        }
    }
}

resource "aws_iam_role" "sagemaker_training_role" {
    name               = "sagemaker_training_role"
    assume_role_policy = data.aws_iam_policy_document.sagemaker_trust_policy.json
}

# Policy cho phép SageMaker đọc training data và ghi model artifacts vào S3
data "aws_iam_policy_document" "sagemaker_s3_policy_document" {
    # Đọc training data từ Dataset Maker
    statement {
        effect  = "Allow"
        actions = ["s3:ListBucket", "s3:GetObject"]
        resources = [
            "arn:aws:s3:::${var.training_data_bucket}",
            "arn:aws:s3:::${var.training_data_bucket}/*"
        ]
    }

    # Ghi model artifacts
    statement {
        effect  = "Allow"
        actions = ["s3:PutObject", "s3:GetObject"]
        resources = [
            "arn:aws:s3:::${var.model_artifact_bucket}",
            "arn:aws:s3:::${var.model_artifact_bucket}/*"
        ]
    }
}

resource "aws_iam_policy" "sagemaker_s3_policy" {
    name   = "sagemaker_s3_policy"
    policy = data.aws_iam_policy_document.sagemaker_s3_policy_document.json
}

resource "aws_iam_role_policy_attachment" "sagemaker_s3_policy_attachment" {
    role       = aws_iam_role.sagemaker_training_role.name
    policy_arn = aws_iam_policy.sagemaker_s3_policy.arn
}

# Cho phép SageMaker ghi logs vào CloudWatch
resource "aws_iam_role_policy_attachment" "sagemaker_cloudwatch_policy_attachment" {
    role       = aws_iam_role.sagemaker_training_role.name
    policy_arn = "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
}

# Policy cho phép SageMaker pull training image từ ECR
data "aws_iam_policy_document" "sagemaker_ecr_policy_document" {
    statement {
        effect  = "Allow"
        actions = [
            "ecr:BatchCheckLayerAvailability",
            "ecr:BatchGetImage",
            "ecr:GetDownloadUrlForLayer"
        ]
        resources = ["arn:aws:ecr:${var.region}:${var.account_id}:repository/*"]
    }

    statement {
        effect    = "Allow"
        actions   = ["ecr:GetAuthorizationToken"]
        resources = ["*"]
    }
}

resource "aws_iam_policy" "sagemaker_ecr_policy" {
    name   = "sagemaker_ecr_policy"
    policy = data.aws_iam_policy_document.sagemaker_ecr_policy_document.json
}

resource "aws_iam_role_policy_attachment" "sagemaker_ecr_policy_attachment" {
    role       = aws_iam_role.sagemaker_training_role.name
    policy_arn = aws_iam_policy.sagemaker_ecr_policy.arn
}
# Policy cho phép SageMaker mô tả VPC resources khi training job chạy trong VPC
data "aws_iam_policy_document" "sagemaker_vpc_policy_document" {
    statement {
        effect  = "Allow"
        actions = [
            "ec2:DescribeSubnets",
            "ec2:DescribeSecurityGroups",
            "ec2:DescribeVpcs",
            "ec2:DescribeNetworkInterfaces",
            "ec2:DescribeDhcpOptions",
            "ec2:DescribeVpcEndpoints",
            "ec2:DescribeRouteTables",
            "ec2:CreateNetworkInterface",
            "ec2:DeleteNetworkInterface",
            "ec2:CreateNetworkInterfacePermission"
        ]
        resources = ["*"]
    }
}

resource "aws_iam_policy" "sagemaker_vpc_policy" {
    name   = "sagemaker_vpc_policy"
    policy = data.aws_iam_policy_document.sagemaker_vpc_policy_document.json
}

resource "aws_iam_role_policy_attachment" "sagemaker_vpc_policy_attachment" {
    role       = aws_iam_role.sagemaker_training_role.name
    policy_arn = aws_iam_policy.sagemaker_vpc_policy.arn
}

# Task 5.2.5: Cấu hình Model Registry với evaluation metrics (RMSE/MAE)
# Lưu trữ tất cả phiên bản model đã huấn luyện để audit và rollback

resource "aws_sagemaker_model_package_group" "forecast_model_registry" {
    model_package_group_name        = "forecast-model-registry"
    model_package_group_description = "Registry lưu trữ tất cả phiên bản XGBoost forecast model. Mỗi version kèm evaluation metrics (RMSE, MAE) để so sánh và promote model tốt nhất lên SageMaker Endpoint."
}

# Policy cho phép SageMaker Training Role đăng ký model vào Model Registry
data "aws_iam_policy_document" "sagemaker_model_registry_policy_document" {
    statement {
        effect  = "Allow"
        actions = [
            "sagemaker:CreateModelPackage",
            "sagemaker:DescribeModelPackage",
            "sagemaker:ListModelPackages",
            "sagemaker:UpdateModelPackage",
            "sagemaker:DescribeModelPackageGroup"
        ]
        resources = [
            aws_sagemaker_model_package_group.forecast_model_registry.arn,
            "arn:aws:sagemaker:*:*:model-package/forecast_model_registry/*"
        ]
    }
}

resource "aws_iam_policy" "sagemaker_model_registry_policy" {
    name   = "sagemaker_model_registry_policy"
    policy = data.aws_iam_policy_document.sagemaker_model_registry_policy_document.json
}

resource "aws_iam_role_policy_attachment" "sagemaker_model_registry_policy_attachment" {
    role       = aws_iam_role.sagemaker_training_role.name
    policy_arn = aws_iam_policy.sagemaker_model_registry_policy.arn
}

# ── SageMaker Endpoint (task 5.4) ─────────────────────────────────────────────
# Task 5.4.1: Tạo Endpoint Configuration
# Task 5.4.2: Deploy initial model lên Endpoint
# Task 5.4.3: Cấu hình Endpoint trong Private Subnet (VPC config)
#
# Thiết kế: Terraform chỉ deploy initial model để Endpoint có thể khởi động.
# Sau đó, model promotion Lambda (task 5.3) sẽ tự động gọi UpdateEndpoint
# mỗi khi có model mới tốt hơn — Terraform không quản lý vòng đời model sau này.

# aws_sagemaker_model: Khai báo model resource trỏ vào initial model package trong Registry.
# Model promotion Lambda sẽ tạo model resource mới (forecast-model-<timestamp>) khi promote.
resource "aws_sagemaker_model" "forecast_initial_model" {
    count              = var.initial_model_package_arn != "" ? 1 : 0
    name               = "forecast-initial-model-${substr(md5(var.initial_model_package_arn), 0, 8)}"
    execution_role_arn = aws_iam_role.sagemaker_training_role.arn

    # Dùng model_package_name để trỏ vào Model Registry — đúng với kiến trúc
    # model promotion Lambda cũng dùng cách này khi tạo model resource mới
    container {
        model_package_name = var.initial_model_package_arn
    }

    # Task 5.4.3: VPC config — Endpoint chạy trong Private Subnet, không expose ra internet
    # Truy cập từ Forecast Service qua VPC Interface Endpoint của SageMaker
    vpc_config {
        subnets            = var.private_subnet_ids
        security_group_ids = [var.sagemaker_sg_id]
    }

    # CI/CD và model promotion Lambda sẽ tạo model resource mới — Terraform không ghi đè
    lifecycle {
        ignore_changes = [container]
    }
}

# Task 5.4.1: Endpoint Configuration — cấu hình phần cứng và traffic routing
# ml.t2.medium là instance nhỏ nhất SageMaker Endpoint hỗ trợ (~$0.056/giờ)
# phù hợp cho XGBoost inference (CPU-bound, latency thấp)
resource "aws_sagemaker_endpoint_configuration" "forecast_endpoint_config" {
    count = var.initial_model_package_arn != "" ? 1 : 0
    name  = "forecast-endpoint-config-${substr(md5(var.initial_model_package_arn), 0, 8)}"

    production_variants {
        variant_name           = "AllTraffic"
        model_name             = aws_sagemaker_model.forecast_initial_model[0].name
        initial_instance_count = 1
        instance_type          = "ml.t2.medium"
        initial_variant_weight = 1
    }

    # Model promotion Lambda tạo endpoint config mới mỗi lần promote
    # Terraform chỉ quản lý config ban đầu này
    lifecycle {
        ignore_changes = [production_variants]
    }
}

# Task 5.4.2: Deploy Endpoint — khởi tạo URL thực tế để Forecast Service gọi đến
resource "aws_sagemaker_endpoint" "forecast_endpoint" {
    count                = var.initial_model_package_arn != "" ? 1 : 0
    name                 = "forecast-endpoint"
    endpoint_config_name = aws_sagemaker_endpoint_configuration.forecast_endpoint_config[0].name

    # Model promotion Lambda sẽ gọi UpdateEndpoint để thay endpoint_config_name
    # khi có model mới — Terraform không ghi đè sau lần deploy đầu
    lifecycle {
        ignore_changes = [endpoint_config_name]
    }
}

