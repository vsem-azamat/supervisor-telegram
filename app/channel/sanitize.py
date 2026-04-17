"""Shared sanitization utilities for the channel content pipeline."""

from __future__ import annotations

import re

_XML_HTML_TAG_RE = re.compile(r"<[^>]+>")


def sanitize_external_text(text: str) -> str:
    """Sanitize external content to prevent prompt injection.

    1. Escape ``<content_item>`` / ``</content_item>`` boundary markers so external
       text cannot break out of the data sandbox in prompts.
    2. Strip remaining XML/HTML tags.
    """
    # Neutralise the specific boundary markers used in prompts
    text = text.replace("</content_item>", "[/content_item]")
    text = text.replace("<content_item>", "[content_item]")
    text = text.replace("</user_message>", "[/user_message]")
    text = text.replace("<user_message>", "[user_message]")
    return _XML_HTML_TAG_RE.sub("", text)


def substitute_template(template: str, **kwargs: str) -> str:
    """Atomically substitute all ``{key}`` placeholders in *template*.

    Unlike chained ``.replace()`` calls, this applies all replacements to the
    *original* template — so a value that contains another placeholder name
    will NOT be double-substituted.
    """
    # Build regex that matches any of the placeholder keys
    if not kwargs:
        return template

    # Use a single re.sub pass for atomic replacement
    pattern = re.compile("|".join(re.escape(f"{{{k}}}") for k in kwargs))
    return pattern.sub(lambda m: kwargs[m.group(0)[1:-1]], template)
