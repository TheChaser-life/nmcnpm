/**
 * RegisterPage.tsx
 *
 * Registration form with client-side validation matching Cognito's password policy.
 * After successful signUp, shows an inline OTP confirmation step.
 *
 * Password policy (mirrors Cognito config):
 *   - Minimum 8 characters
 *   - At least 1 uppercase letter
 *   - At least 1 lowercase letter
 *   - At least 1 digit
 *   - At least 1 symbol
 */

import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { signUp, confirmSignUp } from 'aws-amplify/auth'
import { formStyles as s } from './formStyles'

// ── Validation ────────────────────────────────────────────────────────────────

interface ValidationErrors {
  email?: string
  password?: string
  confirmPassword?: string
}

function validateEmail(email: string): string | undefined {
  if (!email) return 'Email là bắt buộc.'
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(email)) return 'Email không hợp lệ.'
  return undefined
}

function validatePassword(password: string): string | undefined {
  if (!password) return 'Mật khẩu là bắt buộc.'
  if (password.length < 8) return 'Mật khẩu phải có ít nhất 8 ký tự.'
  if (!/[A-Z]/.test(password)) return 'Mật khẩu phải có ít nhất 1 chữ hoa.'
  if (!/[a-z]/.test(password)) return 'Mật khẩu phải có ít nhất 1 chữ thường.'
  if (!/[0-9]/.test(password)) return 'Mật khẩu phải có ít nhất 1 chữ số.'
  if (!/[^A-Za-z0-9]/.test(password)) return 'Mật khẩu phải có ít nhất 1 ký tự đặc biệt.'
  return undefined
}

function validate(
  email: string,
  password: string,
  confirmPassword: string,
): ValidationErrors {
  const errors: ValidationErrors = {}
  const emailErr = validateEmail(email)
  if (emailErr) errors.email = emailErr
  const passErr = validatePassword(password)
  if (passErr) errors.password = passErr
  if (!confirmPassword) {
    errors.confirmPassword = 'Vui lòng xác nhận mật khẩu.'
  } else if (password !== confirmPassword) {
    errors.confirmPassword = 'Mật khẩu xác nhận không khớp.'
  }
  return errors
}

// ── Component ─────────────────────────────────────────────────────────────────

interface LocationState {
  email?: string
  needsConfirmation?: boolean
}

function RegisterPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as LocationState | null

  // Step 1: registration form | Step 2: OTP confirmation
  const [step, setStep] = useState<'register' | 'confirm'>(
    state?.needsConfirmation ? 'confirm' : 'register',
  )

  // Registration fields
  const [email, setEmail] = useState(state?.email ?? '')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<ValidationErrors>({})

  // OTP confirmation
  const [otp, setOtp] = useState('')
  const [otpError, setOtpError] = useState<string | null>(null)

  const [loading, setLoading] = useState(false)
  const [globalError, setGlobalError] = useState<string | null>(null)

  // ── Step 1: Register ────────────────────────────────────────────────────────

  const handleRegister = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setGlobalError(null)

    const errors = validate(email, password, confirmPassword)
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) return

    setLoading(true)
    try {
      await signUp({
        username: email,
        password,
        options: {
          userAttributes: {
            email,
          },
        },
      })
      // Cognito sends OTP to email — move to confirmation step
      setStep('confirm')
    } catch (err: unknown) {
      setGlobalError(mapCognitoError(err))
    } finally {
      setLoading(false)
    }
  }

  // ── Step 2: Confirm OTP ─────────────────────────────────────────────────────

  const handleConfirm = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setOtpError(null)

    if (!otp.trim()) {
      setOtpError('Vui lòng nhập mã OTP.')
      return
    }

    setLoading(true)
    try {
      await confirmSignUp({ username: email, confirmationCode: otp.trim() })
      // Registration complete — redirect to login
      navigate('/login', {
        state: { message: 'Đăng ký thành công! Vui lòng đăng nhập.' },
      })
    } catch (err: unknown) {
      setOtpError(mapCognitoError(err))
    } finally {
      setLoading(false)
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  if (step === 'confirm') {
    return (
      <div style={s.pageContainer}>
        <div style={s.card}>
          <h1 style={s.title}>Xác thực email</h1>
          <p style={s.subtitle}>
            Mã OTP đã được gửi đến <strong>{email}</strong>
          </p>

          <form onSubmit={(e) => void handleConfirm(e)} noValidate>
            <div style={s.fieldGroup}>
              <label htmlFor="otp" style={s.label}>
                Mã OTP
              </label>
              <input
                id="otp"
                type="text"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                style={s.input}
                placeholder="Nhập mã 6 chữ số"
                autoComplete="one-time-code"
                inputMode="numeric"
                maxLength={6}
                required
                disabled={loading}
                aria-required="true"
              />
            </div>

            {otpError && (
              <div style={s.errorBox} role="alert" aria-live="polite">
                {otpError}
              </div>
            )}

            <button
              type="submit"
              style={loading ? { ...s.submitButton, ...s.submitButtonDisabled } : s.submitButton}
              disabled={loading || !otp.trim()}
            >
              {loading ? 'Đang xác thực...' : 'Xác thực'}
            </button>
          </form>

          <div style={s.links}>
            <button
              type="button"
              style={{ background: 'none', border: 'none', color: '#4361ee', cursor: 'pointer', fontSize: '0.875rem' }}
              onClick={() => setStep('register')}
            >
              ← Quay lại
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={s.pageContainer}>
      <div style={s.card}>
        <h1 style={s.title}>Tạo tài khoản</h1>
        <p style={s.subtitle}>Currency Exchange Platform</p>

        <form onSubmit={(e) => void handleRegister(e)} noValidate>
          <div style={s.fieldGroup}>
            <label htmlFor="email" style={s.label}>
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
                setFieldErrors((prev) => ({ ...prev, email: undefined }))
              }}
              style={fieldErrors.email ? { ...s.input, ...s.inputError } : s.input}
              placeholder="you@example.com"
              autoComplete="email"
              required
              disabled={loading}
              aria-required="true"
              aria-describedby={fieldErrors.email ? 'email-error' : undefined}
            />
            {fieldErrors.email && (
              <span id="email-error" style={s.fieldError} role="alert">
                {fieldErrors.email}
              </span>
            )}
          </div>

          <div style={s.fieldGroup}>
            <label htmlFor="password" style={s.label}>
              Mật khẩu
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value)
                setFieldErrors((prev) => ({ ...prev, password: undefined }))
              }}
              style={fieldErrors.password ? { ...s.input, ...s.inputError } : s.input}
              placeholder="••••••••"
              autoComplete="new-password"
              required
              disabled={loading}
              aria-required="true"
              aria-describedby="password-hint"
            />
            <span id="password-hint" style={s.passwordHint}>
              Tối thiểu 8 ký tự, bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt.
            </span>
            {fieldErrors.password && (
              <span style={s.fieldError} role="alert">
                {fieldErrors.password}
              </span>
            )}
          </div>

          <div style={s.fieldGroup}>
            <label htmlFor="confirmPassword" style={s.label}>
              Xác nhận mật khẩu
            </label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value)
                setFieldErrors((prev) => ({ ...prev, confirmPassword: undefined }))
              }}
              style={fieldErrors.confirmPassword ? { ...s.input, ...s.inputError } : s.input}
              placeholder="••••••••"
              autoComplete="new-password"
              required
              disabled={loading}
              aria-required="true"
            />
            {fieldErrors.confirmPassword && (
              <span style={s.fieldError} role="alert">
                {fieldErrors.confirmPassword}
              </span>
            )}
          </div>

          {globalError && (
            <div style={s.errorBox} role="alert" aria-live="polite">
              {globalError}
            </div>
          )}

          <button
            type="submit"
            style={loading ? { ...s.submitButton, ...s.submitButtonDisabled } : s.submitButton}
            disabled={loading}
          >
            {loading ? 'Đang đăng ký...' : 'Đăng ký'}
          </button>
        </form>

        <div style={s.links}>
          <span style={{ color: '#888', fontSize: '0.875rem' }}>Đã có tài khoản?</span>
          <Link to="/login" style={s.link}>
            Đăng nhập
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

    if (name === 'UsernameExistsException') {
      return 'Email này đã được đăng ký. Vui lòng đăng nhập hoặc dùng email khác.'
    }
    if (name === 'InvalidPasswordException') {
      return 'Mật khẩu không đáp ứng yêu cầu bảo mật. Vui lòng kiểm tra lại.'
    }
    if (name === 'InvalidParameterException') {
      return 'Thông tin không hợp lệ. Vui lòng kiểm tra lại.'
    }
    if (name === 'CodeMismatchException') {
      return 'Mã OTP không đúng. Vui lòng kiểm tra lại.'
    }
    if (name === 'ExpiredCodeException') {
      return 'Mã OTP đã hết hạn. Vui lòng yêu cầu mã mới.'
    }
    if (name === 'TooManyRequestsException') {
      return 'Quá nhiều yêu cầu. Vui lòng thử lại sau.'
    }
    if (name === 'LimitExceededException') {
      return 'Đã vượt quá giới hạn yêu cầu. Vui lòng thử lại sau.'
    }
    return message || 'Đã xảy ra lỗi. Vui lòng thử lại.'
  }
  return 'Đã xảy ra lỗi không xác định.'
}

export default RegisterPage
