/**
 * useTours.ts
 *
 * Custom hook that fetches tour data from the Tour Service API.
 *
 * Design references:
 *   - Requirement 7.1 (Tour_Service retrieves tour info from S3 via Gateway Endpoint)
 *   - Requirement 7.2 (Display tour name, description, image)
 *   - Requirement 7.3 (Redirect to affiliate URL in new tab on click)
 *   - Requirement 7.4 (Show "No tours available" when list is empty)
 *   - design.md §4 (Tour Information — Display Flow)
 *
 * API contract:
 *   GET  {VITE_TOUR_SERVICE_URL}/tours/{currency_code}
 *
 *   200 → { tours: Tour[] }   (empty array when no tours available)
 */

import { useState, useEffect, useCallback } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Tour {
  /** Unique tour identifier */
  id: string
  /** Display name of the tour */
  name: string
  /** Short description of the tour */
  description: string
  /**
   * URL of the tour image.
   * Tour Service returns either a pre-signed S3 URL or a public S3 URL.
   */
  image_url: string
  /** Travelpayouts affiliate redirect URL */
  affiliate_url: string
  /** ISO 4217 currency code associated with this tour (e.g. "USD") */
  currency_code: string
  /** Country name associated with this tour */
  country: string
}

export type ToursStatus =
  | 'idle'
  | 'loading'
  | 'success'
  | 'error'

export interface UseToursResult {
  tours: Tour[]
  status: ToursStatus
  errorMessage: string | null
  /** Re-fetch tour data on demand */
  refetch: () => void
}

// ── Constants ─────────────────────────────────────────────────────────────────

const TOUR_SERVICE_URL =
  (import.meta as unknown as { env: Record<string, string> }).env
    ?.VITE_TOUR_SERVICE_URL ?? ''

if (!TOUR_SERVICE_URL) {
  console.warn(
    '[Tour Service] VITE_TOUR_SERVICE_URL is not configured. ' +
    'Set it to https://your-alb-domain.com (production) ' +
    'or http://localhost:7000 (development).'
  )
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Fetches tour data for the given currency code from the Tour Service.
 *
 * @param currencyCode  ISO 4217 currency code (e.g. "USD", "EUR").
 *                      Pass null/empty string to skip fetching.
 */
export function useTours(currencyCode: string | null): UseToursResult {
  const [tours, setTours] = useState<Tour[]>([])
  const [status, setStatus] = useState<ToursStatus>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [fetchTrigger, setFetchTrigger] = useState(0)

  const refetch = useCallback(() => {
    setFetchTrigger((n) => n + 1)
  }, [])

  useEffect(() => {
    if (!currencyCode) {
      setStatus('idle')
      setTours([])
      setErrorMessage(null)
      return
    }

    let cancelled = false

    const fetchTours = async () => {
      setStatus('loading')
      setErrorMessage(null)

      try {
        const url = `${TOUR_SERVICE_URL}/tours/${encodeURIComponent(currencyCode)}`

        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        })

        if (cancelled) return

        if (!response.ok) {
          setStatus('error')
          setErrorMessage(
            `Không thể tải dữ liệu tour (HTTP ${response.status}). Vui lòng thử lại.`,
          )
          return
        }

        const json = (await response.json()) as { tours: Tour[] }
        setTours(json.tours ?? [])
        setStatus('success')
      } catch {
        if (!cancelled) {
          setStatus('error')
          setErrorMessage(
            'Không thể kết nối đến dịch vụ tour. Vui lòng kiểm tra kết nối mạng.',
          )
        }
      }
    }

    void fetchTours()

    return () => {
      cancelled = true
    }
  }, [currencyCode, fetchTrigger])

  return { tours, status, errorMessage, refetch }
}
