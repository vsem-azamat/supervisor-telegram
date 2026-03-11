"""Shared sanitization utilities for the channel content pipeline."""

from __future__ import annotations

import re

_XML_HTML_TAG_RE = re.compile(r"<[^>]+>")


def sanitize_external_text(text: str) -> str:
    """Strip XML/HTML tags from external content to prevent prompt injection."""
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
