/**
 * ExchangeForm.tsx
 *
 * Form đổi tiền giữa các loại tiền tệ.
 *
 * Tasks:
 *   6.2.1  Form đổi tiền (chọn từ/đến currency, nhập số lượng)
 *   6.2.2  Hiển thị tỉ giá hiện tại và số tiền nhận được trước khi xác nhận
 *   6.2.5  Generate UUID idempotency key cho mỗi request trước khi gửi
 *   6.2.6  Xử lý response lỗi (400 insufficient balance, 409 conflict)
 */

import { useState, useRef } from 'react'
import type { FormEvent } from 'react'
import {
  exchangeCurrency,
  generateIdempotencyKey,
  formatAmount,
  formatVND,
  SUPPORTED_CURRENCIES,
  InsufficientBalanceError,
  OptimisticLockConflictError,
  type TransactionResult,
} from '../services/moneyService'
import type { ExchangeRate } from '../hooks/useExchangeRates'

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
  row: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '12px',
    marginBottom: '12px',
  } as const,
  fieldGroup: { marginBottom: '12px' } as const,
  label: {
    display: 'block',
    fontSize: '0.8rem',
    fontWeight: 600,
    color: '#555',
    marginBottom: '5px',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  } as const,
  select: {
    width: '100%',
    padding: '10px 12px',
    border: '1px solid #ddd',
    borderRadius: '8px',
    fontSize: '0.95rem',
    color: '#1a1a2e',
    backgroundColor: '#fafafa',
    cursor: 'pointer',
    outline: 'none',
  } as const,
  sourceBox: {
    width: '100%',
    padding: '10px 12px',
    border: '1px solid #ddd',
    borderRadius: '8px',
    fontSize: '0.95rem',
    color: '#1a1a2e',
    backgroundColor: '#f3f4f6',
    boxSizing: 'border-box' as const,
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
  previewBox: {
    backgroundColor: '#f0f7ff',
    border: '1px solid #bfdbfe',
    borderRadius: '8px',
    padding: '14px 16px',
    marginBottom: '16px',
    fontSize: '0.9rem',
    color: '#1e40af',
  } as const,
  previewRow: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: '4px',
  } as const,
  previewLabel: { color: '#64748b', fontSize: '0.85rem' } as const,
  previewValue: { fontWeight: 600 } as const,
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
    backgroundColor: '#4361ee',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    fontSize: '0.95rem',
    fontWeight: 600,
    cursor: 'pointer',
  } as const,
  submitBtnDisabled: {
    backgroundColor: '#a5b4fc',
    cursor: 'not-allowed',
  } as const,
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface ExchangeFormProps {
  /** Tỉ giá real-time từ useExchangeRates hook (Map<currency, ExchangeRate>) */
  rates: Map<string, ExchangeRate>
  /** Số dư VND hiện tại */
  balanceVnd: number | null
  /** Callback sau khi giao dịch thành công */
  onSuccess: (result: TransactionResult) => void
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ExchangeForm({ rates, balanceVnd, onSuccess }: ExchangeFormProps) {
  const fromCurrency = 'VND'
  const [toCurrency, setToCurrency] = useState<string>('USD')
  const [amountStr, setAmountStr] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // Task 6.2.5 — generate idempotency key khi form mount hoặc sau mỗi giao dịch
  const idempotencyKeyRef = useRef<string>(generateIdempotencyKey())

  // Reset idempotency key sau khi submit thành công
  const resetIdempotencyKey = () => {
    idempotencyKeyRef.current = generateIdempotencyKey()
  }

  // Task 6.2.2 — tính toán số tiền nhận được dựa trên tỉ giá real-time
  const amount = parseFloat(amountStr) || 0
  const previewReceived = (() => {
    if (amount <= 0) return null
    if (fromCurrency === toCurrency) return amount

    // Lấy tỉ giá từ rates (tất cả rates là so với VND)
    // rates[currency].rate = 1 VND = rate * currency
    // => 1 currency = 1/rate VND
    const getVndRate = (currency: string): number | null => {
      if (currency === 'VND') return 1
      const r = rates.get(currency)
      return r ? r.rate : null
    }

    const fromRate = getVndRate(fromCurrency)
    const toRate = getVndRate(toCurrency)

    if (!fromRate || !toRate) return null

    // 1 fromCurrency = (1/fromRate) VND = (1/fromRate) * toRate toCurrency
    const crossRate = toRate / fromRate
    return amount * crossRate
  })()

  // VND cost để hiển thị preview
  const vndCost = (() => {
    if (amount <= 0 || fromCurrency === 'VND') return null
    const fromRate = rates.get(fromCurrency)?.rate
    if (!fromRate) return null
    return amount / fromRate
  })()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccessMsg(null)

    if (amount <= 0) {
      setError('Vui lòng nhập số tiền hợp lệ')
      return
    }
    if (toCurrency === 'VND') {
      setError('Vui lòng chọn hai loại tiền tệ khác nhau')
      return
    }

    setLoading(true)
    try {
      // Task 6.2.5 — dùng idempotency key đã generate sẵn
      const result = await exchangeCurrency(
        { from_currency: fromCurrency, to_currency: toCurrency, amount },
        idempotencyKeyRef.current,
      )

      const receivedStr = formatAmount(result.received_amount ?? result.amount, result.to_currency)
      setSuccessMsg(`✅ Giao dịch thành công! Nhận được ${receivedStr}`)
      setAmountStr('')
      resetIdempotencyKey()
      onSuccess(result)
    } catch (err) {
      // Task 6.2.6 — xử lý lỗi
      if (err instanceof InsufficientBalanceError) {
        setError('❌ Số dư không đủ để thực hiện giao dịch này')
      } else if (err instanceof OptimisticLockConflictError) {
        setError('⚠️ Xung đột giao dịch. Vui lòng thử lại sau vài giây.')
        resetIdempotencyKey()
      } else {
        setError(err instanceof Error ? err.message : 'Đã xảy ra lỗi. Vui lòng thử lại.')
      }
    } finally {
      setLoading(false)
    }
  }

  const isDisabled = loading || amount <= 0 || toCurrency === 'VND'

  return (
    <div style={s.card}>
      <h2 style={s.title}>💱 Đổi tiền</h2>

      {balanceVnd !== null && (
        <div style={{ marginBottom: '16px', fontSize: '0.875rem', color: '#555' }}>
          Số dư hiện tại:{' '}
          <strong style={{ color: '#1a1a2e' }}>{formatVND(balanceVnd)}</strong>
        </div>
      )}

      <form onSubmit={(e) => void handleSubmit(e)}>
        {/* Từ currency */}
        <div style={s.row}>
          <div style={s.fieldGroup}>
            <label style={s.label} htmlFor="from-currency">Từ</label>
            <div
              id="from-currency"
              style={s.sourceBox}
              aria-label="Chọn loại tiền tệ nguồn"
            >
              VND
            </div>
          </div>

          <div style={s.fieldGroup}>
            <label style={s.label} htmlFor="to-currency">Đến</label>
            <select
              id="to-currency"
              style={s.select}
              value={toCurrency}
              onChange={(e) => { setToCurrency(e.target.value); setError(null); setSuccessMsg(null) }}
              aria-label="Chọn loại tiền tệ đích"
            >
              {SUPPORTED_CURRENCIES.filter((c) => c !== 'VND').map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Số tiền */}
        <div style={s.fieldGroup}>
          <label style={s.label} htmlFor="exchange-amount">
            Số tiền ({fromCurrency})
          </label>
          <input
            id="exchange-amount"
            type="number"
            style={s.input}
            value={amountStr}
            onChange={(e) => { setAmountStr(e.target.value); setError(null); setSuccessMsg(null) }}
            placeholder={`Nhập số ${fromCurrency}`}
            min="0"
            step="any"
            aria-label={`Số tiền ${fromCurrency} muốn đổi`}
          />
        </div>

        {/* Task 6.2.2 — Preview tỉ giá và số tiền nhận được */}
        {previewReceived !== null && amount > 0 && fromCurrency !== toCurrency && (
          <div style={s.previewBox} role="status" aria-live="polite">
            <div style={s.previewRow}>
              <span style={s.previewLabel}>Bạn gửi</span>
              <span style={s.previewValue}>{formatAmount(amount, fromCurrency)}</span>
            </div>
            {vndCost !== null && fromCurrency !== 'VND' && (
              <div style={s.previewRow}>
                <span style={s.previewLabel}>Quy đổi VND</span>
                <span style={s.previewValue}>{formatVND(vndCost)}</span>
              </div>
            )}
            <div style={s.previewRow}>
              <span style={s.previewLabel}>Bạn nhận được</span>
              <span style={{ ...s.previewValue, color: '#1d4ed8', fontSize: '1rem' }}>
                ≈ {formatAmount(previewReceived, toCurrency)}
              </span>
            </div>
            {rates.get(fromCurrency) && rates.get(toCurrency) && (
              <div style={{ ...s.previewRow, marginBottom: 0 }}>
                <span style={s.previewLabel}>Tỉ giá</span>
                <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                  1 {fromCurrency} ≈ {formatAmount(previewReceived / amount, toCurrency)}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Error / Success messages */}
        {error && <div style={s.errorBox} role="alert">{error}</div>}
        {successMsg && <div style={s.successBox} role="status">{successMsg}</div>}

        <button
          type="submit"
          style={{ ...s.submitBtn, ...(isDisabled ? s.submitBtnDisabled : {}) }}
          disabled={isDisabled}
          aria-busy={loading}
        >
          {loading ? 'Đang xử lý...' : 'Xác nhận đổi tiền'}
        </button>
      </form>
    </div>
  )
}
