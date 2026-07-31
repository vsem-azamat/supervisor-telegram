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
dispatcher, so any process that sends such a message must send it with the
moderator token, not merely with some working bot token.

**`parse_mode=None` whenever you pass entities.** The moderator bot defaults to
HTML, and that default silently overrides explicit `entities` /
`caption_entities`. The formatting is simply lost; nothing raises. Applies to
every send and edit call, of which there are more than a dozen.

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

## The moderation record

**A moderator's action is written down after it succeeds, never before.** The
row is the claim that something happened, so an attempt that Telegram refused
must not leave one — and a proposal a human rejected leaves nothing at all.

**Failing to write the row never fails the action.** By the time the record is
written the person is already banned; an error surfacing to the admin at that
point would report the opposite of what happened. The write is logged and
swallowed, which is the one place in this codebase where losing data is
preferable to raising.

**The actor is always a person.** The source says how the action was asked for —
a command in a chat, or the control plane — but a token can never be the answer
to "who banned this person", so a confirmed proposal is recorded against the
admin who pressed confirm.

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
bans directly re-opens this — as would any tool that decides and acts in one
call, which is what the removed assistant's `analyze_message` did.

**A ban is attributable, and the token is not a person.** Every proposal records
the admin it acts for — the first super admin, the same one escalations and
magic links answer to. With no admin configured the proposal tools refuse
rather than log an action against nobody.

**Tool errors are masked because they land in an operator's chat history.** An
unmasked exception travels to the external runtime and from there into a
conversation log; a failed database connection would carry its DSN along.
`mask_error_details` is not a debugging convenience to toggle.

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
