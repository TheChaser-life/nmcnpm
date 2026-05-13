/**
 * TopUpForm.tsx
 *
 * Form nạp tiền VND giả lập.
 *
 * Tasks:
 *   6.2.3  Form nạp tiền
 *   6.2.5  Generate UUID idempotency key cho mỗi request trước khi gửi
 *   6.2.6  Xử lý response lỗi
 */

import { useState, useRef } from 'react'
import type { FormEvent } from 'react'
import {
  topUpBalance,
  generateIdempotencyKey,
  formatVND,
  MoneyServiceError,
  type TransactionResult,
} from '../services/moneyService'

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  card: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    padding: '24px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
  } as const,
  title: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#1a1a2e',
    marginBottom: '20px',
    marginTop: 0,
  } as const,
  fieldGroup: { marginBottom: '14px' } as const,
  label: {
    display: 'block',
    fontSize: '0.8rem',
    fontWeight: 600,
    color: '#555',
    marginBottom: '5px',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  } as const,
  input: {
    width: '100%',
    padding: '10px 12px',
    border: '1px solid #ddd',
    borderRadius: '8px',
    fontSize: '0.95rem',
    color: '#1a1a2e',
    backgroundColor: '#fafafa',
    outline: 'none',
    boxSizing: 'border-box' as const,
  } as const,
  quickAmounts: {
    display: 'flex',
    gap: '8px',
    flexWrap: 'wrap' as const,
    marginBottom: '14px',
  } as const,
  quickBtn: {
    padding: '6px 14px',
    border: '1px solid #4361ee',
    borderRadius: '20px',
    backgroundColor: '#fff',
    color: '#4361ee',
    fontSize: '0.8rem',
    fontWeight: 600,
    cursor: 'pointer',
  } as const,
  errorBox: {
    padding: '10px 14px',
    backgroundColor: '#fff5f5',
    border: '1px solid #ffc9c9',
    borderRadius: '8px',
    color: '#c92a2a',
    fontSize: '0.875rem',
    marginBottom: '12px',
  } as const,
  successBox: {
    padding: '10px 14px',
    backgroundColor: '#f0fff4',
    border: '1px solid #b2f2bb',
    borderRadius: '8px',
    color: '#2f9e44',
    fontSize: '0.875rem',
    marginBottom: '12px',
  } as const,
  submitBtn: {
    width: '100%',
    padding: '12px',
    backgroundColor: '#2ecc71',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    fontSize: '0.95rem',
    fontWeight: 600,
    cursor: 'pointer',
  } as const,
  submitBtnDisabled: {
    backgroundColor: '#a8e6c1',
    cursor: 'not-allowed',
  } as const,
  hint: {
    fontSize: '0.78rem',
    color: '#888',
    marginTop: '6px',
  } as const,
}

// ── Quick amounts ─────────────────────────────────────────────────────────────

const QUICK_AMOUNTS = [100_000, 500_000, 1_000_000, 5_000_000, 10_000_000]

// ── Props ─────────────────────────────────────────────────────────────────────

interface TopUpFormProps {
  onSuccess: (result: TransactionResult) => void
}

// ── Component ─────────────────────────────────────────────────────────────────

export function TopUpForm({ onSuccess }: TopUpFormProps) {
  const [amountStr, setAmountStr] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // Task 6.2.5 — generate idempotency key khi form mount
  const idempotencyKeyRef = useRef<string>(generateIdempotencyKey())

  const resetIdempotencyKey = () => {
    idempotencyKeyRef.current = generateIdempotencyKey()
  }

  const amount = parseFloat(amountStr) || 0

  const handleQuickAmount = (value: number) => {
    setAmountStr(String(value))
    setError(null)
    setSuccessMsg(null)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccessMsg(null)

    if (amount <= 0) {
      setError('Vui lòng nhập số tiền hợp lệ')
      return
    }
    if (amount < 1000) {
      setError('Số tiền nạp tối thiểu là 1.000 VND')
      return
    }

    setLoading(true)
    try {
      // Task 6.2.5 — dùng idempotency key đã generate sẵn
      const result = await topUpBalance(
        { amount },
        idempotencyKeyRef.current,
      )

      setSuccessMsg(`✅ Nạp tiền thành công! Số dư mới: ${formatVND(result.new_balance_vnd)}`)
      setAmountStr('')
      resetIdempotencyKey()
      onSuccess(result)
    } catch (err) {
      // Task 6.2.6 — xử lý lỗi
      if (err instanceof MoneyServiceError) {
        setError(`Lỗi ${err.statusCode}: ${err.message}`)
      } else {
        setError(err instanceof Error ? err.message : 'Đã xảy ra lỗi. Vui lòng thử lại.')
      }
    } finally {
      setLoading(false)
    }
  }

  const isDisabled = loading || amount <= 0

  return (
    <div style={s.card}>
      <h2 style={s.title}>💰 Nạp tiền</h2>

      <form onSubmit={(e) => void handleSubmit(e)}>
        {/* Quick amount buttons */}
        <div style={s.quickAmounts}>
          {QUICK_AMOUNTS.map((v) => (
            <button
              key={v}
              type="button"
              style={s.quickBtn}
              onClick={() => handleQuickAmount(v)}
              aria-label={`Nạp ${formatVND(v)}`}
            >
              {formatVND(v)}
            </button>
          ))}
        </div>

        {/* Amount input */}
        <div style={s.fieldGroup}>
          <label style={s.label} htmlFor="topup-amount">
            Số tiền nạp (VND)
          </label>
          <input
            id="topup-amount"
            type="number"
            style={s.input}
            value={amountStr}
            onChange={(e) => { setAmountStr(e.target.value); setError(null); setSuccessMsg(null) }}
            placeholder="Nhập số tiền VND"
            min="1000"
            step="1000"
            aria-label="Số tiền VND muốn nạp"
          />
          {amount > 0 && (
            <p style={s.hint}>
              Bạn sẽ nạp: <strong>{formatVND(amount)}</strong>
            </p>
          )}
        </div>

        {/* Error / Success messages */}
        {error && <div style={s.errorBox} role="alert">{error}</div>}
        {successMsg && <div style={s.successBox} role="status">{successMsg}</div>}

        <button
          type="submit"
          style={{ ...s.submitBtn, ...(isDisabled ? s.submitBtnDisabled : {}) }}
          disabled={isDisabled}
          aria-busy={loading}
        >
          {loading ? 'Đang xử lý...' : 'Nạp tiền ngay'}
        </button>
      </form>
    </div>
  )
}
