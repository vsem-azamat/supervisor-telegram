from aiogram.filters.callback_data import CallbackData


class BlacklistConfirm(CallbackData, prefix="blconfirm"):
    user_id: int
    chat_id: int
    message_id: int
    revoke: int = 0
    mark_spam: int = 0


class UnblockUser(CallbackData, prefix="unblock"):
    user_id: int


class BlacklistPagination(CallbackData, prefix="blpage"):
    page: int
    query: str = ""


class BlacklistSearch(CallbackData, prefix="blsearch"):
    user_id: int


# ── Channel post review callbacks ──


class ReviewAction(CallbackData, prefix="rv"):
    """Single-field callback for simple review actions (approve, reject, delete, etc.)."""

    action: str  # approve, reject, delete, regen, shorter, longer, translate, schedule, back
    post_id: int


class SchedulePick(CallbackData, prefix="rvsp"):
    """Schedule a post at a specific time."""

    post_id: int
    ts: int  # unix timestamp


class PublishNow(CallbackData, prefix="rvpub"):
    """Publish a scheduled post immediately."""

    post_id: int
