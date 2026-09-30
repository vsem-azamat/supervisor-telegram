"""initData verification.

This is the whole of authentication, so it gets tested against real signatures
rather than through the development bypass. The payloads below are signed the
way Telegram signs them.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest

from students_cz.core.config import Settings
from students_cz.core.security import InitDataError, parse_init_data

BOT_TOKEN = "123456:TEST-TOKEN-not-a-real-one"


def sign(fields: dict[str, str], token: str = BOT_TOKEN) -> str:
    """Produce initData the way Telegram does.

    secret = HMAC(key="WebAppData", msg=bot_token), then the payload is signed
    with that secret over the fields sorted by name and joined with newlines.
    """
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


def payload(
    *,
    age: timedelta = timedelta(minutes=1),
    tg_id: int = 4242,
    **extra: str,
) -> dict[str, str]:
    user = {"id": tg_id, "first_name": "Тест", "language_code": "ru"}
    return {
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
        "auth_date": str(int((datetime.now(UTC) - age).timestamp())),
        **extra,
    }


def settings(**overrides) -> Settings:
    # _env_file=None so the developer's own .env cannot change the outcome.
    values = {"bot_token": BOT_TOKEN, "allow_unsigned_init_data": False} | overrides
    # ty: ignore[invalid-argument-type] — a **dict of mixed value types cannot
    # be matched against the individual fields it is spread over.
    return Settings(_env_file=None, **values)


def test_a_correctly_signed_payload_is_accepted():
    identity = parse_init_data(sign(payload()), settings())
    assert identity.tg_id == 4242
    assert identity.first_name == "Тест"
    assert identity.language_code == "ru"


def test_a_tampered_payload_is_rejected():
    raw = sign(payload(tg_id=1))
    forged = raw.replace("%22id%22%3A1", "%22id%22%3A999")
    assert forged != raw
    with pytest.raises(InitDataError, match="invalid init data"):
        parse_init_data(forged, settings())


def test_a_payload_signed_with_another_token_is_rejected():
    raw = sign(payload(), token="999:SOMEONE-ELSES-BOT")
    with pytest.raises(InitDataError, match="invalid init data"):
        parse_init_data(raw, settings())


def test_a_stale_payload_is_rejected():
    """aiogram verifies the signature and never looks at auth_date.

    A two-day-old payload passes its check happily, so the freshness window is
    enforced here or nowhere.
    """
    raw = sign(payload(age=timedelta(days=2)))
    with pytest.raises(InitDataError, match="expired"):
        parse_init_data(raw, settings())


def test_the_window_is_configurable():
    raw = sign(payload(age=timedelta(hours=2)))
    assert parse_init_data(raw, settings()).tg_id == 4242
    with pytest.raises(InitDataError, match="expired"):
        parse_init_data(raw, settings(init_data_max_age_seconds=60))


def test_a_payload_from_the_future_is_rejected():
    """A clock far enough ahead would hand out a payload that outlives its window."""
    raw = sign(payload(age=timedelta(hours=-2)))
    with pytest.raises(InitDataError, match="future"):
        parse_init_data(raw, settings())


def test_a_slash_in_start_param_survives():
    """The failure that rules out the popular third-party validator.

    init-data-py escapes slashes across the whole check string, so any
    start_param containing one — an ordinary referral deep link — fails
    verification for a legitimate user.
    """
    raw = sign(payload(start_param="ref/abc/123"))
    identity = parse_init_data(raw, settings())
    assert identity.start_param == "ref/abc/123"


def test_an_unknown_field_does_not_break_verification():
    """Telegram adds fields over time; a validator must not die when it does."""
    raw = sign(payload(signature="whatever", chat_type="private"))
    assert parse_init_data(raw, settings()).tg_id == 4242


def test_empty_init_data_is_rejected():
    with pytest.raises(InitDataError, match="empty"):
        parse_init_data("", settings())


def test_without_a_bot_token_nothing_is_accepted_by_default():
    with pytest.raises(InitDataError, match="no bot token"):
        parse_init_data(sign(payload()), settings(bot_token=""))


def test_the_development_bypass_needs_to_be_asked_for():
    unsigned = urlencode({"user": json.dumps({"id": 7, "first_name": "Dev"})})
    permissive = settings(bot_token="", allow_unsigned_init_data=True)
    assert parse_init_data(unsigned, permissive).tg_id == 7

    with pytest.raises(InitDataError):
        parse_init_data(unsigned, settings(bot_token=""))


def test_the_development_bypass_still_refuses_nonsense():
    permissive = settings(bot_token="", allow_unsigned_init_data=True)
    with pytest.raises(InitDataError):
        parse_init_data(urlencode({"user": "{not json"}), permissive)
    with pytest.raises(InitDataError):
        parse_init_data(
            urlencode({"user": json.dumps({"first_name": "No id"})}), permissive
        )
    with pytest.raises(InitDataError):
        parse_init_data(urlencode({"user": json.dumps({"id": "abc"})}), permissive)
