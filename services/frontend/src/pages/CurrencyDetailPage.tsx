/**
 * CurrencyDetailPage.tsx
 *
 * Trang chi tiết của một loại tiền tệ.
 * Hiển thị thông tin tỉ giá và danh sách tour du lịch liên quan.
 *
 * Tasks:
 *   7.3.1  Hiển thị danh sách tour trong trang chi tiết của từng currency
 *   7.3.2  Render tour card với tên, mô tả, và hình ảnh (via TourList → TourCard)
 *   7.3.3  Redirect đến affiliate URL trong new tab (via TourCard)
 *   7.3.4  Hiển thị "No tours available" khi danh sách rỗng (via TourList)
 *
 * Design references:
 *   - Requirement 7.1 – 7.4 (Tour display flow)
 *   - design.md §4 (Tour Information — Display Flow)
 *
 * Route: /currency/:currencyCode
 */

import { useParams, Link } from 'react-router-dom'
import Navbar from '../components/Navbar'
import { TourList } from '../components/TourList'
import { useExchangeRates } from '../hooks/useExchangeRates'

// ── Currency metadata ─────────────────────────────────────────────────────────

const CURRENCY_META: Record<string, { flag: string; name: string; country: string }> = {
  USD: { flag: '🇺🇸', name: 'Đô la Mỹ', country: 'Hoa Kỳ' },
  EUR: { flag: '🇪🇺', name: 'Euro', country: 'Liên minh châu Âu' },
  GBP: { flag: '🇬🇧', name: 'Bảng Anh', country: 'Vương quốc Anh' },
  JPY: { flag: '🇯🇵', name: 'Yên Nhật', country: 'Nhật Bản' },
  CNY: { flag: '🇨🇳', name: 'Nhân dân tệ', country: 'Trung Quốc' },
  KRW: { flag: '🇰🇷', name: 'Won Hàn Quốc', country: 'Hàn Quốc' },
  AUD: { flag: '🇦🇺', name: 'Đô la Úc', country: 'Úc' },
  CAD: { flag: '🇨🇦', name: 'Đô la Canada', country: 'Canada' },
  SGD: { flag: '🇸🇬', name: 'Đô la Singapore', country: 'Singapore' },
  THB: { flag: '🇹🇭', name: 'Baht Thái', country: 'Thái Lan' },
  HKD: { flag: '🇭🇰', name: 'Đô la Hồng Kông', country: 'Hồng Kông' },
  CHF: { flag: '🇨🇭', name: 'Franc Thụy Sĩ', country: 'Thụy Sĩ' },
  MYR: { flag: '🇲🇾', name: 'Ringgit Malaysia', country: 'Malaysia' },
  IDR: { flag: '🇮🇩', name: 'Rupiah Indonesia', country: 'Indonesia' },
  PHP: { flag: '🇵🇭', name: 'Peso Philippines', country: 'Philippines' },
}

function getCurrencyMeta(code: string) {
  return CURRENCY_META[code] ?? { flag: '🏳️', name: code, country: '' }
}

// ── Rate formatting ───────────────────────────────────────────────────────────

function formatRate(rate: number): string {
  if (rate === 0) return '—'
  const inverse = 1 / rate
  if (inverse >= 1000) {
    return inverse.toLocaleString('vi-VN', { maximumFractionDigits: 0 })
  }
  if (inverse >= 1) {
    return inverse.toLocaleString('vi-VN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  }
  return inverse.toLocaleString('vi-VN', {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  })
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = {
  page: {
    display: 'flex',
    flexDirection: 'column' as const,
    minHeight: '100vh',
    backgroundColor: '#f0f2f5',
  },
  content: {
    flex: 1,
    padding: '32px 24px',
    maxWidth: '1024px',
    margin: '0 auto',
    width: '100%',
    boxSizing: 'border-box' as const,
  },
  // ── Breadcrumb ─────────────────────────────────────────────────────────────
  breadcrumb: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '0.85rem',
    color: '#888',
    marginBottom: '20px',
  } as const,
  breadcrumbLink: {
    color: '#4361ee',
    textDecoration: 'none',
    fontWeight: 500,
  } as const,
  breadcrumbSep: {
    color: '#ccc',
  } as const,
  // ── Currency header card ───────────────────────────────────────────────────
  headerCard: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    padding: '24px 28px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
    marginBottom: '24px',
    display: 'flex',
    alignItems: 'center',
    gap: '20px',
    flexWrap: 'wrap' as const,
  } as const,
  flagEmoji: {
    fontSize: '3rem',
    lineHeight: 1,
  } as const,
  headerInfo: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '4px',
  } as const,
  currencyCode: {
    fontSize: '1.6rem',
    fontWeight: 800,
    color: '#1a1a2e',
    margin: 0,
  } as const,
  currencyName: {
    fontSize: '1rem',
    color: '#555',
    margin: 0,
  } as const,
  countryName: {
    fontSize: '0.85rem',
    color: '#888',
    margin: 0,
  } as const,
  rateBox: {
    marginLeft: 'auto',
    textAlign: 'right' as const,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '2px',
  } as const,
  rateLabel: {
    fontSize: '0.75rem',
    color: '#aaa',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
    margin: 0,
  } as const,
  rateValue: {
    fontSize: '1.5rem',
    fontWeight: 700,
    color: '#1a1a2e',
    fontFamily: 'monospace',
    margin: 0,
  } as const,
  rateUnit: {
    fontSize: '0.8rem',
    color: '#888',
    margin: 0,
  } as const,
  // ── Not found state ────────────────────────────────────────────────────────
  notFound: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    padding: '48px 24px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
    textAlign: 'center' as const,
    color: '#555',
  } as const,
  backLink: {
    display: 'inline-block',
    marginTop: '16px',
    padding: '8px 20px',
    backgroundColor: '#4361ee',
    color: '#fff',
    borderRadius: '8px',
    fontSize: '0.875rem',
    fontWeight: 600,
    textDecoration: 'none',
  } as const,
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * CurrencyDetailPage — shows exchange rate info and related travel tours
 * for a specific currency code.
 *
 * The TourList component handles all tour-related sub-tasks (7.3.1 – 7.3.4).
 */
function CurrencyDetailPage() {
  const { currencyCode } = useParams<{ currencyCode: string }>()
  const code = currencyCode?.toUpperCase() ?? ''

  // Get live rate from WebSocket (same hook used in DashboardPage)
  const { rates } = useExchangeRates()
  const liveRate = rates.get(code)

  const meta = getCurrencyMeta(code)

  if (!code) {
    return (
      <div style={styles.page}>
        <Navbar />
        <main style={styles.content}>
          <div style={styles.notFound}>
            <p>Không tìm thấy thông tin tiền tệ.</p>
            <Link to="/dashboard" style={styles.backLink}>
              ← Quay lại Dashboard
            </Link>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div style={styles.page}>
      <Navbar />

      <main style={styles.content}>
        {/* Breadcrumb */}
        <nav style={styles.breadcrumb} aria-label="Breadcrumb">
          <Link to="/dashboard" style={styles.breadcrumbLink}>
            Dashboard
          </Link>
          <span style={styles.breadcrumbSep} aria-hidden="true">›</span>
          <span aria-current="page">{code}</span>
        </nav>

        {/* Currency header card */}
        <div style={styles.headerCard}>
          <span style={styles.flagEmoji} aria-hidden="true">
            {meta.flag}
          </span>

          <div style={styles.headerInfo}>
            <h1 style={styles.currencyCode}>{code}</h1>
            <p style={styles.currencyName}>{meta.name}</p>
            {meta.country && (
              <p style={styles.countryName}>🌏 {meta.country}</p>
            )}
          </div>

          {/* Live exchange rate */}
          <div style={styles.rateBox}>
            <p style={styles.rateLabel}>Tỉ giá hiện tại</p>
            <p style={styles.rateValue}>
              {liveRate ? formatRate(liveRate.rate) : '—'}
            </p>
            <p style={styles.rateUnit}>VND / 1 {code}</p>
          </div>
        </div>

        {/* Tour list — tasks 7.3.1 – 7.3.4 */}
        <TourList currencyCode={code} />
      </main>
    </div>
  )
}

export default CurrencyDetailPage
