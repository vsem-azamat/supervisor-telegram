# Sponsored Ads (v0 — Rate Card Funnel)

The bot does not sell or broker advertising. It detects ad-spam, lets a
moderator remove it, and points the would-be advertiser at a legitimate paid
path on the public site catalog.

## Flow

1. The ad-detector flags a message in a managed chat.
2. The bot posts an alert about it in the private moderator chat with three buttons:
   **Пропустить**, **Удалить**, **Бан**. The group sees nothing yet.
3. **Пропустить** — false positive, nothing happens.
4. **Удалить** — the message and every identical copy from the same user
   across all managed chats in the last 24h are deleted; the advertiser is
   contacted (DM if possible, otherwise a public ping) with a smart link.
5. **Бан** — same removal, plus the user is banned from the source chat; no
   outreach.
6. The smart link and the `/ads` command open advertising info: hardcoded
   placement guidance plus a link to the public site catalog with all chats.

## What it is not

No conversational submission, no price negotiation, no payment handling, no
in-bot pricing. The bot does not depend on an externally-maintained pricing
article. Selling is a human job; the bot only redirects to the public site
catalog and the configured sales contact.

## Configuration

`SPONSORED_ADS_ENABLED`, `SPONSORED_ADS_MODERATOR_CHAT_ID`,
`SPONSORED_ADS_SALES_CONTACT`, `WEBAPI_PUBLIC_URL`.
