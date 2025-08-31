"""Telegram WebApp authentication utilities."""

import hashlib
import hmac
import json
from typing import Any
from urllib.parse import parse_qsl, unquote

from fastapi import Header, HTTPException
from pydantic import BaseModel

from app.core.config import settings


class TelegramUser(BaseModel):
    """Telegram user data from WebApp."""

    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool | None = None
    allows_write_to_pm: bool | None = None


class WebAppInitData(BaseModel):
    """Parsed Telegram WebApp init data."""

    query_id: str | None = None
    user: TelegramUser | None = None
    receiver: TelegramUser | None = None
    chat: dict[str, Any] | None = None
    chat_type: str | None = None
    chat_instance: str | None = None
    start_param: str | None = None
    can_send_after: int | None = None
    auth_date: int
    hash: str


def validate_telegram_webapp_data(init_data: str, bot_token: str) -> WebAppInitData:
    """
    Validate Telegram WebApp init data according to official documentation.

    Args:
        init_data: Raw init data string from Telegram WebApp
        bot_token: Bot token for HMAC validation

    Returns:
        Parsed and validated init data

    Raises:
        HTTPException: If validation fails
    """
    try:
        # Parse query string
        parsed_data = dict(parse_qsl(init_data))

        # Extract hash
        received_hash = parsed_data.pop("hash", None)
        if not received_hash:
            raise HTTPException(status_code=401, detail="Missing hash in init data")

        # Create data-check-string
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed_data.items()))

        # Create secret key
        secret_key = hmac.new(key=b"WebAppData", msg=bot_token.encode(), digestmod=hashlib.sha256).digest()

        # Calculate expected hash
        expected_hash = hmac.new(key=secret_key, msg=data_check_string.encode(), digestmod=hashlib.sha256).hexdigest()

        # Compare hashes
        if not hmac.compare_digest(expected_hash, received_hash):
            raise HTTPException(status_code=401, detail="Invalid init data signature")

        # Parse user data if present
        user_data = None
        if "user" in parsed_data:
            try:
                user_dict = json.loads(unquote(parsed_data["user"]))
                user_data = TelegramUser.model_validate(user_dict)
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(status_code=401, detail=f"Invalid user data: {e}") from e

        # Parse other data
        chat_data = None
        if "chat" in parsed_data:
            try:
                chat_data = json.loads(unquote(parsed_data["chat"]))
            except json.JSONDecodeError:
                chat_data = None

        return WebAppInitData(
            query_id=parsed_data.get("query_id"),
            user=user_data,
            receiver=None,  # Not commonly used
            chat=chat_data,
            chat_type=parsed_data.get("chat_type"),
            chat_instance=parsed_data.get("chat_instance"),
            start_param=parsed_data.get("start_param"),
            can_send_after=int(parsed_data["can_send_after"]) if parsed_data.get("can_send_after") else None,
            auth_date=int(parsed_data["auth_date"]),
            hash=received_hash,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Failed to validate init data: {e}") from e


def get_current_admin_user(x_telegram_init_data: str = Header(alias="X-Telegram-Init-Data")) -> dict[str, Any]:
    """
    Get current authenticated admin user from Telegram WebApp init data.

    Args:
        x_telegram_init_data: Telegram WebApp init data from header

    Returns:
        Admin user info

    Raises:
        HTTPException: If authentication fails
    """
    # Validate init data
    init_data = validate_telegram_webapp_data(x_telegram_init_data, settings.telegram.token)

    if not init_data.user:
        raise HTTPException(status_code=401, detail="No user data in init data")

    # Check if user is super admin
    if init_data.user.id not in settings.admin.super_admins:
        raise HTTPException(status_code=403, detail="Access denied: user is not a super admin")

    return {
        "id": init_data.user.id,
        "username": init_data.user.username,
        "first_name": init_data.user.first_name,
        "last_name": init_data.user.last_name,
        "is_super_admin": True,
        "telegram_data": init_data.model_dump(),
    }


# Legacy function for backward compatibility - will be removed
async def get_current_admin_user_legacy() -> dict[str, Any]:
    """
    Legacy mock authentication.
    DEPRECATED: Use get_current_admin_user instead.
    """
    if settings.admin.super_admins:
        admin_id = settings.admin.super_admins[0]
        return {"id": admin_id, "is_super_admin": True, "legacy": True}
    raise HTTPException(status_code=401, detail="No authenticated admin user")
