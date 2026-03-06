"""Create the Konnekt Telegram channel and configure admins."""

import asyncio

from telethon import TelegramClient
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    UpdateUsernameRequest,
)
from telethon.tl.types import ChatAdminRights

API_ID = 23907487
API_HASH = "fac6f4d4c3e6feee8df8f228ef5b4b1c"
SESSION = "moderator_userbot"

BOT_ID = 5145935834  # @konnekt_moder_bot
AZAMAT_ID = 268388996

TITLE = "Konnekt"
DESCRIPTION = "Новости и полезная информация для студентов из СНГ в Чехии. ČVUT, UK, VŠE, VUT, MUNI, VŠCHT и другие."

USERNAMES_TO_TRY = ["konnekt_channel", "konnekt_cz", "konnekt_news"]


async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    print("Connected to Telegram.")

    # Step 1: Create channel (broadcast=True makes it a channel, not supergroup)
    print(f"\nCreating channel '{TITLE}'...")
    result = await client(
        CreateChannelRequest(
            title=TITLE,
            about=DESCRIPTION,
            broadcast=True,
        )
    )

    channel = result.chats[0]
    channel_id = channel.id
    print(f"Channel created! ID: {channel_id} (full: -100{channel_id})")

    # Step 2: Try to set username
    username_set = None
    for username in USERNAMES_TO_TRY:
        try:
            print(f"\nTrying username @{username}...")
            await client(UpdateUsernameRequest(channel=channel, username=username))
            username_set = username
            print(f"Username @{username} set successfully!")
            break
        except Exception as e:
            print(f"Username @{username} unavailable: {e}")

    if not username_set:
        print("\nWARNING: Could not set any username. Channel is private.")

    # Step 3: Add bot as admin with posting rights
    bot_rights = ChatAdminRights(
        post_messages=True,
        edit_messages=True,
        delete_messages=True,
        invite_users=True,
        manage_call=False,
        anonymous=False,
        ban_users=True,
        change_info=True,
        pin_messages=True,
        add_admins=False,
    )

    print(f"\nAdding bot (ID {BOT_ID}) as admin...")
    try:
        bot_entity = await client.get_entity(BOT_ID)
        await client(
            EditAdminRequest(
                channel=channel,
                user_id=bot_entity,
                admin_rights=bot_rights,
                rank="Bot",
            )
        )
        print("Bot added as admin with posting rights.")
    except Exception as e:
        print(f"Failed to add bot as admin: {e}")

    # Step 4: Add Azamat as admin
    azamat_rights = ChatAdminRights(
        post_messages=True,
        edit_messages=True,
        delete_messages=True,
        invite_users=True,
        manage_call=True,
        anonymous=False,
        ban_users=True,
        change_info=True,
        pin_messages=True,
        add_admins=True,
    )

    print(f"\nAdding Azamat (ID {AZAMAT_ID}) as admin...")
    try:
        azamat_entity = await client.get_entity(AZAMAT_ID)
        await client(
            EditAdminRequest(
                channel=channel,
                user_id=azamat_entity,
                admin_rights=azamat_rights,
                rank="Owner",
            )
        )
        print("Azamat added as admin with full rights.")
    except Exception as e:
        print(f"Failed to add Azamat as admin: {e}")

    # Summary
    print("\n" + "=" * 50)
    print("CHANNEL CREATION SUMMARY")
    print("=" * 50)
    print(f"Title: {TITLE}")
    print(f"Channel ID: {channel_id}")
    print(f"Full ID: -100{channel_id}")
    if username_set:
        print(f"Username: @{username_set}")
        print(f"Link: https://t.me/{username_set}")
    else:
        print("Username: None (private channel)")
    print(f"Description: {DESCRIPTION}")
    print(f"Bot admin: @konnekt_moder_bot (ID {BOT_ID})")
    print(f"Azamat admin: ID {AZAMAT_ID}")
    print("=" * 50)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
