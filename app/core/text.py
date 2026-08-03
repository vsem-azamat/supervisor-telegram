"""Core text utilities — layer-independent, no Telegram/aiogram dependency."""

from __future__ import annotations

import html


def escape_html(text: str) -> str:
    """Escape HTML special characters in user-controlled text.

    This MUST be used whenever user-supplied data (display names, usernames,
    message text, etc.) is interpolated into strings sent with parse_mode="HTML".
    """
    return html.escape(text, quote=False)


def plural(count: int, one: str, few: str, many: str) -> str:
    """Pick the Russian ending for a count.

    Russian has three, and picking between two of them is the tell that nobody
    read the string out loud: eleven is "чатов" while twenty-one is "чат", and a
    ternary gets both wrong. The web side spells the same rule in
    `$lib/format.plural`; a bot message and a page describing the same number
    should not disagree about how to say it.
    """
    tail_two = abs(count) % 100
    if 11 <= tail_two <= 14:
        return many
    tail = tail_two % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many
