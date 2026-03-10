"""Magic link authentication for the webapp API."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import TypedDict

_TOKEN_EXPIRY_HOURS = 24


class TokenInfo(TypedDict):
    """Stored token metadata."""

    email: str
    role: str
    expires_at: datetime


# In-memory token store: token_string -> TokenInfo
_tokens: dict[str, TokenInfo] = {}


_MAX_TOKENS = 1000


def _evict_expired_tokens() -> None:
    """Remove all expired tokens to prevent unbounded memory growth."""
    now = datetime.now(tz=UTC)
    expired = [t for t, info in _tokens.items() if now > info["expires_at"]]
    for t in expired:
        del _tokens[t]


def generate_magic_link(email: str, role: str = "viewer") -> str:
    """Generate a magic link token for *email* with the given *role*.

    The token is a URL-safe random string valid for 24 hours.
    """
    # Evict expired tokens to bound memory usage
    _evict_expired_tokens()

    # Hard cap: reject if too many active tokens
    if len(_tokens) >= _MAX_TOKENS:
        # Remove oldest token to make room
        oldest = min(_tokens, key=lambda t: _tokens[t]["expires_at"])
        del _tokens[oldest]

    token = secrets.token_urlsafe(32)
    _tokens[token] = TokenInfo(
        email=email,
        role=role,
        expires_at=datetime.now(tz=UTC) + timedelta(hours=_TOKEN_EXPIRY_HOURS),
    )
    return token


def validate_token(token: str) -> dict[str, str] | None:
    """Return user info ``{"email": ..., "role": ...}`` or *None* if invalid/expired."""
    info = _tokens.get(token)
    if info is None:
        return None
    if datetime.now(tz=UTC) > info["expires_at"]:
        # Clean up expired token
        _tokens.pop(token, None)
        return None
    return {"email": info["email"], "role": info["role"]}


def revoke_token(token: str) -> None:
    """Explicitly remove a token."""
    _tokens.pop(token, None)


def clear_tokens() -> None:
    """Remove all tokens (useful for testing)."""
    _tokens.clear()
