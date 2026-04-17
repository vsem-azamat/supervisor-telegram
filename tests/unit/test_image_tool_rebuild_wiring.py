"""The agent's _refresh_review_message helper delegates to telegram_io._rebuild_review_message.

We don't test via the PydanticAI toolset registry (internals change too often);
we test the seam by lexical inspection of agent.py's source, plus the
Task 9 e2e covers the full runtime behaviour end-to-end.
"""

from __future__ import annotations

import inspect


def test_agent_module_uses_telegram_io_rebuild():
    """Lexical check: agent.py imports and references _rebuild_review_message."""
    import app.channel.review.agent as agent_mod

    src = inspect.getsource(agent_mod)
    assert "_rebuild_review_message" in src, (
        "agent.py should route image-tool refresh through telegram_io._rebuild_review_message"
    )
    # The old per-message delete-and-single-send path must be gone.
    assert "bot.delete_message(chat_id=review_chat_id, message_id=post.review_message_id)" not in src, (
        "agent.py should no longer open-code single-message delete-and-resend; "
        "that logic lives in telegram_io._rebuild_review_message now."
    )
