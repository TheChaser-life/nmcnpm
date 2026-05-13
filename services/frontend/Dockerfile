# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first for better layer caching
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci --frozen-lockfile 2>/dev/null || npm install

# Copy source code
COPY . .

# Build the application
# Build args are passed as environment variables for Vite
ARG VITE_COGNITO_USER_POOL_ID
ARG VITE_COGNITO_CLIENT_ID
ARG VITE_AWS_REGION=ap-southeast-2
ARG VITE_API_BASE_URL
ARG VITE_STREAMING_SERVICE_URL
ARG VITE_MONEY_SERVICE_URL
ARG VITE_FORECAST_SERVICE_URL
ARG VITE_TOUR_SERVICE_URL

ENV VITE_COGNITO_USER_POOL_ID=$VITE_COGNITO_USER_POOL_ID
ENV VITE_COGNITO_CLIENT_ID=$VITE_COGNITO_CLIENT_ID
ENV VITE_AWS_REGION=$VITE_AWS_REGION
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_STREAMING_SERVICE_URL=$VITE_STREAMING_SERVICE_URL
ENV VITE_MONEY_SERVICE_URL=$VITE_MONEY_SERVICE_URL
ENV VITE_FORECAST_SERVICE_URL=$VITE_FORECAST_SERVICE_URL
ENV VITE_TOUR_SERVICE_URL=$VITE_TOUR_SERVICE_URL

# Debug: show the env vars before build
RUN echo "Build environment:" && \
    echo "VITE_COGNITO_USER_POOL_ID=${VITE_COGNITO_USER_POOL_ID}" && \
    echo "VITE_COGNITO_CLIENT_ID=${VITE_COGNITO_CLIENT_ID}" && \
    echo "VITE_AWS_REGION=${VITE_AWS_REGION}" && \
    echo "VITE_STREAMING_SERVICE_URL=${VITE_STREAMING_SERVICE_URL}" && \
    echo "VITE_MONEY_SERVICE_URL=${VITE_MONEY_SERVICE_URL}" && \
    echo "VITE_FORECAST_SERVICE_URL=${VITE_FORECAST_SERVICE_URL}" && \
    echo "VITE_TOUR_SERVICE_URL=${VITE_TOUR_SERVICE_URL}"

RUN npm run build

# ── Stage 2: Serve ────────────────────────────────────────────────────────────
FROM nginx:1.25-alpine AS production

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx configuration for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 3000
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
# CI/CD smoke test marker.
