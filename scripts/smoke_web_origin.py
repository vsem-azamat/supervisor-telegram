"""Smoke-check a public web origin against the deployment routing contract.

Usage:
    uv run python scripts/smoke_web_origin.py https://dev.konnekt.azamat.io
"""

import argparse
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError


class _Response(Protocol):
    status_code: int
    headers: dict[str, str]
    text: str

    def raise_for_status(self) -> None: ...
    def json(self) -> object: ...


class _Client(Protocol):
    def get(self, path: str) -> _Response: ...


class HealthContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]


class AuthConfigContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_mode: Literal["telegram", "magic_link"]
    bot_username: str | None = None
    bot_start_url: str | None = None


class PublicCatalogItemContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: Literal["chat", "channel"]
    id: int
    title: str
    subtitle: str | None = None


_catalog_contract = TypeAdapter(list[PublicCatalogItemContract])


def _json_contract(response: _Response, contract: type[BaseModel] | TypeAdapter[object]) -> object:
    response.raise_for_status()
    try:
        payload = response.json()
        if isinstance(contract, TypeAdapter):
            return contract.validate_python(payload)
        return contract.model_validate(payload)
    except ValidationError as exc:
        raise AssertionError(str(exc)) from exc


def smoke(client: _Client) -> None:
    _json_contract(client.get("/api/health"), HealthContract)
    _json_contract(client.get("/api/auth/config"), AuthConfigContract)
    _json_contract(client.get("/api/public/catalog"), _catalog_contract)

    root = client.get("/")
    root.raise_for_status()
    content_type = root.headers.get("content-type", "")
    if "text/html" not in content_type:
        raise AssertionError(f"expected HTML root response, got content-type {content_type!r}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", help="Public HTTPS origin, e.g. https://dev.konnekt.azamat.io")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    with httpx.Client(base_url=args.origin.rstrip("/"), follow_redirects=True, timeout=15) as client:
        smoke(client)
    print(f"ok: {args.origin}")


if __name__ == "__main__":
    main()
