/**
 * moneyService.ts
 *
 * API client cho Money Service (POST /exchange, POST /topup, POST /premium/upgrade).
 *
 * Tasks:
 *   6.2.5  Generate UUID idempotency key cho mỗi request trước khi gửi
 *   6.2.6  Xử lý response lỗi (400 insufficient balance, 409 conflict)
 *   8.2    Premium upgrade API call
 */

import { getAccessToken } from './authService'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ExchangeRequest {
  from_currency: string
  to_currency: string
  amount: number
}

export interface TopUpRequest {
  amount: number
}

export interface TransactionResult {
  transaction_id: string
  user_id: string
  type: 'exchange' | 'topup'
  from_currency: string | null
  to_currency: string
  amount: number
  rate_applied: number | null
  received_amount?: number
  new_balance_vnd: number
  idempotency_key: string
  created_at: string
}

export interface BalanceInfo {
  balance_vnd: number
  transactions: TransactionRecord[]
}

export interface PremiumUpgradeResult {
  success: boolean
  message: string
  new_balance_vnd: number
  idempotency_key: string
}

export interface PremiumFeeInfo {
  premium_fee: number
}

export interface TransactionRecord {
  id: string
  type: 'exchange' | 'topup'
  from_currency: string | null
  to_currency: string
  amount: number
  rate_applied: number | null
  created_at: string
}

// ── Error types ───────────────────────────────────────────────────────────────

export class InsufficientBalanceError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'InsufficientBalanceError'
  }
}

export class OptimisticLockConflictError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'OptimisticLockConflictError'
  }
}

export class MoneyServiceError extends Error {
  constructor(
    message: string,
    public readonly statusCode: number,
  ) {
    super(message)
    this.name = 'MoneyServiceError'
  }
}

// ── Config ────────────────────────────────────────────────────────────────────

const MONEY_SERVICE_URL = import.meta.env.VITE_MONEY_SERVICE_URL ?? ''

if (!MONEY_SERVICE_URL) {
  console.warn(
    '[Money Service] VITE_MONEY_SERVICE_URL is not configured. ' +
    'Set it to https://your-alb-domain.com (production) ' +
    'or http://localhost:5000 (development).'
  )
}

// ── UUID generator (task 6.2.5) ───────────────────────────────────────────────

/**
 * Generates a RFC 4122 v4 UUID for use as idempotency key.
 * Uses crypto.randomUUID() when available (modern browsers), falls back to
 * manual implementation for older environments.
 */
export function generateIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  // Fallback: manual v4 UUID
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

// ── HTTP helper ───────────────────────────────────────────────────────────────

async function post<T>(
  path: string,
  body: unknown,
  idempotencyKey: string,
): Promise<T> {
  const token = await getAccessToken()
  if (!token) {
    throw new MoneyServiceError('Not authenticated', 401)
  }

  const response = await fetch(`${MONEY_SERVICE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify(body),
  })

  if (response.ok) {
    return response.json() as Promise<T>
  }

  // Task 6.2.6 — xử lý response lỗi
  let errorMessage = `Request failed with status ${response.status}`
  try {
    const errorBody = (await response.json()) as { error?: string; message?: string }
    errorMessage = errorBody.error ?? errorBody.message ?? errorMessage
  } catch {
    // ignore JSON parse error
  }

  if (response.status === 400) {
    throw new InsufficientBalanceError(errorMessage)
  }
  if (response.status === 409) {
    throw new OptimisticLockConflictError(errorMessage)
  }
  throw new MoneyServiceError(errorMessage, response.status)
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * POST /exchange — đổi tiền giữa các loại tiền tệ.
 * Tự động generate idempotency key (task 6.2.5).
 */
export async function exchangeCurrency(
  req: ExchangeRequest,
  idempotencyKey: string = generateIdempotencyKey(),
): Promise<TransactionResult> {
  return post<TransactionResult>('/exchange', req, idempotencyKey)
}

/**
 * POST /topup — nạp tiền VND giả lập.
 * Tự động generate idempotency key (task 6.2.5).
 */
export async function topUpBalance(
  req: TopUpRequest,
  idempotencyKey: string = generateIdempotencyKey(),
): Promise<TransactionResult> {
  return post<TransactionResult>('/topup', req, idempotencyKey)
}

/**
 * GET /balance — lấy số dư và lịch sử giao dịch.
 */
export async function getBalance(): Promise<BalanceInfo> {
  const token = await getAccessToken()
  if (!token) {
    throw new MoneyServiceError('Not authenticated', 401)
  }

  const response = await fetch(`${MONEY_SERVICE_URL}/balance`, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (response.ok) {
    return response.json() as Promise<BalanceInfo>
  }

  throw new MoneyServiceError(`Failed to fetch balance: ${response.status}`, response.status)
}

/**
 * GET /premium/fee — lấy phí nâng cấp premium từ Parameter Store (qua Money Service).
 * Task 8.2.1 — hiển thị premium_fee trên trang Upgrade.
 */
export async function getPremiumFee(): Promise<PremiumFeeInfo> {
  const token = await getAccessToken()
  if (!token) {
    throw new MoneyServiceError('Not authenticated', 401)
  }

  const response = await fetch(`${MONEY_SERVICE_URL}/premium/fee`, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (response.ok) {
    return response.json() as Promise<PremiumFeeInfo>
  }

  throw new MoneyServiceError(`Failed to fetch premium fee: ${response.status}`, response.status)
}

/**
 * POST /premium/upgrade — nâng cấp tài khoản lên Premium.
 *
 * Tasks:
 *   8.2.2  Kiểm tra số dư đủ tiền (Money Service trả HTTP 400 nếu không đủ)
 *   8.2.5  Xử lý lỗi insufficient balance với InsufficientBalanceError
 *
 * Idempotency key được generate tự động để tránh double-charge (Requirement 10.3).
 */
export async function upgradePremium(
  idempotencyKey: string = generateIdempotencyKey(),
): Promise<PremiumUpgradeResult> {
  return post<PremiumUpgradeResult>('/premium/upgrade', {}, idempotencyKey)
}

// ── Formatting helpers ────────────────────────────────────────────────────────

/** Danh sách các loại tiền tệ được hỗ trợ */
export const SUPPORTED_CURRENCIES = [
  'VND', 'USD', 'EUR', 'GBP', 'JPY', 'CNY',
  'KRW', 'THB', 'SGD', 'MYR', 'IDR', 'PHP', 'AUD',
] as const

export type SupportedCurrency = (typeof SUPPORTED_CURRENCIES)[number]

/** Format số tiền theo locale */
export function formatAmount(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat('vi-VN', {
      style: 'currency',
      currency,
      maximumFractionDigits: currency === 'VND' ? 0 : 4,
    }).format(amount)
  } catch {
    return `${amount.toLocaleString('vi-VN')} ${currency}`
  }
}

/** Format số dư VND */
export function formatVND(amount: number): string {
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND',
    maximumFractionDigits: 0,
  }).format(amount)
}
