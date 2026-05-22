"""Rendering for the rate-card and advertiser-outreach messages (HTML)."""

from __future__ import annotations

import html

from app.core.config import settings
from app.core.text import escape_html

_CATALOG_PATH = "/catalog"


def advertising_catalog_url() -> str | None:
    """Public site catalog URL with all chats, if the web UI base URL is configured."""
    base = settings.webapi.public_url.rstrip("/")
    if not base:
        return None
    return f"{base}{_CATALOG_PATH}"


def render_rate_card() -> str:
    """Public advertising info shown by /ads and the smart link."""
    lines = [
        "📢 <b>Реклама в наших чатах</b>",
        "",
        "Можно разместить промо в наших студенческих чатах, если оно полезно аудитории и согласовано заранее.",
        "Мы не публикуем спам, серые офферы и массовые сообщения без согласования.",
        "",
        "Посмотрите список чатов и выберите площадки, которые подходят вашему предложению.",
    ]
    catalog_url = advertising_catalog_url()
    if catalog_url:
        lines.append(
            # href attribute: quote-escape so a stray " can't break out
            f'Каталог чатов: <a href="{html.escape(catalog_url)}">открыть на сайте</a>.'
        )
    if settings.sponsored_ads.sales_contact:
        lines.append(f"По вопросам размещения: {escape_html(settings.sponsored_ads.sales_contact)}")
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
