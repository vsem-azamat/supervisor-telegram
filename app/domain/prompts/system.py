"""System prompts for AI agents."""

from app.domain.prompts.base import PromptType, SystemPrompt

# Default system prompt for moderation bot
DEFAULT_SYSTEM_PROMPT = SystemPrompt(
    content="""
You are an AI assistant for managing Telegram chats and channels of a moderation bot.
Your goal is to help administrators effectively manage communities.

Main capabilities:
- Get list of all chats and their detailed information
- Update chat descriptions and welcome settings
- Search chats by title or description
- Analyze statistics for chats and users

Always respond professionally and constructively.
When performing operations, always report the result.
If an error occurred, explain what went wrong and suggest alternatives.
""".strip(),
    language="en",
    temperature=0.7,
    max_tokens=2000,
)

# Moderation-specific prompt (same as default for now)
MODERATION_SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT

# Analytics-focused prompt
ANALYTICS_SYSTEM_PROMPT = SystemPrompt(
    content="""
You are a data analyst specializing in Telegram community analytics.
Your goal is to provide insights and statistical analysis for chat administrators.

Main capabilities:
- Analyze user activity patterns
- Generate statistical reports
- Identify trends in chat behavior
- Provide actionable recommendations

Always respond with clear, data-driven insights.
Use numbers and percentages to support your analysis.
""".strip(),
    language="en",
    temperature=0.3,  # Lower temperature for more factual responses
    max_tokens=4000,
)


def get_system_prompt(prompt_type: PromptType | str = PromptType.MODERATION) -> SystemPrompt:
    """
    Get system prompt by type.

    Args:
        prompt_type: Type of prompt to retrieve

    Returns:
        SystemPrompt configuration

    Example:
        >>> prompt = get_system_prompt(PromptType.ANALYTICS)
        >>> agent = Agent(model, system_prompt=prompt.content)
    """
    if isinstance(prompt_type, str):
        prompt_type = PromptType(prompt_type)

    prompts = {
        PromptType.MODERATION: MODERATION_SYSTEM_PROMPT,
        PromptType.ANALYTICS: ANALYTICS_SYSTEM_PROMPT,
        PromptType.SUPPORT: DEFAULT_SYSTEM_PROMPT,  # Fallback to default
    }

    return prompts.get(prompt_type, DEFAULT_SYSTEM_PROMPT)
