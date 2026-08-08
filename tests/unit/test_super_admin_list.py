"""Who may open the console, as the deploy actually spells it.

The list arrives as one environment variable forwarded by the deploy, and the
class has always carried a validator that splits it on commas. That validator
was unreachable from the environment: pydantic-settings JSON-decodes a list
field at its source, so a comma-separated value raised before anything could
split it — and both processes refuse to boot on a `SettingsError`, which is
what adding a second administrator would have done.

The same trap is documented on `allowed_origins`, where it went unnoticed for
longer because the cost was a silent empty list rather than a crash.

Read straight from the environment on purpose. `model_validate` takes a Python
value and never touches the source that was doing the decoding, so a test
written that way passes either way and pins nothing.
"""

from __future__ import annotations

import pytest
from app.core.config import AdminSettings

pytestmark = pytest.mark.unit


def _admins() -> list[int]:
    """Build the settings the way a deployed process does.

    `_env_file=None` because a developer's own `.env` would otherwise decide
    the answer.
    """
    return AdminSettings(_env_file=None).super_admins


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("111", [111]),
        # Comma-separated: how the setting is documented, and how anyone would
        # write it when adding a colleague.
        ("111,222", [111, 222]),
        ("111, 222 ,333", [111, 222, 333]),
        # A JSON array: the only spelling that used to work, so it may well be
        # what is deployed right now. Refusing it means a deploy that will not
        # boot.
        ("[111, 222]", [111, 222]),
        ("[111]", [111]),
    ],
)
def test_the_list_parses_however_it_was_written(monkeypatch, raw: str, expected: list[int]) -> None:
    monkeypatch.setenv("ADMIN_SUPER_ADMINS", raw)

    assert _admins() == expected


def test_a_second_administrator_does_not_take_the_process_down(monkeypatch) -> None:
    """The regression itself, stated as the thing that would have happened."""
    monkeypatch.setenv("ADMIN_SUPER_ADMINS", "268388996,7000000")

    assert len(_admins()) == 2
