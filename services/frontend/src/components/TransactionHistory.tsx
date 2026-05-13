/**
 * TransactionHistory.tsx
 *
 * Hiển thị lịch sử giao dịch của user.
 * Task 6.2.4 — Hiển thị số dư hiện tại và lịch sử giao dịch.
 */

import { formatAmount, formatVND, type TransactionRecord } from '../services/moneyService'

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  card: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    padding: '24px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
  } as const,
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '16px',
  } as const,
  title: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#1a1a2e',
    margin: 0,
  } as const,
  balanceBadge: {
    padding: '6px 14px',
    backgroundColor: '#f0f7ff',
    border: '1px solid #bfdbfe',
    borderRadius: '20px',
    fontSize: '0.875rem',
    fontWeight: 600,
    color: '#1e40af',
  } as const,
  empty: {
    textAlign: 'center' as const,
    padding: '32px 0',
    color: '#aaa',
    fontSize: '0.9rem',
  } as const,
  table: {
    width: '100%',
    borderCollapse: 'collapse' as const,
    fontSize: '0.875rem',
  } as const,
  th: {
    textAlign: 'left' as const,
    padding: '8px 12px',
    borderBottom: '2px solid #f0f0f0',
    color: '#888',
    fontWeight: 600,
    fontSize: '0.78rem',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  } as const,
  td: {
    padding: '10px 12px',
    borderBottom: '1px solid #f5f5f5',
    color: '#333',
    verticalAlign: 'middle' as const,
  } as const,
  typeBadgeExchange: {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: '12px',
    fontSize: '0.75rem',
    fontWeight: 600,
    backgroundColor: '#eff6ff',
    color: '#1d4ed8',
  } as const,
  typeBadgeTopup: {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: '12px',
    fontSize: '0.75rem',
    fontWeight: 600,
    backgroundColor: '#f0fff4',
    color: '#15803d',
  } as const,
  amountPositive: { color: '#15803d', fontWeight: 600 } as const,
  amountNegative: { color: '#dc2626', fontWeight: 600 } as const,
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface TransactionHistoryProps {
  transactions: TransactionRecord[]
  balanceVnd: number | null
  loading: boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(isoString: string): string {
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(isoString))
  } catch {
    return isoString
  }
}

function getTransactionDescription(tx: TransactionRecord): string {
  if (tx.type === 'topup') {
    return `Nạp tiền VND`
  }
  return `${tx.from_currency ?? '?'} → ${tx.to_currency}`
}

function getAmountDisplay(tx: TransactionRecord): { text: string; positive: boolean } {
  if (tx.type === 'topup') {
    return { text: `+${formatVND(tx.amount)}`, positive: true }
  }
  // exchange: hiển thị số tiền gốc
  const currency = tx.from_currency ?? tx.to_currency
  return {
    text: `-${formatAmount(tx.amount, currency)}`,
    positive: false,
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export function TransactionHistory({
  transactions,
  balanceVnd,
  loading,
}: TransactionHistoryProps) {
  return (
    <div style={s.card}>
      <div style={s.header}>
        <h2 style={s.title}>📋 Lịch sử giao dịch</h2>
        {balanceVnd !== null && (
          <span style={s.balanceBadge} aria-label="Số dư hiện tại">
            Số dư: {formatVND(balanceVnd)}
          </span>
        )}
      </div>

      {loading ? (
        <div style={s.empty} aria-busy="true">Đang tải...</div>
      ) : transactions.length === 0 ? (
        <div style={s.empty}>Chưa có giao dịch nào</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={s.table} aria-label="Lịch sử giao dịch">
            <thead>
              <tr>
                <th style={s.th}>Loại</th>
                <th style={s.th}>Mô tả</th>
                <th style={s.th}>Số tiền</th>
                <th style={s.th}>Tỉ giá</th>
                <th style={s.th}>Thời gian</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx) => {
                const { text, positive } = getAmountDisplay(tx)
                return (
                  <tr key={tx.id}>
                    <td style={s.td}>
                      <span
                        style={tx.type === 'topup' ? s.typeBadgeTopup : s.typeBadgeExchange}
                      >
                        {tx.type === 'topup' ? '💰 Nạp tiền' : '💱 Đổi tiền'}
                      </span>
                    </td>
                    <td style={s.td}>{getTransactionDescription(tx)}</td>
                    <td style={{ ...s.td, ...(positive ? s.amountPositive : s.amountNegative) }}>
                      {text}
                    </td>
                    <td style={{ ...s.td, color: '#888', fontSize: '0.8rem' }}>
                      {tx.rate_applied != null
                        ? tx.rate_applied.toFixed(6)
                        : '—'}
                    </td>
                    <td style={{ ...s.td, color: '#888', fontSize: '0.8rem', whiteSpace: 'nowrap' as const }}>
                      {formatDate(tx.created_at)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
