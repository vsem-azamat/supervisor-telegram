"""Telegram Login Widget signature verification.

Widget payload contract (per https://core.telegram.org/widgets/login#checking-authorization):

  1. Build a data-check-string = "\n".join(sorted(f"{k}={v}" for k,v in payload if k != 'hash'))
  2. secret = sha256(bot_token).digest()
  3. check_hash = hmac_sha256(secret, data_check_string).hexdigest()
  4. constant-time compare with payload['hash']; also reject if auth_date older than 24h.

Single-tenant; we additionally check user_id in super_admins at the caller.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
from typing import TYPE_CHECKING

from app.core.exceptions import DomainError
from app.core.time import utc_now

if TYPE_CHECKING:
    from collections.abc import Mapping


class LoginWidgetError(DomainError):
    """Raised when a Telegram Login payload fails verification."""


_MAX_AUTH_AGE_SECONDS = 24 * 3600


def verify_login_payload(payload: Mapping[str, str], *, bot_token: str, now: datetime.datetime | None = None) -> int:
    """Return the authenticated ``user_id`` or raise :class:`LoginWidgetError`.

    Expected keys (all stringified by the widget): id, auth_date, hash; optional:
    first_name, last_name, username, photo_url.
    """
    if "hash" not in payload or "id" not in payload or "auth_date" not in payload:
        raise LoginWidgetError("missing required fields")
    claimed_hash = payload["hash"]

    data_check = "\n".join(f"{k}={payload[k]}" for k in sorted(payload) if k != "hash")
    secret = hashlib.sha256(bot_token.encode("utf-8")).digest()
    computed = hmac.new(secret, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, claimed_hash):
        raise LoginWidgetError("signature mismatch")

    try:
        auth_epoch = int(payload["auth_date"])
    except ValueError as err:
        raise LoginWidgetError("auth_date not an integer") from err
    current = now or utc_now()
    age_seconds = (
        current - datetime.datetime.fromtimestamp(auth_epoch, tz=datetime.UTC).replace(tzinfo=None)
    ).total_seconds()
    if age_seconds > _MAX_AUTH_AGE_SECONDS or age_seconds < -300:
        raise LoginWidgetError("auth_date out of range")

    try:
        return int(payload["id"])
    except ValueError as err:
        raise LoginWidgetError("id not an integer") from err
