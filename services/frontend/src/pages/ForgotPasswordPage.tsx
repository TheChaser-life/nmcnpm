/**
 * ForgotPasswordPage.tsx
 *
 * 3-step forgot password flow:
 *   Step 1 — Enter email → call resetPassword() → Cognito sends OTP
 *   Step 2 — Enter OTP code received via email
 *   Step 3 — Enter new password + confirm → call confirmResetPassword() → redirect to /login
 *
 * Password validation matches the same Cognito policy as registration.
 */

import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { resetPassword, confirmResetPassword } from 'aws-amplify/auth'
import { formStyles as s } from './formStyles'

type Step = 'email' | 'otp' | 'newPassword'

// ── Validation ────────────────────────────────────────────────────────────────

function validatePassword(password: string): string | undefined {
  if (!password) return 'Mật khẩu là bắt buộc.'
  if (password.length < 8) return 'Mật khẩu phải có ít nhất 8 ký tự.'
  if (!/[A-Z]/.test(password)) return 'Mật khẩu phải có ít nhất 1 chữ hoa.'
  if (!/[a-z]/.test(password)) return 'Mật khẩu phải có ít nhất 1 chữ thường.'
  if (!/[0-9]/.test(password)) return 'Mật khẩu phải có ít nhất 1 chữ số.'
  if (!/[^A-Za-z0-9]/.test(password)) return 'Mật khẩu phải có ít nhất 1 ký tự đặc biệt.'
  return undefined
}

// ── Component ─────────────────────────────────────────────────────────────────

function ForgotPasswordPage() {
  const navigate = useNavigate()

  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<string | undefined>()
  const [confirmPasswordError, setConfirmPasswordError] = useState<string | undefined>()

  // ── Step 1: Request OTP ─────────────────────────────────────────────────────

  const handleRequestOtp = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)

    if (!email.trim()) {
      setError('Vui lòng nhập email.')
      return
    }

    setLoading(true)
    try {
      await resetPassword({ username: email.trim() })
      setStep('otp')
    } catch (err: unknown) {
      setError(mapCognitoError(err))
    } finally {
      setLoading(false)
    }
  }

  // ── Step 2: Advance to new password step ────────────────────────────────────

  const handleOtpNext = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)

    if (!otp.trim()) {
      setError('Vui lòng nhập mã OTP.')
      return
    }

    setStep('newPassword')
  }

  // ── Step 3: Confirm new password ────────────────────────────────────────────

  const handleConfirmReset = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)

    const passErr = validatePassword(newPassword)
    setPasswordError(passErr)

    let confirmErr: string | undefined
    if (!confirmPassword) {
      confirmErr = 'Vui lòng xác nhận mật khẩu.'
    } else if (newPassword !== confirmPassword) {
      confirmErr = 'Mật khẩu xác nhận không khớp.'
    }
    setConfirmPasswordError(confirmErr)

    if (passErr || confirmErr) return

    setLoading(true)
    try {
      await confirmResetPassword({
        username: email.trim(),
        confirmationCode: otp.trim(),
        newPassword,
      })
      navigate('/login', {
        state: { message: 'Đặt lại mật khẩu thành công! Vui lòng đăng nhập.' },
      })
    } catch (err: unknown) {
      setError(mapCognitoError(err))
    } finally {
      setLoading(false)
    }
  }

  // ── Step indicator ──────────────────────────────────────────────────────────

  const stepIndex = step === 'email' ? 0 : step === 'otp' ? 1 : 2

  const StepIndicator = () => (
    <div style={s.stepIndicator} aria-label={`Bước ${stepIndex + 1} / 3`}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={i <= stepIndex ? { ...s.stepDot, ...s.stepDotActive } : s.stepDot}
        />
      ))}
    </div>
  )

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div style={s.pageContainer}>
      <div style={s.card}>
        <h1 style={s.title}>Quên mật khẩu</h1>
        <p style={s.subtitle}>
          {step === 'email' && 'Nhập email để nhận mã OTP'}
          {step === 'otp' && `Nhập mã OTP đã gửi đến ${email}`}
          {step === 'newPassword' && 'Đặt mật khẩu mới'}
        </p>

        <StepIndicator />

        {/* ── Step 1: Email ── */}
        {step === 'email' && (
          <form onSubmit={(e) => void handleRequestOtp(e)} noValidate>
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

            {error && (
              <div style={s.errorBox} role="alert" aria-live="polite">
                {error}
              </div>
            )}

            <button
              type="submit"
              style={loading ? { ...s.submitButton, ...s.submitButtonDisabled } : s.submitButton}
              disabled={loading || !email.trim()}
            >
              {loading ? 'Đang gửi...' : 'Gửi mã OTP'}
            </button>
          </form>
        )}

        {/* ── Step 2: OTP ── */}
        {step === 'otp' && (
          <form onSubmit={handleOtpNext} noValidate>
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

            {error && (
              <div style={s.errorBox} role="alert" aria-live="polite">
                {error}
              </div>
            )}

            <button
              type="submit"
              style={!otp.trim() ? { ...s.submitButton, ...s.submitButtonDisabled } : s.submitButton}
              disabled={!otp.trim()}
            >
              Tiếp theo
            </button>

            <div style={{ ...s.links, marginTop: '12px' }}>
              <button
                type="button"
                style={{ background: 'none', border: 'none', color: '#4361ee', cursor: 'pointer', fontSize: '0.875rem' }}
                onClick={() => { setStep('email'); setError(null) }}
              >
                ← Quay lại
              </button>
            </div>
          </form>
        )}

        {/* ── Step 3: New password ── */}
        {step === 'newPassword' && (
          <form onSubmit={(e) => void handleConfirmReset(e)} noValidate>
            <div style={s.fieldGroup}>
              <label htmlFor="newPassword" style={s.label}>
                Mật khẩu mới
              </label>
              <input
                id="newPassword"
                type="password"
                value={newPassword}
                onChange={(e) => {
                  setNewPassword(e.target.value)
                  setPasswordError(undefined)
                }}
                style={passwordError ? { ...s.input, ...s.inputError } : s.input}
                placeholder="••••••••"
                autoComplete="new-password"
                required
                disabled={loading}
                aria-required="true"
                aria-describedby="new-password-hint"
              />
              <span id="new-password-hint" style={s.passwordHint}>
                Tối thiểu 8 ký tự, bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt.
              </span>
              {passwordError && (
                <span style={s.fieldError} role="alert">
                  {passwordError}
                </span>
              )}
            </div>

            <div style={s.fieldGroup}>
              <label htmlFor="confirmPassword" style={s.label}>
                Xác nhận mật khẩu mới
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value)
                  setConfirmPasswordError(undefined)
                }}
                style={confirmPasswordError ? { ...s.input, ...s.inputError } : s.input}
                placeholder="••••••••"
                autoComplete="new-password"
                required
                disabled={loading}
                aria-required="true"
              />
              {confirmPasswordError && (
                <span style={s.fieldError} role="alert">
                  {confirmPasswordError}
                </span>
              )}
            </div>

            {error && (
              <div style={s.errorBox} role="alert" aria-live="polite">
                {error}
              </div>
            )}

            <button
              type="submit"
              style={loading ? { ...s.submitButton, ...s.submitButtonDisabled } : s.submitButton}
              disabled={loading}
            >
              {loading ? 'Đang đặt lại...' : 'Đặt lại mật khẩu'}
            </button>

            <div style={{ ...s.links, marginTop: '12px' }}>
              <button
                type="button"
                style={{ background: 'none', border: 'none', color: '#4361ee', cursor: 'pointer', fontSize: '0.875rem' }}
                onClick={() => { setStep('otp'); setError(null) }}
              >
                ← Quay lại
              </button>
            </div>
          </form>
        )}

        <div style={{ ...s.links, marginTop: '20px' }}>
          <Link to="/login" style={s.link}>
            Quay lại đăng nhập
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

    if (name === 'UserNotFoundException') {
      return 'Email không tồn tại trong hệ thống.'
    }
    if (name === 'CodeMismatchException') {
      return 'Mã OTP không đúng. Vui lòng kiểm tra lại.'
    }
    if (name === 'ExpiredCodeException') {
      return 'Mã OTP đã hết hạn. Vui lòng yêu cầu mã mới.'
    }
    if (name === 'InvalidPasswordException') {
      return 'Mật khẩu mới không đáp ứng yêu cầu bảo mật.'
    }
    if (name === 'LimitExceededException') {
      return 'Đã vượt quá giới hạn yêu cầu. Vui lòng thử lại sau.'
    }
    if (name === 'TooManyRequestsException') {
      return 'Quá nhiều yêu cầu. Vui lòng thử lại sau.'
    }
    if (name === 'NotAuthorizedException') {
      return 'Không được phép thực hiện thao tác này.'
    }
    return message || 'Đã xảy ra lỗi. Vui lòng thử lại.'
  }
  return 'Đã xảy ra lỗi không xác định.'
}

export default ForgotPasswordPage