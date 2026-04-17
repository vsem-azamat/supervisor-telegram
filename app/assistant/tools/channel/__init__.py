"""Channel management & pipeline tools — split by concern."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.assistant.tools.channel.channels import register_channels_tools
from app.assistant.tools.channel.pipeline import register_pipeline_tools
from app.assistant.tools.channel.schedule import _SCHEDULE_TIME_RE, register_schedule_tools
from app.assistant.tools.channel.sources import register_sources_tools

if TYPE_CHECKING:
    from pydantic_ai import Agent

    from app.assistant.agent import AssistantDeps


def register_channel_tools(agent: Agent[AssistantDeps, str]) -> None:
    register_channels_tools(agent)
    register_sources_tools(agent)
    register_pipeline_tools(agent)
    register_schedule_tools(agent)


__all__ = ["_SCHEDULE_TIME_RE", "register_channel_tools"]
