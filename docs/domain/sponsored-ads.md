# Sponsored Ads — Domain Rules (v0)

## Entities

- **`ad_leads`** — one row per advertiser redirected to the rate card.
  Fields: `chat_id`, `user_id`, `snippet`, `reached_via` (`dm` / `ping` /
  `failed`), `ping_chat_id`, `ping_message_id`, `created_at`,
  `link_clicked_at`.

## Rules

- An ad alert is sent to moderators only when `SPONSORED_ADS_ENABLED` is true
  and `SPONSORED_ADS_MODERATOR_CHAT_ID` is set.
- Alert dedup: no alert is sent if the same user already posted an identical
  message (normalized: trimmed, whitespace-collapsed, casefolded) within the
  last 24h.
- A moderator decision is authoritative. Any valid non-skip action deletes the
  message.
- Only `skip`, `delete`, and `ban` are valid moderator actions. Unknown
  callback actions are rejected and must not delete messages, ban users, or
  contact advertisers.
- Cleanup deletes every identical message from the same user across all chats
  registered in the managed `chats` table within the last 24h. The source
  message from the moderator action is still deleted even if its history row is
  missing. Telegram forbids bots deleting messages older than 48h; such
  failures are logged and skipped.
- The advertiser is reached by DM when possible, otherwise by a public ping in
  the source chat. `reached_via` records which.
- The smart link (`?start=adlead_<id>`) marks `link_clicked_at` once; repeat
  clicks do not overwrite it.
- If the advertiser was reached by a public ping, opening the smart link deletes
  that public ping best-effort. A delete failure must not block the rate card.
- `/ads` and `?start=ads` show the same rate card without lead tracking.
