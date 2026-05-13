/**
 * useForecast.ts
 *
 * Custom hook that fetches exchange rate forecast data from the Forecast Service.
 *
 * Design references:
 *   - Requirement 3 (ML Forecasting, premium gate)
 *   - Requirement 9 (Authorization — frontend enforces premium check)
 *   - design.md §2 (Forecast Flow: GET /forecast/{currency_code}, Bearer JWT)
 *
 * API contract:
 *   GET  {VITE_FORECAST_SERVICE_URL}/forecast/{currency_code}
 *   Headers: Authorization: Bearer <access_token>
 *
 *   200 → { currency: string; points: { timestamp: number; rate: number }[] }
 *   401 → redirect to /login
 *   403 → show upgrade prompt (non-premium user)
 *   503 → service unavailable message
 */

import { useState, useEffect, useCallback } from 'react'
import { getIdToken } from '../services/authService'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ForecastPoint {
  /** Unix epoch seconds */
  timestamp: number
  /** Forecasted exchange rate (VND per 1 unit of foreign currency) */
  rate: number
}

export interface ForecastData {
  currency: string
  points: ForecastPoint[]
}

interface ForecastApiPoint {
  timestamp?: unknown
  rate?: unknown
  date?: unknown
  predicted_rate?: unknown
}

interface ForecastApiResponse {
  currency?: unknown
  currency_code?: unknown
  points?: unknown
  forecast?: unknown
}

export type ForecastStatus =
  | 'idle'
  | 'loading'
  | 'success'
  | 'error_unauthorized'   // 401 — session expired
  | 'error_forbidden'      // 403 — not premium
  | 'error_unavailable'    // 503 — SageMaker / service down
  | 'error_generic'        // other errors

export interface UseForecastResult {
  data: ForecastData | null
  status: ForecastStatus
  errorMessage: string | null
  /** Re-fetch forecast data on demand */
  refetch: () => void
}

// ── Constants ─────────────────────────────────────────────────────────────────

const FORECAST_BASE_URL =
  (import.meta as unknown as { env: Record<string, string> }).env
    ?.VITE_FORECAST_SERVICE_URL ?? ''

if (!FORECAST_BASE_URL) {
  console.warn(
    '[Forecast Service] VITE_FORECAST_SERVICE_URL is not configured. ' +
    'Set it to https://your-alb-domain.com (production) ' +
    'or http://localhost:6000 (development).'
  )
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function toTimestampSeconds(value: unknown, fallbackDaysFromNow: number): number {
  const numeric = toNumber(value)
  if (numeric !== null) return numeric > 10_000_000_000 ? Math.floor(numeric / 1000) : numeric

  if (typeof value === 'string' && value.trim() !== '') {
    const parsedMs = Date.parse(value)
    if (Number.isFinite(parsedMs)) return Math.floor(parsedMs / 1000)
  }

  return Math.floor(Date.now() / 1000) + fallbackDaysFromNow * 86_400
}

function normalizeForecastResponse(raw: unknown, fallbackCurrency: string): ForecastData {
  const body = (raw ?? {}) as ForecastApiResponse
  const currency =
    typeof body.currency === 'string'
      ? body.currency
      : typeof body.currency_code === 'string'
        ? body.currency_code
        : fallbackCurrency

  if (Array.isArray(body.points)) {
    const points = (body.points as ForecastApiPoint[])
      .map((point, index) => {
        const rate = toNumber(point?.rate)
        if (rate === null) return null
        return {
          timestamp: toTimestampSeconds(point?.timestamp, index + 1),
          rate,
        }
      })
      .filter((point): point is ForecastPoint => point !== null)

    return { currency, points }
  }

  if (Array.isArray(body.forecast)) {
    const points = (body.forecast as Array<ForecastApiPoint | number>)
      .map((point, index) => {
        if (typeof point === 'number') {
          return {
            timestamp: toTimestampSeconds(undefined, index + 1),
            rate: point,
          }
        }

        const rate = toNumber(point?.predicted_rate ?? point?.rate)
        if (rate === null) return null
        return {
          timestamp: toTimestampSeconds(point?.date ?? point?.timestamp, index + 1),
          rate,
        }
      })
      .filter((point): point is ForecastPoint => point !== null)

    return { currency, points }
  }

  return { currency, points: [] }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Fetches forecast data for the given currency code.
 *
 * @param currencyCode  ISO 4217 currency code (e.g. "USD", "EUR").
 *                      Pass null/empty string to skip fetching.
 * @param enabled       Set to false to prevent fetching (e.g. for non-premium users).
 */
export function useForecast(
  currencyCode: string | null,
  enabled: boolean,
): UseForecastResult {
  const [data, setData] = useState<ForecastData | null>(null)
  const [status, setStatus] = useState<ForecastStatus>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [fetchTrigger, setFetchTrigger] = useState(0)

  const refetch = useCallback(() => {
    setFetchTrigger((n) => n + 1)
  }, [])

  useEffect(() => {
    if (!enabled || !currencyCode) {
      setStatus('idle')
      setData(null)
      setErrorMessage(null)
      return
    }

    let cancelled = false

    const fetchForecast = async () => {
      setStatus('loading')
      setErrorMessage(null)

      try {
        const token = await getIdToken()

        if (!token) {
          if (!cancelled) {
            setStatus('error_unauthorized')
            setErrorMessage('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')
          }
          return
        }

        const url = `${FORECAST_BASE_URL}/forecast/${encodeURIComponent(currencyCode)}`

        const response = await fetch(url, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })

        if (cancelled) return

        if (response.status === 401) {
          setStatus('error_unauthorized')
          setErrorMessage('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')
          return
        }

        if (response.status === 403) {
          setStatus('error_forbidden')
          setErrorMessage('Tính năng dự báo chỉ dành cho người dùng Premium.')
          return
        }

        if (response.status === 503) {
          setStatus('error_unavailable')
          setErrorMessage(
            'Dịch vụ dự báo tạm thời không khả dụng. Vui lòng thử lại sau.',
          )
          return
        }

        if (!response.ok) {
          setStatus('error_generic')
          setErrorMessage(`Lỗi không xác định (HTTP ${response.status}). Vui lòng thử lại.`)
          return
        }

        const json = await response.json()
        setData(normalizeForecastResponse(json, currencyCode))
        setStatus('success')
      } catch {
        if (!cancelled) {
          setStatus('error_generic')
          setErrorMessage('Không thể kết nối đến dịch vụ dự báo. Vui lòng kiểm tra kết nối mạng.')
        }
      }
    }

    void fetchForecast()

    return () => {
      cancelled = true
    }
  }, [currencyCode, enabled, fetchTrigger])

  return { data, status, errorMessage, refetch }
}
