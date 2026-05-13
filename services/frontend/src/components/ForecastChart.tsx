/**
 * ForecastChart.tsx
 *
 * Renders an SVG line chart of forecasted exchange rates for a given currency.
 * Only shown to Premium_User — the parent component is responsible for
 * gating access via the `custom:premium` claim (see DashboardPage.tsx).
 *
 * Design references:
 *   - Requirement 3 (ML Forecasting — premium only)
 *   - Requirement 9.5 (Frontend hides forecast UI from Standard_User)
 *   - design.md §2 (Forecast Flow)
 *
 * API:
 *   GET {VITE_FORECAST_SERVICE_URL}/forecast/{currencyCode}
 *   Authorization: Bearer <access_token>
 *
 * Handled states:
 *   loading       — skeleton / spinner
 *   success       — SVG line chart with time axis
 *   error_unavailable (503) — "service unavailable" message
 *   error_unauthorized (401) — redirect hint
 *   error_generic — generic error with retry button
 */

import { useState } from 'react'
import { useForecast } from '../hooks/useForecast'
import type { ForecastPoint } from '../hooks/useForecast'
import { useNavigate } from 'react-router-dom'

// ── Supported currencies (must match model) ───────────────────────────────────

const SUPPORTED_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'KRW', 'AUD', 'CAD', 'SGD', 'THB']

// ── SVG chart dimensions ──────────────────────────────────────────────────────

const CHART_WIDTH = 600
const CHART_HEIGHT = 220
const PADDING = { top: 20, right: 24, bottom: 48, left: 72 }

const PLOT_W = CHART_WIDTH - PADDING.left - PADDING.right
const PLOT_H = CHART_HEIGHT - PADDING.top - PADDING.bottom

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatVND(value: number): string {
  if (value >= 1000) {
    return value.toLocaleString('vi-VN', { maximumFractionDigits: 0 })
  }
  return value.toLocaleString('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString('vi-VN', {
    month: 'short',
    day: 'numeric',
  })
}

// ── SVG Line Chart ────────────────────────────────────────────────────────────

interface LineChartProps {
  points: ForecastPoint[]
  currency: string
}

function LineChart({ points, currency }: LineChartProps) {
  if (points.length === 0) {
    return (
      <p style={{ textAlign: 'center', color: '#aaa', padding: '32px 0' }}>
        Không có dữ liệu dự báo cho {currency}.
      </p>
    )
  }

  const rates = points.map((p) => p.rate)
  const timestamps = points.map((p) => p.timestamp)

  const minRate = Math.min(...rates)
  const maxRate = Math.max(...rates)
  const rateRange = maxRate - minRate || 1 // avoid division by zero

  const minTs = Math.min(...timestamps)
  const maxTs = Math.max(...timestamps)
  const tsRange = maxTs - minTs || 1

  // Map data point → SVG coordinate
  const toX = (ts: number) => PADDING.left + ((ts - minTs) / tsRange) * PLOT_W
  const toY = (rate: number) =>
    PADDING.top + PLOT_H - ((rate - minRate) / rateRange) * PLOT_H

  // Build polyline points string
  const polylinePoints = points
    .map((p) => `${toX(p.timestamp).toFixed(1)},${toY(p.rate).toFixed(1)}`)
    .join(' ')

  // Build area fill path (close below the line)
  const areaPath =
    `M ${toX(points[0].timestamp).toFixed(1)},${toY(points[0].rate).toFixed(1)} ` +
    points
      .slice(1)
      .map((p) => `L ${toX(p.timestamp).toFixed(1)},${toY(p.rate).toFixed(1)}`)
      .join(' ') +
    ` L ${toX(points[points.length - 1].timestamp).toFixed(1)},${(PADDING.top + PLOT_H).toFixed(1)}` +
    ` L ${toX(points[0].timestamp).toFixed(1)},${(PADDING.top + PLOT_H).toFixed(1)} Z`

  // Y-axis ticks (5 evenly spaced)
  const yTicks = Array.from({ length: 5 }, (_, i) => {
    const rate = minRate + (rateRange * i) / 4
    return { rate, y: toY(rate) }
  })

  // X-axis ticks (up to 5 evenly spaced)
  const xTickCount = Math.min(points.length, 5)
  const xTicks = Array.from({ length: xTickCount }, (_, i) => {
    const idx = Math.round((i / (xTickCount - 1 || 1)) * (points.length - 1))
    const p = points[idx]
    return { ts: p.timestamp, x: toX(p.timestamp) }
  })

  return (
    <svg
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      role="img"
      aria-label={`Biểu đồ dự báo tỉ giá ${currency}/VND`}
      style={{ width: '100%', height: 'auto', display: 'block' }}
    >
      <defs>
        <linearGradient id="forecast-area-gradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4361ee" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#4361ee" stopOpacity="0.01" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {yTicks.map(({ y }, i) => (
        <line
          key={i}
          x1={PADDING.left}
          y1={y.toFixed(1)}
          x2={PADDING.left + PLOT_W}
          y2={y.toFixed(1)}
          stroke="#f0f0f0"
          strokeWidth="1"
        />
      ))}

      {/* Area fill */}
      <path d={areaPath} fill="url(#forecast-area-gradient)" />

      {/* Line */}
      <polyline
        points={polylinePoints}
        fill="none"
        stroke="#4361ee"
        strokeWidth="2.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Data point dots */}
      {points.map((p, i) => (
        <circle
          key={i}
          cx={toX(p.timestamp).toFixed(1)}
          cy={toY(p.rate).toFixed(1)}
          r="3.5"
          fill="#fff"
          stroke="#4361ee"
          strokeWidth="2"
        />
      ))}

      {/* Y-axis labels */}
      {yTicks.map(({ rate, y }, i) => (
        <text
          key={i}
          x={PADDING.left - 8}
          y={y.toFixed(1)}
          textAnchor="end"
          dominantBaseline="middle"
          fontSize="11"
          fill="#888"
        >
          {formatVND(rate)}
        </text>
      ))}

      {/* X-axis labels */}
      {xTicks.map(({ ts, x }, i) => (
        <text
          key={i}
          x={x.toFixed(1)}
          y={PADDING.top + PLOT_H + 18}
          textAnchor="middle"
          fontSize="11"
          fill="#888"
        >
          {formatDate(ts)}
        </text>
      ))}

      {/* Axes */}
      <line
        x1={PADDING.left}
        y1={PADDING.top}
        x2={PADDING.left}
        y2={PADDING.top + PLOT_H}
        stroke="#ddd"
        strokeWidth="1"
      />
      <line
        x1={PADDING.left}
        y1={PADDING.top + PLOT_H}
        x2={PADDING.left + PLOT_W}
        y2={PADDING.top + PLOT_H}
        stroke="#ddd"
        strokeWidth="1"
      />

      {/* Y-axis label */}
      <text
        x={14}
        y={PADDING.top + PLOT_H / 2}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize="11"
        fill="#aaa"
        transform={`rotate(-90, 14, ${PADDING.top + PLOT_H / 2})`}
      >
        VND
      </text>
    </svg>
  )
}

// ── Skeleton loader ───────────────────────────────────────────────────────────

function ChartSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Đang tải dữ liệu dự báo..."
      style={{
        height: '220px',
        backgroundColor: '#f8f9fa',
        borderRadius: '8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#aaa',
        fontSize: '0.9rem',
        gap: '10px',
      }}
    >
      <span
        style={{
          display: 'inline-block',
          width: '18px',
          height: '18px',
          border: '2px solid #ddd',
          borderTopColor: '#4361ee',
          borderRadius: '50%',
          animation: 'cep-spin 0.8s linear infinite',
        }}
        aria-hidden="true"
      />
      Đang tải dự báo...
    </div>
  )
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
    gap: '12px',
  } as const,
  title: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#1a1a2e',
    margin: 0,
  } as const,
  currencySelector: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexWrap: 'wrap' as const,
  } as const,
  selectLabel: {
    fontSize: '0.85rem',
    color: '#666',
    fontWeight: 500,
  } as const,
  select: {
    padding: '6px 12px',
    borderRadius: '6px',
    border: '1px solid #dee2e6',
    fontSize: '0.875rem',
    color: '#333',
    backgroundColor: '#fff',
    cursor: 'pointer',
    outline: 'none',
  } as const,
  chartArea: {
    padding: '16px 24px 20px',
  } as const,
  errorBox: {
    margin: '16px 24px',
    padding: '16px',
    borderRadius: '8px',
    backgroundColor: '#fff3cd',
    border: '1px solid #ffc107',
    color: '#856404',
    fontSize: '0.875rem',
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
  } as const,
  unavailableBox: {
    margin: '16px 24px',
    padding: '16px',
    borderRadius: '8px',
    backgroundColor: '#f8d7da',
    border: '1px solid #f5c2c7',
    color: '#842029',
    fontSize: '0.875rem',
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
  } as const,
  retryButton: {
    marginTop: '10px',
    padding: '6px 14px',
    backgroundColor: '#4361ee',
    color: '#fff',
    border: 'none',
    borderRadius: '6px',
    fontSize: '0.8rem',
    fontWeight: 600,
    cursor: 'pointer',
  } as const,
  premiumBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 10px',
    backgroundColor: '#fff3cd',
    color: '#856404',
    borderRadius: '12px',
    fontSize: '0.75rem',
    fontWeight: 600,
    border: '1px solid #ffc107',
  } as const,
  footer: {
    padding: '8px 24px 16px',
    fontSize: '0.75rem',
    color: '#aaa',
  } as const,
}

// ── Main component ────────────────────────────────────────────────────────────

/**
 * ForecastChart — renders ML forecast for Premium_User.
 *
 * This component should only be rendered when `isPremium === true`.
 * The parent (DashboardPage) is responsible for the premium gate.
 */
export function ForecastChart() {
  const navigate = useNavigate()
  const [selectedCurrency, setSelectedCurrency] = useState<string>('USD')

  const { data, status, errorMessage, refetch } = useForecast(selectedCurrency, true)

  const handleCurrencyChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedCurrency(e.target.value)
  }

  const handleRetry = () => {
    refetch()
  }

  const handleLoginRedirect = () => {
    navigate('/login')
  }

  return (
    <section style={styles.wrapper} aria-labelledby="forecast-chart-title">
      {/* Inject spin animation once */}
      <style>{`
        @keyframes cep-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>

      {/* Header */}
      <div style={styles.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h2 id="forecast-chart-title" style={styles.title}>
            🔮 Dự báo tỉ giá
          </h2>
          <span style={styles.premiumBadge}>⭐ Premium</span>
        </div>

        <div style={styles.currencySelector}>
          <label htmlFor="forecast-currency-select" style={styles.selectLabel}>
            Tiền tệ:
          </label>
          <select
            id="forecast-currency-select"
            value={selectedCurrency}
            onChange={handleCurrencyChange}
            style={styles.select}
            aria-label="Chọn tiền tệ để xem dự báo"
          >
            {SUPPORTED_CURRENCIES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Chart area */}
      <div style={styles.chartArea}>
        {status === 'loading' && <ChartSkeleton />}

        {status === 'success' && data && (
          <LineChart points={data.points} currency={data.currency} />
        )}

        {status === 'error_unavailable' && (
          <div style={styles.unavailableBox} role="alert">
            <span aria-hidden="true">⚠️</span>
            <div>
              <strong>Dịch vụ dự báo không khả dụng</strong>
              <p style={{ margin: '4px 0 0' }}>{errorMessage}</p>
              <button
                type="button"
                style={styles.retryButton}
                onClick={handleRetry}
                aria-label="Thử lại tải dự báo"
              >
                Thử lại
              </button>
            </div>
          </div>
        )}

        {status === 'error_unauthorized' && (
          <div style={styles.errorBox} role="alert">
            <span aria-hidden="true">🔒</span>
            <div>
              <strong>Phiên đăng nhập hết hạn</strong>
              <p style={{ margin: '4px 0 0' }}>{errorMessage}</p>
              <button
                type="button"
                style={styles.retryButton}
                onClick={handleLoginRedirect}
                aria-label="Đăng nhập lại"
              >
                Đăng nhập lại
              </button>
            </div>
          </div>
        )}

        {(status === 'error_generic' || status === 'error_forbidden') && (
          <div style={styles.errorBox} role="alert">
            <span aria-hidden="true">❌</span>
            <div>
              <strong>Không thể tải dự báo</strong>
              <p style={{ margin: '4px 0 0' }}>{errorMessage}</p>
              <button
                type="button"
                style={styles.retryButton}
                onClick={handleRetry}
                aria-label="Thử lại tải dự báo"
              >
                Thử lại
              </button>
            </div>
          </div>
        )}

        {status === 'idle' && (
          <p style={{ textAlign: 'center', color: '#aaa', padding: '32px 0' }}>
            Chọn tiền tệ để xem dự báo.
          </p>
        )}
      </div>

      {/* Footer note */}
      {status === 'success' && data && (
        <p style={styles.footer}>
          Dự báo được tạo bởi mô hình Machine Learning. Chỉ mang tính tham khảo.
        </p>
      )}
    </section>
  )
}

export default ForecastChart
