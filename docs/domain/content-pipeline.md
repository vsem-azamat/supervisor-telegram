# Content Pipeline

The content pipeline turns external sources into Telegram posts. Channels with a
review chat use a human approval step before publication; channels without one
publish directly after generation.

## Core Flow

`fetch_sources -> split_and_enrich_topics -> screen_content -> generate_post ->
send_for_review -> await_review -> publish_post | handle_rejection`

When a channel has no review chat, `send_for_review` publishes directly and the
workflow completes without `await_review`.

## Core Rules

- Source content is fetched, normalized, and screened before post generation.
- Duplicate or near-duplicate topics are filtered before publication decisions.
- Generated posts require review before publication when the channel has a
  review chat configured.
- Channels without a review chat use the direct publish path.
- Review supports approve, reject, regenerate, edit, and schedule outcomes.
- Administrator approve/reject decisions may be retained and summarized as
  future generation context.
- Scheduled Telegram publication uses the Telethon userbot because the Bot API
  does not provide the required client-level scheduling behavior.
- Source URLs obtained from external or model-produced input must pass SSRF-safe
  validation before fetching.

## Tests

- Pure transformations and scheduling calculations belong in unit tests.
- Deduplication and persistence-sensitive behavior belong in PostgreSQL
  integration tests when they depend on pgvector or database semantics.
- End-to-end tests should cover the review workflow and observable Telegram I/O.
