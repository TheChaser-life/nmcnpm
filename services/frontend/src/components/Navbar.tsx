/**
 * Navbar.tsx
 *
 * Top navigation bar shown on authenticated pages.
 * Displays the user's email, premium badge, and a logout button.
 */

import { Link } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const styles = {
  nav: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 24px',
    height: '60px',
    backgroundColor: '#1a1a2e',
    color: '#fff',
    boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
  } as const,
  brand: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#4cc9f0',
    letterSpacing: '0.5px',
    textDecoration: 'none',
  } as const,
  navLinks: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  } as const,
  navLink: {
    padding: '6px 14px',
    color: '#ccc',
    textDecoration: 'none',
    fontSize: '0.875rem',
    borderRadius: '6px',
    transition: 'background-color 0.15s',
  } as const,
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  } as const,
  userInfo: {
    fontSize: '0.875rem',
    color: '#ccc',
  } as const,
  premiumBadge: {
    display: 'inline-block',
    padding: '2px 8px',
    backgroundColor: '#f8961e',
    color: '#fff',
    borderRadius: '12px',
    fontSize: '0.75rem',
    fontWeight: 600,
    marginLeft: '8px',
  } as const,
  logoutButton: {
    padding: '6px 16px',
    backgroundColor: 'transparent',
    color: '#ccc',
    border: '1px solid #555',
    borderRadius: '6px',
    fontSize: '0.875rem',
    cursor: 'pointer',
    transition: 'all 0.2s',
  } as const,
}

function Navbar() {
  const { user, isPremium, signOut } = useAuth()

  const handleLogout = () => {
    void signOut()
  }

  return (
    <nav style={styles.nav}>
      <Link to="/dashboard" style={styles.brand}>💱 Currency Exchange</Link>

      {/* Navigation links */}
      <div style={styles.navLinks}>
        <Link to="/dashboard" style={styles.navLink}>Dashboard</Link>
        <Link to="/exchange" style={styles.navLink}>Đổi tiền</Link>
        {!isPremium && (
          <Link
            to="/upgrade"
            style={{
              ...styles.navLink,
              color: '#f8961e',
              fontWeight: 600,
            }}
          >
            ⭐ Premium
          </Link>
        )}
      </div>

      <div style={styles.right}>
        {user && (
          <span style={styles.userInfo}>
            {user.email}
            {isPremium && <span style={styles.premiumBadge}>Premium</span>}
          </span>
        )}
        <button
          style={styles.logoutButton}
          onClick={handleLogout}
          type="button"
          aria-label="Đăng xuất"
        >
          Đăng xuất
        </button>
      </div>
    </nav>
  )
}

export default Navbar
