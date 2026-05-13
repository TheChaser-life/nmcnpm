-- Migration V2: Tạo bảng transactions
-- Audit log bất biến: chỉ INSERT, không UPDATE hay DELETE

CREATE TABLE transactions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id),
    type             VARCHAR(50) NOT NULL,   -- 'exchange', 'topup', 'premium_upgrade'
    from_currency    VARCHAR(10),            -- NULL nếu type = 'topup'
    to_currency      VARCHAR(10),            -- NULL nếu type = 'topup'
    amount           DECIMAL(18, 4) NOT NULL,
    rate_applied     DECIMAL(18, 8),         -- tỉ giá tại thời điểm giao dịch, NULL nếu type = 'topup'
    idempotency_key  VARCHAR(255) UNIQUE NOT NULL,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);
