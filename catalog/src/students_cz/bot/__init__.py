"""The bot this process sends through, and nothing more.

The token is the Konnekt moderator bot's (`supervisor-telegram`), and that
process receives its updates. Here there is no dispatcher, no handler and no
webhook: the greeting, the command list and the menu button are the
moderator's. See docs/architecture.md.
"""

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from students_cz.core.config import Settings


def build_bot(settings: Settings) -> Bot:
    return Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
