/**
 * Rate Poller — Exchange Rate Cache Subscription
 *
 * Polls the Exchange_Rate_Cache (ElastiCache Redis/Valkey) at a configurable
 * interval and pushes updated rates to all connected Socket.IO clients.
 *
 * Design decisions:
 *   - Uses polling (not Redis pub/sub) because the producer writes with simple
 *     SET commands, not PUBLISH.
 *   - Detects changes by comparing the new rate value against the last known
 *     value before emitting to avoid redundant pushes.
 *   - Marks rates as stale when the Redis key TTL has expired or the data
 *     hasn't been refreshed within STALE_THRESHOLD_MS (default 90s).
 *   - On Redis connection error: logs the error, emits `rates:stale` to all
 *     clients, and continues serving the last known rates on the next poll.
 *
 * Requirements addressed:
 *   - Req 2.2: push updated rates within 5s of cache update (poll ≤ 5000ms)
 *   - Req 2.3: heartbeat is handled by Socket.IO config in server.ts
 *   - Req 2.4: reconnection is handled by Socket.IO config in server.ts
 */

import Redis from 'ioredis';
import type { Server, Socket } from 'socket.io';
import { Config } from './config';
import type {
  ClientToServerEvents,
  ExchangeRate,
  ExchangeRateUpdate,
  InterServerEvents,
  ServerToClientEvents,
  SocketData,
} from './types';

// ── Constants ─────────────────────────────────────────────────────────────────

/**
 * Redis key prefix used by the Exchange Rate Producer.
 * Keys are stored as: `exchange_rate:<CURRENCY_CODE>` (e.g. `exchange_rate:USD`).
 */
const RATE_KEY_PREFIX = 'exchange_rate:';

/**
 * How long (ms) without a fresh value before a rate is considered stale.
 * Design: 3× the producer polling interval (30s) = 90s.
 */
const STALE_THRESHOLD_MS = 90_000;

// ── Structured JSON logger ────────────────────────────────────────────────────

function log(level: string, message: string, extra?: Record<string, unknown>): void {
  console.log(
    JSON.stringify({
      level,
      message,
      service: 'streaming-service',
      module: 'ratePoller',
      timestamp: new Date().toISOString(),
      ...extra,
    }),
  );
}

// ── Types ─────────────────────────────────────────────────────────────────────

type IoServer = Server<ClientToServerEvents, ServerToClientEvents, InterServerEvents, SocketData>;

/**
 * Internal state for a single tracked exchange rate.
 */
interface TrackedRate {
  rate: number;
  timestamp: number;       // Unix epoch seconds (from producer)
  lastSeenAt: number;      // Unix epoch ms (local wall clock when we last read this key)
}

// ── RatePoller class ──────────────────────────────────────────────────────────

export class RatePoller {
  private readonly redis: Redis;
  private readonly io: IoServer;
  private readonly pollIntervalMs: number;

  /** Last known rates, keyed by currency code (e.g. "USD"). */
  private lastKnownRates: Map<string, TrackedRate> = new Map();

  /** Whether the poller is currently running. */
  private running = false;

  /** Timer handle for the poll loop. */
  private timer: ReturnType<typeof setTimeout> | null = null;

  /** Whether Redis is currently reachable. */
  private redisAvailable = false;

  constructor(io: IoServer, pollIntervalMs: number = Config.RATE_POLL_INTERVAL_MS) {
    this.io = io;
    this.pollIntervalMs = pollIntervalMs;

    this.redis = new Redis({
      host: Config.REDIS_HOST,
      port: Config.REDIS_PORT,
      tls: Config.REDIS_SSL ? {} : undefined,
      // Do not auto-reconnect indefinitely — ioredis handles reconnect by default.
      // lazyConnect: false means it connects immediately on construction.
      lazyConnect: false,
      // Retry strategy: exponential back-off capped at 10s.
      retryStrategy: (times: number) => Math.min(times * 500, 10_000),
      // Suppress unhandled-rejection warnings; we handle errors via events.
      enableOfflineQueue: true,
    });

    this.redis.on('connect', () => {
      this.redisAvailable = true;
      log('INFO', 'Connected to Exchange Rate Cache (Redis)', {
        host: Config.REDIS_HOST,
        port: Config.REDIS_PORT,
      });
    });

    this.redis.on('ready', () => {
      this.redisAvailable = true;
      log('INFO', 'Redis client ready');
    });

    this.redis.on('error', (err: Error) => {
      this.redisAvailable = false;
      log('ERROR', 'Redis connection error', { error: err.message });
    });

    this.redis.on('close', () => {
      this.redisAvailable = false;
      log('WARN', 'Redis connection closed');
    });

    this.redis.on('reconnecting', () => {
      log('INFO', 'Redis reconnecting…');
    });
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Start the polling loop. Safe to call multiple times (idempotent). */
  start(): void {
    if (this.running) return;
    this.running = true;
    log('INFO', 'Rate poller started', { pollIntervalMs: this.pollIntervalMs });
    this.schedulePoll();
  }

  /** Stop the polling loop and disconnect from Redis. */
  async stop(): Promise<void> {
    this.running = false;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    await this.redis.quit();
    log('INFO', 'Rate poller stopped');
  }

  /**
   * Push the latest known exchange rates to a single socket immediately.
   *
   * Called by server.ts on connect/reconnect (task 4.2.4) so the client
   * receives current rates right away rather than waiting for the next
   * scheduled poll cycle.
   *
   * If no rates are cached yet (e.g. the service just started), this is a
   * no-op — the client will receive rates on the next poll cycle.
   *
   * @param socket - The Socket.IO socket to push rates to.
   */
  pushLatestRatesToSocket(
    socket: Socket<ClientToServerEvents, ServerToClientEvents, InterServerEvents, SocketData>,
  ): void {
    if (this.lastKnownRates.size === 0) return;

    const now = Date.now();
    const allRates: ExchangeRate[] = [];

    for (const [currency, tracked] of this.lastKnownRates.entries()) {
      allRates.push({
        currency,
        rate: tracked.rate,
        timestamp: tracked.timestamp,
      });
    }

    const subscribed = socket.data.subscribedCurrencies ?? [];
    const rates =
      subscribed.length === 0
        ? allRates
        : allRates.filter((r) => subscribed.includes(r.currency));

    if (rates.length === 0) return;

    // Determine staleness for this immediate push.
    const isStale = this.hasStaleRates(now);

    socket.emit('rateUpdate', {
      rates,
      updatedAt: now,
      isStale,
    });

    log('DEBUG', 'Pushed latest rates to newly connected socket', {
      socketId: socket.id,
      currencies: rates.map((r) => r.currency),
      isStale,
    });
  }

  // ── Private helpers ─────────────────────────────────────────────────────────

  private schedulePoll(): void {
    if (!this.running) return;
    this.timer = setTimeout(() => {
      void this.poll().finally(() => this.schedulePoll());
    }, this.pollIntervalMs);
  }

  /**
   * One poll cycle:
   *   1. Scan all `exchange_rate:*` keys in Redis.
   *   2. Fetch their values.
   *   3. Detect changes vs. last known state.
   *   4. Push updates to clients if anything changed.
   *   5. On Redis error: emit `rates:stale` to all clients.
   */
  private async poll(): Promise<void> {
    if (!this.redisAvailable) {
      // Redis is down — emit stale event so clients know data may be outdated.
      this.emitStale();
      return;
    }

    try {
      const keys = await this.scanRateKeys();

      if (keys.length === 0) {
        log('WARN', 'No exchange-rate keys found in Redis', {
          keyPattern: `${RATE_KEY_PREFIX}*`,
          hadLastKnownRates: this.lastKnownRates.size > 0,
        });
        // No keys yet (producer hasn't written anything, or all TTLs expired).
        if (this.lastKnownRates.size > 0) {
          // We had data before — serve last known but mark as stale.
          this.pushRates(true);
        }
        return;
      }

      const now = Date.now();
      let hasChanges = false;

      // Fetch all values in a single pipeline for efficiency.
      const pipeline = this.redis.pipeline();
      for (const key of keys) {
        pipeline.get(key);
      }
      const results = await pipeline.exec();

      if (!results) return;

      for (let i = 0; i < keys.length; i++) {
        const key = keys[i]!;
        const [err, raw] = results[i]!;

        if (err || raw === null || typeof raw !== 'string') {
          // Key expired between SCAN and GET — skip; last known value will be
          // served as stale on the next push.
          continue;
        }

        const currency = key.slice(RATE_KEY_PREFIX.length).toUpperCase();
        const parsed = this.parseRateValue(raw, currency);
        if (!parsed) continue;

        const existing = this.lastKnownRates.get(currency);

        if (
          !existing ||
          existing.rate !== parsed.rate ||
          existing.timestamp !== parsed.timestamp
        ) {
          // Rate has changed (or is new) — update our local state.
          this.lastKnownRates.set(currency, {
            rate: parsed.rate,
            timestamp: parsed.timestamp,
            lastSeenAt: now,
          });
          hasChanges = true;
        } else {
          // Rate value is the same — just refresh the lastSeenAt timestamp so
          // we don't incorrectly mark it as stale.
          existing.lastSeenAt = now;
        }
      }

      if (hasChanges) {
        this.pushRates(false);
      } else {
        // No value changes, but check if any rate has gone stale.
        const anyStale = this.hasStaleRates(now);
        if (anyStale) {
          // Re-push with stale flag so clients know.
          this.pushRates(true);
        }
      }
    } catch (err) {
      log('ERROR', 'Error during rate poll', {
        error: err instanceof Error ? err.message : String(err),
      });
      this.emitStale();
    }
  }

  /**
   * Scan all keys matching `exchange_rate:*` using SCAN (non-blocking, cursor-based).
   */
  private async scanRateKeys(): Promise<string[]> {
    const keys: string[] = [];
    let cursor = '0';

    do {
      const [nextCursor, batch] = await this.redis.scan(
        cursor,
        'MATCH',
        `${RATE_KEY_PREFIX}*`,
        'COUNT',
        100,
      );
      cursor = nextCursor;
      keys.push(...batch);
    } while (cursor !== '0');

    return keys;
  }

  /**
   * Parse a raw Redis value into an ExchangeRate.
   *
   * The producer stores values as JSON: `{"rate": 0.000042, "timestamp": 1718000000}`
   * where `rate` is expressed as: 1 VND = `rate` units of `currency`.
   */
  private parseRateValue(raw: string, currency: string): ExchangeRate | null {
    try {
      const parsed: unknown = JSON.parse(raw);
      if (
        typeof parsed !== 'object' ||
        parsed === null ||
        typeof (parsed as Record<string, unknown>)['rate'] !== 'number' ||
        typeof (parsed as Record<string, unknown>)['timestamp'] !== 'number'
      ) {
        log('WARN', 'Unexpected rate value format', { currency, raw });
        return null;
      }
      const obj = parsed as { rate: number; timestamp: number };
      return { currency, rate: obj.rate, timestamp: obj.timestamp };
    } catch {
      log('WARN', 'Failed to parse rate value as JSON', { currency, raw });
      return null;
    }
  }

  /**
   * Returns true if any tracked rate hasn't been refreshed within STALE_THRESHOLD_MS.
   */
  private hasStaleRates(now: number): boolean {
    for (const tracked of this.lastKnownRates.values()) {
      if (now - tracked.lastSeenAt > STALE_THRESHOLD_MS) {
        return true;
      }
    }
    return false;
  }

  /**
   * Build the ExchangeRateUpdate payload from lastKnownRates and emit it to
   * all connected clients via `rateUpdate`.
   *
   * Clients that have subscribed to specific currencies receive only those
   * currencies; clients with an empty subscription list receive all currencies.
   */
  private pushRates(isStale: boolean): void {
    const now = Date.now();
    const allRates: ExchangeRate[] = [];

    for (const [currency, tracked] of this.lastKnownRates.entries()) {
      allRates.push({
        currency,
        rate: tracked.rate,
        timestamp: tracked.timestamp,
      });
    }

    if (allRates.length === 0) return;

    // Broadcast to each socket, filtering by subscribed currencies.
    const sockets = this.io.sockets.sockets;

    sockets.forEach((socket) => {
      const subscribed = socket.data.subscribedCurrencies ?? [];

      const rates =
        subscribed.length === 0
          ? allRates
          : allRates.filter((r) => subscribed.includes(r.currency));

      if (rates.length === 0) return;

      const payload: ExchangeRateUpdate = {
        rates,
        updatedAt: now,
        isStale,
      };

      socket.emit('rateUpdate', payload);
    });

    log('DEBUG', 'Pushed rate update to clients', {
      currencies: allRates.map((r) => r.currency),
      isStale,
      clientCount: sockets.size,
    });
  }

  /**
   * Emit a `rates:stale` event to all connected clients when Redis is
   * unavailable. Also re-emits last known rates (if any) with isStale=true
   * so the client can still display something.
   */
  private emitStale(): void {
    const sockets = this.io.sockets.sockets;

    if (sockets.size === 0) return;

    // If we have last known rates, push them with isStale=true.
    if (this.lastKnownRates.size > 0) {
      this.pushRates(true);
    }

    // Also emit the dedicated `rates:stale` event so clients can show a
    // "data may be outdated" indicator.
    this.io.emit('rates:stale', {
      reason: 'Exchange Rate Cache unavailable',
      timestamp: Date.now(),
    });

    log('WARN', 'Emitted rates:stale to all clients', { clientCount: sockets.size });
  }
}
