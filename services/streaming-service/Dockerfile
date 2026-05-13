# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM node:20-alpine3.20 AS builder

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY . .

RUN npm run build

# ── Stage 2: Runner. ─────────────────────────────────────────────────────────
FROM node:20-alpine

ENV NODE_ENV=production

WORKDIR /app

COPY package*.json ./

RUN npm install --omit=dev

COPY --from=builder /app/dist ./dist

EXPOSE 4000

CMD ["node", "dist/server.js"]
