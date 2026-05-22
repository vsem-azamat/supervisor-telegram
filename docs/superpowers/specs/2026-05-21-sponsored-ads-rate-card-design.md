# Sponsored Ads v0 — Rate Card Funnel — Design

- **Date:** 2026-05-21
- **Branch:** `docs/sponsored-ads-product`
- **Status:** Approved design — ready for implementation planning

## 1. Context & Problem

Managed Telegram chats receive ad-like spam. Today the ad-detector
(`app/moderation/ad_detector.py` + `ad_detector_service.py`) silently records a
`SpamPing` row for every message with ad signals — no admin notification, no
action is taken.

A previous attempt (`app/sponsored_ads/`, the `SponsoredAdRequest` model,
migration `c3d4e5f6a7b8`, the per-chat gate commits) built a backend skeleton
for a full conversational ad-sales pipeline: advertiser submission, LLM price
negotiation, an 11-state request lifecycle, manual payment. Review concluded
that skeleton is over-scoped for the real volume (~1 placement/chat/month),
stops dead at `payment_confirmed`, and is unreachable by any user. It is
dropped (see §3).

v0 instead delivers a **rate-card funnel**: detect ad-spam, let a moderator
remove it privately, and redirect the would-be advertiser to a legitimate
paid-placement path — without the bot handling money, content, or negotiation.

## 2. Goals / Non-goals

**Goals:**

- Moderators review flagged ads in a private chat and remove them in one tap.
- Removing an ad also clears the same user's identical ad from every managed
  chat within the last 24h (cross-chat blast cleanup).
- The would-be advertiser is redirected to an external pricing article via a
  "smart link" — reached by DM if possible, otherwise by a public ping.
- Advertising info is publicly discoverable via an `/ads` command and a line in
  the bot's `/start` greeting.
- Track the funnel minimally: how many advertisers were reached, how many
  clicked.

**Non-goals (explicitly out of v0):**

- No conversational submission flow, no FSM, no LLM negotiation.
- No prices in the bot or DB — pricing lives in an externally-maintained
  article (Telegraph/Notion).
- No payment handling, no request lifecycle, no admin approval pipeline.
- No web / catalog changes.

## 3. What gets removed

**Verified facts (2026-05-21):**

- Migration `c3d4e5f6a7b8_add_sponsored_ad_requests` exists only on branch
  `docs/sponsored-ads-product`, not on `main`.
- The configured dev DB is at revision `b2c3d4e5f6a7` (`add_admin_magic_links`)
  — i.e. `c3d4e5f6a7b8` has **not** been applied anywhere.

Therefore the `sponsored_ad_requests` table was never created and **no drop
migration is needed**. Remove outright:

- `app/sponsored_ads/domain.py`, `service.py`, `__init__.py` (current contents)
- `app/db/repositories/sponsored_ads.py`
- `SponsoredAdRequest` model in `app/db/models.py` and its enum imports
- migration `alembic/versions/c3d4e5f6a7b8_add_sponsored_ad_requests.py`
- tests `tests/unit/test_sponsored_ads_domain.py`,
  `test_sponsored_ads_repository.py`, `test_sponsored_ads_service.py`
- enums `AdRequestStatus`, `AdCategoryPolicy`

Rewrite to match v0: `docs/product/sponsored-ads.md`, `docs/domain/sponsored-ads.md`.

The `app/sponsored_ads/` module name is **reused** for v0 logic (see §5).

## 4. Flow

```
User posts ad-like message in a managed chat
        │
        ▼
HistoryMiddleware: save to `messages`, run ad-detector
        │ signals found?
        ├── no ──▶ (nothing)
        ▼ yes
record SpamPing  +  notify moderators
        │ dedup: skip the alert if one for (user, normalized text)
        │ was already sent in the last 24h
        ▼
Alert in the private moderator chat:
  message snippet + chat + user  +  [Пропустить] [Удалить] [Бан]
        │
        ▼ admin taps
   ┌───────────────┬────────────────────────────┬─────────────────────────┐
 Пропустить          Удалить                       Бан
   │               │                            │
 mark alert        delete original message       delete original message
 "пропущено"       + cross-chat dup cleanup       + cross-chat dup cleanup
   │               + create ad_lead               + ban user
  done             + reach advertiser             mark alert "удалено+бан"
                   mark alert "удалено+приглашён"  done
                     │
                     ▼
           reach advertiser:
             try DM ──ok──▶ send rate card + smart link
               │ fail (Forbidden / BadRequest)
               ▼
             public ping in the chat: tag user + smart link
        │
        ▼
Advertiser clicks the smart link  t.me/<bot>?start=adlead_<id>
        │
        ▼
/start adlead_<id>: mark ad_lead.link_clicked_at, show rate card
(/ads or /start ads → same rate card screen, no tracking)
```

## 5. Components

**`app/sponsored_ads/`** — feature logic (Telegram types confined to the
callable surface, kept out of pure helpers):

- `review.py` — build the moderator alert; dedup check: skip the alert when
  the `messages` table already holds an *earlier* message (within 24h) from the
  same user with the same normalized text — a repeat of an already-flagged
  blast. This reuses existing data; no new dedup table.
- `cleanup.py` — `find_ad_duplicates(...)` / `delete_ad_duplicates(...)`: query
  the `messages` table for the same `user_id` + normalized text within 24h
  across all chats; delete each via the bot API.
- `outreach.py` — `reach_advertiser(...)`: attempt a DM, fall back to a public
  ping; build the smart link.
- `rate_card.py` — render the rate-card message (blurb + article link +
  contact); pure text.
- `leads.py` — `ad_leads` repository: create lead, mark click.
- `text.py` — text normalization helper (trim, collapse whitespace, lowercase)
  shared by the review dedup and the cleanup query.

**`app/presentation/telegram/handlers/`:**

- `ad_review.py` — callback handler for `[Пропустить] / [Удалить] / [Бан]`;
  idempotent. `[Бан]` bans the user from the **source chat** (reusing existing
  `moderation` ban logic) — Telegram bans are per-chat; the cross-chat reach in
  this feature is the duplicate cleanup, not the ban.
- extend `start.py` — handle `start` payloads `ads` and `adlead_<id>`; add an
  `/ads` command; add an advertising line to the `/start` greeting.

**Wiring:**

- `HistoryMiddleware`, after `record_ad_signals` returns signal rows, calls
  `sponsored_ads.review` to send the moderator alert.
- A new router for `ad_review.py` is registered in `handlers/__init__.py`.

**Callback data:** an aiogram `CallbackData` factory carrying `action`,
`chat_id`, `message_id`, `user_id` — well within the 64-byte limit. The handler
is stateless; it does not depend on the alert message remaining in any store.

## 6. Data model

New table **`ad_leads`**:

| column            | type                | notes                             |
|-------------------|---------------------|-----------------------------------|
| `id`              | Integer PK          |                                   |
| `chat_id`         | BigInteger          | source chat                       |
| `user_id`         | BigInteger          | advertiser                        |
| `snippet`         | String, nullable    | truncated ad text                 |
| `reached_via`     | String(8)           | `dm` / `ping` / `failed`          |
| `created_at`      | DateTime            | `utc_now`                         |
| `link_clicked_at` | DateTime, nullable  | set on smart-link click           |

Index on `created_at` for funnel queries. No foreign keys in v0 — consistent
with the existing `SpamPing` / `messages` tables, where `chat_id` / `user_id`
are plain IDs.

No changes to `chats`, `messages`, or any other existing table.

## 7. Configuration

New `SponsoredAdsSettings` (Pydantic `BaseSettings`) in `app/core/config.py`:

- `enabled: bool = False` — feature flag.
- `moderator_chat_id: int` — chat that receives the alerts.
- `pricing_article_url: str` — external article (Telegraph / Notion).
- `sales_contact: str` — `@username` shown in the rate card.

`.env.example` updated accordingly.

## 8. Error handling

- DM outreach raises `TelegramForbiddenError` / `TelegramBadRequest` → fall back
  to a public ping. If the ping also fails → log, record `reached_via=failed`.
- Duplicate deletion: each `delete_message` may fail (message already gone, bot
  lacks rights, or message older than 48h — Telegram bots cannot delete
  messages older than 48h). Catch per message, log, continue; count successes.
- Stale / duplicate callback (original already deleted, alert already actioned):
  handle idempotently — answer the callback with "уже обработано" and finalize
  the alert.
- Moderator-alert send failure → log; the `SpamPing` row is still recorded.
- All handlers guard on `SponsoredAdsSettings.enabled` and a configured
  `moderator_chat_id`.

**Known limitation:** messages of the same blast that arrive *after* the admin
acts are not retroactively cleaned — the cleanup is a point-in-time query. A
later post by the same user re-triggers detection. Acceptable for v0.

## 9. Testing

- **Unit:** text normalization; `find_ad_duplicates` window / match logic;
  smart-link payload parsing (`ads`, `adlead_<id>`, malformed input);
  rate-card rendering; callback-data round-trip; alert dedup.
- **Integration (FakeTelegramServer):** post an ad → alert appears in the mod
  chat → tap `Удалить` → original + cross-chat duplicates deleted, `ad_lead`
  row created, outreach sent; tap `Пропустить` → no deletion; tap `Бан` →
  deletion + ban, no outreach; DM-forbidden → ping fallback; smart-link click
  sets `link_clicked_at`.
- **Migration:** test for `ad_leads`; full `alembic upgrade head` on a clean DB
  after `c3d4e5f6a7b8` is removed.

## 10. Migration notes

- Delete `c3d4e5f6a7b8_add_sponsored_ad_requests.py` (verified unapplied — §3).
- New migration `add_ad_leads` revises `b2c3d4e5f6a7` (the migration head once
  `c3d4e5f6a7b8` is gone).
- No drop of `sponsored_ad_requests` — the table was never created.

## 11. Future (v2 — not now)

If ad volume grows, a conversational pipeline (advertiser submission, price
negotiation, payment tracking) could be revived from git history. It is out of
scope for v0 — not built, not stubbed.
