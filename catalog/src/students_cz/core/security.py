"""Telegram initData validation.

aiogram ships the signature check, so there is no reason to add a third-party
package for it — and good reason not to: the popular `init-data-py` escapes
slashes across the whole data-check string, which rejects any `start_param`
containing one (an ordinary referral deep link), and it raises on unknown
top-level fields, so it breaks the day Telegram adds one.

What aiogram does *not* do is check `auth_date`. A payload from two days ago
passes its signature check happily. The freshness window is ours to enforce.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data

from students_cz.core.config import Settings


class InitDataError(Exception):
    """initData is missing, malformed, unsigned, forged or stale."""


@dataclass(frozen=True)
class TelegramIdentity:
    tg_id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None
    photo_url: str | None
    start_param: str | None
    # Telegram's `allows_write_to_pm`: this person let the bot message them.
    # The only record of that we have, now that /start is the moderator bot's.
    may_write: bool = False

    @classmethod
    def from_init_data(cls, data: WebAppInitData) -> "TelegramIdentity":
        user = data.user
        if user is None:
            raise InitDataError("init data carries no user")
        return cls(
            tg_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            language_code=user.language_code,
            photo_url=user.photo_url,
            start_param=data.start_param,
            may_write=bool(user.allows_write_to_pm),
        )


def parse_init_data(raw: str, settings: Settings) -> TelegramIdentity:
    """Verify a raw initData string and return who sent it.

    Raises :class:`InitDataError` for anything that is not a fresh, correctly
    signed payload.
    """
    if not raw:
        raise InitDataError("empty init data")

    if not settings.bot_token:
        if not settings.allow_unsigned_init_data:
            raise InitDataError("server has no bot token configured")
        return _parse_unsigned(raw)

    try:
        data = safe_parse_webapp_init_data(settings.bot_token, raw)
    except ValueError as exc:
        raise InitDataError(f"invalid init data: {exc}") from exc

    age = (datetime.now(UTC) - data.auth_date).total_seconds()
    if age > settings.init_data_max_age_seconds:
        raise InitDataError(
            f"init data expired ({age:.0f}s > {settings.init_data_max_age_seconds}s)"
        )
    if age < -300:
        # More than five minutes in the future means a broken clock somewhere,
        # and a payload that would then outlive its window.
        raise InitDataError("init data is dated in the future")

    return TelegramIdentity.from_init_data(data)


def _parse_unsigned(raw: str) -> TelegramIdentity:
    """Development escape hatch: read initData without verifying anything.

    Only reachable when there is no bot token *and* ALLOW_UNSIGNED_INIT_DATA is
    on. It exists so the API can be exercised from a browser before a bot is
    registered, and for nothing else.
    """
    import json
    from urllib.parse import parse_qsl

    fields = dict(parse_qsl(raw))
    try:
        user = json.loads(fields.get("user", "{}"))
    except json.JSONDecodeError as exc:
        raise InitDataError("unparsable user field") from exc
    try:
        tg_id = int(user["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InitDataError("unsigned init data has no usable user id") from exc
    return TelegramIdentity(
        tg_id=tg_id,
        first_name=user.get("first_name") or "Anonymous",
        last_name=user.get("last_name"),
        username=user.get("username"),
        language_code=user.get("language_code"),
        photo_url=user.get("photo_url"),
        start_param=fields.get("start_param"),
    )
