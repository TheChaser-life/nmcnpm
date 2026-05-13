# infra/persistent

Root module chứa các resource **khó/không thể destroy ngay** — chỉ apply một lần, không destroy thường xuyên.

## Modules

| Module | Lý do persistent |
|--------|-----------------|
| `S3_Buckets` | Không xóa được nếu còn objects (`force_destroy = true` đã thêm) |
| `ECR_and_ECS_Cluster` | ECR repos không xóa được nếu còn images (`force_delete = true` đã thêm) |
| `Secrets_Manager_and_Parameter_Store` | Secrets có recovery window (`recovery_window_in_days = 0` để xóa ngay) |

## Cách sử dụng

```bash
cd infra/persistent

# Lần đầu — apply để tạo S3, ECR, Secrets
terraform init
terraform apply

# Xem outputs để lấy giá trị cho main_infra
terraform output
```

## Thứ tự apply

1. Apply `infra/persistent` trước để tạo S3 buckets, ECR repos, và Secrets Manager
2. Apply `infra/main_infra` sau — nó sẽ đọc outputs từ persistent qua `terraform_remote_state`

## Lưu ý

- **Không chạy `terraform destroy`** trên module này trong môi trường production
- Các biến networking (`private_subnet_ids`, `lambda_sg_id`, v.v.) cần được điền sau khi `main_infra` đã apply
- Secrets Manager: `recovery_window_in_days = 0` nghĩa là secret bị xóa ngay lập tức khi destroy (không có recovery period)
- Backend S3: `key = "currency-exchange/persistent.tfstate"` — tách biệt với `main_infra`
