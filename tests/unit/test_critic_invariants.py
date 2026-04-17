"""Tests for critic helpers: link extraction, artifact stripping, invariant validation."""

from __future__ import annotations

from app.channel.critic import (
    CriticError,
    _extract_md_links,
    _strip_agent_artifacts,
    _validate_invariants,
)

FOOTER = "——\n🔗 **Konnekt** | @konnekt_channel"


def test_extract_md_links_empty():
    assert _extract_md_links("") == []


def test_extract_md_links_none():
    assert _extract_md_links("plain text no links") == []


def test_extract_md_links_single():
    out = _extract_md_links("Check [platform](https://example.com/x) today")
    assert out == [("platform", "https://example.com/x")]


def test_extract_md_links_multiple():
    out = _extract_md_links("See [a](http://x/1) and [b](http://y/2)")
    assert out == [("a", "http://x/1"), ("b", "http://y/2")]


def test_extract_md_links_ignores_malformed():
    assert _extract_md_links("broken [text(no close http://x)") == []


def test_strip_agent_artifacts_clean_passthrough():
    text = "🎓 **Headline**\n\nBody.\n\n" + FOOTER
    assert _strip_agent_artifacts(text) == text


def test_strip_agent_artifacts_code_fence():
    text = "```\n🎓 **H**\n\nBody.\n```"
    assert _strip_agent_artifacts(text) == "🎓 **H**\n\nBody."


def test_strip_agent_artifacts_markdown_fence():
    text = "```markdown\n🎓 **H**\n```"
    assert _strip_agent_artifacts(text) == "🎓 **H**"


def test_strip_agent_artifacts_prefix():
    text = "Here's your polished version:\n\n🎓 **H**\n\nBody."
    out = _strip_agent_artifacts(text)
    assert out.startswith("🎓"), out


def test_strip_agent_artifacts_surrounding_quotes():
    text = '"🎓 **H** Body."'
    assert _strip_agent_artifacts(text) == "🎓 **H** Body."


def _make_polished(
    body: str = "Body text with [link](https://x/1). Some extra words to reach the minimum length.",
) -> str:
    return f"🎓 **Headline**\n\n{body}\n\n{FOOTER}"


def test_validate_invariants_all_valid():
    original = _make_polished()
    polished = _make_polished()
    assert _validate_invariants(original, polished, FOOTER) == []


def test_validate_invariants_lost_url():
    original = _make_polished("Body with [link](https://x/1) here.")
    polished = _make_polished("Body without the link here.")
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("lost URL" in v for v in violations), violations


def test_validate_invariants_link_count_dropped():
    original = f"🎓 **H**\n\n[a](http://x/1) and [b](http://y/2)\n\n{FOOTER}"
    polished = f"🎓 **H**\n\nBoth links removed\n\n{FOOTER}"
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("link count" in v or "lost URL" in v for v in violations), violations


def test_validate_invariants_missing_footer():
    original = _make_polished()
    polished = "🎓 **Headline**\n\nBody text with [link](https://x/1)."
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("footer" in v.lower() for v in violations), violations


def test_validate_invariants_length_over_900():
    original = _make_polished()
    polished = "🎓 **H**\n\n" + "word " * 300 + f"\n\n{FOOTER}"
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("over 900" in v or "length" in v.lower() for v in violations), violations


def test_validate_invariants_output_too_short():
    original = _make_polished()
    polished = "🎓 X"
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("too short" in v or "100" in v for v in violations), violations


def test_validate_invariants_missing_headline_emoji():
    original = _make_polished()
    polished = f"**Headline**\n\nBody text with [link](https://x/1).\n\n{FOOTER}"
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("emoji" in v.lower() for v in violations), violations


def test_validate_invariants_whitelisted_emojis_pass():
    for emoji in ["📰", "🎓", "💼", "🎉", "🏠", "💰", "⚡"]:
        body = "Body text with [link](https://x/1). Some extra words to reach the minimum length."
        polished = f"{emoji} **Headline**\n\n{body}\n\n{FOOTER}"
        assert _validate_invariants(polished, polished, FOOTER) == []


def test_critic_error_subclass_of_domain():
    from app.core.exceptions import DomainError

    assert issubclass(CriticError, DomainError)
