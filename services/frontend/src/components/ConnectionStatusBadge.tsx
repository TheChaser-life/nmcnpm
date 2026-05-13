/**
 * ConnectionStatusBadge.tsx
 *
 * Displays the current WebSocket connection status to the user (task 4.3.4).
 *
 * Three states:
 *   connected    — green dot, "Đang kết nối"
 *   reconnecting — yellow pulsing dot, "Đang kết nối lại…"
 *   stale        — orange dot, "Dữ liệu có thể chậm"
 *
 * Design reference: Requirement 2.4 (reconnect without re-auth),
 * design.md §1 (streaming), types.ts ConnectionStatus.
 */

import { useEffect, useRef } from 'react'
import type { ConnectionStatus } from '../hooks/useExchangeRates'

// ── Pulse animation ───────────────────────────────────────────────────────────

const PULSE_STYLE_ID = 'cep-pulse-styles'

function injectPulseStyles(): void {
  if (document.getElementById(PULSE_STYLE_ID)) return
  const style = document.createElement('style')
  style.id = PULSE_STYLE_ID
  style.textContent = `
    @keyframes cep-pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50%       { opacity: 0.4; transform: scale(0.85); }
    }
    .cep-dot-pulse { animation: cep-pulse 1.2s ease-in-out infinite; }
  `
  document.head.appendChild(style)
}

// ── Config per status ─────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  ConnectionStatus,
  { color: string; bg: string; border: string; dot: string; label: string; pulse: boolean }
> = {
  connected: {
    color: '#166534',
    bg: '#dcfce7',
    border: '#86efac',
    dot: '#22c55e',
    label: 'Đang kết nối',
    pulse: false,
  },
  reconnecting: {
    color: '#854d0e',
    bg: '#fef9c3',
    border: '#fde047',
    dot: '#eab308',
    label: 'Đang kết nối lại…',
    pulse: true,
  },
  stale: {
    color: '#9a3412',
    bg: '#ffedd5',
    border: '#fdba74',
    dot: '#f97316',
    label: 'Dữ liệu có thể chậm',
    pulse: false,
  },
}

// ── Component ─────────────────────────────────────────────────────────────────

interface ConnectionStatusBadgeProps {
  status: ConnectionStatus
}

export function ConnectionStatusBadge({ status }: ConnectionStatusBadgeProps) {
  const injectedRef = useRef(false)

  useEffect(() => {
    if (!injectedRef.current) {
      injectPulseStyles()
      injectedRef.current = true
    }
  }, [])

  const cfg = STATUS_CONFIG[status]

  return (
    <span
      role="status"
      aria-live="polite"
      aria-label={`Trạng thái kết nối: ${cfg.label}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '4px 12px',
        borderRadius: '20px',
        fontSize: '0.8rem',
        fontWeight: 600,
        color: cfg.color,
        backgroundColor: cfg.bg,
        border: `1px solid ${cfg.border}`,
        userSelect: 'none',
        transition: 'background-color 0.3s, color 0.3s',
      }}
    >
      <span
        className={cfg.pulse ? 'cep-dot-pulse' : undefined}
        style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          backgroundColor: cfg.dot,
          flexShrink: 0,
          display: 'inline-block',
        }}
        aria-hidden="true"
      />
      {cfg.label}
    </span>
  )
}

export default ConnectionStatusBadge
