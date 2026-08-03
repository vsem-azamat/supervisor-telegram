"""The Russian three-way plural, which is where a ternary always fails."""

import pytest
from app.core.text import plural


@pytest.mark.unit
@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (1, "чат"),
        (2, "чата"),
        (4, "чата"),
        (5, "чатов"),
        (10, "чатов"),
        # The teens all take the third form, including the ones whose last
        # digit says otherwise. This is the case a two-form ternary gets wrong.
        (11, "чатов"),
        (12, "чатов"),
        (14, "чатов"),
        (21, "чат"),
        (22, "чата"),
        (25, "чатов"),
        (101, "чат"),
        (111, "чатов"),
        (0, "чатов"),
    ],
)
def test_endings(count: int, expected: str):
    assert plural(count, "чат", "чата", "чатов") == expected
