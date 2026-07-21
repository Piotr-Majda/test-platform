#!/bin/sh
set -e
echo "Waiting for Postgres..."
uv run python - <<'PY'
import os, time
import psycopg

url = os.environ["DATABASE_URL"]
# psycopg wants postgresql:// not postgresql+psycopg://
dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)
for i in range(60):
    try:
        with psycopg.connect(dsn) as conn:
            conn.execute("SELECT 1")
        print("Postgres is ready")
        break
    except Exception as exc:
        print(f"  attempt {i+1}/60: {exc}")
        time.sleep(1)
else:
    raise SystemExit("Postgres did not become ready in time")
PY

echo "Running Alembic migrations..."
uv run alembic upgrade head

echo "Starting API..."
exec uv run test-platform-api
