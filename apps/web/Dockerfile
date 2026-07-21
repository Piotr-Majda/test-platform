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
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
