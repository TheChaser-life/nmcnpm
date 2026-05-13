-- Migration V3: Tạo indexes cho các cột query thường xuyên

-- Index trên users.cognito_sub:
-- Mỗi request đến Money Service / Forecast Service đều lookup user bằng cognito_sub
-- (extract từ JWT). Không có index → full table scan mỗi request.
CREATE INDEX idx_users_cognito_sub ON users(cognito_sub);

-- Index trên transactions.idempotency_key:
-- Money Service check idempotency_key trước mỗi giao dịch.
-- Lưu ý: UNIQUE constraint ở V2 đã tạo index ngầm cho cột này,
-- nên dòng dưới là tường minh hóa, không tạo index trùng.
-- Nếu dùng Flyway/Liquibase, có thể bỏ dòng này vì index đã tồn tại.
-- CREATE INDEX idx_transactions_idempotency_key ON transactions(idempotency_key);

-- Index trên transactions.user_id:
-- Dùng khi query lịch sử giao dịch của một user (GET /transactions).
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
