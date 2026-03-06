"""Markdown → Telegram entities conversion.

Uses telegramify-markdown to parse standard Markdown (as LLMs output it)
into plain text + MessageEntity objects. This avoids parse_mode entirely —
no HTML escaping, no MarkdownV2 escaping headaches.
"""

from __future__ import annotations

from aiogram.types import MessageEntity
from telegramify_markdown import convert, split_entities  # type: ignore[import-untyped]


def md_to_entities(text: str) -> tuple[str, list[MessageEntity]]:
    """Convert Markdown text to plain text + aiogram MessageEntity list."""
    plain, raw_entities = convert(text)
    return plain, [MessageEntity(**e.to_dict()) for e in raw_entities]


def md_to_entities_chunked(
    text: str,
    max_len: int = 4096,
) -> list[tuple[str, list[MessageEntity]]]:
    """Convert Markdown and split into Telegram-safe chunks.

    Each chunk is a (text, entities) tuple ready for bot.send_message().
    """
    plain, raw_entities = convert(text)

    if len(plain) <= max_len:
        return [(plain, [MessageEntity(**e.to_dict()) for e in raw_entities])]

    chunks = []
    for chunk_text, chunk_entities in split_entities(plain, raw_entities, max_utf16_len=max_len):
        chunks.append((chunk_text, [MessageEntity(**e.to_dict()) for e in chunk_entities]))
    return chunks
