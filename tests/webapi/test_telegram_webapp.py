"""Mini App initData verification.

Not the same algorithm as Telegram's Login Widget, and the difference is one
line: the widget derives its secret as ``sha256(bot_token)``, a Mini App as
``hmac(key="WebAppData", msg=bot_token)``. Signing with the widget's derivation
fails every signature here, and "fixing" that by loosening the check is how a
Mini App ends up trusting whatever the caller claims.

This is now the only way into the console, so these are the checks the whole
admin surface rests on.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest
from app.webapi.auth.telegram_webapp import InitDataError, verify_init_data

pytestmark = pytest.mark.unit

BOT_TOKEN = "123456:ABC-DEF1234567890"  # noqa: S105 — test fixture
USER_ID = 4242


def _epoch() -> int:
    """Seconds since the epoch, from an aware clock.

    Not `utc_now().timestamp()`: utc_now() is naive by design, for PostgreSQL's
    timestamp-without-time-zone columns, and .timestamp() on a naive value
    reads it as local time.
    """
    return int(datetime.datetime.now(datetime.UTC).timestamp())


def _sign(fields: dict[str, str], *, token: str = BOT_TOKEN) -> str:
    """Build a valid initData string the way Telegram does."""
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


def _fields(*, user_id: int = USER_ID, auth_date: int | None = None) -> dict[str, str]:
    return {
        "auth_date": str(auth_date if auth_date is not None else _epoch()),
        "query_id": "AAF-test",
        "user": json.dumps({"id": user_id, "first_name": "Applicant", "is_bot": False}),
    }


class TestAccepts:
    def test_a_genuine_payload_yields_the_user(self) -> None:
        result = verify_init_data(_sign(_fields()), bot_token=BOT_TOKEN)

        assert result.user_id == USER_ID
        assert result.first_name == "Applicant"

    def test_unknown_fields_are_part_of_the_signature(self) -> None:
        """Telegram adds fields over time; they must sign, not be dropped."""
        fields = _fields() | {"chat_type": "private", "start_param": "q-7"}

        result = verify_init_data(_sign(fields), bot_token=BOT_TOKEN)

        assert result.user_id == USER_ID
        assert result.start_param == "q-7"


class TestRejects:
    def test_a_forged_hash(self) -> None:
        raw = _sign(_fields())
        forged = raw.replace(raw[-8:], "0" * 8)

        with pytest.raises(InitDataError):
            verify_init_data(forged, bot_token=BOT_TOKEN)

    def test_a_payload_signed_with_another_token(self) -> None:
        raw = _sign(_fields(), token="999:ZZZ-WRONG0987654321")

        with pytest.raises(InitDataError):
            verify_init_data(raw, bot_token=BOT_TOKEN)

    def test_a_tampered_user_id(self) -> None:
        """The signature covers the user, so impersonation has to fail."""
        raw = _sign(_fields())
        tampered = raw.replace(str(USER_ID), "1")

        with pytest.raises(InitDataError):
            verify_init_data(tampered, bot_token=BOT_TOKEN)

    def test_a_missing_hash(self) -> None:
        with pytest.raises(InitDataError):
            verify_init_data(urlencode(_fields()), bot_token=BOT_TOKEN)

    def test_an_empty_payload(self) -> None:
        with pytest.raises(InitDataError):
            verify_init_data("", bot_token=BOT_TOKEN)

    def test_a_stale_payload(self) -> None:
        old = _epoch() - 7200

        with pytest.raises(InitDataError):
            verify_init_data(_sign(_fields(auth_date=old)), bot_token=BOT_TOKEN, max_age_seconds=3600)

    def test_a_payload_from_the_future(self) -> None:
        ahead = _epoch() + 3600

        with pytest.raises(InitDataError):
            verify_init_data(_sign(_fields(auth_date=ahead)), bot_token=BOT_TOKEN)

    def test_an_empty_bot_token(self) -> None:
        """An unconfigured deployment must refuse rather than derive a secret."""
        with pytest.raises(InitDataError):
            verify_init_data(_sign(_fields()), bot_token="")


class TestSignatureField:
    def test_the_ed25519_signature_is_excluded_from_the_check_string(self) -> None:
        """Telegram's third-party `signature` is not part of the HMAC input.

        Including it would break every real payload from a current client.
        """
        fields = _fields()
        raw = _sign(fields) + "&signature=" + "A" * 32

        assert verify_init_data(raw, bot_token=BOT_TOKEN).user_id == USER_ID
