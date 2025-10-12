"""
Central registry for AI agent models.

This is the single source of truth for all available AI models.
When adding or removing models, edit only this file.
"""

from app.domain.agent import ModelProvider, OpenRouterModel

# Available models for OpenRouter provider
OPENROUTER_MODELS = [
    OpenRouterModel(
        id="x-ai/grok-4-fast",
        name="Grok 4 Fast",
        description="X.AI's fast and efficient Grok model",
        context_length=128000,
    ),
    OpenRouterModel(
        id="anthropic/claude-sonnet-4.5",
        name="Claude Sonnet 4.5",
        description="Latest Claude model with enhanced capabilities",
        context_length=200000,
    ),
    OpenRouterModel(
        id="openai/gpt-5",
        name="GPT-5",
        description="OpenAI's latest flagship model",
        context_length=128000,
    ),
    OpenRouterModel(
        id="openai/gpt-5-mini",
        name="GPT-5 Mini",
        description="Fast and cost-effective GPT-5 variant",
        context_length=128000,
    ),
    OpenRouterModel(
        id="openai/gpt-5-chat",
        name="GPT-5 Chat",
        description="GPT-5 optimized for conversational tasks",
        context_length=128000,
    ),
    OpenRouterModel(
        id="openai/gpt-oss-20b",
        name="GPT OSS 20B",
        description="Open source 20B parameter model",
        context_length=32000,
    ),
]

# Available models for OpenAI provider
OPENAI_MODELS = [
    OpenRouterModel(
        id="gpt-4o",
        name="GPT-4o",
        description="Latest OpenAI model with multimodal capabilities",
        context_length=128000,
    ),
    OpenRouterModel(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        description="Fast and cost-effective version of GPT-4o",
        context_length=128000,
    ),
    OpenRouterModel(
        id="gpt-4-turbo",
        name="GPT-4 Turbo",
        description="Enhanced version of GPT-4 with extended context",
        context_length=128000,
    ),
]


def get_models_by_provider(provider: ModelProvider) -> list[OpenRouterModel]:
    """Get list of available models for a specific provider."""
    if provider == ModelProvider.OPENAI:
        return OPENAI_MODELS
    # provider == ModelProvider.OPENROUTER
    return OPENROUTER_MODELS


def get_all_models() -> list[OpenRouterModel]:
    """Get all available models across all providers."""
    return OPENAI_MODELS + OPENROUTER_MODELS
