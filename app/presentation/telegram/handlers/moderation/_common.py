"""Shared helpers for the moderation handlers."""


def reply_required_error(action: str) -> str:
    """Standard error when a command should be a reply."""
    return f"Примените команду ответом на сообщение пользователя, которого нужно {action}. 🙏"


def is_user_check_error() -> str:
    """Standard error when target message does not contain a user."""
    return "🚫 Это не пользователь или что-то пошло не так."
