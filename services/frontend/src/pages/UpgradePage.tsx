/**
 * UpgradePage.tsx
 *
 * Trang "Nâng cấp Premium" — triển khai Phase 8.2 (tất cả sub-tasks).
 *
 * Tasks:
 *   8.2.1  Hiển thị premium_fee và danh sách lợi ích Premium
 *   8.2.2  Hiển thị số dư hiện tại và kiểm tra đủ tiền trước khi cho phép xác nhận
 *   8.2.3  Sau khi upgrade thành công, tự động gọi Cognito refresh token endpoint
 *   8.2.4  Cập nhật UI ngay lập tức để hiển thị tính năng premium (không cần re-login)
 *   8.2.5  Xử lý lỗi insufficient balance với thông báo rõ ràng
 *
 * Design references:
 *   - Requirement 10 (Premium Upgrade flow)
 *   - design.md §6 (Premium Upgrade — steps 3–9)
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import Navbar from '../components/Navbar'
import { useAuth } from '../contexts/AuthContext'
import { useBalance } from '../hooks/useBalance'
import {
  getPremiumFee,
  upgradePremium,
  formatVND,
  generateIdempotencyKey,
  InsufficientBalanceError,
  OptimisticLockConflictError,
  MoneyServiceError,
} from '../services/moneyService'

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
    padding: '40px 24px',
    maxWidth: '680px',
    margin: '0 auto',
    width: '100%',
    boxSizing: 'border-box' as const,
  },
  // ── Hero card ────────────────────────────────────────────────────────────────
  heroCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: '16px',
    padding: '36px 32px',
    marginBottom: '20px',
    textAlign: 'center' as const,
    boxShadow: '0 4px 24px rgba(0,0,0,0.15)',
    position: 'relative' as const,
    overflow: 'hidden' as const,
  },
  heroBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '5px 14px',
    backgroundColor: 'rgba(248,150,30,0.2)',
    border: '1px solid rgba(248,150,30,0.5)',
    borderRadius: '20px',
    color: '#f8961e',
    fontSize: '0.8rem',
    fontWeight: 700,
    letterSpacing: '0.5px',
    marginBottom: '16px',
  },
  heroTitle: {
    fontSize: '1.8rem',
    fontWeight: 800,
    color: '#fff',
    margin: '0 0 10px',
    lineHeight: 1.2,
  },
  heroSubtitle: {
    fontSize: '0.95rem',
    color: '#adb5bd',
    margin: '0 0 28px',
    lineHeight: 1.6,
  },
  priceRow: {
    display: 'flex',
    alignItems: 'baseline',
    justifyContent: 'center',
    gap: '8px',
    marginBottom: '8px',
  },
  priceLabel: {
    fontSize: '0.9rem',
    color: '#adb5bd',
  },
  priceAmount: {
    fontSize: '2.2rem',
    fontWeight: 800,
    color: '#f8961e',
  },
  priceCurrency: {
    fontSize: '1rem',
    color: '#adb5bd',
    fontWeight: 500,
  },
  priceNote: {
    fontSize: '0.8rem',
    color: '#6c757d',
    marginBottom: '0',
  },
  // ── Benefits card ────────────────────────────────────────────────────────────
  card: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    padding: '24px 28px',
    marginBottom: '20px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
  },
  cardTitle: {
    fontSize: '1rem',
    fontWeight: 700,
    color: '#1a1a2e',
    margin: '0 0 16px',
  },
  benefitList: {
    listStyle: 'none',
    padding: 0,
    margin: 0,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
  },
  benefitItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '12px',
  },
  benefitIcon: {
    fontSize: '1.3rem',
    lineHeight: 1,
    flexShrink: 0,
    marginTop: '1px',
  },
  benefitText: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '2px',
  },
  benefitTitle: {
    fontSize: '0.9rem',
    fontWeight: 600,
    color: '#1a1a2e',
  },
  benefitDesc: {
    fontSize: '0.82rem',
    color: '#888',
    lineHeight: 1.4,
  },
  // ── Balance card ─────────────────────────────────────────────────────────────
  balanceRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap' as const,
    gap: '8px',
  },
  balanceLabel: {
    fontSize: '0.9rem',
    color: '#555',
  },
  balanceValue: {
    fontSize: '1.2rem',
    fontWeight: 700,
    color: '#1a1a2e',
  },
  divider: {
    border: 'none',
    borderTop: '1px solid #f0f0f0',
    margin: '16px 0',
  },
  costRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap' as const,
    gap: '8px',
  },
  costLabel: {
    fontSize: '0.9rem',
    color: '#555',
  },
  costValue: {
    fontSize: '1rem',
    fontWeight: 600,
    color: '#f8961e',
  },
  remainingRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap' as const,
    gap: '8px',
    marginTop: '8px',
  },
  remainingLabel: {
    fontSize: '0.85rem',
    color: '#888',
  },
  remainingValue: (sufficient: boolean) => ({
    fontSize: '0.95rem',
    fontWeight: 600,
    color: sufficient ? '#2f9e44' : '#e63946',
  }),
  // ── Alerts ───────────────────────────────────────────────────────────────────
  errorBox: {
    padding: '14px 16px',
    backgroundColor: '#fff5f5',
    border: '1px solid #ffc9c9',
    borderRadius: '10px',
    color: '#c92a2a',
    fontSize: '0.875rem',
    marginBottom: '16px',
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
  },
  successBox: {
    padding: '14px 16px',
    backgroundColor: '#f0fff4',
    border: '1px solid #b2f2bb',
    borderRadius: '10px',
    color: '#2f9e44',
    fontSize: '0.875rem',
    marginBottom: '16px',
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
  },
  warningBox: {
    padding: '14px 16px',
    backgroundColor: '#fff9db',
    border: '1px solid #ffe066',
    borderRadius: '10px',
    color: '#856404',
    fontSize: '0.875rem',
    marginBottom: '16px',
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
  },
  alertIcon: {
    fontSize: '1.1rem',
    flexShrink: 0,
    marginTop: '1px',
  },
  // ── CTA button ───────────────────────────────────────────────────────────────
  upgradeButton: (disabled: boolean) => ({
    width: '100%',
    padding: '14px',
    backgroundColor: disabled ? '#a5b4fc' : '#f8961e',
    color: '#fff',
    border: 'none',
    borderRadius: '10px',
    fontSize: '1rem',
    fontWeight: 700,
    cursor: disabled ? 'not-allowed' : 'pointer',
    transition: 'background-color 0.2s',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
  }),
  alreadyPremiumCard: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    padding: '32px',
    textAlign: 'center' as const,
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
    marginBottom: '20px',
  },
  alreadyPremiumIcon: {
    fontSize: '3rem',
    marginBottom: '12px',
  },
  alreadyPremiumTitle: {
    fontSize: '1.2rem',
    fontWeight: 700,
    color: '#1a1a2e',
    margin: '0 0 8px',
  },
  alreadyPremiumText: {
    fontSize: '0.9rem',
    color: '#888',
    margin: '0 0 20px',
  },
  backButton: {
    display: 'inline-block',
    padding: '10px 24px',
    backgroundColor: '#4361ee',
    color: '#fff',
    borderRadius: '8px',
    fontSize: '0.9rem',
    fontWeight: 600,
    textDecoration: 'none',
    cursor: 'pointer',
    border: 'none',
  },
  loadingText: {
    color: '#888',
    fontSize: '0.9rem',
    textAlign: 'center' as const,
    padding: '20px 0',
  },
}

// ── Benefit data ──────────────────────────────────────────────────────────────

const BENEFITS = [
  {
    icon: '📈',
    title: 'Dự báo tỉ giá 7 ngày tới',
    desc: 'Xem xu hướng tỉ giá được dự báo bởi mô hình Machine Learning, cập nhật hàng ngày.',
  },
  {
    icon: '🤖',
    title: 'Mô hình ML tự động cải thiện',
    desc: 'Model được huấn luyện lại với dữ liệu mới nhất và chỉ được triển khai khi chính xác hơn.',
  },
  {
    icon: '💱',
    title: 'Hỗ trợ 10+ loại tiền tệ',
    desc: 'Dự báo cho USD, EUR, GBP, JPY, CNY, KRW, THB, SGD và nhiều loại tiền tệ khác.',
  },
  {
    icon: '⚡',
    title: 'Kết quả trong vòng 10 giây',
    desc: 'SageMaker Endpoint được tối ưu để trả kết quả nhanh chóng, không cần chờ đợi.',
  },
]

// ── Component ─────────────────────────────────────────────────────────────────

function UpgradePage() {
  const navigate = useNavigate()
  const { isPremium, refreshAuthState } = useAuth()

  // Task 8.2.2 — số dư hiện tại
  const { balanceVnd, loading: balanceLoading } = useBalance()

  // Task 8.2.1 — premium_fee từ Money Service (đọc từ Parameter Store)
  const [premiumFee, setPremiumFee] = useState<number | null>(null)
  const [feeLoading, setFeeLoading] = useState(true)
  const [feeError, setFeeError] = useState<string | null>(null)

  // Upgrade state
  const [upgrading, setUpgrading] = useState(false)
  const [upgradeError, setUpgradeError] = useState<string | null>(null)
  const [upgradeSuccess, setUpgradeSuccess] = useState(false)

  // Stable idempotency key — generated once per page visit to prevent double-charge
  const [idempotencyKey] = useState(() => generateIdempotencyKey())

  // Fetch premium fee on mount
  useEffect(() => {
    void (async () => {
      try {
        const data = await getPremiumFee()
        setPremiumFee(data.premium_fee)
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Không thể tải phí Premium'
        setFeeError(msg)
      } finally {
        setFeeLoading(false)
      }
    })()
  }, [])

  // Task 8.2.2 — kiểm tra số dư đủ tiền
  const hasSufficientBalance =
    balanceVnd !== null && premiumFee !== null && balanceVnd >= premiumFee

  const remainingAfterUpgrade =
    balanceVnd !== null && premiumFee !== null ? balanceVnd - premiumFee : null

  /**
   * Task 8.2.3 & 8.2.4 — Sau khi upgrade thành công:
   *   1. Gọi Cognito refresh token (qua fetchAuthSession forceRefresh=true trong refreshAuthState)
   *   2. Cập nhật AuthContext → isPremium = true ngay lập tức (không cần re-login)
   */
  const handleUpgrade = useCallback(async () => {
    if (!hasSufficientBalance || upgrading) return

    setUpgrading(true)
    setUpgradeError(null)

    try {
      // POST /premium/upgrade với idempotency key cố định cho lần visit này
      await upgradePremium(idempotencyKey)

      setUpgradeSuccess(true)

      // Task 8.2.3 — tự động gọi Cognito refresh token endpoint
      // Task 8.2.4 — refreshAuthState gọi fetchAuthSession({ forceRefresh: true })
      //              → Amplify lấy token mới với custom:premium=true
      //              → AuthContext cập nhật isPremium = true ngay lập tức
      await refreshAuthState()

      // Redirect về dashboard sau 2 giây để user thấy thông báo thành công
      setTimeout(() => {
        navigate('/dashboard')
      }, 2000)
    } catch (err) {
      // Task 8.2.5 — xử lý lỗi insufficient balance với thông báo rõ ràng
      if (err instanceof InsufficientBalanceError) {
        setUpgradeError(
          'Số dư không đủ để nâng cấp Premium. Vui lòng nạp thêm tiền và thử lại.',
        )
      } else if (err instanceof OptimisticLockConflictError) {
        setUpgradeError(
          'Có xung đột khi xử lý giao dịch. Vui lòng thử lại sau vài giây.',
        )
      } else if (err instanceof MoneyServiceError) {
        setUpgradeError(`Lỗi hệ thống (${err.statusCode}): ${err.message}`)
      } else {
        setUpgradeError('Đã xảy ra lỗi không xác định. Vui lòng thử lại.')
      }
    } finally {
      setUpgrading(false)
    }
  }, [hasSufficientBalance, upgrading, idempotencyKey, refreshAuthState, navigate])

  // ── Already premium ────────────────────────────────────────────────────────

  if (isPremium) {
    return (
      <div style={styles.page}>
        <Navbar />
        <main style={styles.content}>
          <div style={styles.alreadyPremiumCard}>
            <div style={styles.alreadyPremiumIcon}>⭐</div>
            <h1 style={styles.alreadyPremiumTitle}>Bạn đã là thành viên Premium!</h1>
            <p style={styles.alreadyPremiumText}>
              Tài khoản của bạn đã được kích hoạt đầy đủ tính năng Premium.
              Hãy khám phá dự báo tỉ giá ngay trên Dashboard.
            </p>
            <button
              style={styles.backButton}
              onClick={() => navigate('/dashboard')}
              type="button"
            >
              Về Dashboard →
            </button>
          </div>
        </main>
      </div>
    )
  }

  // ── Loading state ──────────────────────────────────────────────────────────

  const isLoading = feeLoading || balanceLoading

  // ── Main render ────────────────────────────────────────────────────────────

  return (
    <div style={styles.page}>
      <Navbar />

      <main style={styles.content}>
        {/* ── Hero card — Task 8.2.1 ─────────────────────────────────────── */}
        <div style={styles.heroCard} aria-labelledby="upgrade-page-title">
          <div style={styles.heroBadge}>
            <span aria-hidden="true">⭐</span> PREMIUM
          </div>

          <h1 id="upgrade-page-title" style={styles.heroTitle}>
            Nâng cấp lên Premium
          </h1>

          <p style={styles.heroSubtitle}>
            Mở khóa dự báo tỉ giá bằng Machine Learning và đưa ra quyết định
            đổi tiền thông minh hơn.
          </p>

          {/* Task 8.2.1 — hiển thị premium_fee */}
          {feeLoading ? (
            <p style={{ color: '#adb5bd', fontSize: '0.9rem' }}>Đang tải phí...</p>
          ) : feeError ? (
            <p style={{ color: '#e63946', fontSize: '0.9rem' }}>{feeError}</p>
          ) : (
            <>
              <div style={styles.priceRow}>
                <span style={styles.priceLabel}>Chỉ</span>
                <span style={styles.priceAmount}>
                  {premiumFee !== null ? premiumFee.toLocaleString('vi-VN') : '—'}
                </span>
                <span style={styles.priceCurrency}>VND</span>
              </div>
              <p style={styles.priceNote}>Thanh toán một lần bằng số dư giả lập</p>
            </>
          )}
        </div>

        {/* ── Benefits — Task 8.2.1 ─────────────────────────────────────────── */}
        <div style={styles.card} aria-labelledby="benefits-title">
          <h2 id="benefits-title" style={styles.cardTitle}>
            🎁 Quyền lợi Premium
          </h2>
          <ul style={styles.benefitList} aria-label="Danh sách quyền lợi Premium">
            {BENEFITS.map((b) => (
              <li key={b.title} style={styles.benefitItem}>
                <span style={styles.benefitIcon} aria-hidden="true">{b.icon}</span>
                <div style={styles.benefitText}>
                  <span style={styles.benefitTitle}>{b.title}</span>
                  <span style={styles.benefitDesc}>{b.desc}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* ── Balance check — Task 8.2.2 ────────────────────────────────────── */}
        <div style={styles.card} aria-labelledby="balance-check-title">
          <h2 id="balance-check-title" style={styles.cardTitle}>
            💰 Kiểm tra số dư
          </h2>

          {isLoading ? (
            <p style={styles.loadingText}>Đang tải thông tin...</p>
          ) : (
            <>
              <div style={styles.balanceRow}>
                <span style={styles.balanceLabel}>Số dư hiện tại</span>
                <span style={styles.balanceValue}>
                  {balanceVnd !== null ? formatVND(balanceVnd) : '—'}
                </span>
              </div>

              <hr style={styles.divider} />

              <div style={styles.costRow}>
                <span style={styles.costLabel}>Phí nâng cấp Premium</span>
                <span style={styles.costValue}>
                  {premiumFee !== null ? `− ${formatVND(premiumFee)}` : '—'}
                </span>
              </div>

              {remainingAfterUpgrade !== null && (
                <div style={styles.remainingRow}>
                  <span style={styles.remainingLabel}>Số dư sau khi nâng cấp</span>
                  <span style={styles.remainingValue(hasSufficientBalance)}>
                    {formatVND(remainingAfterUpgrade)}
                  </span>
                </div>
              )}

              {/* Task 8.2.2 — cảnh báo khi không đủ tiền */}
              {!hasSufficientBalance && balanceVnd !== null && premiumFee !== null && (
                <div style={{ ...styles.warningBox, marginTop: '16px' }} role="alert">
                  <span style={styles.alertIcon} aria-hidden="true">⚠️</span>
                  <span>
                    Số dư không đủ. Bạn cần thêm{' '}
                    <strong>{formatVND(premiumFee - balanceVnd)}</strong> để nâng cấp.{' '}
                    <button
                      type="button"
                      onClick={() => navigate('/exchange')}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: '#856404',
                        fontWeight: 700,
                        cursor: 'pointer',
                        textDecoration: 'underline',
                        padding: 0,
                        fontSize: 'inherit',
                      }}
                    >
                      Nạp tiền ngay →
                    </button>
                  </span>
                </div>
              )}
            </>
          )}
        </div>

        {/* ── Success / Error alerts ────────────────────────────────────────── */}

        {/* Task 8.2.4 — thông báo thành công, UI cập nhật ngay */}
        {upgradeSuccess && (
          <div style={styles.successBox} role="status" aria-live="polite">
            <span style={styles.alertIcon} aria-hidden="true">✅</span>
            <span>
              <strong>Nâng cấp thành công!</strong> Tài khoản của bạn đã được kích hoạt
              Premium. Đang chuyển hướng về Dashboard...
            </span>
          </div>
        )}

        {/* Task 8.2.5 — thông báo lỗi rõ ràng */}
        {upgradeError && !upgradeSuccess && (
          <div style={styles.errorBox} role="alert" aria-live="assertive">
            <span style={styles.alertIcon} aria-hidden="true">❌</span>
            <span>{upgradeError}</span>
          </div>
        )}

        {/* ── CTA button ────────────────────────────────────────────────────── */}
        {!upgradeSuccess && (
          <button
            type="button"
            style={styles.upgradeButton(!hasSufficientBalance || upgrading || isLoading)}
            onClick={() => void handleUpgrade()}
            disabled={!hasSufficientBalance || upgrading || isLoading}
            aria-disabled={!hasSufficientBalance || upgrading || isLoading}
            aria-label={
              !hasSufficientBalance
                ? 'Không đủ số dư để nâng cấp Premium'
                : 'Xác nhận nâng cấp lên Premium'
            }
          >
            {upgrading ? (
              <>
                <span aria-hidden="true">⏳</span> Đang xử lý...
              </>
            ) : (
              <>
                <span aria-hidden="true">⭐</span>
                {hasSufficientBalance
                  ? `Xác nhận nâng cấp — ${premiumFee !== null ? formatVND(premiumFee) : ''}`
                  : 'Số dư không đủ'}
              </>
            )}
          </button>
        )}

        {/* Back link */}
        {!upgradeSuccess && (
          <p style={{ textAlign: 'center', marginTop: '16px' }}>
            <button
              type="button"
              onClick={() => navigate(-1)}
              style={{
                background: 'none',
                border: 'none',
                color: '#888',
                fontSize: '0.875rem',
                cursor: 'pointer',
                textDecoration: 'underline',
              }}
            >
              ← Quay lại
            </button>
          </p>
        )}
      </main>
    </div>
  )
}

export default UpgradePage
