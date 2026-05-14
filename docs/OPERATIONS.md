# Operations & CI/CD

Tài liệu này mô tả cách kiểm thử, build, deploy, monitoring và xử lý sự cố ở mức vận hành.

## CI/CD workflow

Repo có 3 GitHub Actions workflow chính trong `.github/workflows/`.

| Workflow | Trigger | Mục đích |
|---|---|---|
| `1. Scan source code` | Push vào `dev`, path `services/**` | Chạy SonarQube scan source code. |
| `2. Build, Test and Scan images` | Sau khi workflow scan source thành công trên `dev` | Detect service thay đổi, build Docker image local và scan bằng Trivy. |
| `3. Push to ECR and Deploy to ECS` | Push vào `main`, path `services/**` | Detect service thay đổi, build image, push ECR, cập nhật task definition và rolling deploy ECS. |

## Luồng release đề xuất

1. Tạo branch feature từ `dev`.
2. Merge/push vào `dev`.
3. Workflow SonarQube scan chạy trước.
4. Nếu scan source thành công, workflow build/Trivy scan chạy theo từng service thay đổi.
5. Review kết quả scan trong GitHub Security tab.
6. Merge `dev` vào `main` khi sẵn sàng release.
7. Workflow deploy push image lên ECR và rolling deploy ECS service liên quan.

## Detect service thay đổi

Workflows dùng `dorny/paths-filter` để chỉ build/deploy service có thay đổi:

```text
services/exchange-rate-producer/**
services/streaming-service/**
services/money-service/**
services/forecast-service/**
services/tour-producer/**
services/tour-service/**
services/dataset-maker/**
services/frontend/**
```

Điều này giúp giảm thời gian CI và tránh deploy service không liên quan.

## Build và deploy

Mỗi image được tag bằng:

- Commit SHA: phục vụ rollback/audit.
- `latest`: tận dụng Docker cache ở lần build sau.

Deploy ECS thực hiện bằng cách:

1. Lấy task definition hiện tại.
2. Thay image URI của đúng container.
3. Register task definition revision mới.
4. Update ECS service với revision mới.
5. Chờ ECS service stable.

Với scheduled task như `tour-producer`, workflow cập nhật EventBridge target thay vì ECS long-running service.

## Monitoring

Các nguồn quan sát chính:

| Nguồn | Dùng để |
|---|---|
| CloudWatch Logs | Xem stdout/stderr của ECS tasks và Lambda. |
| CloudWatch Metrics | CPU/memory ECS, ALB target health, RDS, ElastiCache, Lambda errors. |
| CloudWatch Alarms + SNS | Nhận cảnh báo qua email. |
| X-Ray | Trace request nếu module X-Ray đã bật và app được instrument. |
| GitHub Security tab | Xem SARIF từ Trivy scan. |
| SonarQube/SonarCloud | Code smell, vulnerability, coverage và quality gate. |

## Log locations gợi ý

Tên log group phụ thuộc Terraform module, nhưng thường nên kiểm tra:

```text
/ecs/<service-name>
/aws/lambda/<lambda-name>
/aws/stepfunctions/<state-machine-name>
```

Các service Python/Node trong repo ưu tiên structured logs ra stdout để CloudWatch ingest trực tiếp.

## Health checks

Các endpoint health quan trọng:

```text
GET /health                # money-service, forecast-service, tour-service, streaming-service
GET /ping                  # SageMaker inference container
```

Khi ECS deploy lỗi, kiểm tra theo thứ tự:

1. Target group health trong ALB.
2. ECS task stopped reason.
3. CloudWatch logs của container.
4. Security group/subnet routing.
5. Secret/env var bị thiếu.

## Runbook sự cố phổ biến

### Frontend không gọi được API

- Kiểm tra `VITE_*_SERVICE_URL` đã đúng domain/path chưa.
- Vì Vite build static asset, biến `VITE_*` phải đúng tại thời điểm build image.
- Kiểm tra CORS ở backend/ALB.
- Kiểm tra ALB listener rule route đúng target group.

### WebSocket không update tỷ giá

- Kiểm tra streaming service health.
- Kiểm tra Redis exchange-rate cache có key mới không.
- Kiểm tra exchange-rate-producer có đang chạy và external API còn quota không.
- Kiểm tra ALB hỗ trợ WebSocket và timeout/sticky config.

### Exchange/top-up bị lỗi

- Kiểm tra JWT còn hạn và Cognito User Pool đúng.
- Kiểm tra request có `Idempotency-Key` dạng UUID.
- Kiểm tra Redis idempotency cache.
- Kiểm tra RDS connection và migration đã chạy đủ.
- Với lỗi conflict, xem log optimistic locking và retry count.

### Forecast trả 403

- Kiểm tra user đã upgrade Premium chưa.
- Kiểm tra token mới có claim `custom:premium=true` chưa.
- Sau khi upgrade, frontend cần refresh token hoặc user đăng nhập lại.

### ECS deploy không stable

- Xem `aws ecs describe-services` và stopped task reason.
- Xem CloudWatch Logs của revision mới.
- Kiểm tra image URI tồn tại trong ECR.
- Kiểm tra task role có quyền đọc Secrets Manager/S3/SageMaker tương ứng.

## Chi phí

Để giảm chi phí khi không demo:

- Destroy `infra/main_infra`.
- Giữ `infra/persistent` nếu còn cần ECR images, S3 data, secrets hoặc Terraform state.
- Tắt/suspend các scheduled task nếu không cần training/tour producer.

Không destroy persistent layer tùy tiện vì có thể mất artifact, bucket data hoặc secret phục vụ lần deploy sau.
