"""Telegram Login Widget HMAC verification."""

from __future__ import annotations

import datetime
import hashlib
import hmac

import pytest
from app.webapi.auth.telegram_login import LoginWidgetError, verify_login_payload


def _sign(payload: dict[str, str], bot_token: str) -> str:
    data_check = "\n".join(f"{k}={payload[k]}" for k in sorted(payload))
    secret = hashlib.sha256(bot_token.encode()).digest()
    return hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()


def test_valid_payload_returns_user_id() -> None:
    now = datetime.datetime(2026, 4, 22, 12, 0, 0)
    unsigned = {
        "id": "268388996",
        "auth_date": str(int(now.replace(tzinfo=datetime.UTC).timestamp())),
        "username": "azamat",
    }
    bot_token = "123:abc"  # noqa: S105
    unsigned["hash"] = _sign(unsigned, bot_token)

    assert verify_login_payload(unsigned, bot_token=bot_token, now=now) == 268388996


def test_tampered_payload_rejected() -> None:
    now = datetime.datetime(2026, 4, 22, 12, 0, 0)
    unsigned = {"id": "1", "auth_date": str(int(now.replace(tzinfo=datetime.UTC).timestamp()))}
    unsigned["hash"] = _sign(unsigned, "token-a")
    with pytest.raises(LoginWidgetError, match="signature"):
        verify_login_payload(unsigned, bot_token="token-b", now=now)


def test_old_auth_date_rejected() -> None:
    now = datetime.datetime(2026, 4, 22, 12, 0, 0)
    old = now - datetime.timedelta(hours=25)
    unsigned = {"id": "1", "auth_date": str(int(old.replace(tzinfo=datetime.UTC).timestamp()))}
    unsigned["hash"] = _sign(unsigned, "token")
    with pytest.raises(LoginWidgetError, match="auth_date"):
        verify_login_payload(unsigned, bot_token="token", now=now)


def test_missing_hash_rejected() -> None:
    with pytest.raises(LoginWidgetError, match="missing"):
        verify_login_payload({"id": "1", "auth_date": "1"}, bot_token="t")
