# syntax=docker/dockerfile:1
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

WORKDIR /app
COPY packages/contracts /app/packages/contracts
COPY services/executor /app/services/executor

WORKDIR /app/services/executor
RUN uv sync --no-dev

ENV API_URL=http://api:8001
ENV REDIS_URL=redis://redis:6379/0
ENV ARTIFACTS_DIR=/data/artifacts
ENV WORKER_COUNT=2

CMD ["uv", "run", "test-platform-executor"]
