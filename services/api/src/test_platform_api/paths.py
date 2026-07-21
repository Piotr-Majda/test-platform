import os
from pathlib import Path


def repo_root() -> Path:
    # .../services/api/src/test_platform_api/paths.py -> repo root
    return Path(__file__).resolve().parents[4]


def artifacts_dir() -> Path:
    configured = os.getenv("ARTIFACTS_DIR")
    if configured:
        return Path(configured).resolve()
    return (repo_root() / "artifacts").resolve()
