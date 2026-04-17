"""Channel review submodule — review agent, presentation, and service.

This package re-exports the public API from all three submodules so that
existing ``from app.channel.review import ...`` statements continue to work.
"""

# ── Agent ──
from app.channel.review.agent import (  # noqa: F401
    ReviewAgentDeps,
    clear_review_conversation,
    create_review_agent,
    register_message,
    resolve_post_id,
    review_agent_turn,
)

# ── Presentation (was review.py) ──
from app.channel.review.presentation import (  # noqa: F401
    build_review_keyboard,
    build_schedule_picker_keyboard,
    handle_approve,
    handle_delete,
    handle_edit_request,
    handle_regen,
    handle_reject,
    send_for_review,
)

# ── Service ──
from app.channel.review.service import (  # noqa: F401
    CB_APPROVE,
    CB_BACK,
    CB_DELETE,
    CB_LONGER,
    CB_PUBLISH_NOW,
    CB_REGEN,
    CB_REJECT,
    CB_SCHEDULE,
    CB_SCHEDULE_PICK,
    CB_SHORTER,
    CB_TRANSLATE,
    approve_post,
    create_review_post,
    delete_post,
    edit_post_text,
    extract_source_btn_data,
    extract_source_urls,
    regen_post_text,
    reject_post,
)

__all__ = [
    # agent
    "ReviewAgentDeps",
    "clear_review_conversation",
    "create_review_agent",
    "register_message",
    "resolve_post_id",
    "review_agent_turn",
    # presentation
    "build_review_keyboard",
    "build_schedule_picker_keyboard",
    "handle_approve",
    "handle_delete",
    "handle_edit_request",
    "handle_regen",
    "handle_reject",
    "send_for_review",
    # service
    "CB_APPROVE",
    "CB_BACK",
    "CB_DELETE",
    "CB_LONGER",
    "CB_PUBLISH_NOW",
    "CB_REGEN",
    "CB_REJECT",
    "CB_SCHEDULE",
    "CB_SCHEDULE_PICK",
    "CB_SHORTER",
    "CB_TRANSLATE",
    "approve_post",
    "create_review_post",
    "delete_post",
    "edit_post_text",
    "extract_source_btn_data",
    "extract_source_urls",
    "regen_post_text",
    "reject_post",
]
