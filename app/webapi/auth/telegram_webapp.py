"""Telegram Mini App ``initData`` signature verification.

Contract (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app):

  1. data_check_string = "\\n".join(sorted(f"{k}={v}")) over every field except
     ``hash`` and ``signature``
  2. secret = HMAC_SHA256(key=b"WebAppData", msg=bot_token)
  3. compare HMAC_SHA256(key=secret, msg=data_check_string) against ``hash``
  4. reject a stale ``auth_date``

Step 2 is the one that catches people out: the Login Widget in
``telegram_login`` derives its secret as ``sha256(bot_token)`` instead, and the
two are not interchangeable. ``signature`` is excluded because it is Telegram's
Ed25519 field for third parties validating without the bot token, and it is not
part of the HMAC input.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

from app.core.exceptions import DomainError
from app.core.time import utc_now

_DEFAULT_MAX_AGE_SECONDS = 3600
_CLOCK_SKEW_SECONDS = 300


class InitDataError(DomainError):
    """Raised when an initData payload fails verification."""


@dataclass(frozen=True)
class WebAppUser:
    """The caller, as attested by Telegram's signature."""

    user_id: int
    first_name: str
    last_name: str | None
    username: str | None
    query_id: str | None
    start_param: str | None
    raw_user: dict[str, Any]


def verify_init_data(
    raw: str,
    *,
    bot_token: str,
    max_age_seconds: int = _DEFAULT_MAX_AGE_SECONDS,
    now: datetime.datetime | None = None,
) -> WebAppUser:
    """Return the verified caller, or raise :class:`InitDataError`.

    Every failure is the same exception on purpose: which check failed is
    useful to an attacker probing the endpoint and useless to a legitimate
    client, whose payload is built by Telegram itself.
    """
    if not bot_token:
        # Deriving a secret from an empty token would still produce a valid
        # HMAC, so an unconfigured deployment would verify attacker-signed data.
        raise InitDataError("bot token not configured")
    if not raw:
        raise InitDataError("empty payload")

    fields = dict(parse_qsl(raw, keep_blank_values=True))
    claimed_hash = fields.pop("hash", None)
    if not claimed_hash:
        raise InitDataError("missing hash")
    fields.pop("signature", None)

    data_check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    computed = hmac.new(secret, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, claimed_hash):
        raise InitDataError("signature mismatch")

    _check_freshness(fields.get("auth_date"), max_age_seconds=max_age_seconds, now=now)

    return _read_user(fields)


def _check_freshness(auth_date: str | None, *, max_age_seconds: int, now: datetime.datetime | None) -> None:
    if auth_date is None:
        raise InitDataError("missing auth_date")
    try:
        issued = int(auth_date)
    except ValueError as err:
        raise InitDataError("auth_date not an integer") from err

    current = now or utc_now()
    age = (current - datetime.datetime.fromtimestamp(issued, tz=datetime.UTC).replace(tzinfo=None)).total_seconds()
    if age > max_age_seconds or age < -_CLOCK_SKEW_SECONDS:
        raise InitDataError("auth_date out of range")


def _read_user(fields: dict[str, str]) -> WebAppUser:
    try:
        user = json.loads(fields.get("user", ""))
    except (json.JSONDecodeError, TypeError) as err:
        raise InitDataError("user field is not JSON") from err
    if not isinstance(user, dict) or "id" not in user:
        raise InitDataError("user field has no id")

    try:
        user_id = int(user["id"])
    except (TypeError, ValueError) as err:
        raise InitDataError("user id not an integer") from err

    return WebAppUser(
        user_id=user_id,
        first_name=str(user.get("first_name", "")),
        last_name=user.get("last_name"),
        username=user.get("username"),
        query_id=fields.get("query_id"),
        start_param=fields.get("start_param"),
        raw_user=user,
    )
