"""Add verified Czech RSS feed sources to the channel_sources table."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.infrastructure.db.models import ChannelSource

load_dotenv()

CHANNEL_ID = "@test908070"

FEEDS = [
    {
        "url": "https://ct24.ceskatelevize.cz/rss/hlavni-zpravy",
        "title": "CT24 Hlavni zpravy",
        "language": "cs",
    },
    {
        "url": "https://www.irozhlas.cz/rss/irozhlas",
        "title": "iROZHLAS",
        "language": "cs",
    },
    {
        "url": "https://www.novinky.cz/rss",
        "title": "Novinky.cz",
        "language": "cs",
    },
    {
        "url": "https://www.seznamzpravy.cz/rss",
        "title": "Seznam Zpravy",
        "language": "cs",
    },
    {
        "url": "https://www.blesk.cz/rss",
        "title": "Blesk.cz",
        "language": "cs",
    },
]


async def main() -> None:
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "moderator_bot")

    url = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    engine = create_async_engine(url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get existing URLs
        result = await session.execute(select(ChannelSource.url).where(ChannelSource.channel_id == CHANNEL_ID))
        existing_urls = {row[0] for row in result.all()}
        print(f"Existing sources for {CHANNEL_ID}: {len(existing_urls)}")
        for u in existing_urls:
            print(f"  - {u}")

        added = []
        skipped = []
        for feed in FEEDS:
            if feed["url"] in existing_urls:
                skipped.append(feed["title"])
                continue
            source = ChannelSource(
                channel_id=CHANNEL_ID,
                url=feed["url"],
                source_type="rss",
                title=feed["title"],
                language=feed["language"],
                added_by="manual",
            )
            session.add(source)
            added.append(feed["title"])

        if added:
            await session.commit()

        print(f"\nAdded {len(added)} sources:")
        for name in added:
            print(f"  + {name}")
        if skipped:
            print(f"\nSkipped {len(skipped)} (already exist):")
            for name in skipped:
                print(f"  ~ {name}")

        # Verify
        result = await session.execute(select(ChannelSource).where(ChannelSource.channel_id == CHANNEL_ID))
        all_sources = result.scalars().all()
        print(f"\nTotal sources for {CHANNEL_ID}: {len(all_sources)}")
        for s in all_sources:
            print(f"  [{s.id}] {s.title} | {s.url} | enabled={s.enabled}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
