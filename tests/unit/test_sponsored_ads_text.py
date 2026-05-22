from app.sponsored_ads.text import normalize_text


def test_normalize_collapses_whitespace_and_casefolds() -> None:
    assert normalize_text("  Buy   NOW\n\nCheap ") == "buy now cheap"


def test_normalize_handles_none_and_empty() -> None:
    assert normalize_text(None) == ""
    assert normalize_text("   ") == ""


def test_normalize_identical_for_blast_copies() -> None:
    a = normalize_text("СРОЧНО продам айфон  @seller")
    b = normalize_text("срочно ПРОДАМ айфон @seller")
    assert a == b
