/**
 * TourCard.tsx
 *
 * Renders a single travel tour card with name, description, and image.
 * Clicking the card opens the affiliate URL in a new browser tab.
 *
 * Tasks:
 *   7.3.2  Render tour card với tên, mô tả, và hình ảnh
 *   7.3.3  Implement redirect đến affiliate URL trong new tab khi user click
 *
 * Design references:
 *   - Requirement 7.2 (display tour name, description, image)
 *   - Requirement 7.3 (redirect to affiliate URL in new tab)
 *   - design.md §4 (Tour Information — Display Flow)
 */

import { useState } from 'react'
import type { Tour } from '../hooks/useTours'

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = {
  card: {
    backgroundColor: '#fff',
    borderRadius: '12px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column' as const,
    cursor: 'pointer',
    transition: 'transform 0.15s ease, box-shadow 0.15s ease',
    textDecoration: 'none',
    color: 'inherit',
    border: '1px solid #f0f0f0',
  } as const,
  cardHover: {
    transform: 'translateY(-3px)',
    boxShadow: '0 6px 20px rgba(0,0,0,0.10)',
  } as const,
  imageWrapper: {
    width: '100%',
    height: '180px',
    overflow: 'hidden',
    backgroundColor: '#f0f2f5',
    flexShrink: 0,
    position: 'relative' as const,
  } as const,
  image: {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
    display: 'block',
  } as const,
  imagePlaceholder: {
    width: '100%',
    height: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#e9ecef',
    fontSize: '2.5rem',
  } as const,
  body: {
    padding: '16px',
    display: 'flex',
    flexDirection: 'column' as const,
    flex: 1,
    gap: '8px',
  } as const,
  countryTag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '0.75rem',
    fontWeight: 600,
    color: '#4361ee',
    backgroundColor: '#eef0fd',
    padding: '2px 8px',
    borderRadius: '10px',
    alignSelf: 'flex-start' as const,
  } as const,
  name: {
    fontSize: '0.95rem',
    fontWeight: 700,
    color: '#1a1a2e',
    margin: 0,
    lineHeight: 1.4,
    // Clamp to 2 lines
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical' as const,
    overflow: 'hidden',
  } as const,
  description: {
    fontSize: '0.82rem',
    color: '#666',
    margin: 0,
    lineHeight: 1.5,
    // Clamp to 3 lines
    display: '-webkit-box',
    WebkitLineClamp: 3,
    WebkitBoxOrient: 'vertical' as const,
    overflow: 'hidden',
    flex: 1,
  } as const,
  footer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    marginTop: '4px',
  } as const,
  viewLink: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '0.8rem',
    fontWeight: 600,
    color: '#4361ee',
  } as const,
}

// ── Component ─────────────────────────────────────────────────────────────────

interface TourCardProps {
  tour: Tour
}

/**
 * TourCard renders a single tour with image, name, description, and country tag.
 *
 * Clicking the card opens the affiliate URL in a new tab (task 7.3.3).
 * Uses rel="noopener noreferrer" for security (prevents the new tab from
 * accessing the opener's window object and leaking the referrer).
 */
export function TourCard({ tour }: TourCardProps) {
  const [isHovered, setIsHovered] = useState(false)
  const [imageError, setImageError] = useState(false)

  const handleClick = () => {
    // Task 7.3.3 — redirect to affiliate URL in a new browser tab
    window.open(tour.affiliate_url, '_blank', 'noopener,noreferrer')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      handleClick()
    }
  }

  return (
    <article
      style={{
        ...styles.card,
        ...(isHovered ? styles.cardHover : {}),
      }}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocus={() => setIsHovered(true)}
      onBlur={() => setIsHovered(false)}
      role="link"
      tabIndex={0}
      aria-label={`Xem tour: ${tour.name} — mở trong tab mới`}
    >
      {/* Tour image (task 7.3.2) */}
      <div style={styles.imageWrapper}>
        {tour.image_url && !imageError ? (
          <img
            src={tour.image_url}
            alt={`Hình ảnh tour ${tour.name}`}
            style={styles.image}
            onError={() => setImageError(true)}
            loading="lazy"
          />
        ) : (
          <div style={styles.imagePlaceholder} aria-hidden="true">
            ✈️
          </div>
        )}
      </div>

      {/* Card body */}
      <div style={styles.body}>
        {/* Country tag */}
        {tour.country && (
          <span style={styles.countryTag}>
            🌏 {tour.country}
          </span>
        )}

        {/* Tour name (task 7.3.2) */}
        <h3 style={styles.name}>{tour.name}</h3>

        {/* Tour description (task 7.3.2) */}
        {tour.description && (
          <p style={styles.description}>{tour.description}</p>
        )}

        {/* Footer link hint */}
        <div style={styles.footer}>
          <span style={styles.viewLink}>
            Xem tour →
          </span>
        </div>
      </div>
    </article>
  )
}

export default TourCard
