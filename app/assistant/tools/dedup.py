"""Dedup, search & analytics tools."""

from pydantic_ai import Agent, RunContext

from app.assistant.agent import AssistantDeps, _validate_channel_id
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("assistant.tools.dedup")


def register_dedup_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register dedup, search & analytics tools on the agent."""

    @agent.tool
    async def check_duplicate(ctx: RunContext[AssistantDeps], channel_id: int, text: str) -> str:
        """Check if a text is semantically similar to recent posts. Returns similarity score."""
        error = await _validate_channel_id(ctx, channel_id)
        if error:
            return error

        try:
            from app.agent.channel.semantic_dedup import find_nearest_posts

            results = await find_nearest_posts(
                text,
                channel_id=channel_id,
                api_key=settings.openrouter.api_key,
                session_maker=ctx.deps.session_maker,
            )

            if not results:
                return "No recent posts with embeddings to compare against."

            lines = ["Similarity to recent posts:\n"]
            for title, similarity in results:
                flag = " DUPLICATE" if similarity >= 0.85 else ""
                lines.append(f"- {similarity:.2%} — {title[:60]}{flag}")
            return "\n".join(lines)
        except Exception:
            logger.exception("check_duplicate_failed", channel_id=channel_id)
            return "Не удалось проверить дубликаты. Проверьте логи."

    @agent.tool
    async def list_recent_topics(ctx: RunContext[AssistantDeps], channel_id: int, days: int = 7) -> str:
        """List recent post topics for a channel to avoid repetition. Shows titles and dates."""
        error = await _validate_channel_id(ctx, channel_id)
        if error:
            return error

        days = min(max(1, days), 30)

        try:
            from sqlalchemy import text as sql_text

            query = sql_text("""
                SELECT title, status, created_at::date as day
                FROM channel_posts
                WHERE channel_id = :channel_id
                  AND created_at > NOW() - make_interval(days => :days)
                ORDER BY created_at DESC
            """)

            async with ctx.deps.session_maker() as session:
                result = await session.execute(query, {"channel_id": channel_id, "days": days})
                rows = result.fetchall()

            if not rows:
                return f"No posts in last {days} days for {channel_id}."

            lines = [f"Posts in last {days} days for {channel_id} ({len(rows)} total):\n"]
            for title, status, day in rows:
                lines.append(f"- [{status}] {day}: {title[:70]}")
            return "\n".join(lines)
        except Exception:
            logger.exception("list_recent_topics_failed", channel_id=channel_id)
            return "Не удалось получить список тем. Проверьте логи."

    @agent.tool
    async def backfill_embeddings(ctx: RunContext[AssistantDeps], channel_id: int, limit: int = 50) -> str:
        """Generate embeddings for posts that don't have them yet. Useful after enabling semantic dedup."""
        error = await _validate_channel_id(ctx, channel_id)
        if error:
            return error

        limit = min(max(1, limit), 200)

        try:
            from sqlalchemy import select

            from app.agent.channel.embeddings import EMBEDDING_MODEL, get_embeddings
            from app.infrastructure.db.models import ChannelPost

            async with ctx.deps.session_maker() as session:
                result = await session.execute(
                    select(ChannelPost)
                    .where(
                        ChannelPost.channel_id == channel_id,
                        ChannelPost.embedding.is_(None),
                    )
                    .order_by(ChannelPost.id.desc())
                    .limit(limit)
                )
                posts = list(result.scalars().all())

            if not posts:
                return f"All posts in {channel_id} already have embeddings."

            texts = [f"{p.title} {(p.post_text or '')[:100]}" for p in posts]
            embeddings = await get_embeddings(texts, api_key=settings.openrouter.api_key, model=EMBEDDING_MODEL)

            post_ids = [p.id for p in posts]
            async with ctx.deps.session_maker() as session:
                result = await session.execute(select(ChannelPost).where(ChannelPost.id.in_(post_ids)))
                db_posts = {p.id: p for p in result.scalars().all()}
                for post, emb in zip(posts, embeddings, strict=True):
                    db_posts[post.id].embedding = emb
                    db_posts[post.id].embedding_model = EMBEDDING_MODEL
                await session.commit()
            updated = len(db_posts)

            return f"Backfilled embeddings for {updated} posts in {channel_id}."
        except Exception:
            logger.exception("backfill_embeddings_failed", channel_id=channel_id)
            return "Не удалось создать эмбеддинги. Проверьте логи."

    @agent.tool
    async def search_news(
        ctx: RunContext[AssistantDeps],  # noqa: ARG001
        query: str,
        count: int = 5,
        freshness: str = "pw",
        country: str = "",
        search_lang: str = "",
    ) -> str:
        """Search the web for current news and information. Use this to find fresh content before generating posts. freshness: pd=past day, pw=past week, pm=past month. country: 2-letter code (CZ, US, DE). search_lang: language code (cs, en, ru). For Czech news, use country='CZ' search_lang='cs'."""
        brave_key = settings.brave.api_key
        if not brave_key:
            return "Brave API key not configured. Set BRAVE_API_KEY in .env."

        if freshness not in {"pd", "pw", "pm", "py"}:
            freshness = "pw"
        count = min(max(1, count), 10)

        try:
            from app.agent.channel.brave_search import brave_search_for_assistant

            return await brave_search_for_assistant(
                brave_key, query, count=count, freshness=freshness, country=country, search_lang=search_lang
            )
        except Exception:
            logger.exception("search_news_failed", query=query)
            return "Не удалось выполнить поиск. Проверьте логи."

    @agent.tool
    async def fetch_url(ctx: RunContext[AssistantDeps], url: str, max_chars: int = 3000) -> str:  # noqa: ARG001
        """Fetch and read the text content of a web page. Use after search_news to read a full article before generating a post. max_chars limits the returned text length."""
        from app.agent.channel.http import SSRFError, safe_fetch

        max_chars = min(max(500, max_chars), 8000)
        try:
            resp = await safe_fetch(url, timeout=15)
        except SSRFError:
            return "URL blocked by security policy (private/internal address)."
        except Exception:
            logger.exception("fetch_url_failed", url=url[:100])
            return "Не удалось загрузить страницу."

        # Extract text from HTML
        import re
        from html.parser import HTMLParser
        from io import StringIO

        html = resp.text
        try:

            class _TextExtractor(HTMLParser):
                def __init__(self) -> None:
                    super().__init__()
                    self._result = StringIO()
                    self._skip = False

                def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
                    if tag in ("script", "style", "nav", "header", "footer", "noscript"):
                        self._skip = True

                def handle_endtag(self, tag: str) -> None:
                    if tag in ("script", "style", "nav", "header", "footer", "noscript"):
                        self._skip = False
                    if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "li"):
                        self._result.write("\n")

                def handle_data(self, data: str) -> None:
                    if not self._skip:
                        self._result.write(data)

            extractor = _TextExtractor()
            extractor.feed(html)
            text = extractor._result.getvalue()
        except Exception:
            # Fallback: strip tags with regex
            text = re.sub(r"<[^>]+>", " ", html)

        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = text.strip()

        if not text:
            return "Page loaded but no text content found."

        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (truncated)"
        return f"Content from {url}:\n\n{text}"

    @agent.tool
    async def fetch_rss(ctx: RunContext[AssistantDeps], feed_url: str, max_items: int = 10) -> str:  # noqa: ARG001
        """Fetch and display items from an RSS feed. Returns titles, dates, and summaries. Useful for checking university/news RSS feeds for fresh content."""
        from app.agent.channel.sources import fetch_rss as _fetch_rss

        max_items = min(max(1, max_items), 20)
        try:
            items = await _fetch_rss(feed_url, max_items=max_items)
        except Exception:
            logger.exception("fetch_rss_tool_failed", feed_url=feed_url[:100])
            return "Не удалось загрузить RSS-ленту."

        if not items:
            return f"No items found in RSS feed: {feed_url}"

        lines = [f"RSS feed ({len(items)} items from {feed_url}):\n"]
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. **{item.title}**")
            if item.url:
                lines.append(f"   {item.url}")
            if item.body:
                lines.append(f"   {item.body[:150]}")
            lines.append("")
        return "\n".join(lines)
