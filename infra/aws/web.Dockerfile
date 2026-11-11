# Next.js web image for the AWS Lightsail container service.
# Build from frontend/: docker build -f ../infra/aws/web.Dockerfile .
FROM node:22.22.1-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# next.config.ts bakes the portfolio proxy target into the build. Containers in one
# Lightsail service share localhost, so the portfolio server is at 127.0.0.1:3108.
ARG PORTFOLIO_API_INTERNAL_URL=http://127.0.0.1:3108
ENV PORTFOLIO_API_INTERNAL_URL=${PORTFOLIO_API_INTERNAL_URL}
RUN npm run build && npm prune --omit=dev && rm -rf .next/cache

FROM node:22.22.1-slim
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000
COPY --from=build --chown=node:node /app ./
USER node
EXPOSE 3000
CMD ["sh", "-c", "exec node_modules/.bin/next start --hostname 0.0.0.0 --port \"$PORT\""]
