"""One-time Telethon authorization script.

Usage: uv run python scripts/telethon_auth.py <code>
"""

import asyncio
import sys

from telethon import TelegramClient

API_ID = 23907487
API_HASH = "fac6f4d4c3e6feee8df8f228ef5b4b1c"
PHONE = "+420704013228"
SESSION_NAME = "moderator_userbot"


async def main() -> None:
    code = sys.argv[1] if len(sys.argv) > 1 else None
    password = sys.argv[2] if len(sys.argv) > 2 else None

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Already authorized as: {me.first_name} (@{me.username}), ID: {me.id}")
        await client.disconnect()
        return

    # Send code and sign in within the same connection
    sent = await client.send_code_request(PHONE)
    print(f"Code sent to {PHONE} (hash: {sent.phone_code_hash[:8]}...)")

    if not code:
        print("Re-run with: uv run python scripts/telethon_auth.py <code>")
        await client.disconnect()
        return

    try:
        await client.sign_in(PHONE, code, phone_code_hash=sent.phone_code_hash)
    except Exception as e:
        if "password" in str(e).lower() or "2fa" in str(e).lower():
            if password:
                await client.sign_in(password=password)
            else:
                print(f"2FA required! Run: uv run python scripts/telethon_auth.py {code} <2fa_password>")
                await client.disconnect()
                return
        else:
            raise

    me = await client.get_me()
    print(f"Authorized as: {me.first_name} (@{me.username}), ID: {me.id}")
    print(f"Session saved to: {SESSION_NAME}.session")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
