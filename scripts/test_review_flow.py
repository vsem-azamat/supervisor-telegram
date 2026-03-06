"""End-to-end test of the Konnekt channel bot review flow.

Steps:
1. Fetch RSS feeds and screen for relevant content
2. Generate a post via LLM
3. Send the post to the review group (-1003823967369) with inline buttons
4. Approve the post programmatically via handle_approve
5. Verify the post was published to @test908070
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# Ensure project root is on sys.path
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env")

import structlog  # noqa: E402

structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)


async def main() -> None:
    from aiogram import Bot
    from app.agent.channel.generator import generate_post, screen_items
    from app.agent.channel.review import handle_approve, send_for_review
    from app.agent.channel.sources import fetch_all_sources
    from app.infrastructure.db.models import Base, ChannelPost
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    # --- Configuration ---
    bot_token = os.environ["BOT_TOKEN"]
    api_key = os.environ["AGENT_OPENROUTER_API_KEY"]
    review_chat_id = -1003823967369
    channel_id = "@test908070"
    rss_feeds = [
        "https://ct24.ceskatelevize.cz/rss/hlavni-zpravy",
        "https://www.irozhlas.cz/rss/irozhlas",
        "https://www.novinky.cz/rss",
    ]
    screening_model = "google/gemini-3.1-flash-lite-preview"
    generation_model = "google/gemini-3.1-flash-lite-preview"

    # --- Setup ---
    bot = Bot(token=bot_token)
    db_url = (
        f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ.get('DB_HOST', 'localhost')}:{os.environ.get('DB_PORT', '5432')}"
        f"/{os.environ['DB_NAME']}"
    )
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        # =====================================================================
        # STEP 1: Fetch RSS feeds
        # =====================================================================
        print("\n" + "=" * 60)
        print("STEP 1: Fetching RSS feeds...")
        print("=" * 60)

        fetch_result = await fetch_all_sources(rss_feeds, http_timeout=30)
        all_items = fetch_result.items
        print(f"  Fetched {len(all_items)} items from {len(fetch_result.successful_urls)} feeds")
        print(f"  Errored feeds: {fetch_result.errored_urls or 'none'}")

        if not all_items:
            print("  ERROR: No items fetched from any feed. Aborting.")
            return

        # Show first few items
        for item in all_items[:3]:
            img_tag = " [IMG]" if item.image_url else ""
            print(f"  - {item.title[:70]}{img_tag}")

        # =====================================================================
        # STEP 2: Screen items for relevance
        # =====================================================================
        print("\n" + "=" * 60)
        print("STEP 2: Screening items for relevance...")
        print("=" * 60)

        # Use a low threshold to ensure we get results for testing
        relevant = await screen_items(
            all_items[:10],  # screen first 10 items max
            api_key=api_key,
            model=screening_model,
            threshold=3,  # low threshold for testing
        )
        print(f"  {len(relevant)} items passed screening (threshold=3)")

        if not relevant:
            print("  WARNING: No items passed screening. Using first 2 items directly.")
            relevant = all_items[:2]

        for item in relevant[:3]:
            img_tag = " [IMG]" if item.image_url else ""
            print(f"  - {item.title[:70]}{img_tag}")

        # =====================================================================
        # STEP 3: Generate post via LLM
        # =====================================================================
        print("\n" + "=" * 60)
        print("STEP 3: Generating post via LLM...")
        print("=" * 60)

        post = await generate_post(
            relevant[:3],
            api_key=api_key,
            model=generation_model,
            language="Russian",
        )

        if not post:
            print("  ERROR: Post generation failed. Aborting.")
            return

        print(f"  Generated post ({len(post.text)} chars)")
        print(f"  Image URL: {post.image_url or 'none'}")
        print(f"  Is sensitive: {post.is_sensitive}")
        print(f"  Preview:\n{'  ' + post.text[:300]}...")

        # =====================================================================
        # STEP 4: Send for review to the review group
        # =====================================================================
        print("\n" + "=" * 60)
        print("STEP 4: Sending to review group...")
        print("=" * 60)

        post_id = await send_for_review(
            bot=bot,
            review_chat_id=review_chat_id,
            channel_id=str(channel_id),
            post=post,
            source_items=relevant[:3],
            session_maker=session_maker,
        )

        if not post_id:
            print("  ERROR: Failed to send for review. Aborting.")
            return

        print(f"  Post sent for review! DB post_id={post_id}")

        # Verify the post in DB
        async with session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            db_post = result.scalar_one_or_none()
            if db_post:
                print(f"  DB status: {db_post.status}")
                print(f"  Review message ID: {db_post.review_message_id}")
                print(f"  Review chat ID: {db_post.review_chat_id}")
                print(f"  Image URL: {db_post.image_url or 'none'}")
            else:
                print("  ERROR: Post not found in DB!")
                return

        # =====================================================================
        # STEP 5: Approve the post (simulating button click)
        # =====================================================================
        print("\n" + "=" * 60)
        print("STEP 5: Approving post (simulating Approve button)...")
        print("=" * 60)

        approve_result = await handle_approve(
            bot=bot,
            post_id=post_id,
            channel_id=channel_id,
            session_maker=session_maker,
        )

        print(f"  Approve result: {approve_result}")

        # =====================================================================
        # STEP 6: Verify publication
        # =====================================================================
        print("\n" + "=" * 60)
        print("STEP 6: Verifying publication...")
        print("=" * 60)

        if "Published" in approve_result:
            print("  SUCCESS: Post was published to @test908070!")

            # Double-check DB status
            async with session_maker() as session:
                result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
                db_post = result.scalar_one_or_none()
                if db_post:
                    print(f"  DB status: {db_post.status}")
                    print(f"  Telegram message ID: {db_post.telegram_message_id}")
                else:
                    print("  WARNING: Could not re-read post from DB")
        else:
            print(f"  FAILURE: Approve did not succeed. Result: {approve_result}")

        # Try to remove the review keyboard after approval
        if db_post and db_post.review_message_id:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=review_chat_id,
                    message_id=db_post.review_message_id,
                    reply_markup=None,
                )
                print("  Cleaned up review message buttons.")
            except Exception as e:
                print(f"  Note: Could not clean review buttons: {e}")

        # =====================================================================
        # SUMMARY
        # =====================================================================
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  RSS items fetched:      {len(all_items)}")
        print(f"  Items passed screening: {len(relevant)}")
        print(f"  Post generated:         {'yes' if post else 'no'}")
        print(f"  Post length:            {len(post.text)} chars")
        print(f"  Has image:              {'yes' if post.image_url else 'no'}")
        print(f"  Sent to review:         post_id={post_id}")
        print(f"  Approve result:         {approve_result}")
        published = "Published" in approve_result
        print(f"  Published to channel:   {'YES' if published else 'NO'}")
        print("=" * 60)

    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
