# Telegram Identities

Supervisor Telegram uses three Telegram identities with distinct
responsibilities.

## Identities

| Identity | Responsibility |
| --- | --- |
| Moderator bot | Mechanical commands, moderation workflows, welcome/captcha behavior, and channel publishing through the Bot API |
| Assistant bot | Conversational admin interface and higher-level tool orchestration |
| Telethon userbot | Client API capabilities unavailable to bots, including history/search access and scheduled messages |

## Core Rules

- Keep responsibilities explicit. Do not move userbot-only behavior into bot API
  code or vice versa.
- Treat the Telethon session as sensitive account-level state.
- Production and development instances must not run concurrently against the
  same bot tokens, userbot session identity, and database unless that overlap is
  explicitly intended and safe.
- When one workflow crosses identities, tests and docs should state which
  identity performs each externally visible action.

## Review Message Ownership

Telegram delivers an inline-keyboard callback to the bot that sent the message,
so the identity that sends a review draft must be the one whose dispatcher
handles review callbacks:

- Assistant bot when the assistant is active (`settings.assistant.active`), because
  `channel_review_router` is attached to its dispatcher.
- Moderator bot otherwise.

This binds processes that never poll for updates. The web API sends review
drafts too, and picks the identity with the same rule
(`app/webapi/services/review_bot.py`); publishing to a channel is unaffected and
always uses the moderator identity. Sending a review draft under the wrong
identity produces a message that renders correctly and whose approve/reject
buttons silently do nothing.
