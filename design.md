# Design Document

## Tổng quan hệ thống

Hệ thống là một ứng dụng web cung cấp các tính năng streaming tỉ giá tiền tệ theo thời gian thực, dự báo tỉ giá bằng machine learning, trao đổi tiền tệ, và gợi ý tour du lịch. Hệ thống được triển khai trên AWS với kiến trúc Multi-AZ để đảm bảo High Availability.

---

## Kiến trúc tổng thể

### Các lớp chính

```
Internet
    │
Route 53 (Alias Record)
    │
WAF (Protect Web Application)
    │
Application Load Balancer
    │
┌───────────────────────────────────────┐
│              VPC                      │
│  ┌─────────────┐  ┌─────────────────┐ │
│  │ Public      │  │ Private         │ │
│  │ Subnet      │  │ Subnet          │ │
│  │ (Frontend,  │  │ (Services,      │ │
│  │  Producers) │  │  DB, Cache)     │ │
│  └─────────────┘  └─────────────────┘ │
└───────────────────────────────────────┘
    │
Gateway Endpoint → S3
Interface Endpoint → AWS Services
```

### Multi-AZ

Hệ thống triển khai trên 2 Availability Zone:

- **AZ 1**: Primary — chứa toàn bộ các service chính
- **AZ 2**: Standby/Failover — chứa các bản replica và service dự phòng, tự động promote khi AZ 1 gặp sự cố

---

## Các luồng chức năng chính

### 1. Thu thập và streaming tỉ giá (Yêu cầu #1, #2)

**Luồng:**
```
Exchange Rate API (External)
    │
Exchange Rate Producer (ECS)
    │
Streaming Exchange Rate (WebSocket - ECS)
    │
ElastiCache Primary for Exchange Rate (Redis)
    │
Frontend (WebSocket connection)
```

**Chi tiết:**
- `Exchange Rate Producer` định kỳ gọi `Exchange Rate API` để lấy tỉ giá mới nhất so với VND
- Dữ liệu được đẩy vào `Streaming Exchange Rate` service chạy trên ECS, sử dụng WebSocket để push real-time đến client
- Tỉ giá được cache tại `ElastiCache Primary for Exchange Rate` (TTL ngắn ~30 giây) để giảm tải cho External API
- ALB được cấu hình **sticky sessions** để đảm bảo WebSocket client luôn kết nối đến cùng một ECS task
- AZ 2 có `ElastiCache Replica for Exchange Rate` và `Exchange Rate Producer (If AZ 1 Failed)` để dự phòng

---

### 2. Dự báo tỉ giá bằng Machine Learning (Yêu cầu #3, #4)

**Luồng huấn luyện:**
```
Exchange Rate Producer
    │
Dataset Maker (ECS) → Training Data (CSV) → S3
    │
SageMaker Training Jobs
    │
Model Artifact (.tar.gz) → S3
    │
Model Registry (SageMaker)
    │ (chọn model tốt nhất)
SageMaker Endpoint
```

**Luồng dự báo:**
```
Frontend (Premium User)
    │
Forecast Exchange Rate (ECS)
    │ [Premium Check: verify JWT claim]
SageMaker Endpoint
    │
Kết quả dự báo → Frontend
```

**Chi tiết:**
- `Dataset Maker` thu thập và xử lý dữ liệu tỉ giá lịch sử, lưu dưới dạng CSV vào S3
- `SageMaker Training Jobs` huấn luyện model định kỳ với data mới
- `Model Registry` lưu trữ và so sánh các phiên bản model, chỉ promote model có metric tốt hơn model hiện tại lên `SageMaker Endpoint`
- `Forecast Exchange Rate` service kiểm tra JWT token của user trước khi gọi SageMaker Endpoint — chỉ user có claim `premium=true` mới được phép (Yêu cầu #9)
- `Private Registry` lưu trữ Docker image của các ECS service

---

### 3. Trao đổi tiền tệ và nạp tiền (Yêu cầu #5)

**Luồng:**
```
Frontend
    │
Update User's Money (ECS)
    │
    ├── Check Idempotency Key
    │       └── ElastiCache for Idempotency Keys (Primary)
    │
    ├── BEGIN TRANSACTION
    │       └── User Information DB (RDS Primary) — Optimistic Lock
    │
    └── Write result → Idempotency Key (no TTL)
```

**Chi tiết:**
- Mỗi request đổi tiền/nạp tiền phải kèm **idempotency key** (UUID) để tránh double-spend khi client retry
- `ElastiCache for Idempotency Keys` được cấu hình riêng biệt với policy `noeviction` và persistence bật (`appendonly yes`) để đảm bảo key không bao giờ bị mất
- Idempotency key được lưu **không có TTL** — background job định kỳ dọn dẹp key cũ hơn 7 ngày
- Database sử dụng **Optimistic Locking** (version column) để tránh race condition khi 2 request đến đồng thời
- AZ 2 có `Update User's Money (Write at Primary DB)` — khi AZ 1 fail, service ở AZ 2 vẫn write vào RDS Primary (hoặc Replica được promote), đọc idempotency key từ `ElastiCache for Idempotency Keys (Replica)` ở AZ 2

---

### 4. Tour du lịch (Yêu cầu #6, #7)

**Luồng thu thập:**
```
Travelpayouts API (External)
    │
Tour Producer (ECS)
    │
Tour's Images + Tour Data → S3
```

**Luồng hiển thị:**
```
Frontend
    │
Tour Display (ECS)
    │
Gateway Endpoint → S3
    │
Tour data + Images → Frontend
(Redirect link đến Travelpayouts khi user click)
```

**Chi tiết:**
- `Tour Producer` định kỳ fetch thông tin tour từ `Travelpayouts`, xử lý và lưu vào S3
- `Tour Display` đọc data từ S3 thông qua **Gateway Endpoint** — traffic đi trong AWS network, không qua internet, không tốn NAT Gateway cost
- Tour data là static content (hình ảnh, mô tả, affiliate link) nên S3 phù hợp hơn RDS về chi phí và khả năng scale
- Khi user click vào tour, frontend redirect đến URL affiliate của Travelpayouts

---

### 5. Nâng cấp Premium (Yêu cầu #10)

**Luồng:**
```
Frontend (trang Upgrade to Premium)
    │
    ├── Kiểm tra số dư hiện tại
    │       └── Update User's Money (ECS) → RDS Primary
    │
    ├── Trừ phí premium (idempotency key kèm theo)
    │       └── Update User's Money (ECS) → RDS Primary
    │
    └── Cập nhật thuộc tính premium
            └── Cognito Admin API (custom:premium = true)
```

**Chi tiết:**
- Trang "Upgrade to Premium" hiển thị giá gói premium (tính bằng tiền giả lập trong hệ thống)
- Khi user xác nhận, hệ thống kiểm tra số dư — nếu không đủ thì báo lỗi, không thực hiện
- Nếu đủ số dư, `Update User's Money` trừ phí và gọi **Cognito Admin API** để set `custom:premium = true` trong User Pool
- Toàn bộ thao tác trừ tiền + update Cognito được thực hiện với idempotency key để tránh trường hợp trừ tiền 2 lần
- Sau khi Cognito cập nhật, user cần **refresh token** để JWT mới chứa claim `custom:premium = true` — frontend tự động gọi Cognito refresh token endpoint
- Gói premium không có thời hạn trong phạm vi đồ án (có thể mở rộng thêm expiry date sau)

---

### 6. Xác thực và phân quyền (Yêu cầu #8, #9)

**Luồng đăng ký:**
```
Frontend → Account Registry and Authentication (Cognito)
    │
Post-confirmation trigger
    │
Write User Information After Register (ECS)
    │
User Information DB (RDS Primary)
```

**Luồng đăng nhập:**
```
Frontend → Cognito
    │
JWT Token (chứa claim: premium=true/false)
    │
Frontend lưu token, gửi kèm mọi request
```

**Chi tiết:**
- `Account Registry and Authentication` sử dụng **AWS Cognito** để quản lý user pool
- Cognito hỗ trợ sẵn: đăng ký, đăng nhập, quên mật khẩu (gửi email reset)
- Sau khi user đăng ký thành công, Cognito trigger `Write User Information After Register` để lưu thông tin bổ sung vào RDS
- Thuộc tính `premium` được lưu trong Cognito User Pool attributes
- JWT token do Cognito cấp chứa claim `custom:premium` — các service backend verify claim này để phân quyền

---

## Hạ tầng và bảo mật

### Network

| Component | Vị trí | Lý do |
|---|---|---|
| Frontend (ECS) | Public Subnet | Cần nhận traffic từ ALB |
| Exchange Rate Producer | Public Subnet | Cần gọi External API |
| Tour Producer | Public Subnet | Cần gọi External API |
| Các service xử lý nghiệp vụ | Private Subnet | Không expose trực tiếp ra internet |
| RDS, ElastiCache | Private Subnet | Bảo vệ data layer |

### Bảo mật

- **WAF**: Bảo vệ ứng dụng khỏi các tấn công phổ biến (SQL injection, XSS) trước khi traffic vào ALB
- **VPC**: Toàn bộ hệ thống nằm trong VPC, tách biệt với internet
- **Gateway Endpoint**: Truy cập S3 không qua internet
- **Interface Endpoint**: Truy cập các AWS service (SageMaker, ECR) không qua internet
- **Cognito**: Quản lý xác thực, không tự xây dựng auth system

### Caching

| Cache | Policy | TTL | Mục đích |
|---|---|---|---|
| ElastiCache Primary for Exchange Rate | `volatile-lru` | 30 giây | Cache tỉ giá, giảm tải External API |
| ElastiCache for Idempotency Keys | `noeviction` | Không có TTL | Tránh double-spend |

### Database

- **RDS Primary (AZ 1)**: Nhận toàn bộ write operation
- **RDS Read Replica (AZ 2)**: Nhận read operation, tự động promote thành Primary khi AZ 1 fail
- **RDS Backups**: Backup định kỳ để phục hồi khi cần

### Observability

- `Logs & Metric Data for Analysis`: Thu thập log và metric từ tất cả service
- `Observability`: Dashboard monitoring, alerting khi có sự cố

---

## Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Compute | AWS ECS (Docker containers) |
| Database | AWS RDS (PostgreSQL/MySQL) |
| Cache | AWS ElastiCache (Redis) |
| ML | AWS SageMaker |
| Auth | AWS Cognito |
| Storage | AWS S3 |
| CDN/DNS | AWS Route 53 |
| Load Balancer | AWS Application Load Balancer |
| Security | AWS WAF |
| WebSocket Server | ECS (Node.js + socket.io hoặc tương đương) |
| External APIs | Exchange Rate API, Travelpayouts |
