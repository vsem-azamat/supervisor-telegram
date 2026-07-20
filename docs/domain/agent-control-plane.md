# Agent Control Plane (MCP)

The web API can expose an MCP endpoint so an external agent runtime — an agent
that talks to the operator in its own chat surface — can inspect channels and
propose content. This document owns the rules for that surface.

It is a second admin control plane next to the authenticated web UI. Everything
here is about keeping it strictly less capable than the operator's own tools.

## Scope

The endpoint exposes exactly three tools:

| Tool | Effect |
| --- | --- |
| `list_channels` | Read. Every channel with its review-chat status. |
| `get_channel` | Read. One channel's configuration plus recent posts. |
| `generate_and_send_for_review` | Write. Generates a draft and puts it in the channel's review chat. |

The toolset is a security boundary, not a convenience list. It must not grow to
include publishing, banning, blacklisting, deleting, or chat mutation. A test
pins the exposed tool names so widening the surface is a deliberate act.

## Rules

- The endpoint is mounted only when `MCP_ENABLED` is true **and** `MCP_TOKEN` is
  set. An enabled-but-tokenless configuration stays closed; a misconfigured
  deploy must never expose admin tooling unauthenticated.
- Every request presents `Authorization: Bearer <MCP_TOKEN>`. The token
  identifies the calling runtime, not a person, and is checked before any MCP
  session is established.
- The token is not an admin session and grants no other web API access. Admin
  session cookies remain the only path to the rest of `/api`.
- `generate_and_send_for_review` must not be able to make anything public. The
  shared generation service publishes directly when a channel has no review
  chat, and that path is reachable only by passing it a publish bot. The MCP
  tool passes none, so the direct-publish branch is unreachable for this
  endpoint by construction — not because the tool checks `review_chat_id` first.
  Such a request returns `no_review_chat` without generating anything.
- Nothing this endpoint produces reaches a channel's audience without a human
  pressing approve on the review keyboard. Approval stays in the bot process.
- `channel_id` is always the numeric Telegram ID. An unknown channel is rejected
  before any LLM call or Telegram send.
- Generation is rate limited (`MCP_MAX_DRAFTS_PER_HOUR`). The endpoint cannot
  publish, but an attacker holding the token could otherwise burn model budget
  and flood a review chat; over-limit calls return `rate_limited`.
- Tool errors are masked. Unhandled exceptions must not be returned verbatim,
  because they reach an external runtime and from there an operator's chat
  history — a failed database connection would otherwise leak its DSN.

The guarantee rests on `review_chat_id` pointing somewhere non-public. Nothing
validates that it differs from the channel itself, so a channel misconfigured
through the admin API would receive drafts directly. That is a property of the
channel configuration, not of this endpoint.

## Review message ownership

A review message carries an inline keyboard, and Telegram delivers a button's
callback to the bot that sent the message. `channel_review_router` is attached
to the assistant dispatcher when the assistant is active, and to the moderator
dispatcher otherwise.

Any process sending a review message must therefore use the same bot identity —
assistant token when `settings.assistant.active`, moderator token otherwise. A
review draft sent under the wrong identity renders correctly and its buttons do
nothing. See [Telegram Identities](telegram-identities.md).

## Relationship to the in-process assistant

Both the assistant tool `generate_and_review` and the MCP tool
`generate_and_send_for_review` call the same service, `app/channel/adhoc.py`, so
generation, deduplication and review routing behave identically. They differ
only in what they are handed and what they render: the assistant supplies a
publish bot, so it keeps the direct-publish fallback for channels without a
review chat, and renders operator-facing Russian text; the MCP tool supplies
none and returns structured data.
