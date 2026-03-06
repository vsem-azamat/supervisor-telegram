"""Set up a Telethon-based review supergroup for the channel content pipeline.

Creates a private supergroup, adds the bot as admin, and invites the owner.

Usage: uv run python scripts/setup_review_channel.py
"""

import asyncio
import sys

from telethon import TelegramClient
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    InviteToChannelRequest,
)
from telethon.tl.types import ChatAdminRights

API_ID = 23907487
API_HASH = "fac6f4d4c3e6feee8df8f228ef5b4b1c"
SESSION_NAME = "moderator_userbot"

# Target channel for the content pipeline
TARGET_CHANNEL = "@test908070"
TARGET_CHANNEL_ID = -1002287191880

# Bot to add as admin
BOT_USERNAME = "konnekt_moder_bot"
BOT_ID = 5145935834

# Owner to invite
OWNER_ID = 268388996


async def main() -> None:
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print("ERROR: Not authorized. Run telethon_auth.py first.")
        await client.disconnect()
        sys.exit(1)

    me = await client.get_me()
    print(f"Authorized as: {me.first_name} (@{me.username}), ID: {me.id}")

    # Step 1: Create supergroup
    print("\n[1/4] Creating supergroup 'Konnekt Review'...")
    try:
        result = await client(
            CreateChannelRequest(
                title="Konnekt Review",
                about=f"Review channel for {TARGET_CHANNEL} content pipeline",
                megagroup=True,
            )
        )
        chat = result.chats[0]
        group_id = chat.id
        full_group_id = int(f"-100{group_id}")
        print(f"  Created: '{chat.title}' (ID: {group_id})")
    except Exception as e:
        print(f"  FAILED to create supergroup: {e}")
        await client.disconnect()
        sys.exit(1)

    # Step 2: Add bot as admin
    print(f"\n[2/4] Adding @{BOT_USERNAME} as admin...")
    try:
        bot_entity = await client.get_input_entity(BOT_USERNAME)
        admin_rights = ChatAdminRights(
            post_messages=True,
            edit_messages=True,
            delete_messages=True,
            ban_users=False,
            invite_users=True,
            pin_messages=True,
            manage_call=False,
        )
        await client(
            EditAdminRequest(
                channel=chat,
                user_id=bot_entity,
                admin_rights=admin_rights,
                rank="Content Bot",
            )
        )
        print(f"  @{BOT_USERNAME} promoted to admin")
    except Exception as e:
        print(f"  FAILED to add bot as admin: {e}")

    # Step 3: Invite owner
    print(f"\n[3/4] Inviting owner (ID: {OWNER_ID})...")
    try:
        owner_entity = await client.get_input_entity(OWNER_ID)
        await client(InviteToChannelRequest(channel=chat, users=[owner_entity]))
        print(f"  User {OWNER_ID} invited")
    except Exception as e:
        print(f"  FAILED to invite owner: {e}")

    # Step 4: Print config
    print("\n[4/4] Setup complete!")
    print("\n" + "=" * 50)
    print("Add this to your .env file:")
    print(f"  CHANNEL_REVIEW_CHAT_ID={full_group_id}")
    print("=" * 50)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
