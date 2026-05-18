# Sponsored Ads

Sponsored ads convert admin-reviewed ad attempts into paid, labeled bot posts.
The product intent lives in [product sponsored ads](../product/sponsored-ads.md);
this document owns the behavioral rules that tests and code must enforce.

## Core Rules

- Sponsored ads are disabled unless the target chat has `ad_enabled`.
- The flow opens only from an admin action on a flagged moderation item, not from
  automatic spam detection alone.
- Blocked categories must be rejected before payment instructions are shown.
- A request may show payment instructions only in `awaiting_payment`.
- A request may reach `awaiting_payment` only after admin approval of content,
  category, target chat, final quote, and optional pinning.
- Payment confirmation is manual in the MVP.
- The bot may post only after payment is confirmed and all posting conditions are
  still valid.
- Every paid placement must be labeled as sponsored.

## Quote Rules

- Static configuration produces `recommended_price`, `minimum_price`, and
  `maximum_price`.
- `minimum_price` is the greater of the chat floor price and the configured
  negotiation floor applied to the recommended price.
- The Agent Bot may discuss price only inside the configured bounds.
- A deterministic validator must reject out-of-bounds LLM quote proposals before
  they become advertiser-visible accepted quotes.
- Payment is valid only when `awaiting_payment.price` is inside the configured
  quote bounds or `admin_override` is true.
- Accepted quotes must retain provenance: category, format, pinning, timing
  factors, recommended price, bounds, final price, admin override status, and a
  negotiation transcript or summary.

## Persistence Contract

- `sponsored_ad_requests` stores one advertiser request for one target chat.
- `chats.ad_enabled` is the opt-in gate; existing chats remain disabled until
  an admin enables sponsored placements.
- It keeps the source flagged message, advertiser Telegram user, target chat,
  current status, category policy, quote bounds, final accepted price, currency,
  admin override flag, and quote provenance.
- Admin payment confirmation is a separate transition from admin approval:
  `pending_admin_review -> awaiting_payment -> payment_confirmed`.
- Invalid quote proposals must fail before mutating stored request state.

## Category Rules

- Automatic category classification is advisory.
- The admin-reviewed category is authoritative for price and policy.
- Blocked categories never become sponsored posts.
- Restricted categories require explicit admin approval before quote acceptance.
- Nicotine, tobacco, vape, exam cheating, hidden earpieces, fake documents,
  scams, adult, drugs, weapons, and predatory finance are blocked in the MVP.

## Pinning Rules

- Pinning is optional and must be enabled for the target chat.
- The Agent Bot must not offer pinning when paid pinning is disabled.
- Only one paid pinned ad may be active in a chat at a time.
- The bot must not replace an existing pin unless the admin approves replacement
  for that request.
- The bot unpins the paid sponsored post after the approved duration only if it
  is still the active paid pin.

## State Rules

The allowed product states are:

- `draft`
- `negotiating`
- `needs_admin_attention`
- `pending_admin_review`
- `rejected`
- `awaiting_payment`
- `payment_confirmed`
- `scheduled`
- `posted`
- `failed`
- `cancelled`

Negotiation exits:

- accepted in-bounds quote moves to `pending_admin_review`;
- blocked category moves to `rejected`;
- repeated validator failures move to `needs_admin_attention`;
- more than `8` advertiser messages without acceptance moves to
  `needs_admin_attention`;
- no advertiser activity for `24h` moves to `cancelled` unless an admin keeps
  the request open.

## Failure Rules

- If money was received and posting or pinning cannot be delivered as approved,
  the request must move to `failed` or `cancelled`.
- Paid failures require an admin resolution note: refund, reschedule, replacement
  placement, or advertiser-approved no-refund resolution.
- The system must not silently retain paid requests that cannot be delivered.

## Tests

- Unit tests should cover price bounds, quote validation, category policy,
  state transitions, and pin eligibility.
- Integration tests should cover persistence of quote provenance, admin approval
  gates, payment visibility, and failure resolution records.
- End-to-end tests should cover the observable admin flow from flagged message to
  labeled sponsored bot post.
