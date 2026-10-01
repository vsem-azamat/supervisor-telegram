"""What Telegram shows about the bot: its name, description and command menu.

Telegram keeps all of this on the bot, not in a message, so it is written at
startup like the menu button. Set by hand it drifted: the menu kept /spam after
its handler was gone, and the description kept the bot's old job.
"""

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeDefault,
    ChatAdministratorRights,
)

NAME = "Konnekt"
SHORT_DESCRIPTION = "Студенческие чаты Чехии и помощь с учёбой."
DESCRIPTION = (
    "Konnekt — студенческие чаты Чехии: по университетам, факультетам и общежитиям. "
    "За ними следят модераторы, спам вычищается.\n\n"
    "Здесь же люди, которые помогут с учёбой: репетиторы, přijímačky, нострификация.\n\n"
    "Нажмите «Открыть» или /start."
)

# What /help lists for everybody; moderator commands stay out of the menu,
# because being a Telegram administrator of a chat grants nothing here.
PRIVATE_COMMANDS = [
    BotCommand(command="start", description="Что здесь есть"),
    BotCommand(command="chats", description="Чаты списком"),
    BotCommand(command="help", description="Команды"),
    BotCommand(command="contacts", description="Связаться"),
]
GROUP_COMMANDS = [
    BotCommand(command="report", description="В ответ на сообщение: позвать модераторов"),
    BotCommand(command="chats", description="Чаты списком"),
    BotCommand(command="help", description="Команды"),
]

# What the bot asks for when somebody adds it as an administrator: exactly what
# its commands use — deleting, muting and banning, invite links for join
# checks, and pinning.
DEFAULT_ADMIN_RIGHTS = ChatAdministratorRights(
    is_anonymous=False,
    can_manage_chat=True,
    can_delete_messages=True,
    can_manage_video_chats=False,
    can_restrict_members=True,
    can_promote_members=False,
    can_change_info=False,
    can_invite_users=True,
    can_post_stories=False,
    can_edit_stories=False,
    can_delete_stories=False,
    can_pin_messages=True,
)


async def publish_profile(bot: Bot) -> None:
    """Bring the bot's profile in line with this module.

    Text is compared first and written only when it differs: setMyName in
    particular is rate-limited hard, and every deploy restarts the bot.
    """
    if (await bot.get_my_name()).name != NAME:
        await bot.set_my_name(name=NAME)
    if (await bot.get_my_description()).description != DESCRIPTION:
        await bot.set_my_description(description=DESCRIPTION)
    if (await bot.get_my_short_description()).short_description != SHORT_DESCRIPTION:
        await bot.set_my_short_description(short_description=SHORT_DESCRIPTION)

    await bot.set_my_commands(commands=PRIVATE_COMMANDS, scope=BotCommandScopeDefault())
    await bot.set_my_commands(commands=GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
    await bot.set_my_default_administrator_rights(rights=DEFAULT_ADMIN_RIGHTS)
