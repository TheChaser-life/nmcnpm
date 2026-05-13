/**
 * UpgradePrompt.tsx
 *
 * Displayed to Standard_User in place of the ForecastChart component.
 * Shows a locked/premium overlay with a clear CTA to upgrade.
 *
 * Design references:
 *   - Requirement 9.5 (Frontend hides forecast UI from Standard_User,
 *                       displays upgrade prompt instead)
 *   - Requirement 10   (Premium upgrade flow)
 *   - design.md §6     (Premium Upgrade Flow)
 */

import { Link } from 'react-router-dom'

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = {
  wrapper: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
    overflow: 'hidden',
    position: 'relative' as const,
  } as const,
  header: {
    padding: '20px 24px 16px',
    borderBottom: '1px solid #f0f0f0',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  } as const,
  title: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#1a1a2e',
    margin: 0,
  } as const,
  lockedBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 10px',
    backgroundColor: '#e9ecef',
    color: '#6c757d',
    borderRadius: '12px',
    fontSize: '0.75rem',
    fontWeight: 600,
    border: '1px solid #dee2e6',
  } as const,
  // Blurred preview area simulating a locked chart
  previewArea: {
    padding: '16px 24px',
    position: 'relative' as const,
    userSelect: 'none' as const,
  } as const,
  blurredChart: {
    height: '180px',
    borderRadius: '8px',
    background: 'linear-gradient(135deg, #e9ecef 0%, #dee2e6 50%, #e9ecef 100%)',
    filter: 'blur(4px)',
    opacity: 0.6,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  } as const,
  // Overlay on top of the blurred chart
  overlay: {
    position: 'absolute' as const,
    top: '16px',
    left: '24px',
    right: '24px',
    bottom: 0,
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    gap: '16px',
    padding: '24px',
    textAlign: 'center' as const,
  } as const,
  lockIcon: {
    fontSize: '2.5rem',
    lineHeight: 1,
  } as const,
  overlayTitle: {
    fontSize: '1.05rem',
    fontWeight: 700,
    color: '#1a1a2e',
    margin: 0,
  } as const,
  overlayText: {
    fontSize: '0.875rem',
    color: '#555',
    margin: 0,
    maxWidth: '340px',
    lineHeight: 1.5,
  } as const,
  upgradeButton: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '10px 24px',
    backgroundColor: '#f8961e',
    color: '#fff',
    borderRadius: '8px',
    fontSize: '0.9rem',
    fontWeight: 700,
    textDecoration: 'none',
    transition: 'background-color 0.2s',
    boxShadow: '0 2px 8px rgba(248,150,30,0.35)',
  } as const,
  featureList: {
    padding: '0 24px 20px',
    margin: 0,
    listStyle: 'none',
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '8px',
  } as const,
  featureItem: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 12px',
    backgroundColor: '#f8f9fa',
    borderRadius: '20px',
    fontSize: '0.8rem',
    color: '#555',
    border: '1px solid #e9ecef',
  } as const,
}

// ── Fake chart lines (decorative, blurred) ────────────────────────────────────

function FakeChartLines() {
  // Simple decorative SVG to hint at a chart behind the blur
  return (
    <svg
      viewBox="0 0 400 120"
      aria-hidden="true"
      style={{ width: '100%', height: '100%', opacity: 0.5 }}
    >
      <polyline
        points="0,80 60,60 120,70 180,40 240,55 300,30 360,45 400,35"
        fill="none"
        stroke="#adb5bd"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <polyline
        points="0,100 60,85 120,90 180,65 240,75 300,55 360,65 400,58"
        fill="none"
        stroke="#ced4da"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * UpgradePrompt — shown to Standard_User where ForecastChart would appear.
 *
 * Requirement 9.5: Frontend SHALL hide forecast UI elements from Standard_User
 * sessions and display an upgrade prompt instead.
 */
export function UpgradePrompt() {
  return (
    <section
      style={styles.wrapper}
      aria-labelledby="upgrade-prompt-title"
      aria-describedby="upgrade-prompt-desc"
    >
      {/* Header */}
      <div style={styles.header}>
        <h2 id="upgrade-prompt-title" style={styles.title}>
          🔮 Dự báo tỉ giá
        </h2>
        <span style={styles.lockedBadge} aria-label="Tính năng bị khóa">
          🔒 Premium
        </span>
      </div>

      {/* Blurred preview + overlay */}
      <div style={styles.previewArea}>
        {/* Decorative blurred chart */}
        <div style={styles.blurredChart} aria-hidden="true">
          <FakeChartLines />
        </div>

        {/* Overlay CTA */}
        <div style={styles.overlay}>
          <span style={styles.lockIcon} aria-hidden="true">🔒</span>

          <h3 style={styles.overlayTitle}>
            Tính năng dành riêng cho Premium
          </h3>

          <p id="upgrade-prompt-desc" style={styles.overlayText}>
            Nâng cấp lên Premium để xem dự báo tỉ giá được tạo bởi mô hình
            Machine Learning — giúp bạn đưa ra quyết định đổi tiền thông minh hơn.
          </p>

          <Link
            to="/upgrade"
            style={styles.upgradeButton}
            aria-label="Nâng cấp lên Premium để xem dự báo tỉ giá"
          >
            ⭐ Nâng cấp Premium
          </Link>
        </div>
      </div>

      {/* Feature highlights */}
      <ul style={styles.featureList} aria-label="Tính năng Premium">
        <li style={styles.featureItem}>
          <span aria-hidden="true">📈</span> Dự báo 7 ngày tới
        </li>
        <li style={styles.featureItem}>
          <span aria-hidden="true">🤖</span> Mô hình ML tự động cập nhật
        </li>
        <li style={styles.featureItem}>
          <span aria-hidden="true">💱</span> Hỗ trợ 10+ loại tiền tệ
        </li>
        <li style={styles.featureItem}>
          <span aria-hidden="true">⚡</span> Kết quả trong 10 giây
        </li>
      </ul>
    </section>
  )
}

export default UpgradePrompt
