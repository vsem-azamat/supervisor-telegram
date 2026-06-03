import pytest
from app.core.config import WebApiSettings
from pydantic import ValidationError


def test_login_start_payload_accepts_telegram_safe_payload() -> None:
    settings = WebApiSettings(login_start_payload="admin-login_123")

    assert settings.login_start_payload == "admin-login_123"


def test_magic_link_auth_requires_login_start_payload() -> None:
    with pytest.raises(ValidationError, match="login_start_payload"):
        WebApiSettings(auth_mode="magic_link")


@pytest.mark.parametrize("payload", ["has space", "x&admin=1", "frag#ment", "x" * 65, "ads", "adlead_123"])
def test_login_start_payload_rejects_invalid_deep_link_payload(payload: str) -> None:
    with pytest.raises(ValidationError, match="login_start_payload"):
        WebApiSettings(login_start_payload=payload)
