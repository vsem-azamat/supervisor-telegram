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
