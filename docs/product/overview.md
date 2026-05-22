# Product Overview

Supervisor Telegram helps teams operating Telegram communities and channels keep
conversations healthy, publishing consistent, and operations visible while
retaining human control over high-impact decisions.

## Target Users

| Persona | Primary Need |
| --- | --- |
| Community operator | Keep one or more Telegram communities useful, safe, and manageable as activity grows |
| Moderator or administrator | Resolve reports, enforce rules, and handle edge cases quickly and consistently |
| Channel editor or content manager | Turn source material into publishable posts on a reliable schedule without rebuilding the workflow by hand |
| Operations owner | Understand managed chats, channels, public catalog state, and AI spend from authenticated operating surfaces |
| Community member | Participate in a healthier community and receive more useful channel content; this is a beneficiary persona, not the primary operator |

## Jobs To Be Done

- When a Telegram community creates more moderation work than admins can handle
  manually, help operators enforce policy consistently while escalating uncertain
  cases to humans.
- When a channel needs regular useful posts, help editors move from source
  discovery to publication with less repetitive work and review where configured.
- When admins need to run day-to-day community and channel operations, help them
  manage workflows from familiar control surfaces instead of stitching together
  ad hoc tools.
- When operator judgment improves the system, preserve that feedback so later
  moderation and content decisions can better reflect admin preferences.
- When operators expose a public catalog, help anonymous visitors browse the
  intended public projection without granting administrative authority.
- When AI-backed operations cost money, help operators see spend patterns before
  they become invisible operating risk.
- When unmanaged ads appear in communities, help operators remove spam and
  redirect acceptable advertisers to a human-owned paid placement path instead
  of letting chaotic spam define the commercial surface.

## Business Outcomes

- Reduce repetitive moderation effort without removing human authority from
  uncertain decisions.
- Improve consistency of enforcement across managed chats.
- Shorten the path from source material to publishable content.
- Support a dependable publishing cadence with review where a review channel is
  configured.
- Reduce operational friction for admins managing moderation and channel work.
- Make public catalog exposure and AI spend visible enough to operate.
- Create a controlled path for monetizing acceptable advertising demand without
  weakening moderation standards or community trust.

## Product Promises

| Promise | What must stay true |
| --- | --- |
| Humans retain control where judgment matters | Uncertain moderation decisions escalate to admins, and generated posts enter review when the channel is configured for review |
| Routine work becomes easier to operate | The platform reduces repeated manual steps across moderation and publishing instead of only moving them elsewhere |
| Feedback is preserved for later use | Admin corrections and editorial decisions are stored so future moderation and content workflows can use them as context |
| Public visibility does not imply admin authority | Public read access and authenticated administrative actions remain separate |
| Operating cost is inspectable | AI spend is visible to operators instead of hidden inside background automation |
| Monetization stays moderated | The bot removes unmanaged ads and points advertisers to the operator's external paid-placement article; negotiation, approval, payment, and posting stay human-owned outside the bot |

## Product Capabilities

| Capability Group | Business Meaning | Included Capabilities |
| --- | --- | --- |
| Community safety | Keep chats healthier with less repetitive administrator effort | Mechanical moderation, assisted moderation, reports, spam workflows, cross-chat blacklist context, escalation |
| Content operations | Move from source material to publication predictably | Source intake, duplicate filtering, drafting, optional review, publish, schedule |
| Operator control | Let a small team run supported workflows coherently | Conversational administration, authenticated admin surface, public catalog projection, cross-workflow visibility |
| Sponsored ad conversion | Turn unmanaged ad attempts into a controlled human-owned advertising path where the community allows it | Ad detection handoff, moderator removal decision, duplicate cleanup, advertiser outreach, `/ads` rate-card link |
| Learning loop | Preserve the team's actual decisions for later context | Moderation corrections and content approve/reject feedback retained for future workflows |
| Spend visibility | Keep AI-backed work financially inspectable | Session operation/model breakdowns, daily cost history, cache savings visibility |

## Technical Enablers

These matter to delivery, but they are not product promises on their own. The
current concrete choices live in [architecture](../architecture.md).

| Enabler | Role |
| --- | --- |
| Telegram API separation | Split bot and client-level responsibilities safely |
| LLM-assisted workflows | Support assisted decisions, drafting, and natural-language control |
| Durable workflow orchestration | Persist and resume multi-step content flows |
| Persistence and semantic search | Store state and support duplicate detection |
| Source integrations | Supply candidate source material |
| Automated verification | Keep the system maintainable as behavior changes |

## In Scope

- Telegram communities and channels managed by platform operators.
- Mechanical and AI-assisted moderation workflows.
- Content generation, editing, publishing, and scheduling, with review where a
  review channel is configured.
- Administrator workflows exposed through Telegram and authenticated web
  surfaces.
- Public read-only views only where they are intentionally exposed.
- A rate-card funnel for chats that explicitly enable sponsored-ad handling:
  remove unmanaged ads, clean up duplicates, and redirect advertisers to an
  external pricing article.
- Cost and usage visibility for AI-backed operations.
- Feedback from administrator decisions where it can improve later moderation or
  content workflows.

## Out Of Scope

- General-purpose social media management outside Telegram.
- Fully autonomous publishing as the default product posture for channels that
  are configured with a review workflow.
- Removing human authority from uncertain moderation decisions.
- Fully automatic conversion of detected spam into paid posts.
- In-bot price negotiation, ad submission, payment gateway automation,
  advertiser wallets, CRM, or a general-purpose ad marketplace.
- Monetizing blocked or legally sensitive categories before explicit policy and
  legal review.
- Replacing operator ownership of community policy, factual verification, or
  editorial judgment.
- Member-facing customer support or general chat assistance unrelated to the
  supported moderation workflows.
- Subscriber monetization unrelated to the sponsored-ad rate-card funnel.

## Boundary With Domain Rules

This document defines product intent, not executable workflow detail. Exact
rules for moderation, content flow, Telegram identities, and admin access live in
the [domain docs](../domain/).

## Wording Risks

- **"AI moderation"** can imply autonomous enforcement. Prefer **assisted
  moderation** unless the text is explicitly about a deterministic automated
  path.
- **"Automated publishing"** can imply posts always go live without review.
  Prefer **content operations** or **publishing workflow**, and state whether a
  channel is configured for review.
- **"General-purpose platform"** overstates the current evidence unless we can
  name supported audiences and workflows beyond the present operating model.
- **"Sponsored ad conversion"** means redirecting unmanaged advertisers to the
  operator's external paid-placement path. It does not imply in-bot ad sales,
  automatic purchase, bot-posted placements, or guaranteed results.
- Workflow libraries, database extensions, model routers, Telegram client
  details, and the number of bots are enablers, not customer outcomes. Keep them
  out of high-level product promises.
