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

### Image edit (`use_candidate`, `add_image_url`, `remove_image`, `reorder_images`, `clear_images`)

The existing `_refresh_after_change` in `app/channel/review/agent.py` already calls `_refresh_review_message` after each image op. We upgrade `_refresh_review_message` (in `agent.py`) to use the new render helper and handle the album case:

1. Re-fetch the post from DB to get fresh `image_urls` and existing `review_message_id` / `review_album_message_ids`.
2. Call `_render_review_message` with the new state — sends fresh messages first.
3. Commit new `(pult_id, album_ids)` to DB (so callbacks on new pult work immediately).
4. Best-effort `bot.delete_messages(chat_id, [old_pult_id, *old_album_ids])`. Log but ignore failures (messages >48h old, already deleted, etc.).

This "new-first-then-delete" order means the worst visible failure is a few seconds of duplicate messages, never a dead-callback state.

Note: `find_and_add_image` does **not** trigger a refresh — it adds to the candidate pool, not to the selected images. Existing behaviour preserved.

`*_op` functions in `image_tools.py` keep their current `-> str` signature. The refresh call stays unconditional at the @tool-wrapper level: if the op returned an error ("invalid index"), refresh rebuilds the same visual state — cheap and idempotent. Not worth the signature-change scope.

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
| `app/channel/review/telegram_io.py` | new `_render_review_message`; `send_for_review` persists album ids; `handle_delete` cleans album ids; `handle_regen` always rebuilds | +90 new, ~40 changed |
| `app/channel/review/agent.py` | `_refresh_review_message` upgraded: fetches album ids from DB, new-first-then-delete, calls `_render_review_message` | ~50 changed |
| `app/channel/review/service.py` | `regen_post_text` returns the updated post with image_urls so the caller can rebuild | ~5 changed |
| `tests/fake_telegram.py` | new `/sendMediaGroup` and `/deleteMessages` endpoints | +60 |

### Design decision: minimise blast radius

`agent.py` already owns the "refresh review message after an image op" call (`_refresh_after_change` → `_refresh_review_message`). We keep that seam. `image_tools.py` stays pure; its unit tests don't need to know about Telegram. The work of the rebuild moves *inside* `_refresh_review_message`, not up into the tool wrappers.

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
- `tests/unit/test_review_refresh_album.py` — `_refresh_review_message` when post has album ids: fetches post, calls render helper, commits new ids, then best-effort deletes old.

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
