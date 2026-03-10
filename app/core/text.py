"""Core text utilities — layer-independent, no Telegram/aiogram dependency."""

from __future__ import annotations

import html


def escape_html(text: str) -> str:
    """Escape HTML special characters in user-controlled text.

    This MUST be used whenever user-supplied data (display names, usernames,
    message text, etc.) is interpolated into strings sent with parse_mode="HTML".
    """
    return html.escape(text, quote=False)
