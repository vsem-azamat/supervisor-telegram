# Domain Ground Truth

This section is the canonical behavioral reference for Supervisor Telegram.
Use it before changing behavior, writing tests, or reviewing externally visible
contracts.

## Documents

- [Moderation](moderation.md) - moderator bot behavior, escalation, and
  blacklist rules.
- [Content Pipeline](content-pipeline.md) - source fetching, review, publishing,
  and scheduling rules.
- [Admin Web](admin-web.md) - public read access, authenticated admin actions,
  and the web surface contract.
- [Sponsored Ads](sponsored-ads.md) - admin-reviewed paid placement rules,
  quote validation, pinning, and payment gates.
- [Telegram Identities](telegram-identities.md) - responsibilities of the
  moderator bot, assistant bot, and Telethon userbot.

## Rules

- Domain docs own current behavior.
- Architecture docs explain code structure, not product truth.
- Project learnings record incidents and lessons, not the behavioral contract.
- Historical plans and reviews are reference material only after the relevant
  behavior has shipped.

## Change Process

When domain behavior changes:

1. Update the relevant domain document first.
2. Add or update a failing test that captures the new rule.
3. Implement the minimal code needed to pass the test.
4. Update architecture or operational docs only when the implementation shape or
   deployment contract also changed.
