from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "smoke_web_origin.py"
    spec = importlib.util.spec_from_file_location("smoke_web_origin", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, json_body: Any = None, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._json_body = json_body
        self.headers = headers or {}
        self.text = str(json_body)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status {self.status_code}")

    def json(self) -> Any:
        return self._json_body


class _FakeClient:
    def __init__(self, responses: dict[str, _FakeResponse]):
        self.responses = responses
        self.requested: list[str] = []

    def get(self, path: str) -> _FakeResponse:
        self.requested.append(path)
        return self.responses[path]


def test_smoke_origin_checks_expected_routes() -> None:
    module = _load_module()
    client = _FakeClient(
        {
            "/api/health": _FakeResponse(json_body={"status": "ok"}),
            "/api/auth/config": _FakeResponse(
                json_body={
                    "auth_mode": "magic_link",
                    "bot_username": "dynamic_bot",
                    "bot_start_url": "https://t.me/dynamic_bot?start=admin_login_dev",
                }
            ),
            "/api/public/catalog": _FakeResponse(json_body=[]),
            "/": _FakeResponse(headers={"content-type": "text/html; charset=utf-8"}, json_body="<html></html>"),
        }
    )

    module.smoke(client)

    assert client.requested == [
        "/api/health",
        "/api/auth/config",
        "/api/public/catalog",
        "/",
    ]


def test_smoke_origin_rejects_secret_auth_config_fields() -> None:
    module = _load_module()
    client = _FakeClient(
        {
            "/api/health": _FakeResponse(json_body={"status": "ok"}),
            "/api/auth/config": _FakeResponse(json_body={"auth_mode": "telegram", "bot_token": "secret"}),
            "/api/public/catalog": _FakeResponse(json_body=[]),
            "/": _FakeResponse(headers={"content-type": "text/html"}, json_body="<html></html>"),
        }
    )

    with pytest.raises(AssertionError, match="bot_token"):
        module.smoke(client)
