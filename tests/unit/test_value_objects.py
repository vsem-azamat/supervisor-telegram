"""Unit tests for core enums (PostStatus, EscalationStatus, ReviewDecision)."""

from app.core.enums import EscalationStatus, PostStatus, ReviewDecision


class TestPostStatus:
    """Test cases for PostStatus StrEnum."""

    def test_values(self):
        assert PostStatus.DRAFT == "draft"
        assert PostStatus.SCHEDULED == "scheduled"
        assert PostStatus.APPROVED == "approved"
        assert PostStatus.REJECTED == "rejected"

    def test_is_str(self):
        assert isinstance(PostStatus.DRAFT, str)

    def test_all_members(self):
        assert set(PostStatus) == {
            PostStatus.DRAFT,
            PostStatus.SCHEDULED,
            PostStatus.APPROVED,
            PostStatus.REJECTED,
        }


class TestEscalationStatus:
    """Test cases for EscalationStatus StrEnum."""

    def test_values(self):
        assert EscalationStatus.PENDING == "pending"
        assert EscalationStatus.RESOLVED == "resolved"
        assert EscalationStatus.TIMEOUT == "timeout"

    def test_is_str(self):
        assert isinstance(EscalationStatus.PENDING, str)

    def test_all_members(self):
        assert set(EscalationStatus) == {
            EscalationStatus.PENDING,
            EscalationStatus.RESOLVED,
            EscalationStatus.TIMEOUT,
        }


class TestReviewDecision:
    """Test cases for ReviewDecision StrEnum."""

    def test_values(self):
        assert ReviewDecision.APPROVED == "approved"
        assert ReviewDecision.REJECTED == "rejected"

    def test_is_str(self):
        assert isinstance(ReviewDecision.APPROVED, str)

    def test_all_members(self):
        assert set(ReviewDecision) == {
            ReviewDecision.APPROVED,
            ReviewDecision.REJECTED,
        }
