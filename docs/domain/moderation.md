# Moderation

The moderation surface combines deterministic bot commands with an AI-assisted
decision layer. Human administrators remain the authority for uncertain cases.

## Core Rules

- The moderator bot owns mechanical moderation commands such as mute, ban,
  blacklist, welcome, report, and spam workflows.
- AI moderation may recommend or execute actions only within the supported
  moderation action set.
- Uncertain decisions must be escalated to administrators with a bounded timeout
  instead of being left unresolved indefinitely.
- Recent administrator corrections are valid moderation context and may be used
  to calibrate later decisions.
- Global blacklist membership applies across managed chats.

## Telegram Output Rules

- Moderator bot messages use HTML by default.
- Any send or edit operation that supplies Telegram entities must pass
  `parse_mode=None`, otherwise Telegram may ignore the explicit entities.

## Tests

- Local moderation rules belong in unit tests.
- Repository and cross-chat blacklist behavior belongs in integration tests when
  it depends on real persistence semantics.
- End-to-end tests should cover observable Telegram workflows such as reports,
  escalations, and admin callbacks.
