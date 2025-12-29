"""
Central registry for AI agent models.

This is the single source of truth for all available AI models.
When adding or removing models, edit only this file.
"""

from app.agent_platform.domain.agent import ModelProvider, OpenRouterModel

# Available models for OpenRouter provider
OPENROUTER_MODELS = [
    OpenRouterModel(
        id="anthropic/claude-sonnet-4.5",
        name="Claude Sonnet 4.5",
        description="Latest Claude model with enhanced capabilities",
        context_length=200000,
    ),
    OpenRouterModel(
        id="openai/gpt-5.2-chat",
        name="GPT-5",
        description="OpenAI's GPT-5.2 lightweight variant",
        context_length=128000,
    ),
    OpenRouterModel(
        id="google/gemini-3-flash-preview",
        name="Gemini 3 Flash Preview",
        description="Fast and cost-effective Gemini 3 variant",
        context_length=128000,
    ),
]


def get_models_by_provider(_provider: ModelProvider) -> list[OpenRouterModel]:
    """Get list of available models for a specific provider."""
    return OPENROUTER_MODELS


def get_all_models() -> list[OpenRouterModel]:
    """Get all available models across all providers."""
    return OPENROUTER_MODELS
