# syntax=docker/dockerfile:1
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

WORKDIR /app
COPY packages/contracts /app/packages/contracts
COPY services/api /app/services/api

WORKDIR /app/services/api
RUN uv sync --no-dev \
    && sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod +x docker-entrypoint.sh

ENV API_HOST=0.0.0.0
ENV API_PORT=8001
ENV DATABASE_URL=postgresql+psycopg://platform:platform@postgres:5432/platform
ENV ARTIFACTS_DIR=/data/artifacts
ENV REDIS_URL=redis://redis:6379/0

EXPOSE 8001
ENTRYPOINT ["./docker-entrypoint.sh"]
