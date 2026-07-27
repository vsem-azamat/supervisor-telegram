# Invariants

Rules a reader would otherwise break, each with the damage it prevents.

Nothing here describes structure, counts anything, or lists capabilities — that
kind of text goes stale without anyone noticing, and this file is only worth
keeping if it stays true. Behaviour is pinned by tests; this is for the rules a
test cannot state, either because they span processes, live in deployment, or
record *why* a design is shaped the way it is.

Add an entry only when all three hold: it cannot be inferred from the code, its
violation causes real damage or silent breakage, and the reason survives the
code moving.

---

## Telegram

**A callback belongs to the bot that sent the message.** Telegram delivers an
inline-keyboard press to the sending identity. A review draft sent by the wrong
bot renders perfectly and its buttons do nothing at all — no error, no log. The
review router is attached to the assistant dispatcher when
`settings.assistant.active` and to the moderator dispatcher otherwise, so
whatever sends a review message must use the matching token. Escalations and
pending-action confirmations are moderator-bot only, because that is the
dispatcher holding their handlers.

**`parse_mode=None` whenever you pass entities.** The moderator bot defaults to
HTML, and that default silently overrides explicit `entities` /
`caption_entities`. The formatting is simply lost; nothing raises. Applies to
every send and edit call, of which there are more than a dozen.

**Scheduled publication requires the Telethon userbot.** The Bot API has no
equivalent, so "simplifying" this onto the Bot API deletes the feature rather
than reworking it.

**The Telethon session is the whole account.** A bot token grants one bot; this
grants every private conversation the account can see. Treat writes, scheduled
messages and account-level side effects as higher-risk than any Bot API call,
and never widen a tool that resolves arbitrary peers.

**Never point a development instance at production tokens, the userbot session,
or the production database.** Two pollers on one token make Telegram split
updates between them non-deterministically, and the development bot then
moderates real chats. No test can catch this.

## Approval

**A chat is approved or it is not — that is a property of the chat, not of an
update type.** The bot records what it observes in unapproved groups but takes
no public action there: no moderation commands, no blacklist ban, no spam
prompt, no ad alert. When a new update type starts carrying public action, the
gate has to learn about it, or the action escapes approval.

**The approval gate must run after history capture.** Reversing them silently
stops passive recording for chats awaiting approval, which is exactly the data
an operator needs in order to decide on approval.

## MCP control plane

**Direct publication is unreachable by construction, not by a check.** The
generation service publishes directly only when handed a publish bot, and the
MCP tool hands it none. This is deliberately not a `review_chat_id` test: a
check can be raced by a reconfiguration between check and send, while a missing
argument cannot.

**The review guarantee rests on `review_chat_id` pointing somewhere non-public,
and nothing validates that.** A channel misconfigured through the admin API to
review into itself would receive drafts publicly. Known, accepted, and not
MCP's to fix — but do not mistake the guarantee for stronger than it is.

**Tool errors are masked because they land in an operator's chat history.** An
unmasked exception travels to the external runtime and from there into a
conversation log; a failed database connection would carry its DSN along.
`mask_error_details` is not a debugging convenience to toggle.

**The rate limit is counted in-process, so it is per worker.** Adding workers
multiplies the cap by the worker count with no error and no log — just a larger
model bill and a flooded review chat.

**Turning `MCP_ENABLED` on publishes the endpoint.** The edge already proxies
the path; there is no second step that exposes it. The bearer token is the only
control, and an unauthenticated scanner can still see that the endpoint exists,
because routing answers before authentication does. Treat the path as public
and the token as the entire secret.

## Deployment

**The web UI port is loopback-only.** It is reached by the server-level edge
proxy. Dropping the `127.0.0.1:` prefix exposes the UI around the edge, past TLS
and any edge rules, and logs nothing.
