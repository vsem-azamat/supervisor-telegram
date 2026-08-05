"""The deploy workflow and compose file must agree on what config to forward.

Configuration lives in GitHub and travels to the host with the deploy command;
nothing is written to a file there. That means the same list of variable names
exists in two places, and a setting added to one but not the other fails at
runtime in production rather than here — silently, since almost every setting
has a default.

So the two are pinned against each other.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yaml"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"

# Set by the workflow itself rather than passed to the app, so they appear in
# the deploy step but have no place in a service's environment.
_DEPLOY_ONLY = {"IMAGE_TAG"}


def _compose_passthrough() -> set[str]:
    """Names the compose file expects to inherit from the environment.

    A null value in the mapping form is compose's "take this from the host";
    entries with a literal value are baked in and are not our concern.
    """
    raw = COMPOSE.read_text()
    # Anchors and merge keys are not part of the YAML core schema that
    # safe_load resolves for us here, so read the anchor block directly.
    # Entries with a literal value are fixed in the file, not forwarded.
    block = re.search(r"^x-runtime-env: &runtime-env\n((?:  \S.*\n)+)", raw, re.M)
    assert block, "the shared environment anchor is gone or was renamed"
    return set(re.findall(r"^  ([A-Z_]+):\s*$", block.group(1), re.M))


def _deploy_step() -> dict:
    workflow = yaml.safe_load(DEPLOY.read_text())
    for step in workflow["jobs"]["deploy"]["steps"]:
        if str(step.get("uses", "")).startswith("appleboy/ssh-action"):
            return step
    raise AssertionError("no ssh deploy step found")


def test_every_forwarded_name_is_declared_in_both_places() -> None:
    step = _deploy_step()
    forwarded = {name.strip() for name in step["with"]["envs"].split(",") if name.strip()}

    assert forwarded - _DEPLOY_ONLY == _compose_passthrough()


def test_every_forwarded_name_has_a_value_to_forward() -> None:
    """`envs` names a variable; without an `env:` entry it forwards nothing."""
    step = _deploy_step()
    forwarded = {name.strip() for name in step["with"]["envs"].split(",") if name.strip()}

    assert forwarded == set(step["env"])


def test_credentials_come_from_secrets_and_the_rest_from_variables() -> None:
    """A token in `vars` is readable by anyone with repository access."""
    step = _deploy_step()
    sensitive = {
        "DB_PASSWORD",
        "MODERATOR_BOT_TOKEN",
        "OPENROUTER_API_KEY",
        "BRAVE_API_KEY",
        "TELETHON_API_ID",
        "TELETHON_API_HASH",
        "MCP_TOKEN",
    }

    for name, expression in step["env"].items():
        if name in sensitive:
            assert "secrets." in expression, f"{name} must come from secrets"
        elif name != "IMAGE_TAG":
            assert "vars." in expression, f"{name} should come from variables, not {expression}"


def test_nothing_writes_configuration_to_the_host() -> None:
    """The point of the exercise: no .env is created, edited or read."""
    script = _deploy_step()["with"]["script"]

    assert ".env" not in script


def test_the_pull_does_not_depend_on_the_host_docker_login() -> None:
    """The images are public and the host is shared with other projects.

    Depending on a login nobody here maintains is how a deploy comes to fail
    with "denied" against images anyone can read: a rejected credential does
    not fall back to anonymous. Our own config directory has nothing in it to
    go stale.
    """
    script = _deploy_step()["with"]["script"]

    assert "DOCKER_CONFIG" in script
    assert script.index("DOCKER_CONFIG") < script.index("docker compose pull")
