# Streaming Service

WebSocket server that pushes real-time exchange rate updates to connected browser clients.

Built with **Node.js + TypeScript + Socket.IO**, deployed as an ECS Fargate task in the **Private Subnet** and accessed exclusively through the Application Load Balancer (ALB) with sticky sessions.

---

## Architecture

```
Exchange_Rate_Cache (ElastiCache Redis)
    │  (poll every RATE_POLL_INTERVAL_MS)
Streaming_Service (ECS, Private Subnet)
    │  (WebSocket push, ≤5s latency)
Frontend (Browser)
```

The ALB is configured with duration-based sticky session cookies so each client always connects to the same ECS task.

---

## Running Locally

### Prerequisites

- Node.js 20+
- A local Redis instance (or Docker: `docker run -p 6379:6379 redis:7-alpine`)

### Setup

```bash
cd services/streaming-service
cp .env.example .env
# Edit .env — set REDIS_HOST=localhost for local development
npm install
```

### Development (hot-reload)

```bash
npm run dev
```

### Production build

```bash
npm run build
npm start
```

### Tests

```bash
npm test
```

---

## Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `PORT` | `3001` | No | TCP port the server listens on |
| `REDIS_HOST` | — | **Yes** | ElastiCache Redis primary endpoint |
| `REDIS_PORT` | `6379` | No | Redis port |
| `CORS_ORIGIN` | `*` | No | Allowed WebSocket origin (set to frontend URL in production) |
| `HEARTBEAT_INTERVAL_MS` | `30000` | No | Socket.IO ping interval (ms) — Requirement 2.3 |
| `HEARTBEAT_TIMEOUT_MS` | `10000` | No | Socket.IO pong timeout (ms) — Requirement 2.3 |
| `RATE_POLL_INTERVAL_MS` | `5000` | No | How often to poll Redis for new rates (ms) — must be ≤5000 for Requirement 2.2 |

---

## API

### HTTP

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | ALB health check — returns `{ status: 'ok', connections: number }` |

### WebSocket (Socket.IO)

#### Server → Client events

| Event | Payload | Description |
|---|---|---|
| `rateUpdate` | `ExchangeRateUpdate` | Pushed when new exchange rates are available |

#### Client → Server events

| Event | Payload | Description |
|---|---|---|
| `subscribe` | `string[]` | Subscribe to specific currency codes (empty = all) |

---

## Relevant Requirements

- **2.1** — Establish WebSocket connection when user opens the dashboard
- **2.2** — Push updated rates within 5 seconds of cache update
- **2.3** — Heartbeat ping every 30s; close connection if no pong within 10s
- **2.4** — Allow reconnection without re-authentication
- **2.5** — ALB sticky sessions (configured in Terraform, task 4.2.7)
