# Learning Log

A running log of issues, root causes, and fixes that are useful to remember
while working on the project.

## Telegram Entity Rendering

### Explicit entities are ignored without `parse_mode=None`

**Cause:** The moderator bot is configured with HTML as its default parse mode.
That default can override explicit `entities` or `caption_entities`.

**Fix:** Pass `parse_mode=None` on send/edit operations that provide Telegram
entities.

## Environment Isolation

### Development and production can accidentally target the same live resources

**Cause:** Bot tokens, Telethon credentials, and database settings can be copied
between local and deployed `.env` files.

**Fix:** Treat bot credentials, userbot sessions, and databases as environment
boundaries. Do not run a development instance against production identities and
data unless that overlap is explicitly intended.

## Remote Web Development

### Remote access should not rely on auth bypasses

**Cause:** Exposing a development web UI from a VPS makes unauthenticated bypass
flags tempting.

**Fix:** Keep the same auth contract for remote development as for production:
public endpoints are intentionally read-only, and admin mutations require real
authentication.
