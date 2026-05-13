Viewed step.md:42-64

Nếu bạn quyết định `destroy` và `apply` lại `main_infra`, toàn bộ hạ tầng cốt lõi (VPC, Database, Redis, Cognito, ALB, ECS Services) sẽ bị xóa và tạo mới hoàn toàn với **các ID và Endpoint mới**. 

Do đó, bạn sẽ cần thực hiện lại một vòng các bước cấu hình để hệ thống có thể kết nối lại với nhau. Dưới đây là danh sách những việc bắt buộc phải làm theo thứ tự:

### 1. Cập nhật lại các ID mạng lưới (Networking) vào `persistent/terraform.tfvars`
Do VPC và Subnets bị tạo mới, bạn cần lấy output từ `main_infra` để điền lại vào `persistent/terraform.tfvars`:
- `s3_vpc_gateway_endpoint_id`
- `private_subnet_ids` và `public_subnet_ids`
- `ecs_services_sg_id`, `producer_sg_id`, `lambda_sg_id`

### 2. Cập nhật lại các Endpoint & ARN vào `persistent/terraform.tfvars`
Tương tự, các dịch vụ runtime cũng có địa chỉ mới, cần lấy từ `terraform output` của `main_infra`:
- `db_host` (Địa chỉ RDS mới)
- `redis_host`, `exchange_rate_redis_host`, `idempotency_redis_host` (Địa chỉ ElastiCache mới)
- `user_pool_id` (Cognito mới)
- `step_functions_state_machine_arn`, `eventbridge_sfn_policy_arn`
- `rotate_redis_password_lambda_function_name` và `arn`

### 3. Chạy lại `terraform apply` trong thư mục `persistent`
Sau khi cập nhật file `tfvars` ở trên, bạn phải chạy lại:
```bash
cd infra/persistent && terraform apply
```
**Mục đích:** Cập nhật các địa chỉ mạng và Endpoint mới này vào AWS Systems Manager Parameter Store. Các container ECS (backend) khi khởi động sẽ tự động lên Parameter Store đọc các thông số này để kết nối đúng vào DB/Redis mới.

### 4. Chạy lại script tạo Database
Vì RDS cũ đã bị xóa, database mới hiện tại hoàn toàn trống rỗng (chưa có table, chưa có user). Bạn phải chạy lại script migration để tạo bảng:
```bash
./db_migrate.sh
```

### 5. Cập nhật file `.env` của Frontend và Build lại
Frontend không đọc Parameter Store mà được đóng gói (build) cùng với các biến môi trường. Bạn phải mở file `services/frontend/.env` (hoặc cấu hình trong môi trường của bạn) và cập nhật:
- `VITE_API_BASE_URL` (Domain/DNS của ALB mới)
- `VITE_COGNITO_USER_POOL_ID` (ID của User Pool mới)
- `VITE_COGNITO_CLIENT_ID` (Client ID mới)

Sau khi điền xong, bạn **bắt buộc phải build và push lại image của frontend**:
```bash
docker build --platform linux/amd64 -t <account>.dkr.ecr.ap-southeast-2.amazonaws.com/frontend_repo:latest services/frontend
docker push <account>.dkr.ecr.ap-southeast-2.amazonaws.com/frontend_repo:latest
```
*(Các service backend bằng Python/Node.js khác thì KHÔNG cần build lại vì chúng lấy cấu hình động tại runtime).*

### 6. Restart các ECS Task Backend (nếu cần)
Nếu lúc bạn apply `persistent` ở Bước 3 mà các ECS Service đã lỡ chạy lên và lưu cache cấu hình cũ (bị crash do không kết nối được DB), chúng sẽ tự động restart. Tuy nhiên, nếu bạn muốn chắc chắn, có thể ép ECS chạy task mới nhất để đọc lại Parameter Store.

---
**Tóm lại:** Khi destroy `main_infra`, điểm đứt gãy lớn nhất là **Parameter Store (nằm ở persistent) đang lưu các URL cũ** và **Database trống trơn**. Chỉ cần cập nhật lại Parameter Store, tạo lại bảng DB và Build lại Frontend là hệ thống sẽ chạy bình thường.