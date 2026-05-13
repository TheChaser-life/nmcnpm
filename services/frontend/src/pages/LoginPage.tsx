/**
 * LoginPage.tsx
 *
 * Login form that authenticates users via AWS Cognito (Amplify v6).
 *
 * Handles:
 *   - NotAuthorizedException    → wrong credentials
 *   - UserNotConfirmedException → redirect to confirm page (inline OTP)
 *   - UserNotFoundException     → user does not exist
 *   - Account lockout (5 failed attempts) — Cognito returns NotAuthorizedException
 *     with a message indicating the account is locked for 15 minutes
 */

import { useState, useEffect, type FormEvent } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { signIn } from 'aws-amplify/auth'
import { useAuth } from '../contexts/AuthContext'
import { formStyles as s } from './formStyles'

interface LocationState {
  from?: { pathname: string }
  message?: string
}

function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as LocationState | null

  const { refreshAuthState, isAuthenticated } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // If already authenticated, redirect to dashboard automatically
  useEffect(() => {
    if (isAuthenticated) {
      const from = state?.from?.pathname ?? '/dashboard'
      navigate(from, { replace: true })
    }
  }, [isAuthenticated, navigate, state])

  // Success message passed from ForgotPasswordPage after reset
  const successMessage = state?.message ?? null

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      const result = await signIn({ username: email, password })

      if (result.isSignedIn) {
        // Refresh global auth state before navigating to ensure ProtectedRoute
        // sees the new session immediately.
        await refreshAuthState()

        // Navigate to the originally requested page, or dashboard
        const from = state?.from?.pathname ?? '/dashboard'
        navigate(from, { replace: true })
      } else if (result.nextStep.signInStep === 'CONFIRM_SIGN_UP') {
        // User registered but hasn't confirmed email yet
        navigate('/register', {
          state: { email, needsConfirmation: true },
        })
      }
    } catch (err: unknown) {
      setError(mapCognitoError(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={s.pageContainer}>
      <div style={s.card}>
        <h1 style={s.title}>Đăng nhập</h1>
        <p style={s.subtitle}>Currency Exchange Platform</p>

        {successMessage && (
          <div style={s.successBox} role="alert">
            {successMessage}
          </div>
        )}

        <form onSubmit={(e) => void handleSubmit(e)} noValidate>
          <div style={s.fieldGroup}>
            <label htmlFor="email" style={s.label}>
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={s.input}
              placeholder="you@example.com"
              autoComplete="email"
              required
              disabled={loading}
              aria-required="true"
            />
          </div>

          <div style={s.fieldGroup}>
            <label htmlFor="password" style={s.label}>
              Mật khẩu
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={s.input}
              placeholder="••••••••"
              autoComplete="current-password"
              required
              disabled={loading}
              aria-required="true"
            />
          </div>

          {error && (
            <div style={s.errorBox} role="alert" aria-live="polite">
              {error}
            </div>
          )}

          <button
            type="submit"
            style={loading ? { ...s.submitButton, ...s.submitButtonDisabled } : s.submitButton}
            disabled={loading || !email || !password}
          >
            {loading ? 'Đang đăng nhập...' : 'Đăng nhập'}
          </button>
        </form>

        <div style={s.links}>
          <Link to="/forgot-password" style={s.link}>
            Quên mật khẩu?
          </Link>
          <span style={s.linkSeparator}>·</span>
          <Link to="/register" style={s.link}>
            Tạo tài khoản mới
          </Link>
        </div>
      </div>
    </div>
  )
}

/**
 * Maps Cognito error codes to user-friendly Vietnamese messages.
 */
function mapCognitoError(err: unknown): string {
  if (err instanceof Error) {
    const name = err.name
    const message = err.message

    if (name === 'NotAuthorizedException') {
      if (message.toLowerCase().includes('locked') || message.toLowerCase().includes('attempts')) {
        return 'Tài khoản bị khóa tạm thời do nhập sai mật khẩu quá nhiều lần. Vui lòng thử lại sau 15 phút.'
      }
      return 'Email hoặc mật khẩu không đúng.'
    }
    if (name === 'UserNotFoundException') {
      return 'Tài khoản không tồn tại. Vui lòng kiểm tra lại email.'
    }
    if (name === 'UserNotConfirmedException') {
      return 'Tài khoản chưa được xác thực. Vui lòng kiểm tra email để lấy mã OTP.'
    }
    if (name === 'PasswordResetRequiredException') {
      return 'Mật khẩu cần được đặt lại. Vui lòng sử dụng chức năng Quên mật khẩu.'
    }
    if (name === 'TooManyRequestsException') {
      return 'Quá nhiều yêu cầu. Vui lòng thử lại sau.'
    }
    return message || 'Đã xảy ra lỗi. Vui lòng thử lại.'
  }
  return 'Đã xảy ra lỗi không xác định.'
}

export default LoginPage
