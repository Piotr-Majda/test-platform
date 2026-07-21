import logging
import os
import signal
import time
from importlib.metadata import PackageNotFoundError, version

import httpx
import redis
from test_platform_contracts import CONTRACTS_VERSION, PluginManifest

from test_platform_executor.events import RedisProgressPublisher
from test_platform_executor.framework.catalog import catalog_definitions
from test_platform_executor.handler import process_execute_command
from test_platform_executor.pool import WorkerPool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def framework_version() -> str:
    try:
        return version("test-platform-executor")
    except PackageNotFoundError:
        return "0.1.0"


def register_catalog(api_url: str, plugin_id: str) -> None:
    manifest = PluginManifest(
        plugin_id=plugin_id,
        framework_version=framework_version(),
        contracts_version=CONTRACTS_VERSION,
        tests=catalog_definitions(),
    )
    url = f"{api_url.rstrip('/')}/plugins/manifest"
    payload = manifest.model_dump(mode="json")
    last_error: Exception | None = None
    for attempt in range(1, 31):
        try:
            response = httpx.post(url, json=payload, timeout=10.0)
            if response.status_code == 409:
                logger.error(
                    "plugin manifest rejected (contracts_version mismatch): %s",
                    response.text,
                )
            response.raise_for_status()
            logger.info(
                "registered plugin manifest with %s tests (framework_version=%s, contracts_version=%s)",
                len(manifest.tests),
                manifest.framework_version,
                manifest.contracts_version,
            )
            return
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            logger.warning("catalog register attempt %s/30 failed: %s", attempt, exc)
            time.sleep(1)
    raise RuntimeError(f"failed to register catalog with {api_url}") from last_error


def run() -> None:
    api_url = os.getenv("API_URL", "http://localhost:8001")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    plugin_id = os.getenv("PLUGIN_ID", "example-executor")
    worker_count = int(os.getenv("WORKER_COUNT", "2"))

    register_catalog(api_url, plugin_id)

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    publisher = RedisProgressPublisher(client)

    def handler(command):
        process_execute_command(command, publisher)

    pool = WorkerPool(client, handler, worker_count=worker_count)
    pool.start()
    logger.info("worker pool started with %s workers", worker_count)

    stop = False

    def _stop(*_args):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not stop:
        time.sleep(0.5)

    pool.stop()
    logger.info("worker pool stopped")


if __name__ == "__main__":
    run()
