FROM node:24-alpine AS dependencies
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci

FROM node:24-alpine AS builder
WORKDIR /app/web
COPY --from=dependencies /app/web/node_modules ./node_modules
COPY web/ ./
ARG API_INTERNAL_URL=http://api:8000
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN mkdir -p public
RUN npm run build

FROM node:24-alpine AS runtime
ARG SOURCE_REVISION=local
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    SOURCE_REVISION=$SOURCE_REVISION
LABEL org.opencontainers.image.revision=$SOURCE_REVISION
WORKDIR /app
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx \
    && addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/web/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/web/.next/static ./.next/static
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+process.env.PORT).then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
