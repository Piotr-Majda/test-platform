# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm install
COPY apps/web/ ./
# Browser calls same origin /api; nginx proxies to the API service
ENV VITE_API_URL=/api
RUN npm run build

FROM nginx:1.27-alpine
COPY apps/web/nginx.conf.template /opt/test-platform/nginx.conf.template
COPY apps/web/render-nginx-config.sh /docker-entrypoint.d/15-render-test-platform-config.sh
RUN chmod +x /docker-entrypoint.d/15-render-test-platform-config.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
