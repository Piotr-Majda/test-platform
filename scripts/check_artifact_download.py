import time
import os
from pathlib import Path

import httpx

API = os.getenv("API_URL", "http://localhost:8001")


def main() -> None:
    client = httpx.Client(base_url=API, timeout=30.0)
    client.post(
        "/auth/login",
        json={
            "username": os.getenv("AUTH_ADMIN_USERNAME", "admin"),
            "password": os.getenv("AUTH_ADMIN_PASSWORD", "admin-demo"),
        },
    ).raise_for_status()
    tests = client.get("/tests").json()
    scenario = client.post(
        "/scenarios", json={"name": "artifact-check", "test_ids": [tests[0]["id"]]}
    ).json()
    run = client.post(f"/scenarios/{scenario['id']}/runs").json()
    detail = None
    for _ in range(60):
        detail = client.get(f"/runs/{run['id']}").json()
        if detail["status"] in {"finished", "failed"}:
            break
        time.sleep(0.5)
    assert detail is not None
    step = detail["projection"]["steps"][0]
    print("open_page_ms", step["duration_ms"], "artifacts", [a["name"] for a in step["artifacts"]])
    artifact = step["artifacts"][0]
    response = client.get(f"/artifacts/{artifact['relative_path']}")
    print("download_status", response.status_code, "bytes", len(response.content))
    print("content_disposition", response.headers.get("content-disposition"))
    root = Path(__file__).resolve().parents[1] / "artifacts" / run["id"]
    print("disk_exists", (root / "open_page" / "step.log.json").is_file(), "at", root)


if __name__ == "__main__":
    main()
