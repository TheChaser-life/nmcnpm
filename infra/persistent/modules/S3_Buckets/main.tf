# S3 bucket cho dataset
resource "aws_s3_bucket" "dataset_bucket" {
    bucket        = "nmcnpm-dataset-bucket"
    force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "dataset_bucket_public_access_block" {
    bucket                  = aws_s3_bucket.dataset_bucket.id
    block_public_acls       = true
    ignore_public_acls      = true
    block_public_policy     = true
    restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "dataset_bucket_versioning" {
    bucket = aws_s3_bucket.dataset_bucket.id
    versioning_configuration {
      status = "Enabled"
    }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "dataset_bucket_server_side_encryption" {
    bucket = aws_s3_bucket.dataset_bucket.id
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
}

resource "aws_s3_bucket_lifecycle_configuration" "dataset_bucket_lifecycle_config" {
    bucket = aws_s3_bucket.dataset_bucket.id
    rule {
        id     = "archive_old_dataset"
        status = "Enabled"
        filter {}
        transition {
          days          = 7
          storage_class = "GLACIER"
        }
    }
}

resource "aws_s3_bucket_policy" "dataset_bucket_policy" {
    bucket = aws_s3_bucket.dataset_bucket.id
    policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
        {
            # Deny truy cập không qua VPC Endpoint,
            # NGOẠI TRỪ các IAM principals cần quản lý bucket (Terraform, CI/CD)
            Sid       = "DenyNonVPCEndpointAccess"
            Effect    = "Deny"
            Principal = "*"
            Action    = "s3:*"
            Resource  = [
                aws_s3_bucket.dataset_bucket.arn,
                "${aws_s3_bucket.dataset_bucket.arn}/*"
            ]
            Condition = {
                StringNotEquals = {
                    "aws:SourceVpce" = var.s3_vpc_gateway_endpoint_id
                }
                ArnNotLike = {
                    "aws:PrincipalArn" = concat(var.admin_iam_arns, [
                        "arn:aws:iam::${var.account_id}:role/sagemaker_training_role",
                        "arn:aws:iam::${var.account_id}:role/Dataset_Maker_Task_Role",
                        "arn:aws:iam::${var.account_id}:role/step_functions_role",
                        "arn:aws:iam::${var.account_id}:role/model-promotion-lambda-role"
                    ])
                }
            }
        },
        {
            Sid       = "AllowSageMakerAccess"
            Effect    = "Allow"
            Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
            Action    = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
            Resource  = [
                aws_s3_bucket.dataset_bucket.arn,
                "${aws_s3_bucket.dataset_bucket.arn}/*"
            ]
            Condition = {
                StringLike = {
                    "aws:PrincipalArn" = [
                        "arn:aws:iam::${var.account_id}:role/sagemaker_training_role",
                        "arn:aws:iam::${var.account_id}:role/Dataset_Maker_Task_Role",
                        "arn:aws:iam::${var.account_id}:role/step_functions_role",
                        "arn:aws:iam::${var.account_id}:role/model-promotion-lambda-role"
                    ]
                }
            }
        }
    ]
    })
}

# S3 bucket cho model artifact
resource "aws_s3_bucket" "model_artifact_bucket" {
    bucket        = "nmcnpm-model-artifact-bucket"
    force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "model_artifact_bucket_public_access_block" {
    bucket                  = aws_s3_bucket.model_artifact_bucket.id
    block_public_acls       = true
    ignore_public_acls      = true
    block_public_policy     = true
    restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "model_artifact_bucket_versioning" {
    bucket = aws_s3_bucket.model_artifact_bucket.id
    versioning_configuration {
      status = "Enabled"
    }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "model_artifact_bucket_server_side_encryption" {
    bucket = aws_s3_bucket.model_artifact_bucket.id
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
}

resource "aws_s3_bucket_lifecycle_configuration" "model_artifact_bucket_lifecycle_config" {
    bucket = aws_s3_bucket.model_artifact_bucket.id
    rule {
        id     = "archive_old_model_artifact"
        status = "Enabled"
        filter {}
        transition {
          days          = 7
          storage_class = "GLACIER"
        }
    }
}

resource "aws_s3_bucket_policy" "model_artifact_bucket_policy" {
    bucket = aws_s3_bucket.model_artifact_bucket.id
    policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
        {
            Sid       = "DenyNonVPCEndpointAccess"
            Effect    = "Deny"
            Principal = "*"
            Action    = "s3:*"
            Resource  = [
                aws_s3_bucket.model_artifact_bucket.arn,
                "${aws_s3_bucket.model_artifact_bucket.arn}/*"
            ]
            Condition = {
                StringNotEquals = {
                    "aws:SourceVpce" = var.s3_vpc_gateway_endpoint_id
                }
                ArnNotLike = {
                    "aws:PrincipalArn" = concat(var.admin_iam_arns, [
                        "arn:aws:iam::${var.account_id}:role/sagemaker_training_role",
                        "arn:aws:iam::${var.account_id}:role/Dataset_Maker_Task_Role",
                        "arn:aws:iam::${var.account_id}:role/step_functions_role",
                        "arn:aws:iam::${var.account_id}:role/model-promotion-lambda-role"
                    ])
                }
            }
        },
        {
            Sid       = "AllowSageMakerAccess"
            Effect    = "Allow"
            Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
            Action    = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
            Resource  = [
                aws_s3_bucket.model_artifact_bucket.arn,
                "${aws_s3_bucket.model_artifact_bucket.arn}/*"
            ]
            Condition = {
                StringLike = {
                    "aws:PrincipalArn" = [
                        "arn:aws:iam::${var.account_id}:role/sagemaker_training_role",
                        "arn:aws:iam::${var.account_id}:role/Dataset_Maker_Task_Role",
                        "arn:aws:iam::${var.account_id}:role/step_functions_role",
                        "arn:aws:iam::${var.account_id}:role/model-promotion-lambda-role"
                    ]
                }
            }
        }
    ]
    })
}

# S3 bucket cho tour information
resource "aws_s3_bucket" "tour_bucket" {
    bucket        = "nmcnpm-tour-bucket"
    force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "tour_bucket_public_access_block" {
    bucket                  = aws_s3_bucket.tour_bucket.id
    block_public_acls       = true
    ignore_public_acls      = true
    block_public_policy     = true
    restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "tour_bucket_versioning" {
    bucket = aws_s3_bucket.tour_bucket.id
    versioning_configuration {
      status = "Enabled"
    }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tour_bucket_server_side_encryption" {
    bucket = aws_s3_bucket.tour_bucket.id
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
}

resource "aws_s3_bucket_lifecycle_configuration" "tour_bucket_lifecycle_config" {
    bucket = aws_s3_bucket.tour_bucket.id
    rule {
        id     = "delete_old_tour_information"
        status = "Enabled"
        filter {}
        expiration {
          days = 7
        }
    }
}

resource "aws_s3_bucket_policy" "tour_bucket_policy" {
    bucket = aws_s3_bucket.tour_bucket.id
    policy = jsonencode({
        Version = "2012-10-17"
        Statement = [{
            Sid       = "DenyNonVPCEndpointAccess"
            Effect    = "Deny"
            Principal = "*"
            Action    = "s3:*"
            Resource  = [
                aws_s3_bucket.tour_bucket.arn,
                "${aws_s3_bucket.tour_bucket.arn}/*"
            ]
            Condition = {
                StringNotEquals = {
                    "aws:SourceVpce" = var.s3_vpc_gateway_endpoint_id
                }
                ArnNotLike = {
                    "aws:PrincipalArn" = concat(var.admin_iam_arns, [
                        "arn:aws:iam::${var.account_id}:role/Tour_Display_Task_Role",
                        "arn:aws:iam::${var.account_id}:role/Tour_Producer_Task_Role"
                    ])
                }
            }
        }]
    })
}
