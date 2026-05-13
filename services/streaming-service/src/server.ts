/**
 * Streaming Service — Main Entry Point
 *
 * Sets up:
 *   - Express HTTP server with a /health endpoint (for ALB health checks)
 *   - Socket.IO WebSocket server attached to the same HTTP server
 *   - Graceful SIGTERM handling for ECS task shutdown
 *   - Reconnection handling (task 4.2.4): clients reconnect without re-auth;
 *     the server emits connection_status and immediately pushes latest rates.
 */

import express, { Request, Response } from 'express';
import { createServer } from 'http';
import { Server } from 'socket.io';

import { Config } from './config';
import { RatePoller } from './ratePoller';
import type {
  ClientToServerEvents,
  InterServerEvents,
  ServerToClientEvents,
  SocketData,
} from './types';

// ── Structured JSON logger ────────────────────────────────────────────────────

function log(level: string, message: string, extra?: Record<string, unknown>): void {
  console.log(
    JSON.stringify({
      level,
      message,
      service: 'streaming-service',
      timestamp: new Date().toISOString(),
      ...extra,
    }),
  );
}

// ── Connection counter ────────────────────────────────────────────────────────

let connectionCount = 0;

// ── Reconnection tracking ─────────────────────────────────────────────────────

/**
 * Tracks the set of remote addresses (IP:port or handshake address) that have
 * previously connected to this server instance.
 *
 * Socket.IO's built-in reconnection creates a brand-new socket with a new
 * socket.id on each reconnect attempt, so we cannot use socket.id to detect
 * reconnections. Instead we use the client-supplied `socket.handshake.auth.clientId`
 * (a stable UUID the client generates once and persists across reconnects) as
 * the reconnection key.
 *
 * If the client does not supply a clientId (e.g. older clients or first-time
 * connections), we fall back to treating the connection as new — which is safe
 * because Requirement 2.4 only requires that re-authentication is NOT required,
 * not that the server must distinguish new vs. reconnected clients.
 *
 * The set is bounded by the number of unique clients that have ever connected
 * to this ECS task instance. ALB sticky sessions (Requirement 2.5) ensure each
 * client always hits the same task, so the set does not grow unboundedly across
 * the fleet.
 */
const knownClientIds = new Set<string>();

// ── Express app ───────────────────────────────────────────────────────────────

const app = express();

/**
 * GET /health
 *
 * Used by the ALB target group health check.
 * Returns HTTP 200 with a JSON body so the ALB marks the task as healthy.
 */
app.get('/health', (_req: Request, res: Response) => {
  res.status(200).json({ status: 'ok', connections: connectionCount });
});

// ── HTTP server ───────────────────────────────────────────────────────────────

export const httpServer = createServer(app);

// ── Socket.IO server ──────────────────────────────────────────────────────────

export const io = new Server<
  ClientToServerEvents,
  ServerToClientEvents,
  InterServerEvents,
  SocketData
>(httpServer, {
  path: '/stream/socket.io',
  cors: {
    origin: Config.CORS_ORIGIN,
    methods: ['GET', 'POST'],
  },
  // Heartbeat settings (Requirement 2.3).
  // pingInterval: how often the server sends a ping.
  // pingTimeout:  how long the server waits for a pong before closing.
  pingInterval: Config.HEARTBEAT_INTERVAL_MS,
  pingTimeout: Config.HEARTBEAT_TIMEOUT_MS,
});

// ── Socket.IO event handlers ──────────────────────────────────────────────────

io.on('connection', (socket) => {
  connectionCount += 1;

  // ── Reconnection detection (Requirement 2.4) ────────────────────────────
  //
  // Socket.IO's built-in reconnection creates a new socket on each attempt.
  // We detect reconnections via a stable `clientId` the client sends in
  // socket.handshake.auth. If the clientId is already known, this is a
  // reconnection; otherwise it is a new connection.
  //
  // No authentication is required on reconnect — the server accepts all
  // connections unconditionally. Auth is handled at the ALB/API level for
  // other services (design.md §5). The WebSocket endpoint is intentionally
  // open so clients can resume rate streaming after a network interruption
  // without needing to re-authenticate (Requirement 2.4).
  const clientId = typeof socket.handshake.auth['clientId'] === 'string'
    ? socket.handshake.auth['clientId']
    : null;

  const isReconnection = clientId !== null && knownClientIds.has(clientId);

  if (clientId !== null) {
    knownClientIds.add(clientId);
  }

  log('INFO', isReconnection ? 'Client reconnected' : 'Client connected', {
    socketId: socket.id,
    clientId: clientId ?? 'unknown',
    isReconnection,
    connections: connectionCount,
    remoteAddress: socket.handshake.address,
  });

  // Initialise per-socket data (task 4.2.2 uses this for filtering)
  socket.data.subscribedCurrencies = [];

  // ── Emit connection_status immediately (Requirement 2.4 / task 4.3.4) ──
  //
  // Inform the client of its connection state so the UI can display the
  // correct indicator (connected / reconnected). This is emitted before any
  // rateUpdate so the client can set up its status display first.
  socket.emit('connection_status', {
    status: isReconnection ? 'reconnected' : 'connected',
    timestamp: Date.now(),
  });

  // ── Push latest rates immediately on connect/reconnect ──────────────────
  //
  // The client should see current rates as soon as it connects rather than
  // waiting up to RATE_POLL_INTERVAL_MS for the next scheduled push.
  // We delegate to the RatePoller which already holds the last known rates.
  ratePoller.pushLatestRatesToSocket(socket);

  /**
   * subscribe event — client sends a list of currency codes it cares about.
   * The server stores them so that task 4.2.2 can filter rateUpdate payloads.
   *
   * Requirement 2.4: clients can reconnect without re-authentication, so
   * subscription state is re-established by the client after reconnect.
   */
  socket.on('subscribe', (currencies: string[]) => {
    // Normalise to uppercase and deduplicate
    const normalised = [...new Set(currencies.map((c) => c.toUpperCase()))];
    socket.data.subscribedCurrencies = normalised;

    log('INFO', 'Client subscribed to currencies', {
      socketId: socket.id,
      clientId: clientId ?? 'unknown',
      currencies: normalised,
    });

    // Push the latest rates immediately after subscription so the client
    // receives filtered data right away rather than waiting for the next poll.
    ratePoller.pushLatestRatesToSocket(socket);
  });

  socket.on('disconnect', (reason) => {
    connectionCount = Math.max(0, connectionCount - 1);

    log('INFO', 'Client disconnected', {
      socketId: socket.id,
      clientId: clientId ?? 'unknown',
      reason,
      connections: connectionCount,
      // Log whether this was a server-initiated close (e.g. heartbeat timeout)
      // or a client-initiated close so operators can distinguish the two.
      serverInitiated: reason === 'ping timeout' || reason === 'server namespace disconnect',
    });
  });
});

// ── Rate Poller (Requirement 2.2) ─────────────────────────────────────────────

/**
 * Polls the Exchange Rate Cache (Redis) and pushes updates to connected clients.
 * Instantiated here so it can be stopped during graceful shutdown.
 */
export const ratePoller = new RatePoller(io);

// ── Graceful shutdown (SIGTERM from ECS) ──────────────────────────────────────

function shutdown(signal: string): void {
  log('INFO', `Received ${signal}, shutting down gracefully`, {
    connections: connectionCount,
  });

  // Stop the rate poller first so no more Redis calls are made.
  void ratePoller.stop();

  // Stop accepting new connections
  httpServer.close(() => {
    log('INFO', 'HTTP server closed');
    process.exit(0);
  });

  // Close all existing Socket.IO connections
  io.close(() => {
    log('INFO', 'Socket.IO server closed');
  });

  // Force exit after 10 seconds if graceful shutdown stalls
  setTimeout(() => {
    log('WARN', 'Graceful shutdown timed out, forcing exit');
    process.exit(1);
  }, 10_000).unref();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

// ── Start listening ───────────────────────────────────────────────────────────

function start(): void {
  try {
    Config.validate();
  } catch (err) {
    log('ERROR', 'Configuration validation failed', {
      error: err instanceof Error ? err.message : String(err),
    });
    process.exit(1);
  }

  httpServer.listen(Config.PORT, () => {
    log('INFO', 'Streaming Service started', {
      port: Config.PORT,
      corsOrigin: Config.CORS_ORIGIN,
      heartbeatIntervalMs: Config.HEARTBEAT_INTERVAL_MS,
      heartbeatTimeoutMs: Config.HEARTBEAT_TIMEOUT_MS,
      ratePollIntervalMs: Config.RATE_POLL_INTERVAL_MS,
    });

    // Start polling the Exchange Rate Cache once the server is ready.
    ratePoller.start();
  });
}

// Only start the server when this file is run directly (not when imported by tests)
if (require.main === module) {
  start();
}
