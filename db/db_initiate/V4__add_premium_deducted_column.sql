-- Migration V4: Thêm cột premium_deducted vào bảng users
-- Dùng để theo dõi trạng thái reconciliation khi Cognito update thất bại
-- sau khi đã trừ phí premium từ balance.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS premium_deducted BOOLEAN NOT NULL DEFAULT FALSE;

-- Index để reconciliation job query nhanh hơn
CREATE INDEX IF NOT EXISTS idx_users_premium_deducted
    ON users (premium_deducted)
    WHERE premium_deducted = TRUE;
