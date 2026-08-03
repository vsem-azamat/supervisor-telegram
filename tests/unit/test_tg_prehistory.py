"""Revealing a chat's past to people who join later.

One inverted flag stands between "show the history" and "hide it", and getting
it backwards would do the opposite of what was asked in every chat at once. So
the call is checked rather than trusted, along with the usual absence of
anything that removes people or the chat.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "tg_prehistory.py"
_TREE = ast.parse(_PATH.read_text(encoding="utf-8"))


def _identifiers() -> set[str]:
    names = set()
    for node in ast.walk(_TREE):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


_NAMES = _identifiers()


def _load():
    spec = importlib.util.spec_from_file_location("tg_prehistory", _PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["tg_prehistory"] = module
    spec.loader.exec_module(module)
    return module


tg_prehistory = _load()


class TestTheFlagIsTheRightWayRound:
    def test_revealing_passes_enabled_false(self) -> None:
        """`enabled` is whether the history stays hidden. True would hide it everywhere."""
        calls = [
            node
            for node in ast.walk(_TREE)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "TogglePreHistoryHiddenRequest"
        ]

        assert len(calls) == 1
        enabled = next(kw.value for kw in calls[0].keywords if kw.arg == "enabled")
        assert isinstance(enabled, ast.Constant)
        assert enabled.value is False

    def test_the_toggle_is_only_ever_called_from_reveal(self) -> None:
        reveal = next(
            node
            for node in ast.walk(_TREE)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "reveal"
        )
        toggles = [
            node
            for node in ast.walk(reveal)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "TogglePreHistoryHiddenRequest"
        ]

        assert len(toggles) == 1


class TestItNeverTakesAnythingAway:
    @pytest.mark.parametrize(
        "call",
        ["EditCreatorRequest", "EditBannedRequest", "DeleteParticipantRequest", "LeaveChannelRequest", "delete_messages"],
    )
    def test_no_call_that_removes_anything(self, call: str) -> None:
        assert call not in _NAMES


class TestPacing:
    def test_there_is_always_a_pause_between_writes(self) -> None:
        assert tg_prehistory.MIN_DELAY > 0
        assert tg_prehistory.MAX_DELAY > tg_prehistory.MIN_DELAY
