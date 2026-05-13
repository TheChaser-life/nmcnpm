/**
 * ExchangeRateTable.tsx
 *
 * Displays a real-time exchange rate table with flash animations when a rate
 * changes (task 4.3.2).
 *
 * Animation strategy:
 *   - When a rate value changes, the row briefly flashes green (rate went up)
 *     or red (rate went down) using a CSS keyframe animation injected once into
 *     the document <head>.
 *   - The previous rate is tracked via a ref so we can compare on each render.
 *   - A short setTimeout clears the flash class after the animation completes
 *     so the next change can trigger it again.
 *
 * Design references:
 *   - Requirement 2.2 (push within 5s, display updated rates)
 *   - design.md §1 (Exchange Rate Collection & Streaming)
 */

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { ExchangeRate } from '../hooks/useExchangeRates'

// ── CSS animation injection ───────────────────────────────────────────────────

const ANIMATION_STYLE_ID = 'cep-rate-flash-styles'

function injectAnimationStyles(): void {
  if (document.getElementById(ANIMATION_STYLE_ID)) return

  const style = document.createElement('style')
  style.id = ANIMATION_STYLE_ID
  style.textContent = `
    @keyframes cep-flash-up {
      0%   { background-color: rgba(34, 197, 94, 0.35); }
      100% { background-color: transparent; }
    }
    @keyframes cep-flash-down {
      0%   { background-color: rgba(239, 68, 68, 0.35); }
      100% { background-color: transparent; }
    }
    .cep-flash-up   { animation: cep-flash-up   0.8s ease-out forwards; }
    .cep-flash-down { animation: cep-flash-down 0.8s ease-out forwards; }
  `
  document.head.appendChild(style)
}

// ── Currency metadata ─────────────────────────────────────────────────────────

const CURRENCY_META: Record<string, { flag: string; name: string }> = {
  USD: { flag: '🇺🇸', name: 'Đô la Mỹ' },
  EUR: { flag: '🇪🇺', name: 'Euro' },
  GBP: { flag: '🇬🇧', name: 'Bảng Anh' },
  JPY: { flag: '🇯🇵', name: 'Yên Nhật' },
  CNY: { flag: '🇨🇳', name: 'Nhân dân tệ' },
  KRW: { flag: '🇰🇷', name: 'Won Hàn Quốc' },
  AUD: { flag: '🇦🇺', name: 'Đô la Úc' },
  CAD: { flag: '🇨🇦', name: 'Đô la Canada' },
  SGD: { flag: '🇸🇬', name: 'Đô la Singapore' },
  THB: { flag: '🇹🇭', name: 'Baht Thái' },
  HKD: { flag: '🇭🇰', name: 'Đô la Hồng Kông' },
  CHF: { flag: '🇨🇭', name: 'Franc Thụy Sĩ' },
}

function getCurrencyMeta(code: string): { flag: string; name: string } {
  return CURRENCY_META[code] ?? { flag: '🏳️', name: code }
}

// ── Formatting helpers ────────────────────────────────────────────────────────

/**
 * Formats a rate value (1 VND = X foreign currency) as a human-readable string.
 * For currencies with very small rates (e.g. JPY, KRW) we show more decimals.
 */
function formatRate(rate: number): string {
  if (rate === 0) return '—'
  // Show the inverse: how many VND per 1 unit of foreign currency
  const inverse = 1 / rate
  if (inverse >= 1000) {
    return inverse.toLocaleString('vi-VN', { maximumFractionDigits: 0 })
  }
  if (inverse >= 1) {
    return inverse.toLocaleString('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return inverse.toLocaleString('vi-VN', { minimumFractionDigits: 4, maximumFractionDigits: 4 })
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = {
  wrapper: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
    overflow: 'hidden',
  } as const,
  header: {
    padding: '20px 24px 16px',
    borderBottom: '1px solid #f0f0f0',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap' as const,
    gap: '8px',
  } as const,
  title: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#1a1a2e',
    margin: 0,
  } as const,
  subtitle: {
    fontSize: '0.8rem',
    color: '#888',
    margin: 0,
  } as const,
  table: {
    width: '100%',
    borderCollapse: 'collapse' as const,
  } as const,
  thead: {
    backgroundColor: '#f8f9fa',
  } as const,
  th: {
    padding: '10px 24px',
    textAlign: 'left' as const,
    fontSize: '0.75rem',
    fontWeight: 600,
    color: '#888',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
    borderBottom: '1px solid #f0f0f0',
  } as const,
  thRight: {
    padding: '10px 24px',
    textAlign: 'right' as const,
    fontSize: '0.75rem',
    fontWeight: 600,
    color: '#888',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
    borderBottom: '1px solid #f0f0f0',
  } as const,
  tr: {
    borderBottom: '1px solid #f8f8f8',
    transition: 'background-color 0.15s',
  } as const,
  td: {
    padding: '14px 24px',
    fontSize: '0.9rem',
    color: '#333',
    verticalAlign: 'middle' as const,
  } as const,
  tdRight: {
    padding: '14px 24px',
    fontSize: '0.9rem',
    color: '#333',
    textAlign: 'right' as const,
    verticalAlign: 'middle' as const,
    fontVariantNumeric: 'tabular-nums' as const,
    fontFamily: 'monospace',
  } as const,
  currencyCode: {
    fontWeight: 700,
    color: '#1a1a2e',
    marginRight: '6px',
  } as const,
  currencyName: {
    color: '#888',
    fontSize: '0.8rem',
  } as const,
  rateValue: {
    fontWeight: 600,
    fontSize: '0.95rem',
  } as const,
  vndLabel: {
    fontSize: '0.75rem',
    color: '#aaa',
    marginLeft: '4px',
  } as const,
  skeleton: {
    display: 'inline-block',
    width: '80px',
    height: '14px',
    backgroundColor: '#e9ecef',
    borderRadius: '4px',
    animation: 'pulse 1.5s ease-in-out infinite',
  } as const,
  emptyState: {
    padding: '48px 24px',
    textAlign: 'center' as const,
    color: '#aaa',
    fontSize: '0.9rem',
  } as const,
}

// ── RateRow component ─────────────────────────────────────────────────────────

interface RateRowProps {
  rate: ExchangeRate
}

function RateRow({ rate }: RateRowProps) {
  const prevRateRef = useRef<number | null>(null)
  const [flashClass, setFlashClass] = useState<string>('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const prev = prevRateRef.current

    if (prev !== null && prev !== rate.rate) {
      // Clear any in-progress animation first
      if (timerRef.current) clearTimeout(timerRef.current)
      setFlashClass('')

      // Use a microtask to allow React to flush the empty class before
      // re-applying the animation class (forces CSS animation restart).
      requestAnimationFrame(() => {
        setFlashClass(rate.rate > prev ? 'cep-flash-up' : 'cep-flash-down')
        timerRef.current = setTimeout(() => setFlashClass(''), 900)
      })
    }

    prevRateRef.current = rate.rate

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [rate.rate])

  const meta = getCurrencyMeta(rate.currency)

  return (
    <tr style={styles.tr} className={flashClass}>
      <td style={styles.td}>
        <span style={{ marginRight: '8px', fontSize: '1.1rem' }}>{meta.flag}</span>
        <span style={styles.currencyCode}>{rate.currency}</span>
        <span style={styles.currencyName}>{meta.name}</span>
      </td>
      <td style={styles.tdRight}>
        <span style={styles.rateValue}>{formatRate(rate.rate)}</span>
        <span style={styles.vndLabel}>VND</span>
      </td>
      <td style={styles.tdRight}>
        <span style={{ fontSize: '0.75rem', color: '#aaa' }}>
          {new Date(rate.timestamp * 1000).toLocaleTimeString('vi-VN')}
        </span>
      </td>
      <td style={styles.tdRight}>
        {/* Task 7.3.1 — link to currency detail page with tour list */}
        <Link
          to={`/currency/${rate.currency}`}
          style={{
            fontSize: '0.75rem',
            color: '#4361ee',
            fontWeight: 600,
            textDecoration: 'none',
            whiteSpace: 'nowrap' as const,
          }}
          aria-label={`Xem tour du lịch cho ${rate.currency}`}
        >
          ✈️ Tour
        </Link>
      </td>
    </tr>
  )
}

// ── Skeleton rows ─────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr style={styles.tr}>
      <td style={styles.td}>
        <span style={{ ...styles.skeleton, width: '120px' }} />
      </td>
      <td style={styles.tdRight}>
        <span style={styles.skeleton} />
      </td>
      <td style={styles.tdRight}>
        <span style={{ ...styles.skeleton, width: '60px' }} />
      </td>
      <td style={styles.tdRight}>
        <span style={{ ...styles.skeleton, width: '40px' }} />
      </td>
    </tr>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface ExchangeRateTableProps {
  rates: Map<string, ExchangeRate>
  lastUpdatedAt: number | null
  hasData: boolean
}

export function ExchangeRateTable({ rates, lastUpdatedAt, hasData }: ExchangeRateTableProps) {
  // Inject CSS animations once on first render
  useEffect(() => {
    injectAnimationStyles()
  }, [])

  // Sort currencies: known ones first (in CURRENCY_META order), then alphabetically
  const knownOrder = Object.keys(CURRENCY_META)
  const sortedRates = [...rates.values()].sort((a, b) => {
    const ai = knownOrder.indexOf(a.currency)
    const bi = knownOrder.indexOf(b.currency)
    if (ai !== -1 && bi !== -1) return ai - bi
    if (ai !== -1) return -1
    if (bi !== -1) return 1
    return a.currency.localeCompare(b.currency)
  })

  const lastUpdatedStr = lastUpdatedAt
    ? new Date(lastUpdatedAt).toLocaleTimeString('vi-VN')
    : null

  return (
    <div style={styles.wrapper}>
      <div style={styles.header}>
        <h2 style={styles.title}>📈 Tỉ giá thời gian thực</h2>
        {lastUpdatedStr && (
          <p style={styles.subtitle}>Cập nhật lúc {lastUpdatedStr}</p>
        )}
      </div>

      <table style={styles.table} aria-label="Bảng tỉ giá tiền tệ so với VND">
        <thead style={styles.thead}>
          <tr>
            <th style={styles.th} scope="col">Tiền tệ</th>
            <th style={styles.thRight} scope="col">Tỉ giá (VND)</th>
            <th style={styles.thRight} scope="col">Cập nhật</th>
            <th style={styles.thRight} scope="col">Tour</th>
          </tr>
        </thead>
        <tbody>
          {!hasData && (
            <>
              {Array.from({ length: 6 }).map((_, i) => (
                <SkeletonRow key={i} />
              ))}
            </>
          )}

          {hasData && sortedRates.length === 0 && (
            <tr>
              <td colSpan={4} style={styles.emptyState}>
                Không có dữ liệu tỉ giá.
              </td>
            </tr>
          )}

          {hasData &&
            sortedRates.map((rate) => (
              <RateRow key={rate.currency} rate={rate} />
            ))}
        </tbody>
      </table>
    </div>
  )
}

export default ExchangeRateTable
