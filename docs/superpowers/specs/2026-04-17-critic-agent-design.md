# Critic Agent (Sprint 2 / Track 2) — Design Spec

**Date:** 2026-04-17
**Status:** Draft
**Branch:** `feat/critic-agent`

## Goal & Non-goals

**Goal.** Add a post-generation polish pass that removes clichés, banal
openers, dead verbs, and pompous/corporate phrasing from generated posts
while preserving facts, links, structure, and length.

**Non-goals.**

- No RAG or few-shot style learning (Track 1, deferred).
- No structural rewrites (paragraph order, headline emoji swaps).
- No fact injection or concreteness augmentation (risk of invented details).
- No multi-model pipeline or routing (single model per call).

## Motivation

Current posts are produced by a single `generate_post` call against
`google/gemini-3.1-flash-lite-preview`. The style guide in the system
prompt lists banned phrases and tone rules, but Flash Lite is the
weakest model in the stack at tool-calling and taste; banned phrases
still leak through ("рады сообщить", "лично расспросить",
"Ознакомиться можно..."), and openers cluster around a handful of
templates. The generation prompt cannot be made stricter without
producing stiff text.

Instead of swapping the generation model (which affects structure,
cost, and latency across the pipeline), we add a cheap, stateless
polish pass behind a kill switch. Claude Sonnet 4.6 leads the EQ-Bench
Creative Writing leaderboard (1936 Elo) and is the judge model for
longform-writing benchmarks — industry-validated for the polish role.

## Architecture

### Flow

```
generate_post(items, ..., critic_enabled, critic_model)
  ├─ agent.run() → raw GeneratedPost
  ├─ enforce_footer_and_length()              ← already exists
  ├─ if critic_enabled and critic_model:      ← NEW
  │     try:
  │         original = post.text
  │         polished = await polish_post(
  │             text=post.text,
  │             footer=footer,
  │             api_key=api_key,
  │             model=critic_model,
  │         )
  │         post.text = polished
  │         post.pre_critic_text = original
  │     except CriticError:
  │         logger.warning("critic_failed_fallback", ...)
  │         # post.text unchanged, pre_critic_text stays None
  └─ image pipeline (unchanged)
```

The polish pass is **best-effort**: on failure the original text is
kept and the pipeline proceeds. The caller (workflow / review service)
does not need to know whether the critic ran.

### Module layout

New module `app/channel/critic.py`.

**Public surface:**

```python
class CriticError(DomainError): ...

def resolve_critic_enabled(channel: Channel, settings: Settings) -> bool:
    """Per-channel override falls back to global default."""
    if channel.critic_enabled is not None:
        return channel.critic_enabled
    return settings.channel.critic_enabled

async def polish_post(
    *,
    text: str,
    footer: str,
    api_key: str,
    model: str,
) -> str:
    """Run critic pass. Returns polished text or raises CriticError."""
```

**Private:**

- `_create_critic_agent(api_key, model) -> Agent[None, str]` — PydanticAI
  agent with `temperature=0.4`, `output_type=str`.
- `CRITIC_PROMPT: str` — system prompt (see below).
- `_validate_invariants(original, polished, footer) -> list[str]` —
  returns a list of violation strings; empty = pass.
- `_strip_agent_artifacts(output: str) -> str` — strips code fences,
  `"Here's your polished version:"` prefixes, surrounding quotes.
- `_extract_md_links(text: str) -> list[tuple[str, str]]` — extracts
  `(label, url)` pairs from `[text](url)` markdown.
- `_RETRY_HINT: str` — preamble used when the first attempt violates an
  invariant.

### Data model

Two nullable columns added via a single Alembic migration.

**`channels` table:**

```python
critic_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
```

`None` means "follow global default". `True` / `False` override.

**`channel_posts` table:**

```python
pre_critic_text: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Set to the generator's output when the critic successfully rewrites
the post; `None` otherwise (critic disabled, critic failed, or post
was not run through the critic).

**`GeneratedPost` pydantic model** gains:

```python
pre_critic_text: str | None = Field(default=None)
```

Orchestrators that persist `GeneratedPost` to `ChannelPost` copy this
field across.

### Configuration

New fields in `ChannelAgentSettings` (`app/channel/config.py`):

```python
critic_enabled: bool = Field(
    default=False,
    description="Master kill-switch for the post critic polish pass",
)
critic_model: str = Field(
    default="anthropic/claude-sonnet-4-6",
    description="Model used by the critic agent",
)
```

Env-overrides: `CHANNEL_CRITIC_ENABLED`, `CHANNEL_CRITIC_MODEL`.

**Default `critic_enabled=False`** — safe rollout. Flip on per-channel
via assistant tool to test on `@test908070`, then flip global to True
after verification.

**Resolution matrix:**

| channel.critic_enabled | settings.channel.critic_enabled | effective |
| --- | --- | --- |
| `None` | `False` | `False` |
| `None` | `True` | `True` |
| `True` | `False` | `True` |
| `True` | `True` | `True` |
| `False` | `False` | `False` |
| `False` | `True` | `False` |

### System prompt

```
You are a ruthless style editor for the Telegram channel "{channel_name}"
(news for CIS students in the Czech Republic). Your ONLY job: polish a
post by removing clichés, banal openers, dead verbs, and pompous or
corporate phrasing.

HARD RULES — violation = task failed:
1. PRESERVE every Markdown link [text](url) — same URLs, same count.
2. PRESERVE the exact footer at the end: {footer}
3. PRESERVE facts: numbers, dates, names, institutions, prices, addresses.
4. PRESERVE structure: same paragraph breaks, same order, same headline
   emoji at the very start.
5. Output MUST be <= 900 characters total.
6. Do NOT add new information. Do NOT invent details, numbers, or names.

WHAT TO FIX:
- Banned phrases: "это отличная/уникальная возможность",
  "не упустите шанс", "лично расспросить", "рады сообщить",
  "с гордостью представляем", "Ознакомиться можно...",
  "Подробнее здесь...", "Узнать больше..."
- Banal openers: "У нас отличная новость", "Есть хорошая новость для
  вас", "Хотим поделиться..."
- Dead verbs: "предоставляем", "сообщаем", "уведомляем" — replace with
  the concrete action.
- Pompous / corporate tone → friendly, peer-to-peer student tone.
- Filler adjectives: "уникальный", "незабываемый", "эксклюзивный".

TONE: simple, slightly witty, like telling a friend about news. At
most one exclamation mark per post.

OUTPUT: return ONLY the polished post text. No explanations, no
"Here's your polished version:", no markdown code fences. Plain
polished post.
```

The prompt is filled with `{channel_name}` and `{footer}` at agent
construction time.

### Invariant checks

Post-call validation; violations are collected then either fixed in a
retry or raised as `CriticError`.

| # | Check | Failure string |
| --- | --- | --- |
| 1 | `set(original_urls) <= set(polished_urls)` | `"lost URL: <url>"` |
| 2 | `len(polished_links) >= len(original_links)` | `"link count dropped: N → M"` |
| 3 | `footer in polished` | `"footer missing"` |
| 4 | `len(polished) <= 900` | `"length over 900: N"` |
| 5 | `len(polished) >= 100` | `"output too short: N"` |
| 6 | First non-whitespace codepoint is emoji | `"headline emoji missing"` |

URL regex: `re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)`.

Emoji check: first codepoint is in Unicode category `So` (Symbol,
Other) or in the approved whitelist `{📰 🎓 💼 🎉 🏠 💰 ⚡}`. We use a
whitelist rather than `\p{Emoji}` to stay dependency-free.

### Failure handling (`polish_post` implementation sketch)

```python
async def polish_post(*, text, footer, api_key, model):
    agent = _create_critic_agent(api_key, model, footer=footer)

    result = await agent.run(text)
    usage = extract_usage_from_pydanticai_result(result, model, "critic")
    if usage:
        await log_usage(usage)

    polished = _strip_agent_artifacts(result.output)
    violations = _validate_invariants(text, polished, footer)
    if not violations:
        return polished

    # Retry once with explicit correction hint.
    retry_prompt = (
        f"{_RETRY_HINT}\n"
        f"Previous violations: {', '.join(violations)}\n\n"
        f"Original post:\n{text}"
    )
    result = await agent.run(retry_prompt)
    usage = extract_usage_from_pydanticai_result(result, model, "critic_retry")
    if usage:
        await log_usage(usage)

    polished = _strip_agent_artifacts(result.output)
    violations = _validate_invariants(text, polished, footer)
    if not violations:
        return polished

    raise CriticError(f"invariant violations after retry: {violations}")
```

Cost tracking logs each attempt separately (`critic` vs
`critic_retry`) so retry rate is observable.

### Integration points

**`app/channel/generator.py::generate_post` — new kwargs:**

```python
async def generate_post(
    ...,
    critic_enabled: bool = False,
    critic_model: str = "",
) -> GeneratedPost | None:
```

Call site sits between `enforce_footer_and_length` (line ~375) and the
image pipeline (line ~400).

**`app/channel/workflow.py::generate_post` (Burr action) — resolves
flags and passes them through:**

```python
critic_enabled = resolve_critic_enabled(channel, settings)
critic_model = settings.channel.critic_model

post = await _generate(
    ...,
    critic_enabled=critic_enabled,
    critic_model=critic_model,
)
```

And when persisting `ChannelPost`:
```python
ChannelPost(
    ...,
    pre_critic_text=post.pre_critic_text,
)
```

**`app/channel/review/service.py` (regeneration path)** — same
plumbing: resolve flags from channel + settings, pass through, copy
`pre_critic_text` into the persisted row.

### Assistant bot tool

New tool (co-located with existing channel-management tools):

```python
async def set_channel_critic(channel_id: int, enabled: bool | None) -> str:
    """
    Override critic enablement for a specific channel.
    - True  → force-on for this channel
    - False → force-off for this channel
    - None  → follow global default (CHANNEL_CRITIC_ENABLED)
    Returns a one-line status including the effective value after update.
    """
```

Semantics mirror the resolution matrix above. The implementation
reads global default from `settings.channel.critic_enabled` so the
response message shows both the override and the effective result.

## Testing strategy

### Unit — `tests/unit/test_critic.py`

1. `_extract_md_links` — empty text, 0/1/many links, malformed
   markdown.
2. `_validate_invariants` — one test per rule:
   - lost URL
   - dropped link count
   - missing footer
   - length > 900
   - length < 100
   - missing headline emoji
   - all-valid → empty list
3. `_strip_agent_artifacts` — strips ```markdown fences, `"Here's..."`
   prefixes, surrounding quotes; idempotent on clean output.
4. `polish_post` success — mock agent returns valid polished text →
   returned as-is, `log_usage` called once with `operation="critic"`.
5. `polish_post` retry-then-success — first call returns text missing
   footer, second call fixes it → returned, `log_usage` called twice
   (`critic` + `critic_retry`).
6. `polish_post` fail after retry → `CriticError` with violation list
   in message.
7. `resolve_critic_enabled` — 6 rows from the resolution matrix.

### DB — `tests/unit/test_critic_columns.py`

1. `Channel.critic_enabled` round-trips `None`, `True`, `False`.
2. `ChannelPost.pre_critic_text` round-trips `None` and a long string.
3. Default on new `Channel(...)` is `None`.
4. Default on new `ChannelPost(...)` is `None`.

### Integration — `tests/integration/test_generator_with_critic.py`

1. `generate_post(critic_enabled=True, critic_model="m")` with mocked
   critic → `post.text` equals polished, `post.pre_critic_text` equals
   the pre-critic text.
2. `generate_post(critic_enabled=False)` → `post.text` unchanged,
   `post.pre_critic_text is None`.
3. `generate_post(critic_enabled=True)` with critic raising
   `CriticError` → `post.text` unchanged, `post.pre_critic_text is
   None`, warning logged. Post is still returned (not None).
4. With critic enabled and `critic_model=""` → critic NOT invoked
   (guarded by `and critic_model`).

### Assistant tool — `tests/unit/test_assistant_set_channel_critic.py`

1. Set `True` on channel → DB column is `True`, response includes
   "enabled: True".
2. Set `False` → DB column is `False`.
3. Set `None` → DB column is `None`, response says "follow global".
4. Unknown `channel_id` → error string, no DB mutation.

### E2E

Skipped. Existing E2E (`tests/e2e/test_review_*.py`) cover the flow;
critic is a narrow polish pass whose integration is covered by the
integration test above.

## Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Sonnet drops a fact ("300 заявок" → "много заявок") | Prompt hard-rule. Invariant checker is URL-only today; facts are out of scope for automated validation. If admin catches a dropped fact, flip channel critic off and file a prompt-improvement ticket. |
| Critic invents new information | Prompt hard-rule; fact-checking is out of scope for v1. Admin review is the authoritative gate. |
| Cost drift if the feature is silently enabled on many channels | Global kill-switch, plus `log_usage(operation="critic")` is visible in the existing cost-tracking query. Watch for anomalies after rollout. |
| Critic removes legitimate stylistic word ("отличный" in "отличное исследование") | Prompt targets clichéd openers and pompous fillers, not all adjectives. First-week test on `@test908070`; adjust prompt if it over-edits. |
| Invariant checker too strict → high retry + fallback rate | Add a counter log `critic_fallback_rate` via existing cost/usage logging; if >10% of generations fall back, soften invariants or the retry hint. |
| LLM returns code fences or a prefix like "Here's your polished version:" | `_strip_agent_artifacts` handles the common patterns before invariant checks. Prompt explicitly forbids them. |
| First codepoint-is-emoji check breaks on legitimate non-emoji openers (e.g. numbers) | Generation prompt already requires a headline emoji, so every input to the critic has one. The check is protecting against the critic stripping it. |

## Rollout plan

1. Merge feature branch with `critic_enabled=False` default. No
   production behavior change on deploy.
2. Via assistant bot on `@test908070` (Konnekt Dev):
   `set_channel_critic(channel_id=<dev>, enabled=True)`.
3. Observe 20–30 posts on the dev channel (one-to-two-day window).
   Check: fallback rate, admin satisfaction with tone, any fact drift.
4. If clean, flip global env `CHANNEL_CRITIC_ENABLED=true`. All
   channels inherit unless overridden.
5. If issues on a specific channel later,
   `set_channel_critic(channel_id=X, enabled=False)` kills it without
   redeploy.

## Open questions

None. All clarifying questions resolved in brainstorming.

## File map

**New:**

- `app/channel/critic.py`
- `tests/unit/test_critic.py`
- `tests/unit/test_critic_columns.py`
- `tests/unit/test_assistant_set_channel_critic.py`
- `tests/integration/test_generator_with_critic.py`
- `alembic/versions/<hash>_add_critic_columns.py`

**Modified:**

- `app/channel/config.py` — `critic_enabled`, `critic_model` fields.
- `app/channel/generator.py` — new kwargs on `generate_post`, critic
  invocation between length-enforcement and image pipeline.
- `app/db/models.py` — `Channel.critic_enabled`, `ChannelPost.pre_critic_text`,
  `GeneratedPost.pre_critic_text`.
- `app/channel/workflow.py` — resolve flags, pass through, persist
  `pre_critic_text`.
- `app/channel/review/service.py` — same plumbing on the regeneration
  path.
- `app/assistant/tools/channel/channels.py` — `set_channel_critic`
  tool registration alongside existing `list_channels`,
  `add_channel`, `edit_channel`, `remove_channel`.
