# Post-Confirmation Lambda

Lambda function được Cognito gọi tự động sau khi user xác nhận email thành công.

## Chức năng

- Nhận Cognito Post-Confirmation trigger event
- Trích xuất `cognito_sub` (từ `event["userName"]`) và `email` (từ `event["request"]["userAttributes"]["email"]`)
- Kết nối RDS PostgreSQL qua credentials từ AWS Secrets Manager
- INSERT user mới vào bảng `users` với:
  - `cognito_sub` = Cognito username/sub
  - `email` = email của user
  - `balance` = 0
  - `version` = 0
- Trả về event không thay đổi (Cognito trigger contract)
- Xử lý lỗi: log và re-raise để Cognito rollback confirmation nếu thất bại

## Environment Variables

Lambda cần các biến môi trường sau:

| Variable | Mô tả | Ví dụ |
|---|---|---|
| `DB_SECRET_ARN` | ARN của Secrets Manager secret chứa DB credentials | `arn:aws:secretsmanager:ap-southeast-2:123456789012:secret:nmcnpm/rds_password-AbCdEf` |
| `DB_HOST` | RDS endpoint hostname | `rds_postgres_primary.abc123.ap-southeast-2.rds.amazonaws.com` |
| `DB_PORT` | RDS port (mặc định 5432) | `5432` |
| `DB_NAME` | Tên database | `nmcnpm` |

### Secret Format

Secret trong Secrets Manager phải có format JSON:

```json
{
  "username": "postgres",
  "password": "your-secure-password"
}
```

## Deployment

### Option 1: Container Image (khuyến nghị)

1. **Build Docker image:**

   ```bash
   cd services/post-confirmation-lambda
   docker build -t post-confirmation-lambda .
   ```

2. **Tag và push lên ECR:**

   ```bash
   # Lấy ECR repository URI từ Terraform output hoặc AWS Console
   ECR_URI=123456789012.dkr.ecr.ap-southeast-2.amazonaws.com/post-confirmation-lambda

   # Authenticate Docker với ECR
   aws ecr get-login-password --region ap-southeast-2 | \
     docker login --username AWS --password-stdin $ECR_URI

   # Tag và push
   docker tag post-confirmation-lambda:latest $ECR_URI:latest
   docker push $ECR_URI:latest
   ```

3. **Tạo Lambda function từ container image:**

   ```bash
   aws lambda create-function \
     --function-name nmcnpm_post_confirmation_lambda \
     --package-type Image \
     --code ImageUri=$ECR_URI:latest \
     --role arn:aws:iam::123456789012:role/lambda-execution-role \
     --timeout 30 \
     --memory-size 256 \
     --environment Variables="{
       DB_SECRET_ARN=arn:aws:secretsmanager:...,
       DB_HOST=rds_postgres_primary.abc123.ap-southeast-2.rds.amazonaws.com,
       DB_PORT=5432,
       DB_NAME=nmcnpm
     }" \
     --vpc-config SubnetIds=subnet-xxx,subnet-yyy,SecurityGroupIds=sg-zzz
   ```

### Option 2: ZIP Package

1. **Cài dependencies vào thư mục local:**

   ```bash
   pip install -r requirements.txt -t ./package
   ```

2. **Tạo ZIP file:**

   ```bash
   cd package
   zip -r ../lambda.zip .
   cd ..
   zip -g lambda.zip handler.py
   ```

3. **Upload lên Lambda:**

   ```bash
   aws lambda create-function \
     --function-name nmcnpm_post_confirmation_lambda \
     --runtime python3.12 \
     --handler handler.handler \
     --zip-file fileb://lambda.zip \
     --role arn:aws:iam::123456789012:role/lambda-execution-role \
     --timeout 30 \
     --memory-size 256 \
     --environment Variables="{...}" \
     --vpc-config SubnetIds=...,SecurityGroupIds=...
   ```

## IAM Permissions

Lambda execution role cần các permissions sau:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-2:*:secret:nmcnpm/rds_password-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DeleteNetworkInterface"
      ],
      "Resource": "*"
    }
  ]
}
```

## Cognito Trigger Configuration

Sau khi deploy Lambda, cấu hình Cognito User Pool trigger:

1. Mở Cognito User Pool trong AWS Console
2. Vào **User pool properties** → **Lambda triggers**
3. Chọn **Post confirmation trigger**
4. Chọn Lambda function: `nmcnpm_post_confirmation_lambda`
5. Save

Hoặc dùng Terraform:

```hcl
resource "aws_cognito_user_pool" "nmcnpm_user_pool" {
  # ... existing config ...

  lambda_config {
    post_confirmation = aws_lambda_function.post_confirmation.arn
  }
}

resource "aws_lambda_permission" "allow_cognito" {
  statement_id  = "AllowExecutionFromCognito"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.post_confirmation.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.nmcnpm_user_pool.arn
}
```

## Testing

### Local Testing với Docker

1. **Tạo test event file (`test_event.json`):**

   ```json
   {
     "version": "1",
     "triggerSource": "PostConfirmation_ConfirmSignUp",
     "region": "ap-southeast-2",
     "userPoolId": "ap-southeast-2_XXXXXXXXX",
     "userName": "test-cognito-sub-12345",
     "request": {
       "userAttributes": {
         "email": "test@example.com",
         "email_verified": "true"
       }
     },
     "response": {}
   }
   ```

2. **Run container locally:**

   ```bash
   docker run -p 9000:8080 \
     -e DB_SECRET_ARN=arn:aws:secretsmanager:... \
     -e DB_HOST=localhost \
     -e DB_PORT=5432 \
     -e DB_NAME=nmcnpm \
     -e AWS_ACCESS_KEY_ID=... \
     -e AWS_SECRET_ACCESS_KEY=... \
     post-confirmation-lambda
   ```

3. **Invoke Lambda:**

   ```bash
   curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
     -d @test_event.json
   ```

### Integration Testing

1. **Đăng ký user mới qua Cognito:**

   ```bash
   aws cognito-idp sign-up \
     --client-id <app-client-id> \
     --username test@example.com \
     --password TestPassword123!
   ```

2. **Xác nhận email (dùng admin command để test):**

   ```bash
   aws cognito-idp admin-confirm-sign-up \
     --user-pool-id ap-southeast-2_XXXXXXXXX \
     --username test@example.com
   ```

3. **Kiểm tra user đã được INSERT vào DB:**

   ```sql
   SELECT * FROM users WHERE email = 'test@example.com';
   ```

   Kết quả mong đợi:
   - `cognito_sub` = Cognito username
   - `email` = test@example.com
   - `balance` = 0
   - `version` = 0

## Monitoring

- **CloudWatch Logs:** `/aws/lambda/nmcnpm_post_confirmation_lambda`
- **Metrics:**
  - `Invocations` — số lần Lambda được gọi
  - `Errors` — số lần Lambda raise exception
  - `Duration` — thời gian thực thi (mục tiêu: < 5s)
  - `Throttles` — số lần bị rate limit

## Troubleshooting

### Lambda timeout

- **Nguyên nhân:** DB connection chậm hoặc network latency cao
- **Giải pháp:** Tăng timeout lên 30s, kiểm tra VPC/Security Group config

### "Unable to import module 'handler'"

- **Nguyên nhân:** Dependencies không được package đúng cách
- **Giải pháp:** Rebuild Docker image hoặc ZIP file, đảm bảo `handler.py` ở root

### "Database connection failed"

- **Nguyên nhân:** Lambda không thể kết nối RDS (VPC/Security Group)
- **Giải pháp:**
  - Kiểm tra Lambda nằm trong cùng VPC với RDS
  - Kiểm tra Security Group của RDS cho phép inbound từ Lambda SG trên port 5432

### "Secrets Manager error"

- **Nguyên nhân:** Lambda không có quyền đọc secret
- **Giải pháo:** Thêm `secretsmanager:GetSecretValue` vào IAM role

## Idempotency

Lambda sử dụng `ON CONFLICT (cognito_sub) DO NOTHING` để đảm bảo idempotency:

- Nếu Cognito retry Lambda (do timeout hoặc lỗi tạm thời), user không bị INSERT trùng
- Log sẽ ghi "User đã tồn tại (idempotent retry), bỏ qua INSERT"
- Lambda vẫn trả về success (event không thay đổi)

## Rollback Behavior

Nếu Lambda raise exception:

1. Cognito nhận error response
2. Cognito rollback user confirmation
3. User vẫn ở trạng thái "unconfirmed" trong Cognito
4. User không thể login cho đến khi xác nhận lại email thành công

Điều này đảm bảo `User_DB` và Cognito luôn đồng bộ.
