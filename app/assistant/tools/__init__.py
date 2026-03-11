"""Assistant agent tool modules.

Each module exports a register_*_tools(agent) function.
"""

from pydantic_ai import Agent

from app.assistant.agent import AssistantDeps


def register_all_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register all tool groups on the agent."""
    from app.assistant.tools.agent_moderation import register_agent_moderation_tools
    from app.assistant.tools.channel import register_channel_tools
    from app.assistant.tools.chat import register_chat_tools
    from app.assistant.tools.dedup import register_dedup_tools
    from app.assistant.tools.moderation import register_moderation_tools
    from app.assistant.tools.telethon import register_telethon_tools

    register_channel_tools(agent)
    register_dedup_tools(agent)
    register_chat_tools(agent)
    register_moderation_tools(agent)
    register_telethon_tools(agent)
    register_agent_moderation_tools(agent)
