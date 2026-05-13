/**
 * TourList.tsx
 *
 * Displays a list of travel tours for a given currency code.
 * Fetches data from the Tour Service API via the useTours hook.
 *
 * Tasks:
 *   7.3.1  Hiển thị danh sách tour trong trang chi tiết của từng currency
 *   7.3.4  Hiển thị thông báo "No tours available" khi danh sách rỗng
 *
 * Design references:
 *   - Requirement 7.1 (Tour_Service retrieves and displays tour info)
 *   - Requirement 7.4 (Show "No tours available" when list is empty)
 *   - design.md §4 (Tour Information — Display Flow)
 */

import { TourCard } from './TourCard'
import { useTours } from '../hooks/useTours'

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = {
  section: {
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
  body: {
    padding: '20px 24px',
  } as const,
  // ── Grid layout for tour cards ─────────────────────────────────────────────
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
    gap: '16px',
  } as const,
  // ── Skeleton cards ─────────────────────────────────────────────────────────
  skeletonCard: {
    backgroundColor: '#f8f9fa',
    borderRadius: '12px',
    overflow: 'hidden',
    border: '1px solid #f0f0f0',
  } as const,
  skeletonImage: {
    width: '100%',
    height: '180px',
    backgroundColor: '#e9ecef',
    animation: 'cep-pulse 1.5s ease-in-out infinite',
  } as const,
  skeletonBody: {
    padding: '16px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '10px',
  } as const,
  skeletonLine: {
    height: '12px',
    backgroundColor: '#e9ecef',
    borderRadius: '4px',
    animation: 'cep-pulse 1.5s ease-in-out infinite',
  } as const,
  // ── Empty state ────────────────────────────────────────────────────────────
  emptyState: {
    padding: '48px 24px',
    textAlign: 'center' as const,
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: '12px',
  } as const,
  emptyIcon: {
    fontSize: '2.5rem',
  } as const,
  emptyTitle: {
    fontSize: '1rem',
    fontWeight: 600,
    color: '#555',
    margin: 0,
  } as const,
  emptyText: {
    fontSize: '0.85rem',
    color: '#aaa',
    margin: 0,
    maxWidth: '320px',
  } as const,
  // ── Error state ────────────────────────────────────────────────────────────
  errorBox: {
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
}

// ── Skeleton card ─────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div style={styles.skeletonCard} aria-hidden="true">
      <div style={styles.skeletonImage} />
      <div style={styles.skeletonBody}>
        <div style={{ ...styles.skeletonLine, width: '60%' }} />
        <div style={{ ...styles.skeletonLine, width: '90%' }} />
        <div style={{ ...styles.skeletonLine, width: '75%' }} />
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface TourListProps {
  /** ISO 4217 currency code (e.g. "USD", "EUR") */
  currencyCode: string
}

/**
 * TourList fetches and renders travel tours for the given currency.
 *
 * States handled:
 *   loading  — skeleton cards
 *   success  — grid of TourCard components
 *   empty    — "No tours available" message (task 7.3.4)
 *   error    — error message with retry button
 */
export function TourList({ currencyCode }: TourListProps) {
  const { tours, status, errorMessage, refetch } = useTours(currencyCode)

  return (
    <section style={styles.section} aria-labelledby="tour-list-title">
      {/* Inject pulse animation once */}
      <style>{`
        @keyframes cep-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>

      {/* Header */}
      <div style={styles.header}>
        <h2 id="tour-list-title" style={styles.title}>
          ✈️ Tour du lịch liên quan
        </h2>
        {status === 'success' && tours.length > 0 && (
          <p style={styles.subtitle}>{tours.length} tour được tìm thấy</p>
        )}
      </div>

      {/* Body */}
      <div style={styles.body}>
        {/* Loading state — skeleton cards */}
        {status === 'loading' && (
          <div style={styles.grid} aria-busy="true" aria-label="Đang tải danh sách tour...">
            {Array.from({ length: 3 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {/* Success state — tour cards (task 7.3.1) */}
        {status === 'success' && tours.length > 0 && (
          <div
            style={styles.grid}
            role="list"
            aria-label={`Danh sách tour du lịch cho ${currencyCode}`}
          >
            {tours.map((tour) => (
              <div key={tour.id} role="listitem">
                <TourCard tour={tour} />
              </div>
            ))}
          </div>
        )}

        {/* Empty state — task 7.3.4 */}
        {status === 'success' && tours.length === 0 && (
          <div style={styles.emptyState} role="status" aria-live="polite">
            <span style={styles.emptyIcon} aria-hidden="true">🗺️</span>
            <p style={styles.emptyTitle}>Không có tour nào</p>
            <p style={styles.emptyText}>
              Hiện tại chưa có tour du lịch nào cho {currencyCode}. Vui lòng quay lại sau.
            </p>
          </div>
        )}

        {/* Error state */}
        {status === 'error' && (
          <div style={styles.errorBox} role="alert">
            <span aria-hidden="true">⚠️</span>
            <div>
              <strong>Không thể tải danh sách tour</strong>
              <p style={{ margin: '4px 0 0' }}>{errorMessage}</p>
              <button
                type="button"
                style={styles.retryButton}
                onClick={refetch}
                aria-label="Thử lại tải danh sách tour"
              >
                Thử lại
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

export default TourList
