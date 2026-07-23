from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

Role = Literal["admin", "viewer", "guest"]
SESSION_COOKIE = "tp_session"


class AuthUser(BaseModel):
    username: str
    role: Role


class LoginRequest(BaseModel):
    username: str
    password: str


@dataclass(frozen=True)
class AuthConfig:
    enabled: bool
    admin_username: str = "admin"
    admin_password: str = ""
    viewer_username: str = "viewer"
    viewer_password: str = ""
    secret: str = ""
    session_ttl_seconds: int = 8 * 60 * 60
    secure_cookie: bool = True

    @classmethod
    def disabled(cls) -> AuthConfig:
        return cls(enabled=False)

    @classmethod
    def from_env(cls) -> AuthConfig:
        admin_password = os.getenv("AUTH_ADMIN_PASSWORD", "")
        viewer_password = os.getenv("AUTH_VIEWER_PASSWORD", "")
        secret = os.getenv("AUTH_SECRET", "")
        missing = [
            name
            for name, value in (
                ("AUTH_ADMIN_PASSWORD", admin_password),
                ("AUTH_VIEWER_PASSWORD", viewer_password),
                ("AUTH_SECRET", secret),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required authentication variables: {', '.join(missing)}")
        return cls(
            enabled=True,
            admin_username=os.getenv("AUTH_ADMIN_USERNAME", "admin"),
            admin_password=admin_password,
            viewer_username=os.getenv("AUTH_VIEWER_USERNAME", "viewer"),
            viewer_password=viewer_password,
            secret=secret,
            session_ttl_seconds=int(os.getenv("AUTH_SESSION_TTL_SECONDS", str(8 * 60 * 60))),
            secure_cookie=os.getenv("AUTH_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"},
        )


class AuthManager:
    def __init__(self, config: AuthConfig) -> None:
        self.config = config

    def authenticate(self, username: str, password: str) -> AuthUser | None:
        candidates: tuple[tuple[str, str, Role], ...] = (
            (self.config.admin_username, self.config.admin_password, "admin"),
            (self.config.viewer_username, self.config.viewer_password, "viewer"),
        )
        for expected_username, expected_password, role in candidates:
            if hmac.compare_digest(username, expected_username) and hmac.compare_digest(
                password, expected_password
            ):
                return AuthUser(username=expected_username, role=role)
        return None

    def create_session(self, user: AuthUser) -> str:
        payload = {
            "sub": user.username,
            "role": user.role,
            "exp": int(time.time()) + self.config.session_ttl_seconds,
        }
        encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signature = _encode(
            hmac.new(self.config.secret.encode(), encoded.encode(), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}"

    def read_session(self, token: str | None) -> AuthUser | None:
        if not token:
            return None
        try:
            encoded, signature = token.split(".", 1)
            expected = _encode(
                hmac.new(self.config.secret.encode(), encoded.encode(), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(_decode(encoded))
            if int(payload["exp"]) < int(time.time()):
                return None
            role = payload["role"]
            if role not in {"admin", "viewer", "guest"}:
                return None
            return AuthUser(username=str(payload["sub"]), role=role)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def guest_user(self) -> AuthUser:
        return AuthUser(username="guest", role="guest")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
