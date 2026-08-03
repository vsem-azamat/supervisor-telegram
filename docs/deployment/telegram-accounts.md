# Telegram accounts

Two user accounts are involved in running these chats, and they are not
interchangeable:

- **main** — the personal account that owns the chats today.
- **work** — the account that is to take administration over, so the personal
  one can step back from day-to-day management.

They exist as separate sessions on purpose. Telethon keeps an authorisation key
in the session file, so one file for both accounts means whichever signed in
last quietly replaced the other — and the failure only shows up later, as the
wrong account doing something.

## Signing in

Needs an application registered at <https://my.telegram.org>; the same
`api_id`/`api_hash` pair serves both accounts, because it identifies the
application rather than the account.

```bash
export TELETHON_API_ID=...
export TELETHON_API_HASH=...

uv run python scripts/tg_accounts.py login main
uv run python scripts/tg_accounts.py login work
```

Each prompts for a phone number, the code Telegram sends to that account, and a
two-step password if one is set — so it has to be run by whoever can read the
code. Signing in again on an account that is already authorised does nothing.

## Checking

```bash
uv run python scripts/tg_accounts.py status
```

```
main       authorised    @azamat (id 268388996)
work       authorised    @konnekt_ops (id ...)
```

This one never prompts. It is what anything unattended runs before acting, to
confirm it is the account it believes it is; a session that was revoked from
Telegram's own device list shows up here as `NOT AUTHORISED` rather than as a
confusing permission error halfway through a job.

## What a session file is

`.creds/sessions/<account>.session` is not a token scoped to this tool. Whoever
holds it can read every chat and message that account can, send as it, and change
its settings — Telegram sees no difference between the file and the person.

- `.creds/` is ignored by git, and nothing there belongs in a backup that leaves
  this machine.
- Deleting the file only makes it unusable here. Actually revoking access means
  ending the session from Telegram's **Devices** list.
- The bot's own userbot session (`moderator_userbot.session`, mounted into the
  container) is a third, unrelated session. Do not point these scripts at it.

## What comes next

Handing the chats over is the following step, and deliberately not part of this
one: with both accounts signed in, `work` gets promoted to administrator
everywhere `main` can appoint admins, and the moderator bot gets invited back to
the chats it left in May. Only then does it make sense to take anything away
from `main`.
