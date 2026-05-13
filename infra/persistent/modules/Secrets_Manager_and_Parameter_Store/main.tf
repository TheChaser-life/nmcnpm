# Tạo password ngẫu nhiên
resource "random_password" "db_generate_pass" {
    length = 10
    special = true
    override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Tạo nơi chứa password của rds trong secrets manager
resource "aws_secretsmanager_secret" "rds_password" {
    name = "nmcnpm/rds_password"
    recovery_window_in_days = 0
}

# Truyền value của random password vào chỗ chứa ở trên
# Format JSON để tương thích với AWS rotation Lambda và handler của post-confirmation Lambda
resource "aws_secretsmanager_secret_version" "rds_password_version" {
    secret_id = aws_secretsmanager_secret.rds_password.id
    secret_string = jsonencode({
        username = "postgres"
        password = random_password.db_generate_pass.result
    })
}

# Lấy template rotate rds postgre secret có sẵn của aws
data "aws_serverlessapplicationrepository_application" "rds_postgre_password_rotation_template" {
    application_id = "arn:aws:serverlessrepo:us-east-1:297356227824:applications/SecretsManagerRDSPostgreSQLRotationSingleUser"
}

# Triển khai template với cloudformation và IAM Role cần thiết
resource "aws_serverlessapplicationrepository_cloudformation_stack" "rds_postgre_password_rotation_lambda" {
    name = "nmcnpm-rds-postgre-password-rotation-stack"
    application_id = data.aws_serverlessapplicationrepository_application.rds_postgre_password_rotation_template.application_id
    capabilities = ["CAPABILITY_IAM", "CAPABILITY_RESOURCE_POLICY"]

    parameters = merge(
        {
            endpoint = "https://secretsmanager.${var.region}.amazonaws.com"
            functionName = "nmcnpm-rds-postgre-password-rotation-lambda"
        },
        length(var.private_subnet_ids) > 0 ? { vpcSubnetIds = join(",", var.private_subnet_ids) } : {},
        var.lambda_sg_id != "" ? { vpcSecurityGroupIds = var.lambda_sg_id } : {}
    )
}

# Gán Lambda ở trên cho secret manager gọi đến
resource "aws_secretsmanager_secret_rotation" "rds_rotation_config" {
    secret_id = aws_secretsmanager_secret.rds_password.id
    rotation_lambda_arn = aws_serverlessapplicationrepository_cloudformation_stack.rds_postgre_password_rotation_lambda.outputs.RotationLambdaARN
    rotation_rules {
      automatically_after_days = 7
    }
}

# Tạo password ngẫu nhiên
resource "random_password" "elasticache_generate_pass" {
    length = 10
    special = true
    override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Tạo nơi chứa password của rds trong secrets manager
resource "aws_secretsmanager_secret" "elasticache_password" {
    name = "nmcnpm/elasticache_password"
    recovery_window_in_days = 0
}

# Truyền value của random password vào chỗ chứa ở trên
resource "aws_secretsmanager_secret_version" "elasticache_password_version" {
    secret_id = aws_secretsmanager_secret.elasticache_password.id
    secret_string = random_password.elasticache_generate_pass.result
}

# do aws không có template có sẵn cho rotate elasticache password nên phải tự xây lambda function sau
# tạo permission cho phép secrets manager sử dụng hàm này
# count = 0 khi chưa có Lambda (lần apply đầu của persistent)
# Sau khi main_infra apply xong, điền rotate_redis_password_lambda_function_name/arn
# vào persistent/terraform.tfvars rồi apply lại persistent để bật rotation
resource "aws_lambda_permission" "allow_secret_manager_to_call_to_redis_password_rotation_function" {
    count         = var.rotate_redis_password_lambda_function_name != "" ? 1 : 0
    statement_id  = "AllowExecutionFromSecretsManager"
    action        = "lambda:InvokeFunction"
    function_name = var.rotate_redis_password_lambda_function_name
    principal     = "secretsmanager.amazonaws.com"
}

# Gán Lambda ở trên cho secret manager gọi đến
# count = 0 khi chưa có Lambda ARN
resource "aws_secretsmanager_secret_rotation" "elasticache_rotate_config" {
    count              = var.rotate_redis_password_lambda_function_arn != "" ? 1 : 0
    secret_id          = aws_secretsmanager_secret.elasticache_password.id
    rotation_lambda_arn = var.rotate_redis_password_lambda_function_arn
    rotation_rules {
      automatically_after_days = 7
    }
    depends_on = [aws_lambda_permission.allow_secret_manager_to_call_to_redis_password_rotation_function]
}

# tạo secret của travelpayouts api key
resource "aws_secretsmanager_secret" "travelpayouts_api_key" {
    name = "nmcnpm/travelpayouts_api_key"
    recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "travelpayouts_api_key_version" {
    secret_id = aws_secretsmanager_secret.travelpayouts_api_key.id
    secret_string = var.travelpayouts_api_key
}

# tạo secret của viator api key
resource "aws_secretsmanager_secret" "viator_api_key" {
    name = "nmcnpm/viator_api_key"
    recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "viator_api_key_version" {
    secret_id = aws_secretsmanager_secret.viator_api_key.id
    secret_string = var.viator_api_key
}

# tạo secret của exchange_rate_api
resource "aws_secretsmanager_secret" "exchange_rate_api_key" {
    name = "nmcnpm/exchange_rate_api_key"
    recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "exchange_rate_api_key_version" {
    secret_id = aws_secretsmanager_secret.exchange_rate_api_key.id
    secret_string = var.exchange_rate_api_key
}

# lưu premium fee trong parameter store
resource "aws_ssm_parameter" "premium_fee" {
    name  = "/nmcnpm/premium_fee"
    type  = "String"
    value = var.premium_fee
}

