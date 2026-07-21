import logging
import os
import threading
import time
from pathlib import Path

import redis
import uvicorn
from dotenv import load_dotenv

# Load services/api/.env before reading OPENAI_API_KEY / ANALYSIS_*
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()  # also cwd .env if present

logging.basicConfig(level=logging.INFO)

from test_platform_api.app import create_app
from test_platform_api.auth import AuthConfig
from test_platform_api.db import create_session_factory
from test_platform_api.event_ingest import poll_events_once
from test_platform_api.redis_bus import RedisEventConsumer, RedisEventPublisher


def _start_event_poller(session_factory, redis_url: str) -> None:
    client = redis.Redis.from_url(redis_url, decode_responses=True)
    consumer = RedisEventConsumer(client)
    last_id = "0-0"

    def loop() -> None:
        nonlocal last_id
        while True:
            try:
                last_id = poll_events_once(consumer, session_factory, last_id)
            except Exception:
                logging.exception("event poller failed")
            time.sleep(0.5)

    thread = threading.Thread(target=loop, name="event-poller", daemon=True)
    thread.start()


def build_app():
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://platform:platform@localhost:5432/platform",
    )
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    session_factory = create_session_factory(database_url)
    client = redis.Redis.from_url(redis_url, decode_responses=True)
    publisher = RedisEventPublisher(client)
    app = create_app(session_factory, publisher, auth_config=AuthConfig.from_env())
    _start_event_poller(session_factory, redis_url)
    return app


app = build_app()


def run() -> None:
    uvicorn.run(
        "test_platform_api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8001")),
        reload=False,
    )


if __name__ == "__main__":
    run()
