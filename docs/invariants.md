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
inline-keyboard press to the sending identity. A message whose buttons were sent
under a different token renders perfectly and does nothing at all when pressed —
no error, no log. Every inline-keyboard handler lives on the moderator
dispatcher, so any process that sends such a message — the web API, the MCP
plane — must send it with the moderator token, not merely with some working bot
token. This is why the outgoing-only review bot exists as its own thing rather
than as whichever `Bot` was nearest.

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

## Mini App

**`initData` and the Login Widget are different algorithms.** The widget derives
its secret as `sha256(bot_token)`; a Mini App as
`hmac(key="WebAppData", msg=bot_token)`. Reusing one helper for the other fails
every signature, and "fixing" that by relaxing the check is how a Mini App ends
up trusting whatever the caller claims. An empty bot token must refuse rather
than derive a secret from nothing.

**A join check belongs to one applicant, and that binding is stored.** Holding
the query id is not the same as being the person it was issued to. Carrying the
applicant in the Mini App's URL would let anyone with the link pass the check
on someone else's behalf — precisely the bot farm a check exists to stop. The
request also arrives in the bot process while the check is answered by the web
API, so the two halves have nowhere else to meet.

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

**The boundary is what a leaked token can do, not which tools exist.** The
original rule was that the toolset must never grow. That held while the plane
only touched content, and stopped holding when the operator's moderation work
moved here, because the point of that work is privileged mutation. What
replaced it: reads never reach outside managed chats, bounded writes are
reversible or self-expiring, and removals are only ever proposed.

**Removing a person is never performed by a tool call.** `propose_ban` and
`propose_blacklist` create a pending action and return. A super admin presses
confirm in the moderator bot, or it expires having done nothing. Any tool that
bans directly re-opens this, which is why `analyze_message` stays unexposed:
it runs the moderation agent and then carries out its verdict, up to a global
blacklist.

**A ban is attributable, and the token is not a person.** `MCP_INITIATOR_ID`
names the admin the token acts as, and it is recorded on every proposal. The
proposal tools refuse while it is unset rather than logging an action against
nobody.

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

**The control plane is not published to the internet, and that is a decision
rather than an oversight.** It binds loopback in the bot container and the edge
has no rule for it. This was not always so: the endpoint used to live on the web
API behind the existing `/api/*` proxy, where enabling the flag was enough to
expose it. Do not restore that convenience — the toolset now includes
privileged moderation, and its safety rests on more than a bearer token.

## Deployment

**The web UI port is loopback-only.** It is reached by the server-level edge
proxy. Dropping the `127.0.0.1:` prefix exposes the UI around the edge, past TLS
and any edge rules, and logs nothing.
