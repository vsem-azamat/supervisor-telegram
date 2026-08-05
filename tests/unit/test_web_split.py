"""The public half of the web must stay public.

Route groups are a directory convention, and a convention is exactly the kind of
thing that erodes: somebody needs a member count on the landing page, reaches for
the endpoint that already returns one, and a page anybody can open starts asking
for an admin session. Nothing in the type system notices.

So the boundary is asserted here instead. These read the sources as text on
purpose — a Svelte component cannot be imported into pytest, and what needs
checking is which imports and which URLs appear, which the text answers exactly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROUTES = Path(__file__).resolve().parents[2] / "webui" / "src" / "routes"
PUBLIC = ROUTES / "(public)"
ADMIN = ROUTES / "(admin)"

# `apiFetch('/api/…')` and friends. Only literal paths are findable, which is the
# point: a computed endpoint on a public page would be unreviewable anyway.
API_CALL = re.compile(r"""['"`](/api/[^'"`\s]*)""")


def _sources(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.svelte")) + sorted(p for p in root.rglob("*.ts"))


def _rel(path: Path) -> str:
    return str(path.relative_to(ROUTES.parent.parent))


class TestTheHalvesExist:
    def test_both_route_groups_are_there(self) -> None:
        assert PUBLIC.is_dir(), "the public half should live in webui/src/routes/(public)"
        assert ADMIN.is_dir(), "the console should live in webui/src/routes/(admin)"

    def test_the_landing_page_is_the_public_one(self) -> None:
        """`/` belongs to the students, not to the console."""
        assert (PUBLIC / "+page.svelte").is_file()
        assert not (ROUTES / "+page.svelte").exists()

    def test_the_console_is_under_admin(self) -> None:
        assert (ADMIN / "admin" / "+page.svelte").is_file()


class TestThePublicHalfAsksNothingOfAnybody:
    @pytest.mark.parametrize("source", _sources(PUBLIC), ids=_rel)
    def test_it_only_calls_public_endpoints(self, source: Path) -> None:
        called = API_CALL.findall(source.read_text(encoding="utf-8"))
        private = [path for path in called if not path.startswith("/api/public")]

        assert not private, f"{_rel(source)} reaches {private}, which needs a session"

    @pytest.mark.parametrize("source", _sources(PUBLIC), ids=_rel)
    def test_it_does_not_pull_in_the_console(self, source: Path) -> None:
        """The admin shell and the auth store are the console's, not the site's."""
        text = source.read_text(encoding="utf-8")

        assert "components/app-shell" not in text
        assert "stores/auth" not in text


class TestTheConsoleIsGuardedByWhereItSits:
    def test_the_group_layout_requires_a_session(self) -> None:
        """A guard in the layout is one a new page cannot forget to add.

        It both asks whether there is a session and tries to open one from the
        signature Telegram attached — there being no sign-in page left to send
        anybody to.
        """
        layout = (ADMIN / "+layout.svelte").read_text(encoding="utf-8")

        assert "auth.refresh()" in layout
        assert "auth.me" in layout
        assert "auth.signInWithTelegram()" in layout

    def test_the_root_layout_guards_nothing_and_shows_nothing(self) -> None:
        """It covers both halves, so anything it decides is decided for both."""
        root = (ROUTES / "+layout.svelte").read_text(encoding="utf-8")

        assert "stores/auth" not in root
        assert "components/app-shell" not in root
