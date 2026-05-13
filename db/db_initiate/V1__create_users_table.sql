-- Migration V1: Tạo bảng users
-- Lưu thông tin user và số dư, sử dụng cột version cho optimistic locking

CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cognito_sub VARCHAR(255) UNIQUE NOT NULL,
    email       VARCHAR(255) UNIQUE NOT NULL,
    balance     DECIMAL(18, 4) NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 0,  -- optimistic lock: tăng 1 mỗi lần UPDATE
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
