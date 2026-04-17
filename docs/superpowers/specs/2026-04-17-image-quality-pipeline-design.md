# Image Quality Pipeline — Design Spec

**Date:** 2026-04-17
**Status:** Approved for implementation
**Scope:** Sprint 1 of the image-improvement initiative ("option A — minimal scope")

## Problem

Channel posts frequently ship with low-quality or duplicate images:
- RSS enclosures often point to generic brand logos or "breaking news" text slides
- The same placeholder image reappears across multiple posts because there is no cross-post image comparison
- Candidate images from the article body are picked by the first regex match, not ranked
- When multiple images are available, the publisher always sends an album, even when the images do not belong together
- The review agent has only coarse tools (`replace_images(all)`, `remove_images(all)`) — no way to tweak one image or reorder

This spec addresses those five gaps with a minimal, low-risk pipeline on top of the existing `app/channel/images.py` extractor.

## Goals (and non-goals)

**In scope (Sprint 1):**
1. Cheap heuristic filter (resolution, aspect ratio, color entropy, file size) to drop obvious junk before any paid API call
2. Vision-model quality/relevance scoring for remaining candidates
3. Perceptual-hash (pHash) deduplication against the last N approved posts in the same channel
4. LLM composition decision — single / album / none — based on scored candidates
5. Granular review-agent tools: list, add, remove-by-index, reorder, use-candidate-from-pool

**Out of scope (deferred):**
- Stock-image APIs (Pexels, Pixabay) — rarely relevant for specific news stories; revisit in Sprint 2 if needed
- Trafilatura/Newspaper4k replacement of current extractor — existing regex+OG extractor covers ~95% of sources
- AI-generated images / meme agent
- Full `PostImage` relational table — JSON on `ChannelPost` is sufficient for 1–10 images per post

## Architecture

### Module layout

```
app/channel/
├── images.py                    # existing — extraction, UNCHANGED
├── image_pipeline/              # NEW package
│   ├── __init__.py              # build_candidates(item, channel_id, session_maker) orchestrator
│   ├── models.py                # ImageCandidate, VisionScore, CompositionDecision (Pydantic)
│   ├── filter.py                # cheap_filter(urls) — Pillow-based heuristics
│   ├── score.py                 # vision_score(candidates, title) — OpenRouter multimodal
│   ├── dedup.py                 # phash_dedup(candidates, channel_id, session_maker)
│   └── compose.py               # pick_composition(text, candidates) + fallback
├── generator.py                 # MODIFIED — calls image_pipeline.build_candidates + pick_composition
├── exceptions.py                # +ImagePipelineError
└── review/
    ├── agent.py                 # MODIFIED — removes coarse tools, adds granular
    └── image_tools.py           # NEW — business logic split out from PydanticAI wrappers
```

### Data flow

```
generator.generate_post(item)
    ↓
  text = llm_generate(item)                   # existing
    ↓
  candidates = image_pipeline.build_candidates(item, channel_id, session_maker):
      ├─ urls = images.find_images_for_post(...) + images.extract_rss_media_url(...)
      ├─ cheap_filter(urls) → drop small/solid/weird
      ├─ vision_score(remaining, title) → drop is_logo/is_text_slide, sort by score
      └─ phash_dedup(scored, channel_id) → drop duplicates vs last 30 approved
    ↓
  decision = image_pipeline.pick_composition(text, candidates)
    ↓
  persist to ChannelPost:
      image_urls = [c.url for c in candidates if selected]  # source of truth for publishing
      image_candidates = [c.model_dump() for c in candidates]  # full pool incl. unused
      image_phashes = [c.phash for c in candidates if selected]  # for future dedup queries
```

### Storage changes on `ChannelPost`

Two new nullable JSON columns — no new table:

| Column | Type | Purpose |
|---|---|---|
| `image_candidates` | `JSON \| None` | Full scored pool produced by `build_candidates`. Each element = `ImageCandidate.model_dump()` |
| `image_phashes` | `JSON \| None` (list of hex strings) | pHashes of currently-selected images — queried by future posts in the same channel for dedup |

Existing `image_url: str | None` and `image_urls: list[str] | None` remain as-is. `image_urls` stays the source of truth for what is actually in the Telegram post; `image_candidates` is analytics + pool for the review agent.

Migration: one Alembic revision, both columns nullable, zero-downtime, fully backward-compatible.

## Pydantic models

```python
class ImageCandidate(BaseModel):
    url: str
    source: str                              # "og_image" | "article_body" | "rss_enclosure" | "reviewer_added" | "brave_image"
    width: int | None = None
    height: int | None = None
    phash: str | None = None
    quality_score: int | None = Field(default=None, ge=0, le=10)
    relevance_score: int | None = Field(default=None, ge=0, le=10)
    is_logo: bool = False
    is_text_slide: bool = False
    is_duplicate: bool = False
    description: str = ""
    selected: bool = False
    model_config = {"extra": "ignore"}


class VisionScore(BaseModel):
    """LLM vision-model output per image (one element per input image)."""
    index: int
    quality_score: int = Field(ge=0, le=10)
    relevance_score: int = Field(ge=0, le=10)
    is_logo: bool
    is_text_slide: bool
    description: str


class CompositionDecision(BaseModel):
    composition: Literal["single", "album", "none"]
    selected_indices: list[int] = Field(default_factory=list)
    reason: str = ""
```

`bytes_` (raw downloaded image bytes used only during filtering/hashing) lives in a local dict keyed by URL inside `image_pipeline`, never in the Pydantic model and never persisted.

## Stage-by-stage detail

### `cheap_filter(urls) -> list[ImageCandidate]`

Parallel download via `safe_fetch` (SSRF-protected). For each URL, open with PIL and apply:

| Check | Threshold | Rationale |
|---|---|---|
| Content size | ≤ 20 MB | Sanity cap; avoid OOM |
| Min resolution | ≥ 600 × 400 | Below this, unusable in Telegram posts |
| Aspect ratio | ≤ 3:1 | Wider/taller → typically banners, ad strips |
| Color entropy | ≥ 30 unique colors after palette reduction (1024 max) | Solid logos and flat graphics fail |
| File size vs area | ≥ 20 KB when `w*h > 500 000` | Catches synthetic/vector rescales pretending to be photos |

Failures → silent skip, debug log with reason. Total timeout 30 s for the stage; what we have after timeout is what we use.

### `vision_score(candidates, post_title) -> list[ImageCandidate]`

Single batched call to OpenRouter multimodal (model: `google/gemini-2.5-flash`, configurable via `CHANNEL_VISION_MODEL`). Up to 5 images per batch.

System prompt asks for a JSON array of `VisionScore` objects, one per image, ordered by index.

Post-processing:
- Drop any candidate with `is_logo=true` or `is_text_slide=true`
- Drop any candidate with `quality_score < 5` or `relevance_score < 4`
- Sort remaining by `quality_score + relevance_score` descending
- Keep top 5

Failure modes: on API error, malformed JSON, or timeout — mark all candidates' `quality_score=None` and continue. Downstream handles this via `_fallback_composition`.

**Cost:** ~$0.002–0.005 per post (Gemini bills by image resolution).

### `phash_dedup(candidates, channel_id, session_maker) -> list[ImageCandidate]`

1. Compute `imagehash.phash` on each candidate's bytes → 64-bit hex string
2. Query last 30 approved posts in the same channel: `SELECT image_phashes FROM channel_posts WHERE channel_id=:cid AND status='APPROVED' ORDER BY created_at DESC LIMIT 30`
3. Flatten to a set of recent hashes
4. For each candidate: Hamming distance to any recent hash ≤ 10 → set `is_duplicate=True`, drop

Library: `imagehash>=4.3` (transitively depends on Pillow, NumPy, SciPy — all already present or small).

Configurable via `CHANNEL_IMAGE_PHASH_LOOKBACK_POSTS` (default 30) and `CHANNEL_IMAGE_PHASH_THRESHOLD` (default 10).

### `pick_composition(post_text, candidates) -> CompositionDecision`

One LLM call (text-only, `google/gemini-2.5-flash`, ~$0.0005). Candidates sent as text metadata (index, description, quality_score, relevance_score, source) — not re-uploading bytes.

Prompt rules:
- `"none"`: no candidate is good enough (all off-topic or low-quality)
- `"single"`: one strong image
- `"album"`: 2–4 images with coherent style AND shared narrative
- Cap at 4 images in an album (not 10 — fewer is better)
- Prefer `"single"` over weak `"album"`, prefer `"none"` over bad `"single"`

Fallback when the LLM call fails (`_fallback_composition`):
```python
good = [c for c in candidates if (c.quality_score or 0) >= 6 and not c.is_logo and not c.is_text_slide]
if not good:
    return CompositionDecision(composition="none", selected_indices=[], reason="fallback: no high-quality candidates")
return CompositionDecision(composition="single", selected_indices=[0], reason="fallback: used highest-scored candidate")
```

## Review agent tool contract

**Removed** (coarse): `replace_images(urls)`, `remove_images()`, `find_new_images(query)`.

**Added** (granular):

| Tool | Signature | Behavior |
|---|---|---|
| `list_images` | `() -> str` | Table of current images + candidate pool with index/source/score/description/selected-flag |
| `use_candidate` | `(pool_index: int, position: int \| None = None) -> str` | Promote pool candidate to the post. `position=None` → append |
| `add_image_url` | `(url: str, position: int \| None = None) -> str` | Validates via cheap_filter + vision_score. On pass, appends to both pool and selected |
| `find_and_add_image` | `(query: str) -> str` | Brave Image search, adds best-scored result to pool (not auto-selected) |
| `remove_image` | `(position: int) -> str` | Removes from selected; candidate stays in pool for re-use |
| `reorder_images` | `(order: list[int]) -> str` | Reorder selected images by current-position indices |
| `clear_images` | `() -> str` | Empty the selected list (pool preserved) |

Validation errors → readable strings to the agent (`"rejected: is_logo=true"`, `"rejected: quality=3"`, `"rejected: unsafe URL"`). No exceptions bubble up — the agent retries or explains to the admin.

Every write tool calls `_refresh_review_message` (existing helper) to re-render the preview.

System prompt gains an `## Images workflow` block explaining the flow: `list_images` first, then `use_candidate` / `find_and_add_image` / `add_image_url` to compose, then `remove_image` / `reorder_images` as needed.

## Error handling

Image pipeline is **best-effort**. A post must reach review even when image handling fully fails — `image_urls=[]` is a valid outcome, not an error.

| Stage | Failure | Behavior |
|---|---|---|
| `extract_candidates` | HTTP/SSRF | Skip URL, continue with others |
| `cheap_filter` | Timeout, corrupt image | Skip that candidate |
| `vision_score` | API error, malformed JSON | Retry once, then null scores, continue |
| `phash_dedup` | Hash computation error | Candidate keeps `phash=None`, not deduped |
| `phash_dedup` | DB unavailable | Skip dedup stage (log), continue |
| `pick_composition` | LLM error | `_fallback_composition` heuristic |
| Total pipeline | Any uncaught | `image_urls=[]`, `image_candidates=None`, `logger.exception`, post still goes to review |

New exception type: `ImagePipelineError(ChannelPipelineError)` in `app/channel/exceptions.py` — caller interprets as "skip images and continue", never halts the pipeline.

### Time budget

Hard `asyncio.wait_for` per stage: extract 30 s, filter 30 s, score 20 s, dedup 5 s, compose 15 s. Total ≤ 100 s per post. Overrun → abort that stage, proceed without images.

## Testing

Follow existing patterns: unit tests with SQLite in-memory + mocked externals; integration tests with testcontainers PG + mocked LLM/HTTP.

| Component | Type | Mock | Real |
|---|---|---|---|
| `cheap_filter` | unit | httpx | PIL, in-memory bytes |
| `vision_score` | unit | `openrouter_chat_completion` | Pydantic validation, JSON parsing |
| `phash_dedup` (pure) | unit | — | imagehash |
| `phash_dedup` (DB) | integration PG | — | Real pgvector container, SQL |
| `pick_composition` | unit | LLM | Pydantic parsing, fallback |
| `build_candidates` | integration PG | LLM, HTTP | PIL, real dedup query |
| Review agent tools | unit | LLM, DB (aiosqlite) | tool logic, validation strings |
| Full E2E flow | E2E | — | FakeTelegramServer |

New shared fixture `tests/fixtures/images.py::make_test_image(width, height, colors, format)` produces deterministic in-memory JPEG/PNG bytes for all tests.

**Estimated test counts:**
- PR #1 foundation: 13 (6 filter + 4 dedup unit + 3 dedup PG)
- PR #2 pipeline: 14 (5 score + 4 compose + 3 orchestrator PG + 2 full flow)
- PR #3 review tools: 12 (10 tool unit + 2 E2E)
- **Total: ~37 new tests**, +1–2 s to suite runtime

**Coverage targets:** image pipeline ≥ 85 %, review agent tools ≥ 80 %, overall project ≥ 58 % (not lower than current).

No real LLM or Telegram API calls in any automated test. Manual smoke via `/generate_post` in the test channel after merging PR #2.

## Rollout — PR breakdown

### PR #1 — Foundation (scaffolding)

**Changes:**
- Alembic migration: `+image_candidates: JSON`, `+image_phashes: JSON` on `ChannelPost`
- `pyproject.toml`: `+imagehash>=4.3`
- New package `app/channel/image_pipeline/` with `models.py`, `filter.py`, `dedup.py`, `__init__.py`
- `app/channel/exceptions.py`: `+ImagePipelineError`
- `app/core/config.py`: `ChannelAgentSettings.vision_model`, `image_phash_lookback_posts`, `image_phash_threshold`
- `tests/fixtures/images.py`: `make_test_image()` helper
- 13 tests

**Safety:** purely additive. New columns nullable, nothing writes to them yet. Existing behavior unchanged. Only risk is the migration itself → exercised in testcontainer CI.

**Size:** ~300 LOC code, ~200 LOC tests.

### PR #2 — Pipeline integration (behavior change)

**Changes:**
- `image_pipeline/score.py` — vision scoring via OpenRouter multimodal
- `image_pipeline/compose.py` — pick_composition + fallback
- `image_pipeline/__init__.py` — `build_candidates` orchestrator
- `generator.py` — replaces `find_images_for_post` call with `build_candidates` + `pick_composition`, writes `image_candidates` and `image_phashes` alongside existing `image_urls`
- `workflow.py` — minor: ensures `image_candidates` round-trips through `generated_post` dict and lands in the DB on persist
- 14 tests (including 2 full-flow integration)

**Safety:** behavior **does** change after this PR — posts now pass through filter+score+dedup. Some images that previously got through (logos) will now be filtered. This is the goal, but:

**24 h smoke period** before merging PR #3:
- Watch `image_pipeline_duration_ms`, `vision_score_called`, `phash_dedup_hits`, `pick_composition_decision` in logs
- Visually check 5–10 review-group posts — is anything good being rejected?
- If `% posts with composition="none"` > 40 %, lower thresholds (`quality >= 4`) and iterate

**Size:** ~400 LOC code, ~250 LOC tests.

### PR #3 — Review agent granular tools

**Changes:**
- Remove coarse tools from `review/agent.py`
- Add seven granular tools (see Review agent tool contract section)
- New helper `app/channel/review/image_tools.py` — business logic, clean testing boundary
- System prompt update (Images workflow block)
- Rewrite/extend old image-related tests in `tests/unit/test_channel_agent.py`
- 12 tests

**Safety:** isolated to review.agent. Admin-facing behavior is functionally the same or richer. Old tests exercising `replace_images`/`remove_images` are ported to new tool names.

**Size:** ~350 LOC code, ~300 LOC tests.

### Merge order and dependencies

```
PR #1 (foundation) → PR #2 (pipeline) → PR #3 (review tools)
                           │
                           └── 24 h smoke before PR #3
```

- PR #1 → PR #2: hard import dependency
- PR #2 → PR #3: soft dependency — PR #3 works without PR #2 (pool just stays empty) but UX is leaner when the pool is populated

**Total effort:** ~2–3 days of actual work + 1 day smoke window.

## Open questions

None at this time. All decisions above are settled with the user. Any further refinement happens in the implementation plan (writing-plans skill).
