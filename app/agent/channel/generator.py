"""Post generation using PydanticAI + OpenRouter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.agent.channel.cost_tracker import extract_usage_from_pydanticai_result, log_usage
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agent.channel.sources import ContentItem

logger = get_logger("channel.generator")


class GeneratedPost(BaseModel):
    """Output from the post generation agent."""

    text: str = Field(description="The post text ready for Telegram (HTML format)")
    is_sensitive: bool = Field(default=False, description="Whether the post needs admin review")


SCREENING_PROMPT = """\
You are a content screener for a Telegram channel targeting CIS students in Czech Republic.
Rate the relevance of the following content item on a scale 0-10.
Return ONLY a number 0-10. 10 = highly relevant, 0 = irrelevant.

Topics of interest: education, universities, student life, visas, housing, \
Czech Republic news, technology, career opportunities, scholarships.
"""

GENERATION_PROMPT = """\
You are a content writer for a Telegram channel targeting CIS students in Czech Republic.
Write an engaging post in {language} based on the provided content.

Rules:
- Keep it concise (100-300 words)
- Use HTML formatting (<b>, <i>, <a href="...">) for Telegram
- Include a link to the source if available
- Add 2-3 relevant hashtags at the end
- Be informative but engaging, not dry
- If the content is about a specific event/deadline, highlight the date
- Do NOT use markdown, only HTML tags
"""


def _create_screening_agent(api_key: str, model: str) -> Agent[None, str]:
    """Create a cheap screening agent."""
    provider = OpenAIProvider(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    llm = OpenAIModel(model_name=model, provider=provider)
    return Agent(llm, system_prompt=SCREENING_PROMPT, output_type=str)


def _create_generation_agent(api_key: str, model: str, language: str) -> Agent[None, GeneratedPost]:
    """Create a post generation agent."""
    provider = OpenAIProvider(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    llm = OpenAIModel(model_name=model, provider=provider)
    prompt = GENERATION_PROMPT.format(language=language)
    return Agent(llm, system_prompt=prompt, output_type=GeneratedPost)


async def screen_items(
    items: list[ContentItem],
    api_key: str,
    model: str,
    threshold: int = 5,
) -> list[ContentItem]:
    """Screen items for relevance, return only relevant ones."""
    if not items:
        return []

    agent = _create_screening_agent(api_key, model)
    relevant: list[ContentItem] = []

    for item in items:
        try:
            result = await agent.run(item.summary)
            usage = extract_usage_from_pydanticai_result(result, model, "screening")
            if usage:
                await log_usage(usage)
            score_text = result.output.strip()
            # Parse score: try direct int first, then extract first number
            try:
                score = int(score_text)
            except ValueError:
                import re

                m = re.search(r"\b(\d{1,2})\b", score_text)
                score = int(m.group(1)) if m else 0
            if score >= threshold:
                relevant.append(item)
                logger.info("item_relevant", title=item.title[:60], score=score)
            else:
                logger.debug("item_irrelevant", title=item.title[:60], score=score)
        except Exception:
            logger.exception("screening_error", title=item.title[:60])

    return relevant


async def generate_post(
    items: list[ContentItem],
    api_key: str,
    model: str,
    language: str = "Russian",
    feedback_context: str | None = None,
) -> GeneratedPost | None:
    """Generate a post from one or more content items."""
    if not items:
        return None

    agent = _create_generation_agent(api_key, model, language)

    # Build the prompt with source content
    source_text = "\n\n---\n\n".join(
        f"Title: {item.title}\nURL: {item.url or 'N/A'}\nContent: {item.body[:800]}"
        for item in items[:3]  # max 3 sources per post
    )

    prompt = f"Generate a post based on these sources:\n\n{source_text}"

    if feedback_context:
        prompt += f"\n\n---\nAdmin preferences (use to guide your writing):\n{feedback_context}"

    try:
        result = await agent.run(prompt)
        usage = extract_usage_from_pydanticai_result(result, model, "generation")
        if usage:
            await log_usage(usage)
        logger.info("post_generated", length=len(result.output.text))
        return result.output
    except Exception:
        logger.exception("generation_error")
        return None
