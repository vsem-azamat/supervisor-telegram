"""Fetch one RSS item, generate a Konnekt-style post, and publish to test channel."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

CHANNEL_ID = "@test908070"
BOT_TOKEN = os.environ["BOT_TOKEN"]
API_KEY = os.environ["AGENT_OPENROUTER_API_KEY"]
MODEL = "google/gemini-2.0-flash-001"


async def main() -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from app.agent.channel.generator import generate_post
    from app.agent.channel.publisher import publish_post
    from app.agent.channel.sources import fetch_all_sources

    # 1. Fetch RSS
    rss_urls = ["https://ct24.ceskatelevize.cz/rss/hlavni-zpravy"]
    print("Fetching RSS...")
    fetch_result = await fetch_all_sources(rss_urls, http_timeout=15)
    print(f"  Got {len(fetch_result.items)} items")

    if not fetch_result.items:
        print("No items found!")
        return

    # Pick an item (use index from CLI arg or default to 0)
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    item = fetch_result.items[min(idx, len(fetch_result.items) - 1)]
    print(f"  Using: {item.title}")
    print(f"  URL: {item.url}")

    # 2. Generate post (1 news = 1 post)
    print("\nGenerating post...")
    post = await generate_post(
        [item],
        api_key=API_KEY,
        model=MODEL,
        language="Russian",
    )
    if not post:
        print("Generation failed!")
        return

    print(f"  Text ({len(post.text)} chars):")
    print(f"  ---\n{post.text}\n  ---")
    print(f"  Images: {post.image_urls}")

    # 3. Publish
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        print(f"\nPublishing to {CHANNEL_ID}...")
        msg_id = await publish_post(bot, CHANNEL_ID, post)
        if msg_id:
            print(f"  Published! message_id={msg_id}")
        else:
            print("  Publish failed!")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
