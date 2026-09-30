"""The catalog reads its own .env, never the one of the repository it sits in."""

from pathlib import Path

from students_cz.core.config import _find_env_file


def _layout(root: Path) -> Path:
    project = root / "catalog"
    module = project / "src" / "students_cz" / "core" / "config.py"
    module.parent.mkdir(parents=True)
    module.touch()
    (project / "alembic.ini").touch()
    return module


def test_the_projects_own_env_is_found(tmp_path: Path) -> None:
    module = _layout(tmp_path)
    (tmp_path / "catalog" / ".env").write_text("X=1\n")

    assert _find_env_file(module) == tmp_path / "catalog" / ".env"


def test_the_search_stops_at_the_project(tmp_path: Path) -> None:
    """supervisor-telegram's .env is above catalog/, and is not this service's."""
    module = _layout(tmp_path)
    (tmp_path / ".env").write_text("MODERATOR_BOT_TOKEN=1\n")

    assert _find_env_file(module) is None
