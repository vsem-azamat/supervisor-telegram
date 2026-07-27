"""Application-wide singleton holder.

Three long-lived objects the bot process wires once at startup: the session
maker, the bot, and the Telethon client. Not a DI container — the generic
register/resolve API it once had never had a caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.telethon.telethon_client import TelethonClient


class Container:
    """Holds the long-lived singletons wired at bot startup."""

    def __init__(self) -> None:
        self._session_maker: async_sessionmaker[AsyncSession] | None = None
        self._bot: Bot | None = None
        self._telethon_client: TelethonClient | None = None

    def set_session_maker(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    def get_session_maker(self) -> async_sessionmaker[AsyncSession]:
        if not self._session_maker:
            raise ValueError("Session maker not set")
        return self._session_maker

    def set_bot(self, bot: Bot) -> None:
        self._bot = bot

    def get_bot(self) -> Bot:
        if not self._bot:
            raise ValueError("Bot not set")
        return self._bot

    def try_get_bot(self) -> Bot | None:
        return self._bot

    def set_telethon_client(self, client: TelethonClient) -> None:
        self._telethon_client = client

    def get_telethon_client(self) -> TelethonClient | None:
        return self._telethon_client


container = Container()


def setup_container(session_maker: async_sessionmaker[AsyncSession], bot: Bot) -> None:
    container.set_session_maker(session_maker)
    container.set_bot(bot)
