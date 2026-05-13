/**
 * TypeScript type definitions for the Streaming Service.
 *
 * These types are shared between the server and can be imported by
 * integration tests or other modules that interact with the service.
 */

/**
 * A single exchange rate entry as stored in Exchange_Rate_Cache (Redis).
 * Rate is expressed as: 1 VND = `rate` units of `currency`.
 */
export interface ExchangeRate {
  currency: string;
  rate: number;
  timestamp: number; // Unix epoch seconds (matches producer format)
}

/**
 * Payload pushed to clients on the `rateUpdate` event.
 */
export interface ExchangeRateUpdate {
  rates: ExchangeRate[];
  updatedAt: number; // Unix epoch milliseconds
  isStale: boolean;  // true when the cache key has expired and we are serving last-known data
}

// ── Socket.IO typed event maps ────────────────────────────────────────────────

/**
 * Payload pushed to clients on the `rates:stale` event.
 * Emitted when the Exchange Rate Cache (Redis) is unavailable.
 */
export interface RatesStalePayload {
  reason: string;
  timestamp: number; // Unix epoch milliseconds
}

/**
 * Connection status values pushed to clients on the `connection_status` event.
 * - `connected`:    first-time connection (new socket).
 * - `reconnected`:  client has reconnected after a previous disconnection.
 * - `stale`:        connection is alive but exchange rate data may be outdated.
 */
export type ConnectionStatus = 'connected' | 'reconnected' | 'stale';

/**
 * Payload pushed to clients on the `connection_status` event.
 * Emitted immediately after a client connects or reconnects so the UI can
 * display the correct connection indicator (Requirement 2.4, task 4.3.4).
 */
export interface ConnectionStatusPayload {
  status: ConnectionStatus;
  timestamp: number; // Unix epoch milliseconds
}

/**
 * Events emitted by the server and received by the client.
 */
export interface ServerToClientEvents {
  /**
   * Pushed whenever new exchange rate data is available.
   * Requirement 2.2: push within 5 seconds of cache update.
   */
  rateUpdate: (data: ExchangeRateUpdate) => void;

  /**
   * Pushed when the Exchange Rate Cache (Redis) is unavailable and the
   * service cannot guarantee fresh data. Clients should display a
   * "data may be outdated" indicator.
   */
  'rates:stale': (data: RatesStalePayload) => void;

  /**
   * Pushed immediately after a client connects or reconnects.
   * Allows the client to display the correct connection status indicator.
   * Requirement 2.4: client can reconnect without re-authentication.
   */
  connection_status: (data: ConnectionStatusPayload) => void;
}

/**
 * Events emitted by the client and received by the server.
 */
export interface ClientToServerEvents {
  /**
   * Client subscribes to a specific set of currency codes.
   * The server stores these in socket.data.subscribedCurrencies and
   * filters future rateUpdate payloads accordingly (task 4.2.2).
   */
  subscribe: (currencies: string[]) => void;
}

/**
 * Events used for inter-server communication (not used in this service yet).
 */
// eslint-disable-next-line @typescript-eslint/no-empty-interface
export interface InterServerEvents {}

/**
 * Per-socket data stored on the server side.
 */
export interface SocketData {
  /** Currency codes the client has subscribed to. Empty = all currencies. */
  subscribedCurrencies: string[];
}
