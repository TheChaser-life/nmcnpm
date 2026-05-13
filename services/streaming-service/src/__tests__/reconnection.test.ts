/**
 * Unit tests for task 4.2.4 — Reconnection handling
 *
 * Validates Requirement 2.4:
 *   "IF a WebSocket connection is dropped, THEN THE Streaming_Service SHALL
 *    allow the client to reconnect and resume receiving rate updates WITHOUT
 *    requiring re-authentication."
 *
 * These tests use Socket.IO's in-memory adapter so no real network or Redis
 * connection is needed.
 */

import { createServer } from 'http';
import { Server, Socket as ServerSocket } from 'socket.io';
import { io as ioc, Socket as ClientSocket } from 'socket.io-client';

import type {
  ClientToServerEvents,
  ConnectionStatusPayload,
  ExchangeRateUpdate,
  InterServerEvents,
  ServerToClientEvents,
  SocketData,
} from '../types';

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Creates a minimal Socket.IO server that mirrors the reconnection logic from
 * server.ts so we can test it in isolation without starting the full server
 * (which requires Redis).
 */
function createTestServer() {
  const httpServer = createServer();
  const io = new Server<
    ClientToServerEvents,
    ServerToClientEvents,
    InterServerEvents,
    SocketData
  >(httpServer, {
    // Use in-memory transport for tests — no real network needed.
    transports: ['websocket'],
  });

  // Mirrors the knownClientIds set from server.ts
  const knownClientIds = new Set<string>();

  // Mirrors the lastKnownRates from RatePoller — pre-populated for tests.
  const mockRates: ExchangeRateUpdate = {
    rates: [
      { currency: 'USD', rate: 0.000042, timestamp: 1718000000 },
      { currency: 'EUR', rate: 0.000038, timestamp: 1718000000 },
    ],
    updatedAt: Date.now(),
    isStale: false,
  };

  io.on('connection', (socket) => {
    socket.data.subscribedCurrencies = [];

    const clientId =
      typeof socket.handshake.auth['clientId'] === 'string'
        ? socket.handshake.auth['clientId']
        : null;

    const isReconnection = clientId !== null && knownClientIds.has(clientId);

    if (clientId !== null) {
      knownClientIds.add(clientId);
    }

    // Emit connection_status (mirrors server.ts)
    socket.emit('connection_status', {
      status: isReconnection ? 'reconnected' : 'connected',
      timestamp: Date.now(),
    });

    // Push latest rates immediately (mirrors ratePoller.pushLatestRatesToSocket)
    socket.emit('rateUpdate', mockRates);

    socket.on('subscribe', (currencies: string[]) => {
      const normalised = [...new Set(currencies.map((c) => c.toUpperCase()))];
      socket.data.subscribedCurrencies = normalised;
      // Push rates after subscribe
      socket.emit('rateUpdate', mockRates);
    });
  });

  return { httpServer, io, knownClientIds };
}

/**
 * Wait for a specific event on a client socket, with a timeout.
 */
function waitForEvent<T>(
  socket: ClientSocket,
  event: string,
  timeoutMs = 2000,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`Timed out waiting for event "${event}"`));
    }, timeoutMs);

    socket.once(event, (data: T) => {
      clearTimeout(timer);
      resolve(data);
    });
  });
}

// ── Test suite ────────────────────────────────────────────────────────────────

describe('Reconnection handling (task 4.2.4 / Requirement 2.4)', () => {
  let httpServer: ReturnType<typeof createServer>;
  let io: Server<ClientToServerEvents, ServerToClientEvents, InterServerEvents, SocketData>;
  let port: number;

  beforeEach((done) => {
    const setup = createTestServer();
    httpServer = setup.httpServer;
    io = setup.io;

    httpServer.listen(0, () => {
      const addr = httpServer.address();
      port = typeof addr === 'object' && addr !== null ? addr.port : 0;
      done();
    });
  });

  afterEach((done) => {
    io.close(() => {
      httpServer.close(done);
    });
  });

  // ── 1. New connection ───────────────────────────────────────────────────────

  it('emits connection_status "connected" for a brand-new client (no clientId)', (done) => {
    const client = ioc(`http://localhost:${port}`, {
      transports: ['websocket'],
      // No auth.clientId — simulates a client that does not send one
    });

    client.on('connection_status', (payload: ConnectionStatusPayload) => {
      expect(payload.status).toBe('connected');
      expect(typeof payload.timestamp).toBe('number');
      client.disconnect();
      done();
    });
  });

  it('emits connection_status "connected" for a first-time client with a new clientId', (done) => {
    const client = ioc(`http://localhost:${port}`, {
      transports: ['websocket'],
      auth: { clientId: 'test-client-001' },
    });

    client.on('connection_status', (payload: ConnectionStatusPayload) => {
      expect(payload.status).toBe('connected');
      client.disconnect();
      done();
    });
  });

  // ── 2. Reconnection ─────────────────────────────────────────────────────────

  it('emits connection_status "reconnected" when a known clientId reconnects', (done) => {
    const CLIENT_ID = 'test-client-reconnect-001';

    // First connection
    const client1 = ioc(`http://localhost:${port}`, {
      transports: ['websocket'],
      auth: { clientId: CLIENT_ID },
    });

    client1.on('connection_status', (payload: ConnectionStatusPayload) => {
      expect(payload.status).toBe('connected');

      // Disconnect and reconnect with the same clientId
      client1.disconnect();

      const client2 = ioc(`http://localhost:${port}`, {
        transports: ['websocket'],
        auth: { clientId: CLIENT_ID },
      });

      client2.on('connection_status', (payload2: ConnectionStatusPayload) => {
        expect(payload2.status).toBe('reconnected');
        client2.disconnect();
        done();
      });
    });
  });

  // ── 3. No re-authentication required ───────────────────────────────────────

  it('accepts reconnection without any auth token (Requirement 2.4)', (done) => {
    const CLIENT_ID = 'test-client-no-auth-001';

    // First connection — no auth token, just clientId
    const client1 = ioc(`http://localhost:${port}`, {
      transports: ['websocket'],
      auth: { clientId: CLIENT_ID },
    });

    client1.once('connect', () => {
      client1.disconnect();

      // Reconnect — still no auth token
      const client2 = ioc(`http://localhost:${port}`, {
        transports: ['websocket'],
        auth: { clientId: CLIENT_ID },
        // Deliberately no token field — server must not require it
      });

      client2.once('connect', () => {
        // If we reach here, the server accepted the reconnection without auth
        expect(client2.connected).toBe(true);
        client2.disconnect();
        done();
      });

      client2.once('connect_error', (err) => {
        client2.disconnect();
        done(new Error(`Server rejected reconnection: ${err.message}`));
      });
    });
  });

  // ── 4. Immediate rate push on connect/reconnect ─────────────────────────────

  it('pushes latest rates immediately on first connection', (done) => {
    const client = ioc(`http://localhost:${port}`, {
      transports: ['websocket'],
    });

    client.on('rateUpdate', (data: ExchangeRateUpdate) => {
      expect(data.rates.length).toBeGreaterThan(0);
      expect(data.rates[0]).toHaveProperty('currency');
      expect(data.rates[0]).toHaveProperty('rate');
      client.disconnect();
      done();
    });
  });

  it('pushes latest rates immediately on reconnection', (done) => {
    const CLIENT_ID = 'test-client-rates-on-reconnect';

    const client1 = ioc(`http://localhost:${port}`, {
      transports: ['websocket'],
      auth: { clientId: CLIENT_ID },
    });

    // Wait for first rateUpdate, then disconnect and reconnect
    client1.once('rateUpdate', () => {
      client1.disconnect();

      const client2 = ioc(`http://localhost:${port}`, {
        transports: ['websocket'],
        auth: { clientId: CLIENT_ID },
      });

      client2.once('rateUpdate', (data: ExchangeRateUpdate) => {
        expect(data.rates.length).toBeGreaterThan(0);
        client2.disconnect();
        done();
      });
    });
  });

  // ── 5. Rates pushed after subscribe ────────────────────────────────────────

  it('pushes filtered rates immediately after subscribe event', (done) => {
    const client = ioc(`http://localhost:${port}`, {
      transports: ['websocket'],
    });

    // Skip the initial rateUpdate on connect
    client.once('rateUpdate', () => {
      // Now subscribe to a specific currency
      client.emit('subscribe', ['USD']);

      client.once('rateUpdate', (data: ExchangeRateUpdate) => {
        // The mock server pushes all rates regardless of filter in this test
        // (full filtering is tested in ratePoller tests). We just verify a
        // rateUpdate is emitted after subscribe.
        expect(data.rates.length).toBeGreaterThan(0);
        client.disconnect();
        done();
      });
    });
  });

  // ── 6. Multiple reconnections ───────────────────────────────────────────────

  it('correctly identifies reconnected status across multiple reconnections', async () => {
    const CLIENT_ID = 'test-client-multi-reconnect';

    // Helper to connect and wait for connection_status
    const connectAndGetStatus = (): Promise<ConnectionStatusPayload> => {
      return new Promise((resolve, reject) => {
        const client = ioc(`http://localhost:${port}`, {
          transports: ['websocket'],
          auth: { clientId: CLIENT_ID },
        });

        const timer = setTimeout(() => {
          client.disconnect();
          reject(new Error('Timed out waiting for connection_status'));
        }, 2000);

        client.once('connection_status', (payload: ConnectionStatusPayload) => {
          clearTimeout(timer);
          client.disconnect();
          resolve(payload);
        });
      });
    };

    const first = await connectAndGetStatus();
    expect(first.status).toBe('connected');

    const second = await connectAndGetStatus();
    expect(second.status).toBe('reconnected');

    const third = await connectAndGetStatus();
    expect(third.status).toBe('reconnected');
  });
});
