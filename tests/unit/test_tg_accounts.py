"""Session files must stay one per account, and stay where they belong.

Everything else in the script is Telegram I/O. What can go wrong without
Telegram noticing is the file layout: two accounts sharing a path means the
second login silently replaces the first, and a name that escapes the sessions
directory means an account key written somewhere the repository does track.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "tg_accounts.py"


def _load():
    spec = importlib.util.spec_from_file_location("tg_accounts", _PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["tg_accounts"] = module
    spec.loader.exec_module(module)
    return module


tg_accounts = _load()


class TestSessionPaths:
    def test_each_account_gets_its_own_file(self, tmp_path: Path) -> None:
        """The whole point: one session per account, never shared."""
        main = tg_accounts.session_path("main", directory=tmp_path)
        work = tg_accounts.session_path("work", directory=tmp_path)

        assert main != work
        assert (main.parent, work.parent) == (tmp_path, tmp_path)

    def test_sessions_live_under_the_ignored_credentials_directory(self) -> None:
        """A session is the account; it must not land somewhere git tracks."""
        assert tg_accounts.SESSIONS_DIR.parts[0] == ".creds"

    @pytest.mark.parametrize("name", ["../escape", "main/../..", "Main", "", "a" * 32, "main session"])
    def test_a_name_that_could_escape_is_refused(self, name: str, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            tg_accounts.session_path(name, directory=tmp_path)

    @pytest.mark.parametrize("name", ["main", "work", "agent-2", "azamat_personal"])
    def test_ordinary_names_are_accepted(self, name: str, tmp_path: Path) -> None:
        assert tg_accounts.session_path(name, directory=tmp_path).name == f"{name}.session"


class TestDiscovery:
    def test_stored_sessions_are_listed(self, tmp_path: Path) -> None:
        (tmp_path / "work.session").touch()
        (tmp_path / "main.session").touch()
        (tmp_path / "notes.txt").touch()

        assert tg_accounts.known_accounts(tmp_path) == ["main", "work"]

    def test_an_absent_directory_is_not_an_error(self, tmp_path: Path) -> None:
        assert tg_accounts.known_accounts(tmp_path / "nothing-here") == []


class TestApiCredentials:
    def test_both_halves_are_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Half a pair authenticates nothing, and fails later than here."""
        monkeypatch.setenv("TELETHON_API_ID", "12345")
        monkeypatch.delenv("TELETHON_API_HASH", raising=False)

        with pytest.raises(SystemExit):
            tg_accounts.api_credentials()

    def test_a_non_numeric_api_id_is_caught_before_telethon_sees_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELETHON_API_ID", "not-a-number")
        monkeypatch.setenv("TELETHON_API_HASH", "abc")

        with pytest.raises(SystemExit):
            tg_accounts.api_credentials()

    def test_a_configured_pair_is_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELETHON_API_ID", " 12345 ")
        monkeypatch.setenv("TELETHON_API_HASH", " deadbeef ")

        assert tg_accounts.api_credentials() == (12345, "deadbeef")
