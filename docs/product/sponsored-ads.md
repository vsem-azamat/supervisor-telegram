# Sponsored Ads

This document defines the product intent for converting unmanaged ad attempts in
Telegram communities into approved sponsored placements. It is a product-level
contract, not the final domain implementation.

## Problem

Some managed chats receive recurring ad-like messages: tutoring offers, housing
and sales posts, exam-help services, product promotions, and other unsolicited
commercial messages. Ignoring them leaves noise in the community. Deleting them
only removes the immediate problem. A subset may be legitimate advertisers who
would pay for a clear, approved placement path.

The product opportunity is to turn acceptable ad attempts into a moderated lead
flow while rejecting unsafe or trust-damaging categories.

## Product Outcome

Operators can reduce chaotic spam and capture some commercial demand without
making the chat feel pay-to-spam. Sponsored posts remain scarce, labeled,
admin-approved, and governed by category policy.

## MVP Principles

- Sponsored placements can be offered only inside managed chats.
- Detected ad-like messages become admin-reviewed leads, not automatic posts.
- The sponsored-ad flow opens only when an admin reviewing a flagged message
  chooses to offer paid placement; ad detection itself remains part of
  moderation.
- The advertiser must submit a request through the bot before receiving payment
  instructions.
- The Agent Bot should explain how the quote is formed and may negotiate within
  configured bounds before the request reaches payment.
- The bot posts sponsored ads only after content approval and manual payment
  confirmation.
- Every sponsored post is clearly labeled.
- Admins can override price, reject content, or ban the advertiser.
- High-risk categories are blocked by default instead of sold at a higher price.

## First Pilot Defaults

The MVP runs only in chats already managed by the bot. Per-chat enablement is
intentionally skipped for now; admins control whether to offer paid placement on
each flagged message.

Required pricing values:

- base price;
- hard floor price;
- currency;
- daily sponsored-post quota;
- whether paid pinning is allowed.

For the current Czech community pilot, the assumed currency is `CZK` and prices
are represented as whole currency units. A reasonable starting base-price band is
`200` to `2000` CZK per placement, adjusted manually per chat size and quality.

Default quota:

- max `1` sponsored post per chat per day;
- max `1` request per advertiser per day until there is evidence that a higher
  limit is useful.

## Core Flow

1. A message in a managed chat looks like an ad or spam.
2. The bot sends the message to an admin review queue.
3. Admin chooses one action:
   - delete;
   - allow;
   - ban or mute;
   - offer paid placement.
4. If paid placement is offered, the bot asks the advertiser to open a private
   request flow. If the bot cannot DM the advertiser first, the in-chat response
   should contain only a neutral bot link and should not expose payment details.
5. The advertiser submits ad text, optional media or link, target chat, and
   desired timing.
6. The bot classifies the request into a provisional pricing and policy
   category.
7. If the provisional category is blocked, the bot refuses the request before
   any price is quoted.
8. The Agent Bot explains the quote in plain language, including chat demand,
   category, format, optional pinning, and timing factors.
9. A deterministic quote validator checks every Agent Bot price proposal against
   category policy, enabled add-ons, floor price, ceiling price, and chat
   settings.
10. The advertiser may accept the quote, change the request, or ask for a lower
   price.
11. The Agent Bot may negotiate only inside configured minimum and maximum
    bounds.
12. Admin reviews the content, category, final quote, negotiation transcript,
    quote provenance, and optional pinning.
13. The bot provides payment instructions with a unique request code.
14. Admin manually confirms payment.
15. The bot posts or schedules the labeled sponsored message.
16. If the placement includes pinning, the bot pins it for the approved duration
    and later unpins it if it is still the active paid pin.

## Posting Contract

The bot may post a sponsored ad only when all conditions are true:

- the target chat is managed by the bot;
- the bot has permission to send messages in the target chat;
- the category policy is `allowed` or explicitly admin-approved as `restricted`;
- content is approved by an admin;
- the quote is accepted by the advertiser and approved by an admin;
- payment is manually confirmed;
- the daily chat quota has not been reached;
- any requested pin slot is available or explicitly approved for replacement.

Blocked categories never become sponsored posts.

## Advertiser Identity

For the MVP, an advertiser is the Telegram user identity that submitted the ad
request. Rate limits, request history, rejection history, and bans apply to that
Telegram user across managed chats. If an advertiser acts through multiple
accounts, admins can still reject, ban, or blacklist manually.

## Category Policy

Categories drive policy and price. The exact list can evolve, but the product
needs three policy states:

| Policy | Meaning |
| --- | --- |
| `allowed` | Normal sponsored placement category. Admin approval is still required. |
| `restricted` | Sensitive category that needs explicit admin approval and may require higher pricing, stricter copy review, or legal checks. |
| `blocked` | Category must be rejected and should not receive payment instructions. |

Initial category direction:

| Category | Default Policy | Pricing Direction |
| --- | --- | --- |
| Tutoring and education services | `allowed` | Lower multiplier |
| Housing and relocation | `allowed` | Medium or higher multiplier |
| Jobs and recruiting | `allowed` | Medium multiplier |
| Events | `allowed` | Medium multiplier |
| Local services | `allowed` | Medium multiplier |
| General marketplace sales | `restricted` | Higher multiplier or manual price |
| Nicotine, tobacco, vape, and related products | `blocked` | Not monetized in MVP |
| Exam cheating, hidden earpieces, fake documents, scams, adult, drugs, weapons, or predatory finance | `blocked` | Not monetized |

Nicotine products should not simply be priced higher in the MVP. Telegram's own
ad guidelines and many local laws treat tobacco and nicotine advertising as
sensitive or prohibited, so the safe product default is to block them until the
operator makes an explicit policy decision with legal context.

The admin-reviewed category is authoritative for pricing. Automatic
classification is only a suggestion until an admin confirms or changes it before
payment instructions are shown.

## Pricing And Negotiation Model

The pricing model should be guardrailed, not fully invented by the LLM. Static
configuration creates a quote range. The Agent Bot explains the range, discusses
tradeoffs with the advertiser, and proposes a final quote inside the allowed
bounds.

```text
recommended_price = chat_base_price * category_multiplier * format_multiplier * pin_multiplier
minimum_price = max(
  chat_floor_price,
  recommended_price * negotiation_floor_multiplier
)
maximum_price = recommended_price * negotiation_ceiling_multiplier
```

Recommended MVP defaults:

- each chat has a `base_price`;
- each chat has a `floor_price`;
- each chat has a configured `currency`;
- category multipliers are global;
- format multipliers are global;
- pin multipliers are global;
- each chat or deployment has negotiation bounds;
- admin may override the final price before payment instructions are shown.

Worked example:

```text
chat_base_price = 500 CZK
chat_floor_price = 350 CZK
category = tutoring, multiplier 0.8
format = text and image, multiplier 1.3
pin = none, multiplier 1.0
negotiation floor = 0.85
negotiation ceiling = 1.20

recommended_price = 500 * 0.8 * 1.3 * 1.0 = 520 CZK
minimum_price = max(350, 520 * 0.85) = 442 CZK
maximum_price = 520 * 1.20 = 624 CZK
```

The Agent Bot may explain this as:

```text
The recommended price is 520 CZK based on this chat, the education category,
and image format. I can discuss a pilot discount, or we can increase visibility
with paid pinning if this chat supports it.
```

LLM negotiation rules:

- the Agent Bot may not quote below `minimum_price`;
- the Agent Bot may not quote above `maximum_price` unless an admin explicitly
  creates an override;
- the Agent Bot may not sell blocked categories at any price;
- the Agent Bot may not offer pinning unless paid pinning is enabled for the
  target chat;
- the Agent Bot may suggest a higher price only by adding value, such as image
  format, better timing, or paid pinning;
- the Agent Bot must explain pricing factors in plain language without exposing
  the full multiplier table, negotiation floor, or internal validator limits;
- the Agent Bot must not promise reach, conversion, posting time, or pin
  replacement unless that commitment is represented in the request record;
- payment instructions are shown only after the advertiser accepts a quote and
  admin approves it.

The quote validator is authoritative. If the Agent Bot proposes an invalid
price, disabled add-on, blocked category, or unrecorded commitment, the system
must reject the proposal before showing it as an accepted quote. Repeated
validator failures escalate the request to admin review.

The accepted quote must retain provenance:

- recommended price;
- minimum and maximum price;
- final advertiser-accepted price;
- category, format, pin, and timing factors used;
- whether admin override was used;
- negotiation transcript or summary visible to the reviewing admin.

The invariant for payment is:

```text
awaiting_payment.price is inside [minimum_price, maximum_price]
or admin_override is true
```

Example categories:

| Category | Example Multiplier |
| --- | --- |
| Tutoring | `0.8` |
| Local services | `1.0` |
| Housing | `1.2` |
| General marketplace sales | `1.5` |

Example formats:

| Format | Example Multiplier |
| --- | --- |
| Text only | `1.0` |
| Text and image | `1.3` |
| Text and link | `1.2` |

## Pinning

Pinning is a paid add-on, not the default sponsored post behavior.

MVP rules:

- paid pinning must be explicitly enabled for the target chat;
- only one paid pinned ad can be active in a chat at a time;
- supported durations are `6h`, `12h`, and `24h`;
- the bot never replaces an existing pin without explicit admin approval for
  that specific request;
- the bot unpins the sponsored post after the approved duration if it is still
  the active paid pin.

Example pin multipliers:

| Pin Option | Example Multiplier |
| --- | --- |
| No pin | `1.0` |
| Pin for 6h | `1.5` |
| Pin for 12h | `2.0` |
| Pin for 24h | `3.0` |

## Request States

The product-level state machine is:

| State | Meaning |
| --- | --- |
| `draft` | Advertiser has started the request but has not submitted content. |
| `negotiating` | Agent Bot is explaining price, adjusting format or pinning, and discussing a quote inside configured bounds. |
| `needs_admin_attention` | Negotiation exceeded limits, hit validator failures, or needs a human decision before payment. |
| `pending_admin_review` | Content is ready for admin review. |
| `rejected` | Admin or policy rejected the request. |
| `awaiting_payment` | Content, category, price, and target chat are approved; payment instructions may be shown. |
| `payment_confirmed` | Admin manually confirmed payment. |
| `scheduled` | Paid request is approved for a future post time. |
| `posted` | Bot posted the sponsored message. |
| `failed` | Posting or pinning could not complete. |
| `cancelled` | Admin cancelled the request before posting. |

Only `awaiting_payment` requests may show payment instructions. Blocked,
rejected, or still-negotiating requests must not reach `awaiting_payment`.

Negotiation exits:

- accepted in-bounds quote moves to `pending_admin_review`;
- blocked category moves to `rejected`;
- invalid repeated quote proposals move to `needs_admin_attention`;
- more than `8` advertiser messages without acceptance moves to
  `needs_admin_attention`;
- no advertiser activity for `24h` moves to `cancelled` unless an admin keeps
  the request open.

Advertiser-requested timing is a preference. The admin-approved posting time is
authoritative. If no future time is approved, the bot may post immediately after
payment confirmation.

## Failure And Refund Handling

Manual payment means refund and failure handling are also manual in the MVP, but
the product must still make the state visible.

Failure cases include:

- bot loses permission to post in the target chat;
- the chat disables ads before posting;
- the daily quota is already exhausted;
- an approved pin can no longer be applied;
- admin cancels after payment confirmation.

If money was received and the ad cannot be posted as approved, the request moves
to `failed` or `cancelled` and requires an admin resolution note:

- refund manually;
- reschedule manually;
- replace with another approved placement;
- mark as resolved without refund only when the advertiser explicitly agrees.

The product must not silently keep paid requests that cannot be delivered.

## Trust And Safety

The feature must not reward harmful spam. It should create a clean path for
acceptable advertisers and a faster rejection path for unsafe ones.

Required controls:

- clear sponsored label in every paid post;
- request ID linking advertiser, target chat, amount, and payment reference;
- rate limit ad requests per advertiser, initially `1` submitted request per
  advertiser per day;
- retain admin decision history for disputes and repeat-offender handling;
- reject blocked categories before payment instructions are shown;
- keep payment details out of public chats where possible.

Decision history should be retained for at least `180` days in the MVP unless a
deployment-specific retention policy requires a shorter period.

Operators remain responsible for Telegram terms, local advertising law, tax
treatment, and category-specific compliance. The product records policy and
approval workflow; it does not assert that any specific placement is legal.

## Success Metrics

The first pilot is successful only if sponsored ads reduce moderation friction
without creating new trust problems.

Initial signals:

- at least `1` paid approved placement per enabled pilot chat per month;
- `0` paid blocked-category placements;
- `0` unresolved paid requests older than `7` days;
- no sustained increase in member complaints about ads after enabling the flow.

## Non-MVP

- automatic payment gateway integration;
- self-serve advertiser dashboard;
- advertiser wallets or balances;
- auctions, dynamic demand pricing, or bidding;
- automatic publication immediately after payment;
- selling blocked categories at premium prices;
- guaranteed reach, conversion, or endorsement claims.

## Open Questions

- Should sponsored posts be deleted after a fixed period or remain in history?
- Should public catalog pages expose which chats accept sponsored placements?
- Which payment account details can be safely shown in the private request flow?
