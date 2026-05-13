/**
 * AuthContext.tsx
 *
 * Provides authentication state and actions to the entire app.
 * Integrates useTokenRefresh to proactively refresh tokens before expiry.
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchAuthSession, getCurrentUser } from 'aws-amplify/auth'
import { logout, isPremiumUser, getCurrentUserEmail } from '../services/authService'
import { useTokenRefresh } from '../hooks/useTokenRefresh'

// ── Types ─────────────────────────────────────────────────────────────────────

interface AuthUser {
  email: string
  sub: string
}

interface AuthContextValue {
  /** The currently authenticated user, or null if not logged in */
  user: AuthUser | null
  /** Whether the user is authenticated */
  isAuthenticated: boolean
  /** Whether the user has premium status */
  isPremium: boolean
  /** Whether the auth state is still being loaded */
  loading: boolean
  /** Signs out the user and navigates to /login */
  signOut: () => Promise<void>
  /** Refreshes the auth state (call after premium upgrade) */
  refreshAuthState: () => Promise<void>
}

// ── Context ───────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null)

// ── Provider ──────────────────────────────────────────────────────────────────

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const navigate = useNavigate()

  const [user, setUser] = useState<AuthUser | null>(null)
  const [isAuth, setIsAuth] = useState(false)
  const [isPremium, setIsPremium] = useState(false)
  const [loading, setLoading] = useState(true)

  /**
   * Loads the current auth state from Amplify.
   * Called on mount and after token refresh.
   */
  const loadAuthState = useCallback(async (forceRefresh = false) => {
    try {
      const session = await fetchAuthSession({ forceRefresh })

      if (session.tokens?.accessToken && session.tokens?.idToken) {
        const cognitoUser = await getCurrentUser()
        const email = await getCurrentUserEmail()

        setUser({
          email: email ?? cognitoUser.username,
          sub: cognitoUser.userId,
        })
        setIsAuth(true)
        setIsPremium(await isPremiumUser(forceRefresh))
      } else {
        setUser(null)
        setIsAuth(false)
        setIsPremium(false)
      }
    } catch {
      // Not authenticated
      setUser(null)
      setIsAuth(false)
      setIsPremium(false)
    } finally {
      setLoading(false)
    }
  }, [])

  // Load auth state on mount
  useEffect(() => {
    void loadAuthState()
  }, [loadAuthState])

  /**
   * Signs out the user, clears state, and navigates to /login.
   * Amplify signOut() revokes the refresh token on Cognito and clears localStorage.
   */
  const handleSignOut = useCallback(async () => {
    try {
      await logout()
    } finally {
      setUser(null)
      setIsAuth(false)
      setIsPremium(false)
      navigate('/login')
    }
  }, [navigate])

  /**
   * Refreshes auth state — call after premium upgrade so the new
   * custom:premium=true claim is reflected immediately without re-login.
   */
  const refreshAuthState = useCallback(async () => {
    await loadAuthState(true)
  }, [loadAuthState])

  const handleTokenRefreshed = useCallback(async () => {
    await loadAuthState(false)
  }, [loadAuthState])

  // Proactively refresh tokens before expiry (only when authenticated)
  useTokenRefresh(isAuth, handleTokenRefreshed)

  const value: AuthContextValue = {
    user,
    isAuthenticated: isAuth,
    isPremium,
    loading,
    signOut: handleSignOut,
    refreshAuthState,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Returns the current auth context.
 * Must be used inside <AuthProvider>.
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}
