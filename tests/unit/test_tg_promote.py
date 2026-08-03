"""The promotion pass writes to real chats, so its guarantees are pinned here.

Two of them are absolute. It never transfers ownership — that call is
irreversible without the new owner's cooperation, and the file must not contain
it. And it never takes anything away from anybody: no demotion, no removal, no
leaving. Both are properties of the source, so both are checked against it.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "tg_promote.py"


def _identifiers() -> set[str]:
    """Every name the code actually refers to.

    Read from the syntax tree rather than the text, so that naming a forbidden
    call in a docstring — to explain why it is absent — does not read as using
    it. The prose and the program are different things and this test is about
    the program.
    """
    tree = ast.parse(_PATH.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


_NAMES = _identifiers()


def _load():
    spec = importlib.util.spec_from_file_location("tg_promote", _PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["tg_promote"] = module
    spec.loader.exec_module(module)
    return module


tg_promote = _load()


class TestItNeverTakesAnythingAway:
    def test_ownership_is_never_transferred(self) -> None:
        """editCreator hands the chat over for good. It has no business here."""
        assert "EditCreatorRequest" not in _NAMES

    @pytest.mark.parametrize(
        "call",
        [
            "EditBannedRequest",
            "DeleteParticipantRequest",
            "kick_participant",
            "LeaveChannelRequest",
            "DeleteChatUserRequest",
        ],
    )
    def test_no_call_that_removes_or_demotes_appears(self, call: str) -> None:
        assert call not in _NAMES

    def test_the_only_write_is_the_promotion_and_the_invite_it_needs(self) -> None:
        assert {"edit_admin", "InviteToChannelRequest"} <= _NAMES


class TestRights:
    def test_every_administrator_right_is_granted(self) -> None:
        rights = tg_promote.admin_rights()

        assert all(rights[name] for name in rights if name != "anonymous")

    def test_the_account_can_appoint_further_admins(self) -> None:
        """Without it, it could not invite the bot back or hand over in turn."""
        assert tg_promote.admin_rights()["add_admins"] is True

    def test_moderation_is_not_anonymous(self) -> None:
        assert tg_promote.admin_rights()["anonymous"] is False


class TestScope:
    def test_ids_are_read_with_their_labels(self, tmp_path: Path) -> None:
        """A scope file is pasted from a report, so it carries titles too."""
        path = tmp_path / "scope.txt"
        path.write_text(
            "# universities\n1405134944 ČVUT | ЧВУТ\n\n1192822531 Karlova univerzita\n1370017010\n",
            encoding="utf-8",
        )

        scope = tg_promote.read_scope(path)

        assert [entry.chat_id for entry in scope] == [1405134944, 1192822531, 1370017010]
        assert scope[0].title == "ČVUT | ЧВУТ"
        assert scope[2].title == ""


class TestJournal:
    def test_a_resumed_run_skips_finished_chats(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        tg_promote.Journal(path).record(1405134944, ok=True)

        resumed = tg_promote.Journal(path)

        assert resumed.already(1405134944) is True
        assert resumed.already(1192822531) is False

    def test_a_chat_that_hit_a_flood_wait_is_tried_again(self, tmp_path: Path) -> None:
        """Stopping on a limit must not look like having finished the chat."""
        path = tmp_path / "journal.jsonl"
        tg_promote.Journal(path).record(1405134944, ok=False, detail="peer_flood")

        assert tg_promote.Journal(path).already(1405134944) is False


class TestPacing:
    def test_there_is_always_a_pause_between_writes(self) -> None:
        """A burst of membership changes is what gets the owner's account limited."""
        assert tg_promote.MIN_DELAY > 0
        assert tg_promote.MAX_DELAY > tg_promote.MIN_DELAY
