"""Tests for resolve_critic_enabled — per-channel-override-then-global."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.channel.critic import resolve_critic_enabled


def _mk_channel(critic_enabled):
    return SimpleNamespace(critic_enabled=critic_enabled)


def _mk_settings(global_enabled: bool):
    return SimpleNamespace(channel=SimpleNamespace(critic_enabled=global_enabled))


@pytest.mark.parametrize(
    ("channel_val", "global_val", "expected"),
    [
        (None, False, False),
        (None, True, True),
        (True, False, True),
        (True, True, True),
        (False, False, False),
        (False, True, False),
    ],
)
def test_resolve_critic_enabled_matrix(channel_val, global_val, expected):
    assert resolve_critic_enabled(_mk_channel(channel_val), _mk_settings(global_val)) is expected
