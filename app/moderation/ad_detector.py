"""Ad / external-promotion detector.

v1 heuristic only — regex over message text. Two patterns:

  - t.me / telegram.me / telegram.dog links (with optional `joinchat/`
    or `+` invite prefixes)
  - bare @username mentions (Telegram username spec: 5–32 chars,
    starts with a letter, then letters/digits/underscores)

Matches are normalized to a canonical lowercase form (`@handle` for
mentions, `t.me/handle` for links) so the whitelist comparison and the
storage layer don't need to know about case or domain variation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

AdKind = Literal["link", "mention"]

_LINK_RE = re.compile(
    r"(?ix)(?<!\w)(?:https?://)?(?:t|telegram)\.(?:me|dog)/(?P<handle>(?:joinchat/|\+)?[A-Za-z0-9_-]+)"
)
_MENTION_RE = re.compile(r"(?<![\w@])@(?P<handle>[A-Za-z][A-Za-z0-9_]{4,31})\b")


@dataclass(frozen=True)
class AdSignal:
    kind: AdKind
    canonical: str  # whitelist-comparable form, e.g. "@konnekt_channel" or "t.me/somegroup"
    raw: str  # original substring as it appeared


def _normalize_whitelist(items: list[str]) -> set[str]:
    """Reduce each entry to its bare handle so `@foo`, `t.me/foo`, and `foo` collide.

    Returns a set of handles only. Callers test handle membership; both
    link and mention paths normalize to the same handle space, so
    whitelisting `@foo` also clears `t.me/foo` and vice versa.
    """
    out: set[str] = set()
    for raw in items:
        if not raw or not raw.strip():
            continue
        s = raw.strip().lower()
        if s.startswith("@"):
            s = s[1:]
        for prefix in ("https://", "http://"):
            if s.startswith(prefix):
                s = s[len(prefix) :]
        for prefix in ("t.me/", "telegram.me/", "telegram.dog/"):
            if s.startswith(prefix):
                s = s[len(prefix) :]
                break
        if s:
            out.add(s)
    return out


def extract_ad_signals(text: str | None, whitelist: list[str] | None = None) -> list[AdSignal]:
    """Return canonical ad signals found in `text`, excluding whitelisted handles.

    Returns an empty list for None / blank text. Order is preserved
    (links first then mentions, both in document order). Duplicates
    within the same call are collapsed by canonical form to keep the
    persisted row tidy.
    """
    if not text:
        return []
    wl = _normalize_whitelist(whitelist or [])

    seen: set[str] = set()
    signals: list[AdSignal] = []

    for m in _LINK_RE.finditer(text):
        handle = m.group("handle").lower()
        canonical = f"t.me/{handle}"
        if handle in wl:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        signals.append(AdSignal(kind="link", canonical=canonical, raw=m.group(0)))

    for m in _MENTION_RE.finditer(text):
        handle = m.group("handle").lower()
        canonical = f"@{handle}"
        if handle in wl:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        signals.append(AdSignal(kind="mention", canonical=canonical, raw=m.group(0)))

    return signals
