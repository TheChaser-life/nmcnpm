/**
 * DashboardPage.tsx
 *
 * Main authenticated dashboard. Implements tasks 4.3.1 – 4.3.4 and 5.6:
 *
 *   4.3.1  WebSocket client connects to Streaming Service via useExchangeRates hook.
 *   4.3.2  ExchangeRateTable renders live rates with flash animations on change.
 *   4.3.3  Reconnection logic is handled inside useExchangeRates (Socket.IO
 *          exponential back-off, auto-reconnect on server disconnect).
 *   4.3.4  ConnectionStatusBadge shows connected / reconnecting / stale state.
 *   5.6.1  ForecastChart renders ML forecast for Premium_User.
 *   5.6.2  UpgradePrompt is shown to Standard_User in place of ForecastChart.
 *   5.6.3  Forecast section calls Forecast Service API via useForecast hook.
 *
 * Design references:
 *   - Requirements 2.1 – 2.5 (streaming, heartbeat, reconnection, sticky sessions)
 *   - Requirements 3, 9 (ML forecasting, premium gate)
 *   - design.md §1 (Exchange Rate Collection & Streaming)
 *   - design.md §2 (Forecast Flow)
 */

import { Link } from 'react-router-dom'
import Navbar from '../components/Navbar'
import { ExchangeRateTable } from '../components/ExchangeRateTable'
import { ConnectionStatusBadge } from '../components/ConnectionStatusBadge'
import { ForecastChart } from '../components/ForecastChart'
import { UpgradePrompt } from '../components/UpgradePrompt'
import { useAuth } from '../contexts/AuthContext'
import { useExchangeRates } from '../hooks/useExchangeRates'

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
  // ── Welcome card ────────────────────────────────────────────────────────────
  welcomeCard: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    padding: '24px 28px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
    marginBottom: '24px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap' as const,
    gap: '16px',
  },
  welcomeLeft: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px',
  },
  welcomeTitle: {
    fontSize: '1.4rem',
    fontWeight: 700,
    color: '#1a1a2e',
    margin: 0,
  },
  statusRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    flexWrap: 'wrap' as const,
  },
  premiumBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 12px',
    borderRadius: '20px',
    fontSize: '0.8rem',
    fontWeight: 600,
    backgroundColor: '#fff3cd',
    color: '#856404',
    border: '1px solid #ffc107',
  } as const,
  standardBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 12px',
    borderRadius: '20px',
    fontSize: '0.8rem',
    fontWeight: 600,
    backgroundColor: '#e9ecef',
    color: '#495057',
    border: '1px solid #dee2e6',
  } as const,
  upgradeLink: {
    display: 'inline-block',
    padding: '7px 18px',
    backgroundColor: '#f8961e',
    color: '#fff',
    borderRadius: '8px',
    fontSize: '0.85rem',
    fontWeight: 600,
    textDecoration: 'none',
  } as const,
  // ── Rate table section ───────────────────────────────────────────────────────
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '12px',
    flexWrap: 'wrap' as const,
    gap: '8px',
  },
  // ── Feature cards grid ───────────────────────────────────────────────────────
  featureGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: '16px',
    marginTop: '24px',
  },
  featureCard: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    padding: '22px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
    borderTop: '4px solid #4361ee',
  } as const,
  featureTitle: {
    fontSize: '0.95rem',
    fontWeight: 600,
    color: '#1a1a2e',
    marginBottom: '6px',
    marginTop: 0,
  } as const,
  featureText: {
    fontSize: '0.85rem',
    color: '#888',
    margin: 0,
  } as const,
  comingSoon: {
    display: 'inline-block',
    padding: '2px 8px',
    backgroundColor: '#e9ecef',
    color: '#666',
    borderRadius: '4px',
    fontSize: '0.75rem',
    marginTop: '8px',
  } as const,
}

// ── Component ─────────────────────────────────────────────────────────────────

function DashboardPage() {
  const { user, isPremium } = useAuth()

  // Task 4.3.1 — connect to Streaming Service WebSocket.
  // Task 4.3.3 — reconnection is handled inside the hook.
  const { rates, lastUpdatedAt, connectionStatus, hasData } = useExchangeRates()

  return (
    <div style={styles.page}>
      <Navbar />

      <main style={styles.content}>
        {/* ── Welcome card ─────────────────────────────────────────────────── */}
        <div style={styles.welcomeCard}>
          <div style={styles.welcomeLeft}>
            <h1 style={styles.welcomeTitle}>
              Xin chào{user?.email ? `, ${user.email}` : ''}! 👋
            </h1>
            <div style={styles.statusRow}>
              {isPremium ? (
                <span style={styles.premiumBadge}>⭐ Premium</span>
              ) : (
                <span style={styles.standardBadge}>👤 Standard</span>
              )}
            </div>
          </div>

          {!isPremium && (
            <Link to="/upgrade" style={styles.upgradeLink}>
              Nâng cấp Premium
            </Link>
          )}
        </div>

        {/* ── Exchange rate table ───────────────────────────────────────────── */}
        {/* Task 4.3.4 — connection status badge */}
        <div style={styles.sectionHeader}>
          <div /> {/* spacer */}
          <ConnectionStatusBadge status={connectionStatus} />
        </div>

        {/* Task 4.3.2 — real-time table with flash animations */}
        <ExchangeRateTable
          rates={rates}
          lastUpdatedAt={lastUpdatedAt}
          hasData={hasData}
        />

        {/* ── Forecast section (tasks 5.6.1 – 5.6.3) ──────────────────────── */}
        {/*
         * Requirement 9.5: Frontend SHALL hide forecast UI elements from
         * Standard_User sessions and display an upgrade prompt instead.
         *
         * isPremium is derived from the custom:premium claim in the Cognito
         * JWT (see AuthContext → isPremiumUser() in authService.ts).
         */}
        <div style={{ marginTop: '24px' }}>
          {isPremium ? (
            /* Task 5.6.1 — ForecastChart for Premium_User */
            /* Task 5.6.3 — calls Forecast Service API via useForecast hook */
            <ForecastChart />
          ) : (
            /* Task 5.6.2 — UpgradePrompt for Standard_User */
            <UpgradePrompt />
          )}
        </div>

        {/* ── Other feature cards ───────────────────────────────────────────── */}
        <div style={styles.featureGrid}>
          <div style={styles.featureCard}>
            <h2 style={styles.featureTitle}>💱 Đổi tiền & Nạp tiền</h2>
            <p style={styles.featureText}>
              Thực hành giao dịch tiền tệ với số dư giả lập, không rủi ro.
            </p>
            <Link
              to="/exchange"
              style={{
                display: 'inline-block',
                marginTop: '10px',
                padding: '6px 16px',
                backgroundColor: '#4361ee',
                color: '#fff',
                borderRadius: '6px',
                fontSize: '0.82rem',
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              Đổi tiền ngay →
            </Link>
          </div>

          <div style={styles.featureCard}>
            <h2 style={styles.featureTitle}>✈️ Tour du lịch</h2>
            <p style={styles.featureText}>
              Khám phá các tour du lịch liên quan đến loại tiền tệ bạn quan tâm.
            </p>
            <Link
              to="/currency/USD"
              style={{
                display: 'inline-block',
                marginTop: '10px',
                padding: '6px 16px',
                backgroundColor: '#4361ee',
                color: '#fff',
                borderRadius: '6px',
                fontSize: '0.82rem',
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              Xem tour →
            </Link>
          </div>
        </div>
      </main>
    </div>
  )
}

export default DashboardPage
