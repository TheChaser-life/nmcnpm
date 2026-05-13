/**
 * Configuration for the Streaming Service.
 *
 * All values are read from environment variables so the same Docker image
 * can be used in local development, staging, and production without rebuilding.
 *
 * Call `Config.validate()` at startup to catch missing required values early.
 */

import * as dotenv from 'dotenv';

// Load .env file in development; in production the values come from ECS task
// definition environment / Secrets Manager injection.
dotenv.config();

export const Config = {
  /** TCP port the HTTP + WebSocket server listens on. */
  PORT: parseInt(process.env['PORT'] ?? '3001', 10),

  // ── Redis (Exchange_Rate_Cache) ─────────────────────────────────────────

  /** ElastiCache Redis hostname. Required. */
  REDIS_HOST: process.env['REDIS_HOST'] ?? '',

  /** ElastiCache Redis port. */
  REDIS_PORT: parseInt(process.env['REDIS_PORT'] ?? '6379', 10),

  /** Whether to use SSL for Redis connection. */
  REDIS_SSL: process.env['REDIS_SSL']?.toLowerCase() === 'true',

  // ── CORS ────────────────────────────────────────────────────────────────

  /**
   * Allowed origin for Socket.IO CORS.
   * Set to the frontend URL in production (e.g. https://app.example.com).
   * Defaults to '*' which is acceptable behind the ALB in a private subnet.
   */
  CORS_ORIGIN: process.env['CORS_ORIGIN'] ?? '*',

  // ── Heartbeat (Requirement 2.3) ─────────────────────────────────────────

  /**
   * How often Socket.IO sends a ping to each connected client (ms).
   * Design: 30 seconds.
   */
  HEARTBEAT_INTERVAL_MS: parseInt(process.env['HEARTBEAT_INTERVAL_MS'] ?? '30000', 10),

  /**
   * How long Socket.IO waits for a pong before closing the connection (ms).
   * Design: 10 seconds.
   */
  HEARTBEAT_TIMEOUT_MS: parseInt(process.env['HEARTBEAT_TIMEOUT_MS'] ?? '10000', 10),

  // ── Rate polling (Requirement 2.2) ──────────────────────────────────────

  /**
   * How often the service polls Redis for updated exchange rates (ms).
   * Default 2000ms — well within the ≤5s push latency requirement (Req 2.2).
   * Must be ≤ 5000 ms to satisfy the ≤5s push latency requirement.
   */
  RATE_POLL_INTERVAL_MS: parseInt(process.env['RATE_POLL_INTERVAL_MS'] ?? '2000', 10),

  /**
   * Validate required configuration values.
   * Throws an error if any required value is missing or invalid.
   */
  validate(): void {
    if (!this.REDIS_HOST) {
      throw new Error('REDIS_HOST environment variable is required');
    }
    if (this.PORT <= 0 || this.PORT > 65535) {
      throw new Error(`Invalid PORT: ${this.PORT}`);
    }
    if (this.RATE_POLL_INTERVAL_MS > 5000) {
      // Warn but do not throw — operator may intentionally relax this in dev
      log('WARN', 'RATE_POLL_INTERVAL_MS exceeds 5000ms; may violate ≤5s push latency requirement', {
        value: this.RATE_POLL_INTERVAL_MS,
      });
    }
  },
} as const;

// ── Structured JSON logger (used by config module itself) ─────────────────────

function log(level: string, message: string, extra?: Record<string, unknown>): void {
  console.log(JSON.stringify({ level, message, service: 'streaming-service', ...extra }));
}
