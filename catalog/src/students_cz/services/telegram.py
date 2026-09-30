"""What the process knows about its own bot.

One thing so far: the handle. It is asked for rather than configured, because
the token the API already runs with is the only place a bot's identity should
live — change the bot and neither the frontend nor the build needs to know.

A service and not three `getattr` defaults in a route. What is kept here is
per-process state rather than a value — the answer, and the cooldown that stops
a failing Telegram being asked again on every visit to the landing page — which
is why it is an object built once beside the bot rather than something a
handler assembles for itself. See docs/architecture.md.
"""

import logging
import time as clock
from collections.abc import Callable
from typing import Protocol

log = logging.getLogger("students_cz")

# Long enough that a Telegram outage costs one call rather than one per visitor,
# short enough that a bot that came back is usable within half a minute.
LOOKUP_COOLDOWN = 30.0


class BotUser(Protocol):
    """What Telegram says when asked who the token belongs to."""

    username: str | None


class SelfAware(Protocol):
    """The one thing `BotHandle` needs of a bot, so a test can be that much."""

    async def get_me(self) -> BotUser: ...


class BotHandle:
    """The bot's public handle, asked for once and remembered.

    A handle with no bot answers `None`, which is how the API runs locally,
    under test, and in any deployment without a token. That is a working
    handle that knows nothing, not an error — the same shape `Notifier` takes,
    and for the same reason: the caller would otherwise have to decide what a
    missing bot means, separately, every time.
    """

    def __init__(
        self,
        bot: SelfAware | None,
        *,
        cooldown: float = LOOKUP_COOLDOWN,
        clock: Callable[[], float] = clock.monotonic,
    ) -> None:
        self._bot = bot
        self._cooldown = cooldown
        self._clock = clock
        self._username: str | None = None
        self._quiet_until = 0.0

    async def username(self) -> str | None:
        if self._username:
            return self._username
        if self._bot is None:
            return None
        now = self._clock()
        if now < self._quiet_until:
            return None
        try:
            me = await self._bot.get_me()
        except Exception:
            self._quiet_until = now + self._cooldown
            log.warning("could not read the bot's own username", exc_info=True)
            return None
        if not me.username:
            # A bot without a public handle cannot be linked to at all. The
            # cooldown applies here too: nothing is cached, so without it every
            # visitor to the landing page would ask Telegram again.
            self._quiet_until = now + self._cooldown
            log.warning("the bot has no public username")
            return None
        self._username = me.username
        return self._username


__all__ = ["BotHandle", "BotUser", "SelfAware"]
