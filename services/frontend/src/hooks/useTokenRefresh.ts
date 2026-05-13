/**
 * useTokenRefresh.ts
 *
 * Proactively refreshes the Cognito access token 60 seconds before it expires.
 *
 * How Amplify v6 handles token refresh:
 *   - Calling fetchAuthSession({ forceRefresh: false }) automatically refreshes
 *     the access token if it is expired, using the stored refresh token.
 *   - This hook goes one step further: it schedules a proactive refresh
 *     60 seconds BEFORE the access token expires, so there is no gap in
 *     authenticated API calls.
 *
 * Token validity (from Cognito config):
 *   - Access token: 1 hour
 *   - ID token: 1 hour
 *   - Refresh token: 30 days
 */

import { useEffect, useRef } from 'react'
import { fetchAuthSession } from 'aws-amplify/auth'
import { getAccessToken, getTokenExpiry } from '../services/authService'

const REFRESH_BUFFER_SECONDS = 60 // refresh 60s before expiry

/**
 * Schedules a proactive token refresh for authenticated users.
 *
 * @param isAuthenticated - Whether the user is currently authenticated
 * @param onRefreshed - Callback invoked after a successful refresh (to update auth state)
 */
export function useTokenRefresh(
  isAuthenticated: boolean,
  onRefreshed: () => Promise<void>,
): void {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!isAuthenticated) {
      // Clear any pending refresh when user logs out
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
      return
    }

    let cancelled = false

    async function scheduleRefresh() {
      try {
        const accessToken = await getAccessToken()
        if (!accessToken || cancelled) return

        const expiry = getTokenExpiry(accessToken)
        if (expiry === null) return

        const nowSeconds = Math.floor(Date.now() / 1000)
        const secondsUntilExpiry = expiry - nowSeconds
        const secondsUntilRefresh = secondsUntilExpiry - REFRESH_BUFFER_SECONDS

        if (secondsUntilRefresh <= 0) {
          // Token is already near expiry — refresh immediately
          await performRefresh()
          return
        }

        // Schedule refresh before expiry
        timeoutRef.current = setTimeout(() => {
          void performRefresh()
        }, secondsUntilRefresh * 1000)
      } catch {
        // Silently ignore scheduling errors — Amplify will handle expired tokens
        // on the next API call via fetchAuthSession({ forceRefresh: false })
      }
    }

    async function performRefresh() {
      if (cancelled) return

      try {
        // Force a token refresh via Amplify
        await fetchAuthSession({ forceRefresh: true })

        if (!cancelled) {
          // Notify AuthContext so it can update the premium status etc.
          await onRefreshed()

          // Re-schedule for the next expiry cycle
          await scheduleRefresh()
        }
      } catch {
        // Refresh failed (e.g., refresh token expired) — the user will be
        // redirected to /login when they next make an authenticated request
      }
    }

    void scheduleRefresh()

    return () => {
      cancelled = true
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
    }
  }, [isAuthenticated, onRefreshed])
}
