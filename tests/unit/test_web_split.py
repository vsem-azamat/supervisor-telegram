"""The public half of the web must stay public.

The public half is the Mini App in `web/`; the console is the Svelte app in
`webui/`, under `/admin`. Which build answers which path is docker/Caddyfile's
business, and a convention is exactly the kind of thing that erodes: somebody
needs a member count on a public screen, reaches for the endpoint that already
returns one, and a page anybody can open starts asking for an admin session.
Nothing in the type system notices.

So the boundary is asserted here instead. These read the sources as text on
purpose — what needs checking is which imports and which URLs appear, which the
text answers exactly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "webui" / "src" / "routes"
ADMIN = ROUTES / "(admin)"
APP = ROOT / "web" / "src"

# `fetch('/api/…')` and friends, template prefixes included. Only literal paths
# are findable, which is the point: a computed endpoint on a public screen
# would be unreviewable anyway.
API_CALL = re.compile(r"""['"`](/api/[^'"`\s$]*)""")

# What the Mini App may reach under /api: this repository's public endpoints,
# and the catalog's API, which Caddy sends to another backend altogether.
ALLOWED = ("/api/public", "/api/v1")


def _app_sources() -> list[Path]:
    generated = APP / "lib" / "generated"
    return sorted(p for p in [*APP.rglob("*.ts"), *APP.rglob("*.tsx")] if generated not in p.parents)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


class TestTheHalvesExist:
    def test_the_console_is_under_admin(self) -> None:
        assert (ADMIN / "admin" / "+page.svelte").is_file()

    def test_the_console_build_has_no_public_pages(self) -> None:
        """Every Svelte page is the console's; the public screens are the Mini App's.

        A page outside /admin would be unreachable (Caddy sends only /admin and
        /_app to this build) or, worse, a second public site nobody maintains.
        """
        pages = sorted(ROUTES.rglob("+page.svelte")) + sorted(ROUTES.rglob("+page.ts"))
        outside = [_rel(p) for p in pages if (ADMIN / "admin") not in p.parents]

        assert not outside

    def test_the_mini_app_is_there(self) -> None:
        assert (APP / "lib" / "api.ts").is_file()


class TestThePublicHalfAsksNothingOfAnybody:
    @pytest.mark.parametrize("source", _app_sources(), ids=_rel)
    def test_it_only_calls_public_endpoints(self, source: Path) -> None:
        called = API_CALL.findall(source.read_text(encoding="utf-8"))
        private = [path for path in called if not path.startswith(ALLOWED)]

        assert not private, f"{_rel(source)} reaches {private}, which needs a session"


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
