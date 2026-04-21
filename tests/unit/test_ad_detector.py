"""Tests for app.moderation.ad_detector — pure-function behavior."""

from __future__ import annotations

import pytest
from app.moderation.ad_detector import extract_ad_signals


def test_empty_text_returns_empty() -> None:
    assert extract_ad_signals("") == []
    assert extract_ad_signals(None) == []


def test_detects_t_me_link() -> None:
    signals = extract_ad_signals("Check out https://t.me/somegroup for cool stuff")
    assert len(signals) == 1
    assert signals[0].kind == "link"
    assert signals[0].canonical == "t.me/somegroup"


def test_detects_bare_mention() -> None:
    signals = extract_ad_signals("hey @cool_channel come join us")
    assert len(signals) == 1
    assert signals[0].kind == "mention"
    assert signals[0].canonical == "@cool_channel"


def test_link_and_mention_in_one_message() -> None:
    signals = extract_ad_signals("see @awesome_chat or t.me/another_one")
    canonicals = {s.canonical for s in signals}
    assert canonicals == {"@awesome_chat", "t.me/another_one"}


def test_whitelist_excludes_handles() -> None:
    signals = extract_ad_signals(
        "@konnekt_channel news! also t.me/konnekt_channel",
        whitelist=["@konnekt_channel"],
    )
    # both forms reference the whitelisted handle → both filtered
    assert signals == []


def test_whitelist_link_form_filters_both_forms() -> None:
    # Whitelist semantics is "trust this handle" — entry form (link vs
    # mention) doesn't change which forms get filtered.
    signals = extract_ad_signals(
        "t.me/foo and @foo_handle",
        whitelist=["t.me/foo", "@foo_handle"],
    )
    assert signals == []


def test_email_addresses_not_matched_as_mentions() -> None:
    signals = extract_ad_signals("write to user@example.com please")
    assert signals == []


def test_short_handles_below_5_chars_not_matched() -> None:
    signals = extract_ad_signals("@abc and @abcd should not match")
    assert signals == []


def test_telegram_me_and_telegram_dog_match() -> None:
    signals = extract_ad_signals("https://telegram.me/foobar and telegram.dog/bazqux")
    canonicals = {s.canonical for s in signals}
    assert canonicals == {"t.me/foobar", "t.me/bazqux"}


def test_invite_link_prefixes_match() -> None:
    s1 = extract_ad_signals("t.me/joinchat/abc123XYZ-_")
    s2 = extract_ad_signals("t.me/+abc123XYZ-_")
    assert s1[0].canonical == "t.me/joinchat/abc123xyz-_"
    assert s2[0].canonical == "t.me/+abc123xyz-_"


def test_duplicate_handles_collapse() -> None:
    signals = extract_ad_signals("@foo_bar @foo_bar t.me/qux t.me/qux")
    canonicals = [s.canonical for s in signals]
    assert canonicals == ["t.me/qux", "@foo_bar"]


def test_case_insensitive_canonical() -> None:
    signals = extract_ad_signals("@FooBar and T.ME/BazQux")
    canonicals = {s.canonical for s in signals}
    assert canonicals == {"@foobar", "t.me/bazqux"}


@pytest.mark.parametrize(
    "noise",
    [
        "hello world",
        "https://example.com/something",
        "1234567890",
        "@",
        "t.me/",
    ],
)
def test_no_false_positives_on_noise(noise: str) -> None:
    assert extract_ad_signals(noise) == []
