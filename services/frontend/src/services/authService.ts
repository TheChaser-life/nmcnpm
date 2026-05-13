/**
 * authService.ts
 *
 * Thin wrapper around AWS Amplify v6 auth functions.
 *
 * Token storage:
 *   Amplify v6 stores tokens in localStorage by default via
 *   CognitoUserPoolsTokenProvider. This is acceptable for this SPA because
 *   there is no backend proxy available to set httpOnly cookies.
 *
 * Token refresh:
 *   Amplify v6 automatically refreshes the access token when calling
 *   fetchAuthSession({ forceRefresh: false }) if the token is expired.
 *   The useTokenRefresh hook proactively refreshes 60 seconds before expiry
 *   to avoid any gap in authenticated API calls.
 */

import {
  signIn,
  signOut,
  signUp,
  confirmSignUp,
  resetPassword,
  confirmResetPassword,
  fetchAuthSession,
  getCurrentUser,
  type SignInInput,
  type SignUpInput,
  type ConfirmSignUpInput,
  type ResetPasswordInput,
  type ConfirmResetPasswordInput,
} from 'aws-amplify/auth'

// ── Re-export Amplify auth functions for use in components ────────────────────

export { signIn, signUp, confirmSignUp, resetPassword, confirmResetPassword }
export type {
  SignInInput,
  SignUpInput,
  ConfirmSignUpInput,
  ResetPasswordInput,
  ConfirmResetPasswordInput,
}

// ── Token helpers ─────────────────────────────────────────────────────────────

/**
 * Returns the raw access token string, or null if not authenticated.
 */
export async function getAccessToken(forceRefresh = false): Promise<string | null> {
  try {
    const session = await fetchAuthSession({ forceRefresh })
    return session.tokens?.accessToken?.toString() ?? null
  } catch {
    return null
  }
}

/**
 * Returns the raw ID token string, or null if not authenticated.
 * The ID token contains the custom:premium claim.
 */
export async function getIdToken(forceRefresh = false): Promise<string | null> {
  try {
    const session = await fetchAuthSession({ forceRefresh })
    return session.tokens?.idToken?.toString() ?? null
  } catch {
    return null
  }
}

/**
 * Returns true if the current session has valid tokens.
 */
export async function isAuthenticated(): Promise<boolean> {
  try {
    const session = await fetchAuthSession({ forceRefresh: false })
    return (
      session.tokens?.accessToken !== undefined &&
      session.tokens?.idToken !== undefined
    )
  } catch {
    return false
  }
}

/**
 * Decodes the ID token payload and checks the custom:premium claim.
 * Cognito stores custom attributes with the "custom:" prefix in the JWT payload.
 *
 * Note: The custom:premium attribute is marked as developer_only_attribute=true
 * in Terraform, which means it appears in the ID token payload as-is.
 */
export async function isPremiumUser(forceRefresh = false): Promise<boolean> {
  try {
    const session = await fetchAuthSession({ forceRefresh })
    const idToken = session.tokens?.idToken

    if (!idToken) return false

    // Amplify v6 exposes the decoded payload directly on the JWT object
    const payload = idToken.payload as Record<string, unknown>
    return payload['custom:premium'] === true || payload['custom:premium'] === 'true'
  } catch {
    return false
  }
}

/**
 * Returns the current authenticated user's email, or null if not authenticated.
 */
export async function getCurrentUserEmail(): Promise<string | null> {
  try {
    const session = await fetchAuthSession({ forceRefresh: false })
    const idToken = session.tokens?.idToken

    if (!idToken) return null

    const payload = idToken.payload as Record<string, unknown>
    return (payload['email'] as string) ?? null
  } catch {
    return null
  }
}

/**
 * Returns the current authenticated user's Cognito username (sub), or null.
 */
export async function getCurrentUserSub(): Promise<string | null> {
  try {
    const user = await getCurrentUser()
    return user.userId ?? null
  } catch {
    return null
  }
}

/**
 * Signs out the current user.
 * Amplify v6 signOut() revokes the refresh token on the Cognito side
 * and clears all tokens from localStorage.
 */
export async function logout(): Promise<void> {
  await signOut()
}

/**
 * Forces a token refresh and returns the new access token.
 * Called by useTokenRefresh hook 60 seconds before expiry.
 */
export async function forceTokenRefresh(): Promise<string | null> {
  try {
    const session = await fetchAuthSession({ forceRefresh: true })
    return session.tokens?.accessToken?.toString() ?? null
  } catch {
    return null
  }
}

// ── JWT utility ───────────────────────────────────────────────────────────────

/**
 * Decodes a JWT token and returns the payload.
 * Does NOT verify the signature — use only for reading claims client-side.
 */
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null

    const payload = parts[1]
    // Base64url decode
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const jsonStr = atob(base64)
    return JSON.parse(jsonStr) as Record<string, unknown>
  } catch {
    return null
  }
}

/**
 * Returns the expiry timestamp (Unix seconds) from a JWT token, or null.
 */
export function getTokenExpiry(token: string): number | null {
  const payload = decodeJwtPayload(token)
  if (!payload) return null

  const exp = payload['exp']
  if (typeof exp !== 'number') return null

  return exp
}
