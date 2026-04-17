# Review Album UI Design

**Date:** 2026-04-17
**Status:** Draft
**Sprint:** 1.5 (Sprint 1 follow-up)

## Problem

After Sprint 1 landed the multi-image pipeline, posts routinely carry 2–4 images in `ChannelPost.image_urls`. The channel **publisher** already sends these as a Telegram media group, but the **review flow** still only shows the **first** image (see `app/channel/review/telegram_io.py:187`). Reviewers cannot see what the agent actually composed until the post is published.

This design replaces the review-message rendering with an "album + pult" presentation when a post has 2+ images, keeping the existing single-photo and text-only paths for smaller posts.

## Goals

- Reviewer sees **every** image a post carries, in the exact order the publisher will use.
- Review buttons (Approve / Reject / Delete / Regen / etc.) stay fully functional regardless of image count.
- Reviewer's granular image tools (`use_candidate`, `add_image_url`, `remove_image`, `reorder_images`, `find_and_add_image`, `clear_images`) refresh the visible album after mutation.

## Non-goals

- Longer-than-900-char posts. Generator cap remains 900; Telegram caption cap is 1024; the "caption too long → image lost" edge case does not trigger under existing rules.
- In-place per-slot editing of media groups. We use a uniform **delete-and-resend** strategy when the album changes.
- Carousel UI (◀ 1/3 ▶) — explicitly rejected in brainstorming.
- A style-RAG or critic agent. Those are separate Sprint 2 tracks.

## Architecture overview

```
┌────────────────────────────── Review chat ──────────────────────────────┐
│                                                                          │
│  [📷] [📷] [📷]        ← send_media_group (N photos, no captions)        │
│  ────────────────                                                        │
│  Post text...          ← send_message (text + entities + reply_markup)   │
│  [✅ Approve] [⏰ Schedule] [❌ Reject] [🗑 Delete]                        │
│  [✂️ Shorter] [📝 Longer] [🔄 Regen]                                      │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

Rendering modes (decided by `len(image_urls)`):

| Mode | Condition | Messages sent | Callback target |
|---|---|---|---|
| `text` | 0 images | 1 text msg (text + buttons) | The text msg |
| `single` | 1 image | 1 photo msg (caption + buttons) | The photo msg |
| `album` | ≥2 images | N photo msgs (no caption) + 1 **pult** text msg (reply to first photo, text + buttons) | The pult |

`text` and `single` are existing behaviour and do not change. `album` is new.

### Invariants

- `ChannelPost.review_message_id` always points to the message that carries inline buttons (pult in `album` mode, the single msg in `text`/`single`).
- `ChannelPost.review_album_message_ids` is **not null** iff mode is `album`. In that case it holds the photo message ids (in display order), **not** including the pult.
- Callbacks are routed by `post_id` embedded in `callback_data` — the pult message id is only used for edits.

## Data model

### ORM

`app/db/models.py` gains one column on `ChannelPost`:

```python
review_album_message_ids: Mapped[list[int] | None] = mapped_column(
    JSON, nullable=True, default=None
)
```

Precedent: `reply_chain_message_ids` (same line) is already `Mapped[list[int] | None]` over JSON. The same conventions apply:

- Add `review_album_message_ids: list[int] | None = None` as an `__init__` kwarg with default `None`, and assign `self.review_album_message_ids = review_album_message_ids` inside `__init__`. Sprint 1 code review flagged missed `__init__` kwargs for new columns — this is now a permanent checklist item.

### Migration

New Alembic revision with `down_revision = <latest>`. Up adds the column; down drops it. No backfill: posts already in a terminal status are unaffected, and `DRAFT` posts without the column behave as non-album (falls back to existing `review_message_id` path).

## Message lifecycle

All send/edit/rebuild logic lives in `app/channel/review/telegram_io.py` behind two new private helpers:

```python
async def _render_review_message(
    bot, chat_id, post_text, image_urls, keyboard
) -> tuple[int, list[int] | None]:
    """Send the review message in the right mode. Returns (pult_id, album_ids | None)."""

async def _rebuild_review_message(
    bot, chat_id, post, session_maker, keyboard
) -> tuple[int, list[int] | None]:
    """New-first-then-delete rebuild. Commits new ids before best-effort deleting old."""
```

### Send (primary)

`send_for_review` calls `_render_review_message` once and persists the returned ids:

- `album` mode: `bot.send_media_group(N InputMediaPhoto, no caption)` → `bot.send_message(text + entities + reply_markup, reply_to=media[0].message_id, parse_mode=None)`. Returns `(pult.id, [photo.id ...])`.
- `single` mode: existing `send_photo(caption+buttons)` path. Returns `(photo.id, None)`.
- `text` mode: existing `send_message(text+buttons)` path. Returns `(msg.id, None)`.

### Text-only edit (`update_post`, shorter, longer)

No change in behaviour. `_edit_review_message(pult_id, ...)` works identically whether pult is a photo-with-caption (single mode) or a plain text message (album mode). Album photos are never touched.

### Image edit (`use_candidate`, `add_image_url`, `remove_image`, `reorder_images`, `find_and_add_image`, `clear_images`)

After a successful mutation, the @agent.tool wrapper in `app/channel/review/agent.py` calls `_rebuild_review_message`:

1. Call `_render_review_message` with the post's new state — this sends *new* messages first.
2. Commit new `(pult_id, album_ids)` to DB (so callbacks on new pult work immediately).
3. Best-effort `bot.delete_messages(chat_id, [old_pult_id, *old_album_ids])`. Log but ignore failures (messages >48h old, already deleted, etc.).

This "new-first-then-delete" order means the worst visible failure is a few seconds of duplicate messages, never a dead-callback state.

### Regen

`regen_post_text` already recomputes text **and** re-runs the image pipeline. After a successful regen we **always** rebuild — simpler than diffing new vs old image sets, and regen is the heaviest operation anyway.

### Approve / Reject / Delete

- **Approve:** `publisher.publish_post` already handles `image_urls` as a media group. No changes.
- **Delete:** `handle_delete` currently calls `bot.delete_message(review_message_id)`. Extend to `bot.delete_messages(chat_id, [pult_id, *album_ids])` when album_ids is non-null. Best-effort.
- **Reject:** The review message stays in chat (status changes, button set rebuilt elsewhere). No album-specific work.

## Code surface

| File | Change | Est. LOC |
|---|---|---|
| `app/db/models.py` | +1 field `review_album_message_ids` (JSON nullable) | +3 |
| `alembic/versions/<new>.py` | new migration | ~25 |
| `app/channel/review/telegram_io.py` | new `_render_review_message`, `_rebuild_review_message`, `_delete_album` helpers; refactor `_send_review_message` into `_render`; `handle_delete` cleans album ids | +120 new, ~30 changed |
| `app/channel/review/image_tools.py` | each `*_op` returns `(status: str, mutated: bool)` | +30 |
| `app/channel/review/agent.py` | each @agent.tool wrapper calls `_rebuild_review_message` when `mutated` | +15 |
| `app/channel/review/service.py` | `create_review_post` initialises `review_album_message_ids=None`; `regen_post_text` triggers rebuild via caller | +10 |

### Design decision: where does the Telegram side-effect live?

image_tools `*_op` functions are currently pure DB operations, testable without Telegram mocks. Adding a Telegram side-effect has two viable shapes:

- **X (chosen):** `*_op` returns `(status, mutated)`. The agent @tool wrapper (which already has `bot` in deps) decides when to call `_rebuild_review_message`. Keeps image_tools Telegram-agnostic. Small duplication in 7 wrappers.
- **Y (rejected):** inject a `rebuild_fn` callable into `ImageToolsDeps`. DRY-er but forces image_tools unit tests to mock the callback; blurs the layering.

We take **X**. Duplication is minimal (one line per wrapper) and the layering is cleaner.

## Testing

### Unit

- `tests/unit/test_channel_post_album_ids.py` — ORM round-trips `list[int]` and `None`.
- `tests/unit/test_review_render_modes.py` — `_render_review_message` with mocked `Bot`:
  - 0 images → `send_message` once.
  - 1 image → `send_photo(caption+buttons)` once.
  - 2 images → `send_media_group` once + `send_message` once, reply-to set correctly.
- `tests/unit/test_review_rebuild.py` — `_rebuild_review_message`:
  - Order: new send → DB commit → old delete.
  - `delete_messages` raising does **not** roll back DB or bubble.
- `tests/unit/test_image_tools_mutated_flag.py` — each of the 7 `*_op` returns `mutated=True` on success, `False` on invalid-input / wrong-status.

### Integration (PG)

- `tests/integration/test_review_album_migration_pg.py` — alembic `upgrade head` then `downgrade -1` on a clean DB.
- `tests/integration/test_review_album_persistence_pg.py` — after rebuild, DB has new ids; old ids are gone from column.

### E2E (`FakeTelegramServer`)

**Pre-req:** the fake server at `tests/fake_telegram.py` does **not** currently route `sendMediaGroup` or `deleteMessages`. Add handlers that:

- `POST /bot{token}/sendMediaGroup` — accepts `media` (JSON-encoded list of `InputMediaPhoto`), returns a list of minimal `Message` objects with distinct `message_id`s, records the call for assertions.
- `POST /bot{token}/deleteMessages` — accepts `message_ids` (list of ints), records the call, returns `{ok: true, result: true}`.


- `tests/e2e/test_review_album_send.py` — generate post with 2 images → `send_for_review` → fake server sees exactly one `sendMediaGroup` (2 photos, no captions) + one `sendMessage` (reply_to=first photo, has `reply_markup`).
- `tests/e2e/test_review_album_image_tool_rebuild.py` — reviewer calls `remove_image` → fake server sees: 1× `sendMediaGroup` (1 photo now) OR `sendPhoto` (if mode flips to single), 1× `sendMessage` (new pult), 1× `deleteMessages` with old ids.
- `tests/e2e/test_review_album_regen.py` — regen always triggers rebuild.
- `tests/e2e/test_review_album_approve.py` — approve still publishes the full album via `publisher.publish_post`.

### Out of scope for tests

- Real Telegram API (only via `FakeTelegramServer`).
- Image rendering / bytes — handled by Sprint 1 pipeline.

## Error handling

| Failure | Strategy |
|---|---|
| `send_media_group` raises (bad URL, rate limit) | Rebuild fails — don't update DB, return error status from tool. Existing review message remains valid. **No** fallback to single-photo mode (would desynchronise vs what publisher will do). Log and surface to reviewer. |
| `send_message` (pult) fails after `send_media_group` succeeded | Rare (API hiccup). Log error. DB still has old pult; album photos are "orphaned" in chat. Reviewer sees duplicate photos plus old pult. Acceptable — rebuild can be retried via another tool call. |
| `delete_messages` raises (too-old / already-deleted) | Best-effort. Log warning, swallow exception. New messages already committed. |
| Migration `downgrade` on a DB with non-null `review_album_message_ids` | Column drop is destructive. That is fine — ids are ephemeral (review chat only). |

## Rollout

- Single PR off `feat/review-album-ui` branch → squash to `main`.
- Order of changes inside the PR (for reviewer sanity):
  1. Migration + model field
  2. `_render_review_message` / `_rebuild_review_message` + renaming
  3. `send_for_review` persists album ids
  4. image_tools return `(status, mutated)`
  5. agent wrappers call rebuild
  6. `handle_delete` extends cleanup
  7. Tests: unit → integration → e2e
- No feature flag. Backwards-compat holds because the new column is nullable and mode is decided at render time from `len(image_urls)`.
- Rollback: `alembic downgrade -1`. No data loss (column is ephemeral review-chat state).

## Risk register

- **`delete_messages` batch partial failure** — Telegram occasionally accepts a batch and leaves some messages undeleted. We treat the whole batch as best-effort. Acceptable.
- **Media-group order drift** — if `send_media_group` returns messages in a different order than we sent, callbacks still work (they target pult), but our stored `album_message_ids` should match the returned order. Sort by `message_id` is **not** safe — Telegram guarantees the returned list matches request order, so we store `[m.message_id for m in messages]`.
- **Pult reply-to becomes orphan on delete** — when we delete the first album photo, the pult's `reply_to_message_id` points to a dead id. Telegram shows "deleted message" hint. Cosmetic only; rebuild replaces pult anyway. Not worth fixing.
- **Race: reviewer clicks a callback mid-rebuild** — the callback hits the old pult which is about to be deleted. The handler looks up the post by `post_id` (from `callback_data`), so it still resolves. Between new-send and delete-old, the old pult keyboard is still live. Acceptable.

## Future work (explicitly deferred)

- In-place `edit_message_media` when album size is unchanged (less chat noise).
- Long-text posts with a separate pult even in single-image mode (requires generator changes).
- Sprint 2: critic agent, style-RAG.
