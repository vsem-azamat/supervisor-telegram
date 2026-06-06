from app.core.config import WebApiSettings


def test_magic_link_auth_does_not_require_login_start_payload_env() -> None:
    settings = WebApiSettings(auth_mode="magic_link")

    assert settings.auth_mode == "magic_link"
    assert not hasattr(settings, "login_start_payload")
