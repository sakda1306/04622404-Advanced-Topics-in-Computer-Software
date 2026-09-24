# syntax=docker/dockerfile:1.7
# 01_web_app — Next.js 14 (App Router). Targets: dev | runner
# Requires `output: "standalone"` in next.config.js (see README note).

ARG NODE_VERSION=20.18-alpine

# ---------------------------------------------------------------- base
FROM node:${NODE_VERSION} AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# ---------------------------------------------------------------- deps
# Separate layer so node_modules is only reinstalled when the lockfile changes.
FROM base AS deps
COPY package.json package-lock.json* ./
RUN npm ci

# ---------------------------------------------------------------- dev
# Hot reload. The source comes from a bind mount at runtime, not from this layer.
FROM base AS dev
ENV NODE_ENV=development
# File events do not cross Windows/WSL bind mounts, so watch by polling.
ENV WATCHPACK_POLLING=true \
    CHOKIDAR_USEPOLLING=true
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ---------------------------------------------------------------- builder
# NEXT_PUBLIC_* is inlined into the client bundle AT BUILD TIME.
# Changing these later needs a rebuild — they are build args, not runtime env.
FROM base AS builder
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_KEYCLOAK_URL=http://localhost:8180
ARG NEXT_PUBLIC_KEYCLOAK_REALM=travel-safety
ARG NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=travel-safety-web
ARG NEXT_PUBLIC_DEFAULT_LOCALE=th
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_KEYCLOAK_URL=${NEXT_PUBLIC_KEYCLOAK_URL} \
    NEXT_PUBLIC_KEYCLOAK_REALM=${NEXT_PUBLIC_KEYCLOAK_REALM} \
    NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=${NEXT_PUBLIC_KEYCLOAK_CLIENT_ID} \
    NEXT_PUBLIC_DEFAULT_LOCALE=${NEXT_PUBLIC_DEFAULT_LOCALE} \
    NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---------------------------------------------------------------- runner
FROM node:${NODE_VERSION} AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 1001 -S nodejs && adduser -u 1001 -S nextjs -G nodejs

COPY --from=builder /app/public ./public
# standalone already contains the trimmed node_modules and server.js
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --retries=5 --start-period=15s \
  CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
