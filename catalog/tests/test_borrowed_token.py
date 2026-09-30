"""The token is the moderator bot's, and so are its updates.

`supervisor-telegram` receives them by polling, and Telegram gives a token one
consumer. So this process may send through the token and check `initData`
with it, and must never ask for updates or reshape the bot's chat: a webhook
set from here stops the moderator's polling, and a command list or menu button
set from here overwrites the moderator's. See docs/architecture.md.
"""

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from students_cz.core.config import Settings

pytestmark = pytest.mark.asyncio


class RecordingBot:
    """Records every Telegram method the process calls on it."""

    def __init__(self) -> None:
        self.called: list[str] = []
        self.session = self

    async def close(self) -> None:
        """What the lifespan calls on the bot's HTTP session at shutdown."""

    def __getattr__(self, name: str):
        async def call(*_: object, **__: object) -> None:
            self.called.append(name)

        return call


async def test_a_process_holding_the_token_asks_telegram_for_nothing(
    monkeypatch, settings
) -> None:
    import students_cz.main as main

    bot = RecordingBot()
    borrowed = settings.model_copy(
        update={
            "bot_token": "123456:borrowed",
            "public_base_url": "https://tests.example",
        }
    )
    monkeypatch.setattr(main, "get_settings", lambda: borrowed)
    monkeypatch.setattr(main, "build_bot", lambda _: bot)

    app = FastAPI()
    async with main.lifespan(app):
        # Long enough for any background work to have started.
        await asyncio.sleep(0.2)
        assert app.state.bot is bot, "notifications need the bot to send through"

    # Nothing at all, not merely nothing from a list: set_my_description,
    # log_out or close would change or break the moderator bot just as surely.
    assert bot.called == [], bot.called


async def test_there_is_no_address_for_updates_to_arrive_at() -> None:
    from students_cz.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.post("/tg/webhook", json={"update_id": 1})

    assert response.status_code == 404


# ── who may be written to ──────────────────────────────────────────────
# Our own /start used to record it; now Telegram's signed initData says it.


def _signed_open(*, allows_write: bool | None) -> tuple[str, Settings]:
    from tests.test_security import BOT_TOKEN, payload, settings, sign

    fields = payload()
    if allows_write is not None:
        import json

        user = json.loads(fields["user"])
        user["allows_write_to_pm"] = allows_write
        fields["user"] = json.dumps(user, separators=(",", ":"), ensure_ascii=False)
    return sign(fields, BOT_TOKEN), settings()


async def test_initdata_that_allows_writing_says_so() -> None:
    from students_cz.core.security import parse_init_data

    raw, config = _signed_open(allows_write=True)
    assert parse_init_data(raw, config).may_write is True


async def test_initdata_without_the_permission_does_not_claim_it() -> None:
    from students_cz.core.security import parse_init_data

    raw, config = _signed_open(allows_write=None)
    assert parse_init_data(raw, config).may_write is False


async def test_opening_the_app_with_permission_makes_somebody_reachable(session) -> None:
    from students_cz.services.notify import Recipient
    from students_cz.services.people import remember

    user = await remember(
        session, tg_id=770001, first_name="Ada", supported_langs=("ru",), may_write=True
    )
    assert user.bot_started_at is not None
    assert Recipient.of(user).reachable


async def test_opening_it_without_permission_does_not(session) -> None:
    from students_cz.services.notify import Recipient
    from students_cz.services.people import remember

    user = await remember(session, tg_id=770002, first_name="Bo", supported_langs=("ru",))
    assert not Recipient.of(user).reachable


async def test_the_app_passes_telegrams_permission_on_to_the_record(session) -> None:
    """The wiring, not the two halves: initData in, a reachable person out."""
    from students_cz.api.deps import current_user
    from students_cz.core.security import parse_init_data
    from students_cz.services.notify import Recipient

    raw, config = _signed_open(allows_write=True)
    identity = parse_init_data(raw, config)

    user = await current_user(identity, session, config)

    assert user.bot_started_at is not None
    assert Recipient.of(user).reachable
