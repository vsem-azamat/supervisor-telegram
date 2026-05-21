"""Text normalization shared by ad-review dedup and cross-chat cleanup."""

from __future__ import annotations


def normalize_text(text: str | None) -> str:
    """Return a comparison-friendly form: trimmed, whitespace-collapsed, casefolded."""
    if not text:
        return ""
    return " ".join(text.split()).casefold()
