/**
 * useExchangeRates.ts
 *
 * Custom hook that manages the WebSocket connection to the Streaming Service
 * and exposes live exchange rate data to React components.
 *
 * Responsibilities (tasks 4.3.1 – 4.3.4):
 *   4.3.1  Connect to the Streaming Service via Socket.IO.
 *   4.3.2  Expose the latest rates array so the UI can render them.
 *   4.3.3  Implement client-side reconnection with exponential back-off.
 *   4.3.4  Track and expose connection status: 'connected' | 'reconnecting' | 'stale'.
 *
 * Design references:
 *   - Requirement 2.1 – 2.5 (streaming, heartbeat, reconnection, sticky sessions)
 *   - design.md §1 (Exchange Rate Collection & Streaming)
 *   - streaming-service/src/types.ts (ServerToClientEvents, ExchangeRate, etc.)
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { io, Socket } from 'socket.io-client'

// ── Types (mirrored from streaming-service/src/types.ts) ─────────────────────

export interface ExchangeRate {
  currency: string
  rate: number
  timestamp: number // Unix epoch seconds
}

export interface ExchangeRateUpdate {
  rates: ExchangeRate[]
  updatedAt: number // Unix epoch milliseconds
  isStale: boolean
}

/**
 * Connection status values exposed to the UI (task 4.3.4).
 *
 * - 'connected'    — WebSocket is open and receiving fresh data.
 * - 'reconnecting' — Socket.IO is attempting to reconnect after a drop.
 * - 'stale'        — Connected but the server has flagged data as potentially
 *                    outdated (Exchange Rate Cache unavailable on the server).
 */
export type ConnectionStatus = 'connected' | 'reconnecting' | 'stale'

export interface UseExchangeRatesResult {
  /** Latest exchange rates keyed by currency code (e.g. "USD", "EUR"). */
  rates: Map<string, ExchangeRate>
  /** Timestamp (ms) of the last successful rate update from the server. */
  lastUpdatedAt: number | null
  /** Current WebSocket connection status. */
  connectionStatus: ConnectionStatus
  /** Whether the hook has received at least one rate update. */
  hasData: boolean
}

// ── Constants ─────────────────────────────────────────────────────────────────

/**
 * Stable client ID persisted in sessionStorage so the server can detect
 * reconnections within the same browser session (server.ts §reconnection tracking).
 * A new ID is generated each time the browser tab is opened.
 */
function getOrCreateClientId(): string {
  const KEY = 'cep_ws_client_id'
  let id = sessionStorage.getItem(KEY)
  if (!id) {
    id = crypto.randomUUID()
    sessionStorage.setItem(KEY, id)
  }
  return id
}

/**
 * Streaming Service URL.
 * In production this is the ALB path routed to the Streaming Service.
 * Falls back to localhost for local development.
 */
const STREAMING_URL =
  (import.meta as unknown as { env: Record<string, string> }).env
    ?.VITE_STREAMING_SERVICE_URL ?? 'http://localhost:3001'

if (!import.meta.env.VITE_STREAMING_SERVICE_URL) {
  console.warn(
    '[Streaming Service] VITE_STREAMING_SERVICE_URL is not configured. ' +
    'Using fallback: http://localhost:3001. ' +
    'Set it to https://your-alb-domain.com/stream (production).'
  )
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Connects to the Streaming Service WebSocket and returns live exchange rate data.
 *
 * The socket is created once on mount and cleaned up on unmount.
 * Socket.IO's built-in reconnection handles transient network failures
 * (task 4.3.3); the hook surfaces the reconnecting state to the UI (task 4.3.4).
 *
 * @param currencies  Optional list of currency codes to subscribe to.
 *                    Pass an empty array (default) to receive all currencies.
 */
export function useExchangeRates(currencies: string[] = []): UseExchangeRatesResult {
  const [rates, setRates] = useState<Map<string, ExchangeRate>>(new Map())
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('reconnecting')
  const [hasData, setHasData] = useState(false)

  // Keep a stable ref to the currencies list so the effect doesn't re-run
  // every render when the caller passes an inline array literal.
  const currenciesRef = useRef<string[]>(currencies)
  useEffect(() => {
    currenciesRef.current = currencies
  }, [currencies])

  // Stable ref to the socket so event handlers can access it without
  // being recreated on every render.
  const socketRef = useRef<Socket | null>(null)

  const handleRateUpdate = useCallback((data: ExchangeRateUpdate) => {
    setRates((prev) => {
      const next = new Map(prev)
      for (const rate of data.rates) {
        next.set(rate.currency, rate)
      }
      return next
    })
    setLastUpdatedAt(data.updatedAt)
    setHasData(true)

    // If the server flags the data as stale, reflect that in the UI status
    // only when we are currently in 'connected' state (don't override
    // 'reconnecting' which is a more severe condition).
    if (data.isStale) {
      setConnectionStatus((prev) => (prev === 'connected' ? 'stale' : prev))
    } else {
      // Fresh data received — clear any stale flag.
      setConnectionStatus((prev) => (prev === 'stale' ? 'connected' : prev))
    }
  }, [])

  useEffect(() => {
    const clientId = getOrCreateClientId()

    // ── Create socket (task 4.3.1) ──────────────────────────────────────────
    //
    // Socket.IO reconnection is enabled by default.
    // reconnectionDelay / reconnectionDelayMax implement exponential back-off
    // (task 4.3.3): starts at 1s, doubles each attempt, caps at 10s.
    const socket: Socket = io(STREAMING_URL, {
      path: '/stream/socket.io',
      auth: { clientId },
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 10_000,
      randomizationFactor: 0.3,
    })

    socketRef.current = socket

    // ── Connection events (task 4.3.4) ──────────────────────────────────────

    socket.on('connect', () => {
      // Subscribe to requested currencies immediately after (re)connect.
      // The server will push filtered rates right away (server.ts §subscribe).
      if (currenciesRef.current.length > 0) {
        socket.emit('subscribe', currenciesRef.current)
      }
    })

    socket.on('disconnect', (reason) => {
      // 'io server disconnect' means the server intentionally closed the
      // connection (e.g. heartbeat timeout). Socket.IO will NOT auto-reconnect
      // in this case unless we call socket.connect() manually.
      if (reason === 'io server disconnect') {
        socket.connect()
      }
      setConnectionStatus('reconnecting')
    })

    socket.on('connect_error', () => {
      setConnectionStatus('reconnecting')
    })

    // ── Server-pushed connection status (task 4.3.4) ────────────────────────
    //
    // The server emits `connection_status` immediately after connect/reconnect
    // (server.ts §connection_status). We use it to distinguish 'connected' from
    // 'reconnected' — both map to 'connected' in our UI status model.
    socket.on('connection_status', (payload) => {
      if (payload.status === 'connected' || payload.status === 'reconnected') {
        setConnectionStatus('connected')
      } else if (payload.status === 'stale') {
        setConnectionStatus('stale')
      }
    })

    // ── Rate updates (task 4.3.2) ───────────────────────────────────────────
    socket.on('rateUpdate', handleRateUpdate)

    // ── Server-pushed stale signal (task 4.3.4) ─────────────────────────────
    socket.on('rates:stale', () => {
      setConnectionStatus('stale')
    })

    // ── Cleanup on unmount ──────────────────────────────────────────────────
    return () => {
      socket.off('connect')
      socket.off('disconnect')
      socket.off('connect_error')
      socket.off('connection_status')
      socket.off('rateUpdate')
      socket.off('rates:stale')
      socket.disconnect()
      socketRef.current = null
    }
  }, [handleRateUpdate]) // Only re-run if handleRateUpdate identity changes (it won't)

  return { rates, lastUpdatedAt, connectionStatus, hasData }
}
