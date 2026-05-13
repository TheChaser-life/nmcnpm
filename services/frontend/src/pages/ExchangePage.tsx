/**
 * ExchangePage.tsx
 *
 * Trang Currency Exchange & Top-Up — tổng hợp tất cả sub-tasks 6.2.
 *
 * Tasks:
 *   6.2.1  Form đổi tiền (chọn từ/đến currency, nhập số lượng)
 *   6.2.2  Hiển thị tỉ giá hiện tại và số tiền nhận được trước khi xác nhận
 *   6.2.3  Form nạp tiền
 *   6.2.4  Hiển thị số dư hiện tại và lịch sử giao dịch
 *   6.2.5  Generate UUID idempotency key (trong ExchangeForm và TopUpForm)
 *   6.2.6  Xử lý response lỗi (trong ExchangeForm và TopUpForm)
 */

import { useState, useCallback } from 'react'
import Navbar from '../components/Navbar'
import { ExchangeForm } from '../components/ExchangeForm'
import { TopUpForm } from '../components/TopUpForm'
import { TransactionHistory } from '../components/TransactionHistory'
import { useExchangeRates } from '../hooks/useExchangeRates'
import { useBalance } from '../hooks/useBalance'
import { ConnectionStatusBadge } from '../components/ConnectionStatusBadge'
import type { TransactionResult } from '../services/moneyService'

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
  pageHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '24px',
    flexWrap: 'wrap' as const,
    gap: '12px',
  },
  pageTitle: {
    fontSize: '1.5rem',
    fontWeight: 700,
    color: '#1a1a2e',
    margin: 0,
  } as const,
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
    gap: '20px',
    marginBottom: '24px',
  } as const,
  tabBar: {
    display: 'flex',
    gap: '8px',
    marginBottom: '20px',
    borderBottom: '2px solid #e9ecef',
    paddingBottom: '0',
  } as const,
  tab: {
    padding: '10px 20px',
    border: 'none',
    backgroundColor: 'transparent',
    fontSize: '0.95rem',
    fontWeight: 600,
    cursor: 'pointer',
    color: '#888',
    borderBottom: '2px solid transparent',
    marginBottom: '-2px',
    transition: 'all 0.15s',
  } as const,
  tabActive: {
    color: '#4361ee',
    borderBottomColor: '#4361ee',
  } as const,
}

// ── Component ─────────────────────────────────────────────────────────────────

type Tab = 'exchange' | 'topup'

function ExchangePage() {
  const [activeTab, setActiveTab] = useState<Tab>('exchange')

  // Real-time exchange rates từ WebSocket (dùng cho preview tỉ giá)
  const { rates, connectionStatus } = useExchangeRates()

  // Số dư và lịch sử giao dịch
  const { balanceVnd, transactions, loading: balanceLoading, refresh: refreshBalance } = useBalance()

  // Callback sau khi giao dịch thành công — refresh balance và history
  const handleTransactionSuccess = useCallback(
    (_result: TransactionResult) => {
      void refreshBalance()
    },
    [refreshBalance],
  )

  return (
    <div style={styles.page}>
      <Navbar />

      <main style={styles.content}>
        {/* Page header */}
        <div style={styles.pageHeader}>
          <h1 style={styles.pageTitle}>💱 Đổi tiền & Nạp tiền</h1>
          <ConnectionStatusBadge status={connectionStatus} />
        </div>

        {/* Tab bar */}
        <div style={styles.tabBar} role="tablist" aria-label="Chọn chức năng">
          <button
            role="tab"
            aria-selected={activeTab === 'exchange'}
            style={{
              ...styles.tab,
              ...(activeTab === 'exchange' ? styles.tabActive : {}),
            }}
            onClick={() => setActiveTab('exchange')}
            type="button"
          >
            💱 Đổi tiền
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'topup'}
            style={{
              ...styles.tab,
              ...(activeTab === 'topup' ? styles.tabActive : {}),
            }}
            onClick={() => setActiveTab('topup')}
            type="button"
          >
            💰 Nạp tiền
          </button>
        </div>

        {/* Form section */}
        <div style={styles.grid}>
          {activeTab === 'exchange' ? (
            /* Task 6.2.1, 6.2.2, 6.2.5, 6.2.6 */
            <ExchangeForm
              rates={rates}
              balanceVnd={balanceVnd}
              onSuccess={handleTransactionSuccess}
            />
          ) : (
            /* Task 6.2.3, 6.2.5, 6.2.6 */
            <TopUpForm onSuccess={handleTransactionSuccess} />
          )}
        </div>

        {/* Task 6.2.4 — Số dư và lịch sử giao dịch */}
        <TransactionHistory
          transactions={transactions}
          balanceVnd={balanceVnd}
          loading={balanceLoading}
        />
      </main>
    </div>
  )
}

export default ExchangePage
