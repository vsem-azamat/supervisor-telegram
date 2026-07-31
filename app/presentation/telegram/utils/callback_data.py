from aiogram.filters.callback_data import CallbackData


class BlacklistConfirm(CallbackData, prefix="blconfirm"):
    user_id: int
    chat_id: int
    message_id: int
    revoke: int = 0
    mark_spam: int = 0


class PendingActionDecision(CallbackData, prefix="pact"):
    """Confirm or drop a destructive action proposed from outside.

    Typed rather than hand-built from an f-string, so aiogram validates the
    64-byte limit instead of leaving it to arithmetic.
    """

    pending_id: int
    confirm: int


class UnblockUser(CallbackData, prefix="unblock"):
    user_id: int


class BlacklistPagination(CallbackData, prefix="blpage"):
    page: int
    query: str = ""
