"""Rendering for the rate-card and advertiser-outreach messages (HTML)."""

from __future__ import annotations

import html

from app.core.config import settings
from app.core.text import escape_html


def render_rate_card() -> str:
    """Public advertising info shown by /ads and the smart link."""
    cfg = settings.sponsored_ads
    lines = [
        "📢 <b>Реклама в наших чатах</b>",
        "",
        "Хотите разместить рекламу легально? Возможно платное размещение.",
    ]
    if cfg.pricing_article_url:
        lines.append(
            # href attribute: quote-escape so a stray " can't break out
            f'Цены, условия и список чатов: <a href="{html.escape(cfg.pricing_article_url)}">подробнее тут</a>.'
        )
    if cfg.sales_contact:
        lines.append(f"По вопросам размещения: {escape_html(cfg.sales_contact)}")
    return "\n".join(lines)


def render_outreach_message(smart_link: str) -> str:
    """DM text sent to a would-be advertiser after their ad is removed."""
    return (
        "👋 Ваше сообщение выглядело как реклама и было удалено — "
        "здесь реклама запрещена.\n\n"
        f"Хотите разместить рекламу легально? "
        # href attribute: quote-escape so a stray " can't break out
        f'<a href="{html.escape(smart_link)}">Узнать про платное размещение</a>.'
    )


def render_ping_message(user_id: int, smart_link: str) -> str:
    """Public group ping used when the advertiser cannot be reached by DM."""
    mention = f'<a href="tg://user?id={user_id}">Пользователь</a>'
    return (
        f"{mention}, реклама в этом чате запрещена. "
        f"Хотите разместить легально? "
        # href attribute: quote-escape so a stray " can't break out
        f'<a href="{html.escape(smart_link)}">Узнать про платное размещение</a>.'
    )
