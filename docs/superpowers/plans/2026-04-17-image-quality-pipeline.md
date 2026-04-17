# Image Quality Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filter low-quality images, dedup across posts, let an LLM pick the final composition, and give the review agent granular image-editing tools.

**Architecture:** New `app/channel/image_pipeline/` package wraps the existing `images.py` extractor with four stages (filter → score → dedup → compose). Results persist as JSON on `ChannelPost` (no new table). The review agent's coarse `replace_images`/`remove_images`/`find_new_images` are replaced with seven granular tools backed by a separate `image_tools.py` business-logic module.

**Tech Stack:** Python 3.12 · Pillow · imagehash · Pydantic v2 · PydanticAI · OpenRouter multimodal (`google/gemini-2.5-flash`) · SQLAlchemy 2 async · pytest + testcontainers[postgres] (pgvector).

**Reference spec:** `docs/superpowers/specs/2026-04-17-image-quality-pipeline-design.md`

**Rollout:** Three PRs merged in order: PR #1 Foundation (Tasks 1–8) → PR #2 Pipeline (Tasks 9–14) → PR #3 Review Tools (Tasks 15–18). Create a new branch per PR off `main` once the previous merges; see **PR boundaries** at the end of each PR section.

---

## PR #1 — Foundation

Non-behaviour-changing scaffold: new columns, new package with filter + dedup, Pydantic models, test fixtures, the new exception, the new config entries. Nothing yet writes to the new columns.

---

### Task 1: Add `imagehash` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the dep to `[project].dependencies`**

Open `pyproject.toml` and locate the `dependencies = [ ... ]` list under `[project]`. Append `imagehash>=4.3` in alphabetical order (it goes between `httpx` and `pgvector`):

```toml
dependencies = [
    "aiogram>=3.5",
    "alembic>=1.13",
    "psycopg2-binary>=2.9",
    "pydantic>=2.5",
    "pydantic-settings>=2.1",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "python-dotenv",
    "structlog>=23.2",
    "pydantic-ai[openai]>=1.84",
    "httpx>=0.27",
    "imagehash>=4.3",
    "feedparser>=6.0.12",
    "telethon>=1.42.0",
    "burr>=0.40.2",
    "telegramify-markdown>=1.1,<2",
    "pgvector>=0.4.2",
]
```

- [ ] **Step 2: Lock + install**

Run:
```bash
uv lock && uv sync
```
Expected: `uv.lock` is updated; `imagehash` appears in `uv.lock`. `Pillow`, `numpy`, `scipy` come in transitively.

- [ ] **Step 3: Verify the import works**

```bash
uv run python -c "import imagehash; from PIL import Image; print(imagehash.__version__, Image.__version__)"
```
Expected: prints two version strings, no error.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add imagehash for perceptual-hash image dedup"
```

---

### Task 2: Alembic migration + ORM fields for `image_candidates` and `image_phashes`

**Files:**
- Create: `alembic/versions/<hash>_add_image_candidates_phashes.py`
- Modify: `app/db/models.py:397-453` (`ChannelPost`)

- [ ] **Step 1: Write the failing test for new ORM fields**

Create `tests/unit/test_channel_post_image_fields.py`:

```python
"""Regression test: image_candidates and image_phashes fields on ChannelPost."""

from __future__ import annotations

import pytest
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio


async def test_channel_post_image_candidates_roundtrip(session_maker: async_sessionmaker):
    """image_candidates JSON field persists a list-of-dicts and reads back equal."""
    payload = [
        {"url": "https://example.com/a.jpg", "source": "og_image", "quality_score": 8, "selected": True},
        {"url": "https://example.com/b.jpg", "source": "article_body", "quality_score": 6, "selected": False},
    ]
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=-100,
            external_id="ext1",
            title="Title",
            post_text="Body",
            status=PostStatus.DRAFT,
        )
        post.image_candidates = payload
        post.image_phashes = ["a3f8d2c1b9e47f05"]
        session.add(post)
        await session.commit()
        await session.refresh(post)

        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == post.id))).scalar_one()
        assert row.image_candidates == payload
        assert row.image_phashes == ["a3f8d2c1b9e47f05"]


async def test_channel_post_image_fields_default_to_none(session_maker: async_sessionmaker):
    """Both fields are nullable and None by default — backward compatible."""
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=-100,
            external_id="ext2",
            title="Title",
            post_text="Body",
            status=PostStatus.DRAFT,
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        assert post.image_candidates is None
        assert post.image_phashes is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run -m pytest tests/unit/test_channel_post_image_fields.py -v
```
Expected: `AttributeError: 'ChannelPost' object has no attribute 'image_candidates'` (or similar).

- [ ] **Step 3: Add the ORM fields**

In `app/db/models.py`, find the `ChannelPost` class. Add two new mapped columns right after `image_urls` (around line 411):

```python
    image_urls: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    image_candidates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    image_phashes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=PostStatus.DRAFT, index=True)
```

Do **not** add them as `__init__` parameters — they are written after creation via attribute assignment (see the test). This keeps the constructor signature stable for existing callers.

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run -m pytest tests/unit/test_channel_post_image_fields.py -v
```
Expected: both tests pass.

- [ ] **Step 5: Create the Alembic migration**

Run:
```bash
uv run alembic revision -m "add image_candidates and image_phashes to channel_posts"
```
Expected: creates a file under `alembic/versions/`. Open it and replace the auto-generated body with:

```python
"""add image_candidates and image_phashes to channel_posts

Revision ID: <auto-generated>
Revises: a3b1c2d4e5f6
Create Date: <auto-generated>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '<auto-generated — keep as-is>'
down_revision: Union[str, None] = 'a3b1c2d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channel_posts', sa.Column('image_candidates', sa.JSON(), nullable=True))
    op.add_column('channel_posts', sa.Column('image_phashes', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('channel_posts', 'image_phashes')
    op.drop_column('channel_posts', 'image_candidates')
```

Double-check that `down_revision` points to `'a3b1c2d4e5f6'` (the previous image-related migration `add_image_urls_json_to_channel_posts`). If alembic picked a different parent, run `uv run alembic history` and fix `down_revision` manually.

- [ ] **Step 6: Verify migration applies against testcontainer**

Run:
```bash
uv run -m pytest tests/integration/test_semantic_dedup_pg.py -v -x
```
Expected: passes. (The pg_engine fixture does `Base.metadata.create_all`, so this confirms SQLAlchemy can build the schema with the new columns. Real alembic apply is exercised in Task 2a below.)

- [ ] **Step 7: Run alembic upgrade end-to-end against a throwaway PG**

```bash
docker run --rm -d --name pg-mig-check -e POSTGRES_PASSWORD=test -p 55432:5432 pgvector/pgvector:pg18
sleep 3
DB_HOST=localhost DB_PORT=55432 DB_USER=postgres DB_PASSWORD=test DB_NAME=postgres uv run alembic upgrade head
docker rm -f pg-mig-check
```
Expected: no errors; alembic reports applying the new revision. If anything errors, fix before committing.

- [ ] **Step 8: Commit**

```bash
git add alembic/versions/*_add_image_candidates_phashes.py app/db/models.py tests/unit/test_channel_post_image_fields.py
git commit -m "feat(db): add image_candidates and image_phashes JSON columns to channel_posts"
```

---

### Task 3: Add `ImagePipelineError` exception

**Files:**
- Modify: `app/channel/exceptions.py`

- [ ] **Step 1: Write the failing test**

Append to the end of the (currently absent) `tests/unit/test_channel_exceptions.py` (create if missing):

```python
"""Unit tests for app.channel.exceptions."""

from app.channel.exceptions import (
    ChannelPipelineError,
    ImagePipelineError,
)


def test_image_pipeline_error_inherits_from_channel_pipeline_error():
    exc = ImagePipelineError("boom")
    assert isinstance(exc, ChannelPipelineError)
    assert isinstance(exc, Exception)
    assert str(exc) == "boom"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run -m pytest tests/unit/test_channel_exceptions.py -v
```
Expected: `ImportError: cannot import name 'ImagePipelineError'`.

- [ ] **Step 3: Add the exception class**

In `app/channel/exceptions.py`, append:

```python


class ImagePipelineError(ChannelPipelineError):
    """Recoverable failure in the image pipeline.

    Caller should skip images (``image_urls=[]``) and continue the post
    through review rather than halting the whole content pipeline.
    """
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run -m pytest tests/unit/test_channel_exceptions.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/channel/exceptions.py tests/unit/test_channel_exceptions.py
git commit -m "feat(channel): add ImagePipelineError for best-effort image failures"
```

---

### Task 4: Config fields for image pipeline

**Files:**
- Modify: `app/channel/config.py:25-82` (`ChannelAgentSettings`)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_channel_config_image.py`:

```python
"""Regression tests for image-pipeline config fields."""

from app.channel.config import ChannelAgentSettings


def test_default_vision_model():
    s = ChannelAgentSettings()
    assert s.vision_model == "google/gemini-2.5-flash"


def test_default_phash_thresholds():
    s = ChannelAgentSettings()
    assert s.image_phash_lookback_posts == 30
    assert s.image_phash_threshold == 10


def test_vision_model_env_override(monkeypatch):
    monkeypatch.setenv("CHANNEL_VISION_MODEL", "anthropic/claude-haiku-4-5")
    s = ChannelAgentSettings()
    assert s.vision_model == "anthropic/claude-haiku-4-5"


def test_phash_lookback_env_override(monkeypatch):
    monkeypatch.setenv("CHANNEL_IMAGE_PHASH_LOOKBACK_POSTS", "15")
    s = ChannelAgentSettings()
    assert s.image_phash_lookback_posts == 15
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run -m pytest tests/unit/test_channel_config_image.py -v
```
Expected: `AttributeError: 'ChannelAgentSettings' object has no attribute 'vision_model'`.

- [ ] **Step 3: Add the fields**

In `app/channel/config.py`, inside `ChannelAgentSettings`, right after the `generation_model` field (around line 45), add:

```python
    vision_model: str = Field(
        default="google/gemini-2.5-flash",
        description="Multimodal model for scoring candidate images (OpenRouter slug)",
    )
    image_phash_lookback_posts: int = Field(
        default=30,
        description="How many recent approved posts to compare pHash against for dedup",
    )
    image_phash_threshold: int = Field(
        default=10,
        description="Hamming distance threshold for pHash duplicate detection (0-64)",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run -m pytest tests/unit/test_channel_config_image.py -v
```
Expected: all four tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/channel/config.py tests/unit/test_channel_config_image.py
git commit -m "feat(config): add vision_model and image-phash settings to ChannelAgentSettings"
```

---

### Task 5: Pydantic models (`ImageCandidate`, `VisionScore`, `CompositionDecision`)

**Files:**
- Create: `app/channel/image_pipeline/__init__.py`
- Create: `app/channel/image_pipeline/models.py`
- Create: `tests/unit/test_image_pipeline_models.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_image_pipeline_models.py`:

```python
"""Unit tests for image pipeline Pydantic models."""

from __future__ import annotations

import pytest
from app.channel.image_pipeline.models import (
    CompositionDecision,
    ImageCandidate,
    VisionScore,
)
from pydantic import ValidationError


class TestImageCandidate:
    def test_defaults(self):
        c = ImageCandidate(url="https://x/y.jpg", source="og_image")
        assert c.url == "https://x/y.jpg"
        assert c.source == "og_image"
        assert c.selected is False
        assert c.is_logo is False
        assert c.quality_score is None

    def test_json_roundtrip(self):
        c = ImageCandidate(
            url="https://x/y.jpg",
            source="article_body",
            width=800,
            height=600,
            phash="a3f8d2c1b9e47f05",
            quality_score=7,
            relevance_score=8,
            description="people in a lecture hall",
            selected=True,
        )
        dumped = c.model_dump()
        restored = ImageCandidate.model_validate(dumped)
        assert restored == c

    def test_model_ignores_unknown_fields(self):
        """image_candidates JSON from older schema versions must not break loading."""
        restored = ImageCandidate.model_validate(
            {"url": "https://x/y.jpg", "source": "og_image", "legacy_junk_field": "ignore_me"}
        )
        assert restored.url == "https://x/y.jpg"

    def test_score_range_validation(self):
        with pytest.raises(ValidationError):
            ImageCandidate(url="u", source="s", quality_score=11)
        with pytest.raises(ValidationError):
            ImageCandidate(url="u", source="s", relevance_score=-1)


class TestVisionScore:
    def test_minimal(self):
        v = VisionScore(
            index=0,
            quality_score=7,
            relevance_score=8,
            is_logo=False,
            is_text_slide=False,
            description="photo of a building",
        )
        assert v.index == 0
        assert v.description == "photo of a building"

    def test_requires_all_fields(self):
        with pytest.raises(ValidationError):
            VisionScore(index=0)  # type: ignore[call-arg]


class TestCompositionDecision:
    def test_defaults(self):
        d = CompositionDecision(composition="none")
        assert d.selected_indices == []
        assert d.reason == ""

    def test_rejects_invalid_composition(self):
        with pytest.raises(ValidationError):
            CompositionDecision(composition="carousel")  # type: ignore[arg-type]

    def test_full(self):
        d = CompositionDecision(composition="album", selected_indices=[0, 2, 3], reason="coherent photos")
        assert d.composition == "album"
        assert d.selected_indices == [0, 2, 3]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run -m pytest tests/unit/test_image_pipeline_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.channel.image_pipeline'`.

- [ ] **Step 3: Create package + models**

Create `app/channel/image_pipeline/__init__.py` — empty file for now (the orchestrator lands in PR #2):

```python
"""Image pipeline package: filter → score → dedup → compose.

The orchestrator ``build_candidates`` and the composition helper
``pick_composition`` are added in PR #2.
"""
```

Create `app/channel/image_pipeline/models.py`:

```python
"""Pydantic models for the image pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ImageCandidate(BaseModel):
    """One scored image candidate — a row in the post's candidate pool.

    Persisted to ``ChannelPost.image_candidates`` as a list of dicts.
    Raw image ``bytes`` are *not* stored — they live in an in-memory cache
    during pipeline processing and are discarded afterwards.
    """

    url: str
    source: str  # "og_image" | "article_body" | "rss_enclosure" | "reviewer_added" | "brave_image"
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

    model_config = ConfigDict(extra="ignore")


class VisionScore(BaseModel):
    """Per-image score returned by the vision model (one per input image)."""

    index: int
    quality_score: int = Field(ge=0, le=10)
    relevance_score: int = Field(ge=0, le=10)
    is_logo: bool
    is_text_slide: bool
    description: str


class CompositionDecision(BaseModel):
    """Output of ``pick_composition`` — final shape of the post's images."""

    composition: Literal["single", "album", "none"]
    selected_indices: list[int] = Field(default_factory=list)
    reason: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run -m pytest tests/unit/test_image_pipeline_models.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/channel/image_pipeline/ tests/unit/test_image_pipeline_models.py
git commit -m "feat(channel): add image_pipeline package with Pydantic models"
```

---

### Task 6: Test fixture — `make_test_image`

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/images.py`
- Create: `tests/unit/test_fixture_images.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_fixture_images.py`:

```python
"""Sanity tests for the image fixture helper."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image
from tests.fixtures.images import make_test_image


def test_returns_valid_jpeg_bytes():
    data = make_test_image(width=800, height=600, format="JPEG")
    assert isinstance(data, bytes)
    assert len(data) > 1000
    img = Image.open(BytesIO(data))
    assert img.format == "JPEG"
    assert img.size == (800, 600)


def test_png_also_works():
    data = make_test_image(width=400, height=300, format="PNG")
    img = Image.open(BytesIO(data))
    assert img.format == "PNG"
    assert img.size == (400, 300)


def test_solid_fill_has_low_entropy():
    data = make_test_image(width=800, height=600, fill=(120, 120, 120), colors=None)
    img = Image.open(BytesIO(data))
    palette = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=1024)
    uniques = palette.getcolors(maxcolors=1024)
    assert uniques is not None
    # JPEG introduces slight variance even in solid fills — allow up to 10.
    assert len(uniques) <= 10


def test_random_noise_has_high_entropy():
    data = make_test_image(width=800, height=600, fill=(120, 120, 120), colors=200)
    img = Image.open(BytesIO(data))
    palette = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=1024)
    uniques = palette.getcolors(maxcolors=1024)
    assert uniques is not None
    assert len(uniques) > 50


def test_deterministic():
    a = make_test_image(width=500, height=400, colors=100)
    b = make_test_image(width=500, height=400, colors=100)
    assert a == b, "same inputs must produce byte-identical output"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run -m pytest tests/unit/test_fixture_images.py -v
```
Expected: `ModuleNotFoundError: No module named 'tests.fixtures'`.

- [ ] **Step 3: Implement the fixture**

`tests/fixtures/__init__.py`:
```python
"""Shared test fixtures (in-memory image builders, mock responses)."""
```

`tests/fixtures/images.py`:

```python
"""Deterministic in-memory image builder for tests.

Produces valid JPEG/PNG bytes without hitting disk or the network.
"""

from __future__ import annotations

import random
from io import BytesIO

from PIL import Image


def make_test_image(
    width: int = 800,
    height: int = 600,
    fill: tuple[int, int, int] = (100, 150, 200),
    colors: int | None = None,
    format: str = "JPEG",
    seed: int = 42,
) -> bytes:
    """Build deterministic image bytes for use in tests.

    Args:
        width, height: pixel dimensions.
        fill: base fill colour (RGB 0-255).
        colors: if set, paint ``colors * 100`` random pixels on top of the
                base fill. ``None`` = solid fill (very low entropy).
        format: ``"JPEG"`` or ``"PNG"``.
        seed: RNG seed — same seed ⇒ byte-identical output.
    """
    img = Image.new("RGB", (width, height), fill)
    if colors and colors > 1:
        rng = random.Random(seed)
        pixels = img.load()
        assert pixels is not None
        for _ in range(colors * 100):
            x = rng.randint(0, width - 1)
            y = rng.randint(0, height - 1)
            pixels[x, y] = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
    buf = BytesIO()
    save_kwargs: dict[str, int] = {}
    if format == "JPEG":
        save_kwargs["quality"] = 85
    img.save(buf, format=format, **save_kwargs)
    return buf.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run -m pytest tests/unit/test_fixture_images.py -v
```
Expected: all five tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/ tests/unit/test_fixture_images.py
git commit -m "test: add deterministic in-memory image fixture builder"
```

---

### Task 7: `cheap_filter` — heuristic image filter

**Files:**
- Create: `app/channel/image_pipeline/filter.py`
- Create: `tests/unit/test_image_pipeline_filter.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_image_pipeline_filter.py`:

```python
"""Unit tests for ``cheap_filter``."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.channel.image_pipeline.filter import FilteredImage, cheap_filter
from tests.fixtures.images import make_test_image

pytestmark = pytest.mark.asyncio


def _response(data: bytes, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=data, request=httpx.Request("GET", "https://x"))


class TestCheapFilter:
    async def test_happy_path_large_colorful(self):
        data = make_test_image(width=1200, height=800, colors=300)
        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(return_value=_response(data))):
            result = await cheap_filter(["https://x/ok.jpg"])
        assert len(result) == 1
        assert isinstance(result[0], FilteredImage)
        assert result[0].url == "https://x/ok.jpg"
        assert result[0].width == 1200
        assert result[0].height == 800
        assert result[0].bytes_ == data

    async def test_drops_small_image(self):
        data = make_test_image(width=400, height=300, colors=200)
        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(return_value=_response(data))):
            result = await cheap_filter(["https://x/small.jpg"])
        assert result == []

    async def test_drops_extreme_aspect_ratio(self):
        data = make_test_image(width=2400, height=300, colors=200)  # 8:1
        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(return_value=_response(data))):
            result = await cheap_filter(["https://x/banner.jpg"])
        assert result == []

    async def test_drops_solid_color_low_entropy(self):
        data = make_test_image(width=1000, height=800, fill=(40, 40, 40), colors=None)
        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(return_value=_response(data))):
            result = await cheap_filter(["https://x/logo.png"])
        assert result == []

    async def test_drops_oversize_bytes(self):
        """Anything over 20 MB → skipped without opening PIL."""
        huge = b"\x00" * (21 * 1024 * 1024)
        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(return_value=_response(huge))):
            result = await cheap_filter(["https://x/huge.bin"])
        assert result == []

    async def test_skips_download_failure_continues(self):
        """If one URL fails, others still processed."""
        good = make_test_image(width=900, height=700, colors=200)

        async def side_effect(url, **kwargs):
            if "bad" in url:
                raise httpx.ConnectError("boom")
            return _response(good)

        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=side_effect)):
            result = await cheap_filter(["https://x/bad.jpg", "https://x/ok.jpg"])
        assert len(result) == 1
        assert result[0].url == "https://x/ok.jpg"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run -m pytest tests/unit/test_image_pipeline_filter.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.channel.image_pipeline.filter'`.

- [ ] **Step 3: Implement `cheap_filter`**

`app/channel/image_pipeline/filter.py`:

```python
"""Stage 1 of the image pipeline: cheap heuristic filters.

Downloads each candidate URL (SSRF-safe), opens with Pillow, drops anything
that's obviously unusable (too small, weird aspect, low entropy, oversize
file-vs-area ratio). No paid APIs are called.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.channel.http import SSRFError, safe_fetch
from app.core.logging import get_logger

logger = get_logger("channel.image_pipeline.filter")

MAX_BYTES = 20 * 1024 * 1024  # 20 MB
MIN_WIDTH = 600
MIN_HEIGHT = 400
MAX_ASPECT_RATIO = 3.0
MIN_UNIQUE_COLORS = 30
MIN_FILE_SIZE_FOR_LARGE_IMAGES = 20_000
LARGE_IMAGE_AREA = 500_000
DOWNLOAD_TIMEOUT_SECONDS = 10


@dataclass(slots=True)
class FilteredImage:
    """An image that passed ``cheap_filter``. Carries bytes so downstream
    stages (vision_score, phash_dedup) don't re-download."""

    url: str
    width: int
    height: int
    bytes_: bytes


async def cheap_filter(urls: list[str]) -> list[FilteredImage]:
    """Download candidates in parallel and keep only those that pass the checks.

    Failures (network, SSRF, decode, threshold) silently drop that URL; other
    URLs are unaffected. Returns results in the same order as input, minus
    dropped items.
    """
    if not urls:
        return []

    tasks = [asyncio.create_task(_check_one(u)) for u in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    kept: list[FilteredImage] = []
    for url, r in zip(urls, results, strict=True):
        if isinstance(r, FilteredImage):
            kept.append(r)
        elif isinstance(r, Exception):
            logger.debug("image_filter_failed", url=url[:120], error=type(r).__name__)
    return kept


async def _check_one(url: str) -> FilteredImage | None:
    try:
        resp = await safe_fetch(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    except SSRFError:
        logger.debug("image_filter_ssrf_blocked", url=url[:120])
        return None
    except Exception as exc:
        logger.debug("image_filter_download_failed", url=url[:120], error=type(exc).__name__)
        return None

    data = resp.content
    if len(data) > MAX_BYTES:
        logger.debug("image_filter_oversize", url=url[:120], bytes=len(data))
        return None

    try:
        img = Image.open(BytesIO(data))
        img.verify()  # structural check
        img = Image.open(BytesIO(data))  # reopen after verify() consumes it
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        logger.debug("image_filter_decode_failed", url=url[:120])
        return None

    w, h = img.size
    if w < MIN_WIDTH or h < MIN_HEIGHT:
        logger.debug("image_filter_too_small", url=url[:120], w=w, h=h)
        return None

    if max(w, h) / min(w, h) > MAX_ASPECT_RATIO:
        logger.debug("image_filter_aspect", url=url[:120], w=w, h=h)
        return None

    palette = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=1024)
    uniques = palette.getcolors(maxcolors=1024)
    if uniques is None or len(uniques) < MIN_UNIQUE_COLORS:
        logger.debug("image_filter_low_entropy", url=url[:120], uniques=len(uniques or []))
        return None

    if w * h > LARGE_IMAGE_AREA and len(data) < MIN_FILE_SIZE_FOR_LARGE_IMAGES:
        logger.debug("image_filter_suspicious_size_ratio", url=url[:120], bytes=len(data), area=w * h)
        return None

    return FilteredImage(url=url, width=w, height=h, bytes_=data)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run -m pytest tests/unit/test_image_pipeline_filter.py -v
```
Expected: all six tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/channel/image_pipeline/filter.py tests/unit/test_image_pipeline_filter.py
git commit -m "feat(image_pipeline): cheap_filter with resolution/aspect/entropy heuristics"
```

---

### Task 8: `phash_dedup` — perceptual-hash deduplication

**Files:**
- Create: `app/channel/image_pipeline/dedup.py`
- Create: `tests/unit/test_image_pipeline_dedup.py`
- Create: `tests/integration/test_image_pipeline_dedup_pg.py`

- [ ] **Step 1: Write the unit tests**

`tests/unit/test_image_pipeline_dedup.py`:

```python
"""Unit tests for pHash-based image deduplication (no DB)."""

from __future__ import annotations

from io import BytesIO

import imagehash
import pytest
from app.channel.image_pipeline.dedup import (
    compute_phash,
    hamming_distance,
    phash_dedup_against,
)
from app.channel.image_pipeline.filter import FilteredImage
from PIL import Image
from tests.fixtures.images import make_test_image


def _make_filtered(bytes_: bytes) -> FilteredImage:
    img = Image.open(BytesIO(bytes_))
    w, h = img.size
    return FilteredImage(url=f"https://x/{h}x{w}.jpg", width=w, height=h, bytes_=bytes_)


class TestHamming:
    def test_zero_distance(self):
        assert hamming_distance("ffff", "ffff") == 0

    def test_single_bit_diff(self):
        # 0xF0 = 11110000, 0xF1 = 11110001 → 1 bit different
        assert hamming_distance("f0", "f1") == 1

    def test_different_length_raises(self):
        with pytest.raises(ValueError):
            hamming_distance("ff", "fff")


class TestComputePhash:
    def test_identical_bytes_same_hash(self):
        data = make_test_image(width=800, height=600, colors=100)
        h1 = compute_phash(data)
        h2 = compute_phash(data)
        assert h1 == h2
        assert len(h1) == 16  # 64 bits = 16 hex chars

    def test_different_images_different_hashes(self):
        a = make_test_image(width=800, height=600, colors=100, seed=1)
        b = make_test_image(width=800, height=600, colors=200, seed=2)
        assert compute_phash(a) != compute_phash(b)


class TestPhashDedupAgainst:
    def test_drops_identical_image(self):
        data = make_test_image(width=800, height=600, colors=100)
        img = _make_filtered(data)
        existing_hash = compute_phash(data)
        kept = phash_dedup_against([img], [existing_hash], threshold=10)
        assert kept == []
        assert img.phash == existing_hash  # mutated onto the candidate
        assert img.is_duplicate is True

    def test_passes_when_no_recent_hashes(self):
        data = make_test_image(width=800, height=600, colors=100)
        img = _make_filtered(data)
        kept = phash_dedup_against([img], [], threshold=10)
        assert len(kept) == 1
        assert kept[0].is_duplicate is False
        assert kept[0].phash is not None

    def test_passes_when_over_threshold(self):
        a = make_test_image(width=800, height=600, colors=50, seed=1)
        b = make_test_image(width=800, height=600, colors=250, seed=99)
        img = _make_filtered(b)
        kept = phash_dedup_against([img], [compute_phash(a)], threshold=3)  # strict
        # Very-different images → Hamming typically ≥ 20 → kept
        assert len(kept) == 1

    def test_mutates_phash_even_when_kept(self):
        data = make_test_image(width=800, height=600, colors=100)
        img = _make_filtered(data)
        kept = phash_dedup_against([img], [], threshold=10)
        assert kept[0].phash is not None
```

- [ ] **Step 2: Run unit tests to verify they fail**

```bash
uv run -m pytest tests/unit/test_image_pipeline_dedup.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.channel.image_pipeline.dedup'`.

- [ ] **Step 3: Write the integration tests (PG)**

`tests/integration/test_image_pipeline_dedup_pg.py`:

```python
"""Integration tests: pHash dedup queries against a real Postgres container."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.channel.image_pipeline.dedup import (
    compute_phash,
    phash_dedup,
    recent_phashes_for_channel,
)
from app.channel.image_pipeline.filter import FilteredImage
from app.core.enums import PostStatus
from app.core.time import utc_now
from app.db.models import ChannelPost
from tests.fixtures.images import make_test_image

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CHANNEL = -100555666


async def _insert_post(session_maker, *, phashes: list[str], age_days: int = 0, status: str = PostStatus.APPROVED) -> int:
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=_CHANNEL,
            external_id=f"e{age_days}_{phashes[0][:4]}",
            title="t",
            post_text="b",
            status=status,
        )
        post.image_phashes = phashes
        if age_days:
            post.created_at = utc_now() - timedelta(days=age_days)
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post.id


class TestRecentPhashesForChannel:
    async def test_returns_flat_list_sorted_newest_first(self, pg_session_maker):
        data_a = make_test_image(width=800, height=600, colors=50, seed=1)
        data_b = make_test_image(width=800, height=600, colors=50, seed=2)
        ha = compute_phash(data_a)
        hb = compute_phash(data_b)
        await _insert_post(pg_session_maker, phashes=[ha])
        await _insert_post(pg_session_maker, phashes=[hb])

        hashes = await recent_phashes_for_channel(pg_session_maker, _CHANNEL, lookback=30)
        assert set(hashes) == {ha, hb}

    async def test_skips_non_approved_posts(self, pg_session_maker):
        data = make_test_image(width=800, height=600, colors=50, seed=1)
        h = compute_phash(data)
        await _insert_post(pg_session_maker, phashes=[h], status=PostStatus.DRAFT)
        hashes = await recent_phashes_for_channel(pg_session_maker, _CHANNEL, lookback=30)
        assert hashes == []

    async def test_respects_lookback_limit(self, pg_session_maker):
        """Only the most recent N posts are included."""
        for i in range(5):
            data = make_test_image(width=800, height=600, colors=50, seed=i + 1)
            await _insert_post(pg_session_maker, phashes=[compute_phash(data)])

        hashes = await recent_phashes_for_channel(pg_session_maker, _CHANNEL, lookback=3)
        assert len(hashes) == 3  # takes the 3 newest posts


class TestPhashDedupPg:
    async def test_full_flow_filters_duplicate(self, pg_session_maker):
        data = make_test_image(width=800, height=600, colors=100, seed=7)
        h = compute_phash(data)
        await _insert_post(pg_session_maker, phashes=[h])

        img = FilteredImage(url="https://x/new.jpg", width=800, height=600, bytes_=data)
        kept = await phash_dedup(pg_session_maker, _CHANNEL, [img], threshold=10, lookback=30)
        assert kept == []

    async def test_full_flow_keeps_unique(self, pg_session_maker):
        stored = make_test_image(width=800, height=600, colors=50, seed=1)
        new = make_test_image(width=800, height=600, colors=250, seed=99)
        await _insert_post(pg_session_maker, phashes=[compute_phash(stored)])

        img = FilteredImage(url="https://x/new.jpg", width=800, height=600, bytes_=new)
        kept = await phash_dedup(pg_session_maker, _CHANNEL, [img], threshold=3, lookback=30)
        assert len(kept) == 1
        assert kept[0].phash is not None

    async def test_no_posts_keeps_everything(self, pg_session_maker):
        data = make_test_image(width=800, height=600, colors=100, seed=1)
        img = FilteredImage(url="https://x/new.jpg", width=800, height=600, bytes_=data)
        kept = await phash_dedup(pg_session_maker, _CHANNEL, [img], threshold=10, lookback=30)
        assert len(kept) == 1
```

- [ ] **Step 4: Implement dedup module**

`app/channel/image_pipeline/dedup.py`:

```python
"""Stage 3 of the image pipeline: pHash-based deduplication.

For each filtered candidate we compute a 64-bit perceptual hash, look up the
last N approved posts' stored hashes in the same channel, and drop candidates
whose Hamming distance to any recent hash is below the configured threshold.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import imagehash
from PIL import Image
from sqlalchemy import select

from app.channel.image_pipeline.filter import FilteredImage
from app.core.enums import PostStatus
from app.core.logging import get_logger
from app.db.models import ChannelPost

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger("channel.image_pipeline.dedup")

PHASH_HEX_LEN = 16  # 64-bit pHash = 16 hex chars


def compute_phash(image_bytes: bytes) -> str:
    """Return a 64-bit perceptual hash as a 16-char hex string.

    Raises whatever PIL / imagehash raise on bad input — callers handle it.
    """
    img = Image.open(BytesIO(image_bytes))
    h = imagehash.phash(img)  # 8×8 DCT = 64 bits by default
    return str(h)


def hamming_distance(a: str, b: str) -> int:
    """Hamming distance between two equal-length hex strings.

    Converts both to ints and xors, then popcount.
    """
    if len(a) != len(b):
        raise ValueError(f"hash length mismatch: {len(a)} vs {len(b)}")
    return (int(a, 16) ^ int(b, 16)).bit_count()


def phash_dedup_against(
    images: list[FilteredImage],
    recent_hashes: list[str],
    *,
    threshold: int,
) -> list[FilteredImage]:
    """Pure-function dedup: keep images whose pHash is > threshold from every
    recent hash. Mutates ``phash`` and ``is_duplicate`` on every input image
    (callers may want the annotation even on dropped items).
    """
    kept: list[FilteredImage] = []
    for img in images:
        try:
            img_hash = compute_phash(img.bytes_)
        except Exception:
            logger.warning("phash_compute_failed", url=img.url[:120], exc_info=True)
            # Cannot hash → cannot dedup. Best-effort: keep but mark no-hash.
            img.phash = None
            kept.append(img)
            continue

        img.phash = img_hash
        img.is_duplicate = any(hamming_distance(img_hash, h) <= threshold for h in recent_hashes)
        if img.is_duplicate:
            logger.info("phash_duplicate_dropped", url=img.url[:120], hash=img_hash)
            continue
        kept.append(img)
    return kept


async def recent_phashes_for_channel(
    session_maker: "async_sessionmaker[AsyncSession]",
    channel_id: int,
    *,
    lookback: int,
) -> list[str]:
    """Flatten ``image_phashes`` across the last ``lookback`` approved posts in
    this channel. Oldest posts first in the list does not matter — callers
    treat this as a set."""
    if lookback <= 0:
        return []
    async with session_maker() as session:
        stmt = (
            select(ChannelPost.image_phashes)
            .where(ChannelPost.channel_id == channel_id)
            .where(ChannelPost.status == PostStatus.APPROVED)
            .where(ChannelPost.image_phashes.isnot(None))
            .order_by(ChannelPost.created_at.desc())
            .limit(lookback)
        )
        rows = (await session.execute(stmt)).scalars().all()
    flat: list[str] = []
    for row in rows:
        if row:
            flat.extend(row)
    return flat


async def phash_dedup(
    session_maker: "async_sessionmaker[AsyncSession]",
    channel_id: int,
    images: list[FilteredImage],
    *,
    threshold: int,
    lookback: int,
) -> list[FilteredImage]:
    """End-to-end: fetch recent hashes from DB, then filter images against them."""
    if not images:
        return []
    try:
        recent = await recent_phashes_for_channel(session_maker, channel_id, lookback=lookback)
    except Exception:
        logger.warning("phash_lookup_failed_skipping_dedup", channel_id=channel_id, exc_info=True)
        # DB unavailable → best-effort: keep everything. compute_phash still runs
        # so downstream stores phash for future dedup.
        return phash_dedup_against(images, recent_hashes=[], threshold=threshold)

    return phash_dedup_against(images, recent_hashes=recent, threshold=threshold)
```

- [ ] **Step 5: Run all dedup tests to verify they pass**

```bash
uv run -m pytest tests/unit/test_image_pipeline_dedup.py tests/integration/test_image_pipeline_dedup_pg.py -v
```
Expected: all 11 tests pass (4 unit + 4 phash_dedup unit branches + 6 PG integration = actually 9 unit + 6 PG; let pytest count). On first run, pytest may take ~20 s for the PG container to boot — that's normal.

- [ ] **Step 6: Commit**

```bash
git add app/channel/image_pipeline/dedup.py tests/unit/test_image_pipeline_dedup.py tests/integration/test_image_pipeline_dedup_pg.py
git commit -m "feat(image_pipeline): phash_dedup against recent approved posts"
```

---

### PR #1 boundary — open pull request

- [ ] **Step 1: Push the branch**

```bash
git push -u origin design/image-quality-pipeline
```

- [ ] **Step 2: Open PR against `main`**

```bash
gh pr create --title "feat(image): Sprint 1 foundation — models, config, filter, pHash dedup" --body "$(cat <<'EOF'
## Summary
- New `app/channel/image_pipeline/` package with Pydantic models, `cheap_filter`, `phash_dedup`
- Two nullable JSON columns on `channel_posts`: `image_candidates`, `image_phashes`
- `ImagePipelineError` for best-effort failures
- `ChannelAgentSettings.vision_model`, `image_phash_lookback_posts`, `image_phash_threshold`
- `tests/fixtures/images.py` for deterministic in-memory JPEG/PNG

## Safety
Purely additive. Nothing in the running pipeline writes to the new columns yet. Migration is zero-downtime (both columns nullable).

## Test plan
- [ ] Unit: filter, dedup, models, fixtures, config, exceptions
- [ ] Integration PG: dedup query scoped by channel + lookback
- [ ] `alembic upgrade head` applies cleanly on a fresh pgvector container

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Wait for CI + merge once green**

```bash
gh pr checks --watch
gh pr merge --squash --admin --delete-branch
git checkout main && git pull
```

---

## PR #2 — Pipeline integration

Branch off `main` once PR #1 is merged. This PR introduces the three external-dependent stages (vision_score, pick_composition, orchestrator) and wires them into `generator.py` and `workflow.py`. Behaviour changes visibly — see the 24 h smoke requirement before PR #3.

- [ ] **PR #2 setup:** `git checkout main && git pull && git checkout -b feat/image-pipeline-integration`

---

### Task 9: `vision_score` — batched multimodal scoring

**Files:**
- Create: `app/channel/image_pipeline/score.py`
- Create: `tests/unit/test_image_pipeline_score.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_image_pipeline_score.py`:

```python
"""Unit tests for the batched vision-model scorer."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from app.channel.image_pipeline.filter import FilteredImage
from app.channel.image_pipeline.score import ScoredImage, vision_score
from tests.fixtures.images import make_test_image

pytestmark = pytest.mark.asyncio


def _img(url: str) -> FilteredImage:
    data = make_test_image(width=800, height=600, colors=100)
    return FilteredImage(url=url, width=800, height=600, bytes_=data)


def _good_response(n: int) -> str:
    items = [
        {
            "index": i,
            "quality_score": 8,
            "relevance_score": 7,
            "is_logo": False,
            "is_text_slide": False,
            "description": f"photo {i}",
        }
        for i in range(n)
    ]
    return json.dumps(items)


class TestVisionScore:
    async def test_happy_path_keeps_all_and_sorts(self):
        imgs = [_img(f"https://x/{i}.jpg") for i in range(3)]
        resp = json.dumps(
            [
                {"index": 0, "quality_score": 4, "relevance_score": 8, "is_logo": False, "is_text_slide": False, "description": "a"},
                {"index": 1, "quality_score": 9, "relevance_score": 8, "is_logo": False, "is_text_slide": False, "description": "b"},
                {"index": 2, "quality_score": 7, "relevance_score": 6, "is_logo": False, "is_text_slide": False, "description": "c"},
            ]
        )
        with patch("app.channel.image_pipeline.score.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            out = await vision_score(imgs, title="Test", api_key="k", model="m")
        # index 0 has quality_score=4 → dropped; remaining sorted by (q + r) desc
        assert [s.url for s in out] == ["https://x/1.jpg", "https://x/2.jpg"]
        assert all(isinstance(s, ScoredImage) for s in out)
        assert out[0].quality_score == 9
        assert out[0].description == "b"

    async def test_drops_is_logo_and_is_text_slide(self):
        imgs = [_img(f"https://x/{i}.jpg") for i in range(2)]
        resp = json.dumps(
            [
                {"index": 0, "quality_score": 9, "relevance_score": 9, "is_logo": True, "is_text_slide": False, "description": "logo"},
                {"index": 1, "quality_score": 8, "relevance_score": 7, "is_logo": False, "is_text_slide": True, "description": "slide"},
            ]
        )
        with patch("app.channel.image_pipeline.score.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            out = await vision_score(imgs, title="Test", api_key="k", model="m")
        assert out == []

    async def test_drops_low_relevance(self):
        imgs = [_img(f"https://x/{i}.jpg") for i in range(2)]
        resp = json.dumps(
            [
                {"index": 0, "quality_score": 9, "relevance_score": 2, "is_logo": False, "is_text_slide": False, "description": "irrelevant"},
                {"index": 1, "quality_score": 7, "relevance_score": 5, "is_logo": False, "is_text_slide": False, "description": "on-topic"},
            ]
        )
        with patch("app.channel.image_pipeline.score.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            out = await vision_score(imgs, title="Test", api_key="k", model="m")
        assert [s.url for s in out] == ["https://x/1.jpg"]

    async def test_api_failure_returns_unscored_copy(self):
        imgs = [_img(f"https://x/{i}.jpg") for i in range(2)]
        with patch(
            "app.channel.image_pipeline.score.openrouter_chat_completion",
            new=AsyncMock(side_effect=RuntimeError("api down")),
        ):
            out = await vision_score(imgs, title="Test", api_key="k", model="m")
        assert len(out) == 2
        assert all(s.quality_score is None for s in out)
        assert all(s.description == "" for s in out)

    async def test_malformed_json_returns_unscored(self):
        imgs = [_img("https://x/0.jpg")]
        with patch(
            "app.channel.image_pipeline.score.openrouter_chat_completion",
            new=AsyncMock(return_value="not json at all"),
        ):
            out = await vision_score(imgs, title="Test", api_key="k", model="m")
        assert len(out) == 1
        assert out[0].quality_score is None

    async def test_empty_input_short_circuits(self):
        with patch("app.channel.image_pipeline.score.openrouter_chat_completion", new=AsyncMock()) as m:
            out = await vision_score([], title="Test", api_key="k", model="m")
        assert out == []
        m.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run -m pytest tests/unit/test_image_pipeline_score.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.channel.image_pipeline.score'`.

- [ ] **Step 3: Implement `vision_score`**

`app/channel/image_pipeline/score.py`:

```python
"""Stage 2 of the image pipeline: vision-model quality/relevance scoring.

A single batched OpenRouter multimodal call (max 5 images) with a strict
JSON schema. Failures are swallowed — every candidate gets returned with
``quality_score=None`` so downstream stages can still proceed.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.channel.image_pipeline.filter import FilteredImage
from app.channel.image_pipeline.models import VisionScore
from app.channel.llm_client import openrouter_chat_completion
from app.core.logging import get_logger

logger = get_logger("channel.image_pipeline.score")

MIN_QUALITY = 5
MIN_RELEVANCE = 4
MAX_BATCH = 5

_SYSTEM_PROMPT = """\
You are an image quality reviewer for a Telegram news channel.
You will receive a post headline and up to 5 candidate images.

For EACH image return a JSON object:
{
  "index": int,
  "quality_score": 0-10,
  "relevance_score": 0-10,
  "is_logo": bool,
  "is_text_slide": bool,
  "description": string
}

Scoring rules:
- "quality_score" rates the photo itself: sharpness, composition, colour.
- "relevance_score" rates how well the image matches the headline topic.
- "is_logo" = true for company/brand marks, favicons, flat icons.
- "is_text_slide" = true if the image is mostly a text overlay, chart-with-text,
  or "breaking news" style banner. A real photo with some caption text is NOT
  a text slide.
- "description" is 4-8 words describing what is shown.

Return ONLY a JSON array of N objects, one per image, ordered by index 0..N-1.
No commentary, no markdown, no code fences.
"""


@dataclass(slots=True)
class ScoredImage:
    """A FilteredImage annotated with vision-model scores."""

    url: str
    width: int
    height: int
    bytes_: bytes
    quality_score: int | None = None
    relevance_score: int | None = None
    is_logo: bool = False
    is_text_slide: bool = False
    description: str = ""


async def vision_score(
    images: list[FilteredImage],
    *,
    title: str,
    api_key: str,
    model: str,
) -> list[ScoredImage]:
    """Rate up to MAX_BATCH candidates. Returns a filtered + sorted list.

    Failure modes all produce a ``ScoredImage`` per input with null scores;
    the downstream ``pick_composition`` has its own fallback.
    """
    if not images:
        return []

    batch = images[:MAX_BATCH]
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": f"Topic: {title}\n\nImages follow in order 0..{len(batch) - 1}."}
    ]
    for img in batch:
        b64 = base64.b64encode(img.bytes_).decode("ascii")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )

    try:
        raw = await openrouter_chat_completion(
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            operation="vision_score",
            temperature=0.0,
            timeout=20,
        )
    except Exception:
        logger.warning("vision_score_api_error", count=len(batch), exc_info=True)
        return [_unscored(img) for img in batch]

    if not raw:
        logger.warning("vision_score_empty_response", count=len(batch))
        return [_unscored(img) for img in batch]

    try:
        parsed = json.loads(raw if isinstance(raw, str) else json.dumps(raw))
        if not isinstance(parsed, list):
            raise TypeError(f"expected list, got {type(parsed).__name__}")
        scores: dict[int, VisionScore] = {}
        for item in parsed:
            vs = VisionScore.model_validate(item)
            scores[vs.index] = vs
    except (json.JSONDecodeError, ValidationError, TypeError):
        logger.warning("vision_score_parse_error", raw_snippet=str(raw)[:300], exc_info=True)
        return [_unscored(img) for img in batch]

    annotated: list[ScoredImage] = []
    for i, img in enumerate(batch):
        s = scores.get(i)
        if s is None:
            annotated.append(_unscored(img))
            continue
        annotated.append(
            ScoredImage(
                url=img.url,
                width=img.width,
                height=img.height,
                bytes_=img.bytes_,
                quality_score=s.quality_score,
                relevance_score=s.relevance_score,
                is_logo=s.is_logo,
                is_text_slide=s.is_text_slide,
                description=s.description,
            )
        )

    # Post-processing
    kept = [
        s
        for s in annotated
        if not s.is_logo
        and not s.is_text_slide
        and (s.quality_score or 0) >= MIN_QUALITY
        and (s.relevance_score or 0) >= MIN_RELEVANCE
    ]
    kept.sort(key=lambda s: (s.quality_score or 0) + (s.relevance_score or 0), reverse=True)
    return kept


def _unscored(img: FilteredImage) -> ScoredImage:
    return ScoredImage(
        url=img.url,
        width=img.width,
        height=img.height,
        bytes_=img.bytes_,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run -m pytest tests/unit/test_image_pipeline_score.py -v
```
Expected: all six tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/channel/image_pipeline/score.py tests/unit/test_image_pipeline_score.py
git commit -m "feat(image_pipeline): vision_score batched multimodal scoring"
```

---

### Task 10: `pick_composition` — LLM chooses single / album / none

**Files:**
- Create: `app/channel/image_pipeline/compose.py`
- Create: `tests/unit/test_image_pipeline_compose.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_image_pipeline_compose.py`:

```python
"""Unit tests for pick_composition + fallback."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from app.channel.image_pipeline.compose import (
    CompositionDecision,
    fallback_composition,
    pick_composition,
)
from app.channel.image_pipeline.score import ScoredImage

pytestmark = pytest.mark.asyncio


def _scored(url: str, q: int = 7, r: int = 7, description: str = "photo") -> ScoredImage:
    return ScoredImage(
        url=url,
        width=800,
        height=600,
        bytes_=b"\x00",
        quality_score=q,
        relevance_score=r,
        description=description,
    )


class TestPickComposition:
    async def test_returns_single(self):
        cands = [_scored("https://x/0.jpg")]
        resp = json.dumps({"composition": "single", "selected_indices": [0], "reason": "best fit"})
        with patch("app.channel.image_pipeline.compose.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            d = await pick_composition(post_text="Body.", candidates=cands, api_key="k", model="m")
        assert d.composition == "single"
        assert d.selected_indices == [0]

    async def test_returns_album(self):
        cands = [_scored(f"https://x/{i}.jpg") for i in range(3)]
        resp = json.dumps({"composition": "album", "selected_indices": [0, 1, 2], "reason": "coherent"})
        with patch("app.channel.image_pipeline.compose.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            d = await pick_composition(post_text="Body.", candidates=cands, api_key="k", model="m")
        assert d.composition == "album"
        assert d.selected_indices == [0, 1, 2]

    async def test_returns_none(self):
        cands = [_scored(f"https://x/{i}.jpg", q=3, r=3) for i in range(2)]
        resp = json.dumps({"composition": "none", "selected_indices": [], "reason": "all weak"})
        with patch("app.channel.image_pipeline.compose.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            d = await pick_composition(post_text="Body.", candidates=cands, api_key="k", model="m")
        assert d.composition == "none"
        assert d.selected_indices == []

    async def test_llm_failure_falls_back(self):
        cands = [_scored("https://x/0.jpg", q=8, r=8), _scored("https://x/1.jpg", q=6, r=6)]
        with patch(
            "app.channel.image_pipeline.compose.openrouter_chat_completion",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            d = await pick_composition(post_text="Body.", candidates=cands, api_key="k", model="m")
        assert d.composition == "single"
        assert d.selected_indices == [0]
        assert d.reason.startswith("fallback")

    async def test_no_candidates_returns_none(self):
        # No LLM call when candidate pool is empty.
        with patch("app.channel.image_pipeline.compose.openrouter_chat_completion", new=AsyncMock()) as m:
            d = await pick_composition(post_text="Body.", candidates=[], api_key="k", model="m")
        assert d.composition == "none"
        m.assert_not_called()

    async def test_clamps_indices_to_valid_range(self):
        cands = [_scored("https://x/0.jpg")]
        resp = json.dumps({"composition": "album", "selected_indices": [0, 7, 99], "reason": ""})
        with patch("app.channel.image_pipeline.compose.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            d = await pick_composition(post_text="Body.", candidates=cands, api_key="k", model="m")
        # Out-of-range indices dropped; still returns as album if ≥2 valid, else single.
        assert d.selected_indices == [0]
        assert d.composition in ("single", "none")


class TestFallbackComposition:
    def test_picks_highest_scored_non_logo(self):
        cands = [
            _scored("https://x/0.jpg", q=5, r=5),
            _scored("https://x/1.jpg", q=9, r=8),
        ]
        # Sorted by vision_score already → [0]=bad, [1]=good. Fallback takes index 0 by convention.
        d = fallback_composition(cands)
        assert d.composition == "single"
        assert d.selected_indices == [0]

    def test_none_when_all_low_quality(self):
        cands = [_scored("https://x/0.jpg", q=3, r=5)]
        d = fallback_composition(cands)
        assert d.composition == "none"
        assert d.selected_indices == []

    def test_empty_input(self):
        d = fallback_composition([])
        assert d.composition == "none"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run -m pytest tests/unit/test_image_pipeline_compose.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.channel.image_pipeline.compose'`.

- [ ] **Step 3: Implement `pick_composition`**

`app/channel/image_pipeline/compose.py`:

```python
"""Stage 4 of the image pipeline: LLM composition decision.

Given the generated post text and up to 5 scored candidates (metadata only,
not images), asks the model to pick ``single`` / ``album`` / ``none`` and the
indices to use. Falls back to a deterministic heuristic on any failure.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.channel.image_pipeline.models import CompositionDecision
from app.channel.image_pipeline.score import ScoredImage
from app.channel.llm_client import openrouter_chat_completion
from app.core.logging import get_logger

logger = get_logger("channel.image_pipeline.compose")

MAX_ALBUM_SIZE = 4
FALLBACK_MIN_QUALITY = 6

_SYSTEM_PROMPT = """\
You are a visual editor for a Telegram news channel. Given a post and up to
5 candidate images with metadata, decide the final composition.

Return EXACTLY one JSON object:
{
  "composition": "single" | "album" | "none",
  "selected_indices": [int, ...],
  "reason": string
}

Rules:
- "none": no candidate is good enough, or all are off-topic/low-quality.
- "single": one strong image carrying the post's main visual.
- "album": 2-4 images that together tell the story AND share a coherent
  style. Do NOT mix a screenshot with a photograph, or unrelated scenes.
- Max 4 images in an album. Fewer is better — don't pad.
- When unsure, prefer "single" over weak "album", and "none" over bad "single".

No commentary, no markdown, no code fences.
"""


async def pick_composition(
    *,
    post_text: str,
    candidates: list[ScoredImage],
    api_key: str,
    model: str,
) -> CompositionDecision:
    """LLM picks the final composition; falls back to a heuristic on failure."""
    if not candidates:
        return CompositionDecision(composition="none", selected_indices=[], reason="no candidates")

    user_body = _build_user_payload(post_text, candidates)

    try:
        raw = await openrouter_chat_completion(
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_body},
            ],
            operation="pick_composition",
            temperature=0.1,
            timeout=15,
        )
    except Exception:
        logger.warning("pick_composition_api_error", exc_info=True)
        return fallback_composition(candidates)

    if not raw:
        logger.warning("pick_composition_empty_response")
        return fallback_composition(candidates)

    try:
        parsed = json.loads(raw if isinstance(raw, str) else json.dumps(raw))
        decision = CompositionDecision.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError):
        logger.warning("pick_composition_parse_error", raw_snippet=str(raw)[:300], exc_info=True)
        return fallback_composition(candidates)

    # Clamp indices + enforce consistency between composition and count
    n = len(candidates)
    valid_indices = [i for i in decision.selected_indices if 0 <= i < n]
    if len(valid_indices) > MAX_ALBUM_SIZE:
        valid_indices = valid_indices[:MAX_ALBUM_SIZE]

    if not valid_indices:
        return CompositionDecision(composition="none", selected_indices=[], reason=decision.reason or "no valid indices")
    if len(valid_indices) == 1:
        return CompositionDecision(composition="single", selected_indices=valid_indices, reason=decision.reason)
    return CompositionDecision(composition="album", selected_indices=valid_indices, reason=decision.reason)


def fallback_composition(candidates: list[ScoredImage]) -> CompositionDecision:
    """Deterministic fallback: highest-quality non-junk candidate as a single."""
    good = [c for c in candidates if (c.quality_score or 0) >= FALLBACK_MIN_QUALITY and not c.is_logo and not c.is_text_slide]
    if not good:
        return CompositionDecision(
            composition="none", selected_indices=[], reason="fallback: no high-quality candidates"
        )
    # Pool is already sorted by score in vision_score, so index 0 is the best.
    best_idx = candidates.index(good[0])
    return CompositionDecision(
        composition="single",
        selected_indices=[best_idx],
        reason="fallback: used highest-scored candidate",
    )


def _build_user_payload(post_text: str, candidates: list[ScoredImage]) -> str:
    lines = [f"Post text:\n---\n{post_text}\n---", "", "Candidates:"]
    for i, c in enumerate(candidates):
        lines.append(
            f"  {i}: quality={c.quality_score} relevance={c.relevance_score} "
            f"— {c.description}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run -m pytest tests/unit/test_image_pipeline_compose.py -v
```
Expected: all nine tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/channel/image_pipeline/compose.py tests/unit/test_image_pipeline_compose.py
git commit -m "feat(image_pipeline): pick_composition with deterministic fallback"
```

---

### Task 11: `build_candidates` — orchestrator

**Files:**
- Modify: `app/channel/image_pipeline/__init__.py`
- Create: `tests/integration/test_image_pipeline_build_pg.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_image_pipeline_build_pg.py`:

```python
"""Integration test: build_candidates end-to-end against real Postgres."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.channel.image_pipeline import build_candidates
from app.channel.image_pipeline.models import ImageCandidate
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from tests.fixtures.images import make_test_image

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CHANNEL = -100888999


def _resp(data: bytes) -> httpx.Response:
    return httpx.Response(200, content=data, request=httpx.Request("GET", "https://x"))


def _good_vision_batch(n: int) -> str:
    import json
    return json.dumps(
        [
            {
                "index": i,
                "quality_score": 8,
                "relevance_score": 7,
                "is_logo": False,
                "is_text_slide": False,
                "description": f"photo {i}",
            }
            for i in range(n)
        ]
    )


class TestBuildCandidates:
    async def test_happy_flow(self, pg_session_maker):
        """Two URLs → both pass filter → both scored → no duplicates → pool of 2."""
        data_a = make_test_image(width=900, height=700, colors=200, seed=1)
        data_b = make_test_image(width=900, height=700, colors=200, seed=2)

        async def fake_fetch(url, **kwargs):
            return _resp(data_a if "a" in url else data_b)

        with (
            patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=fake_fetch)),
            patch(
                "app.channel.image_pipeline.score.openrouter_chat_completion",
                new=AsyncMock(return_value=_good_vision_batch(2)),
            ),
        ):
            out = await build_candidates(
                urls=["https://x/a.jpg", "https://x/b.jpg"],
                title="Students in Prague",
                channel_id=_CHANNEL,
                session_maker=pg_session_maker,
                api_key="k",
                vision_model="m",
                phash_threshold=10,
                phash_lookback=30,
            )
        assert len(out) == 2
        assert all(isinstance(c, ImageCandidate) for c in out)
        assert all(c.quality_score == 8 for c in out)
        assert all(c.phash is not None for c in out)

    async def test_existing_phash_drops_duplicate(self, pg_session_maker):
        """Insert a prior post with phash of image A; when A comes in again it's dedup'd."""
        from app.channel.image_pipeline.dedup import compute_phash

        data_a = make_test_image(width=900, height=700, colors=200, seed=1)
        data_b = make_test_image(width=900, height=700, colors=200, seed=2)
        async with pg_session_maker() as session:
            prior = ChannelPost(
                channel_id=_CHANNEL,
                external_id="prior",
                title="t",
                post_text="b",
                status=PostStatus.APPROVED,
            )
            prior.image_phashes = [compute_phash(data_a)]
            session.add(prior)
            await session.commit()

        async def fake_fetch(url, **kwargs):
            return _resp(data_a if "a" in url else data_b)

        with (
            patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=fake_fetch)),
            patch(
                "app.channel.image_pipeline.score.openrouter_chat_completion",
                new=AsyncMock(return_value=_good_vision_batch(2)),
            ),
        ):
            out = await build_candidates(
                urls=["https://x/a.jpg", "https://x/b.jpg"],
                title="Students",
                channel_id=_CHANNEL,
                session_maker=pg_session_maker,
                api_key="k",
                vision_model="m",
                phash_threshold=10,
                phash_lookback=30,
            )
        assert len(out) == 1
        assert out[0].url == "https://x/b.jpg"

    async def test_vision_failure_still_returns_candidates(self, pg_session_maker):
        """Vision API dead → candidates come back without scores (for fallback composition)."""
        data = make_test_image(width=900, height=700, colors=200, seed=1)

        async def fake_fetch(url, **kwargs):
            return _resp(data)

        with (
            patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=fake_fetch)),
            patch(
                "app.channel.image_pipeline.score.openrouter_chat_completion",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            out = await build_candidates(
                urls=["https://x/a.jpg"],
                title="T",
                channel_id=_CHANNEL,
                session_maker=pg_session_maker,
                api_key="k",
                vision_model="m",
                phash_threshold=10,
                phash_lookback=30,
            )
        # Vision failed → candidates come back with null quality_score, but cheap_filter + phash still ran
        assert len(out) == 1
        assert out[0].quality_score is None
        assert out[0].phash is not None

    async def test_empty_urls_short_circuits(self, pg_session_maker):
        out = await build_candidates(
            urls=[],
            title="T",
            channel_id=_CHANNEL,
            session_maker=pg_session_maker,
            api_key="k",
            vision_model="m",
            phash_threshold=10,
            phash_lookback=30,
        )
        assert out == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run -m pytest tests/integration/test_image_pipeline_build_pg.py -v
```
Expected: `ImportError: cannot import name 'build_candidates' from 'app.channel.image_pipeline'`.

- [ ] **Step 3: Implement `build_candidates` in `__init__.py`**

Replace `app/channel/image_pipeline/__init__.py` with:

```python
"""Image pipeline package: filter → score → dedup → (compose externally).

Top-level orchestrator ``build_candidates`` runs the four-stage pipeline and
returns a list of ``ImageCandidate`` ready to be passed to ``pick_composition``
and persisted on ``ChannelPost.image_candidates``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.channel.image_pipeline.compose import CompositionDecision, fallback_composition, pick_composition
from app.channel.image_pipeline.dedup import phash_dedup
from app.channel.image_pipeline.filter import cheap_filter
from app.channel.image_pipeline.models import (
    CompositionDecision as CompositionDecisionModel,
    ImageCandidate,
    VisionScore,
)
from app.channel.image_pipeline.score import ScoredImage, vision_score
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger("channel.image_pipeline")

__all__ = [
    "CompositionDecision",
    "ImageCandidate",
    "ScoredImage",
    "VisionScore",
    "build_candidates",
    "fallback_composition",
    "pick_composition",
]


async def build_candidates(
    *,
    urls: list[str],
    title: str,
    channel_id: int,
    session_maker: "async_sessionmaker[AsyncSession]",
    api_key: str,
    vision_model: str,
    phash_threshold: int,
    phash_lookback: int,
    source_map: dict[str, str] | None = None,
) -> list[ImageCandidate]:
    """Run filter → score → dedup and return a list of Pydantic ImageCandidates.

    The returned list is the post's candidate pool: all inputs that survived
    filter + dedup, with scores attached where the vision model succeeded.
    Caller is responsible for ``pick_composition`` + persistence.

    ``source_map`` maps URL → source label ("og_image", "article_body",
    "rss_enclosure", ...). Missing URLs default to ``"article_body"``.
    """
    if not urls:
        return []

    source_map = source_map or {}

    # Stage 1: cheap filter (download + Pillow heuristics)
    filtered = await cheap_filter(urls)
    if not filtered:
        logger.info("image_pipeline_no_candidates_after_filter", channel_id=channel_id, input=len(urls))
        return []

    # Stage 2: vision scoring (batched multimodal call)
    scored = await vision_score(filtered, title=title, api_key=api_key, model=vision_model)

    # Stage 2b: any cheap_filter-passed candidates that vision_score dropped
    # come back as ScoredImage with null scores via _unscored, so the list
    # length is preserved. However vision_score applies post-filtering (is_logo
    # etc.) which can shrink the list. We want *all* filtered images here even
    # when vision marked them low-quality — so the reviewer can still see them
    # in the pool. So merge: if vision dropped an image, keep a null-scored
    # version.
    kept_urls = {s.url for s in scored}
    for img in filtered:
        if img.url not in kept_urls:
            scored.append(
                ScoredImage(url=img.url, width=img.width, height=img.height, bytes_=img.bytes_)
            )

    # Stage 3: phash dedup (DB query for recent hashes + Hamming compare)
    # The dedup module works on FilteredImage; we pass ScoredImage (same shape).
    # It mutates .phash and .is_duplicate and returns only non-duplicates.
    from app.channel.image_pipeline.filter import FilteredImage

    filtered_for_dedup = [FilteredImage(url=s.url, width=s.width, height=s.height, bytes_=s.bytes_) for s in scored]
    unique = await phash_dedup(
        session_maker,
        channel_id,
        filtered_for_dedup,
        threshold=phash_threshold,
        lookback=phash_lookback,
    )
    unique_urls = {u.url: u for u in unique}

    # Stitch scores back onto deduped candidates
    pool: list[ImageCandidate] = []
    for s in scored:
        f = unique_urls.get(s.url)
        if f is None:
            continue  # was a duplicate
        pool.append(
            ImageCandidate(
                url=s.url,
                source=source_map.get(s.url, "article_body"),
                width=s.width,
                height=s.height,
                phash=f.phash,
                quality_score=s.quality_score,
                relevance_score=s.relevance_score,
                is_logo=s.is_logo,
                is_text_slide=s.is_text_slide,
                is_duplicate=False,
                description=s.description,
                selected=False,
            )
        )

    logger.info(
        "image_pipeline_pool_built",
        channel_id=channel_id,
        input=len(urls),
        post_filter=len(filtered),
        post_dedup=len(pool),
    )
    return pool
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run -m pytest tests/integration/test_image_pipeline_build_pg.py -v
```
Expected: all four tests pass.

- [ ] **Step 5: Run ALL image_pipeline tests to catch regressions**

```bash
uv run -m pytest tests/unit/test_image_pipeline_*.py tests/integration/test_image_pipeline_*_pg.py -v
```
Expected: ~30 tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/channel/image_pipeline/__init__.py tests/integration/test_image_pipeline_build_pg.py
git commit -m "feat(image_pipeline): build_candidates orchestrator (filter→score→dedup)"
```

---

### Task 12: Integrate into `generator.py`

**Files:**
- Modify: `app/channel/generator.py:312-404` (`generate_post` function)
- Modify: `tests/unit/test_channel_agent.py` (existing tests exercising image URL logic)

- [ ] **Step 1: Inspect existing image-integration tests**

```bash
uv run -m pytest tests/unit/test_channel_agent.py -v -k image
```
Note which tests pass today. They patch `app.channel.images.find_images_for_post`. After this task they'll patch `app.channel.image_pipeline.build_candidates` + `pick_composition`.

- [ ] **Step 2: Write the failing test for new wiring**

Create `tests/unit/test_generator_image_pipeline.py`:

```python
"""Unit tests: generator.generate_post wires into the new image_pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.channel.generator import generate_post
from app.channel.image_pipeline.models import CompositionDecision, ImageCandidate
from app.channel.sources import ContentItem

pytestmark = pytest.mark.asyncio


def _item() -> ContentItem:
    return ContentItem(source_url="https://src/a", external_id="x1", title="Students", body="Body.")


async def _fake_generate_agent_run():
    """Stub Agent.run returning a minimal GeneratedPost."""
    from app.channel.generator import GeneratedPost

    class _Result:
        def __init__(self):
            self.output = GeneratedPost(text="Body text.\n\n——\n🔗 **Konnekt**", is_sensitive=False, image_urls=[])

        def all_messages(self):
            return []

    return _Result()


@patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None)
@patch("app.channel.generator._create_generation_agent")
async def test_generator_persists_candidates_and_selected_urls(mock_agent_factory, _mock_usage, session_maker):
    """Generator populates image_urls AND image_candidates from the new pipeline."""
    agent = AsyncMock()
    agent.run = AsyncMock(side_effect=lambda *a, **kw: _fake_generate_agent_run())
    mock_agent_factory.return_value = agent

    pool = [
        ImageCandidate(
            url="https://x/a.jpg", source="og_image", quality_score=8, relevance_score=7,
            description="a", phash="aaaa", width=800, height=600, selected=False,
        ),
        ImageCandidate(
            url="https://x/b.jpg", source="article_body", quality_score=6, relevance_score=6,
            description="b", phash="bbbb", width=800, height=600, selected=False,
        ),
    ]
    decision = CompositionDecision(composition="single", selected_indices=[0], reason="best")

    with (
        patch("app.channel.generator.build_candidates", new=AsyncMock(return_value=pool)),
        patch("app.channel.generator.pick_composition", new=AsyncMock(return_value=decision)),
    ):
        post = await generate_post(
            [_item()],
            api_key="k",
            model="m",
            language="Russian",
            channel_id=-100,
            session_maker=session_maker,
        )

    assert post is not None
    assert post.image_urls == ["https://x/a.jpg"]
    assert post.image_url == "https://x/a.jpg"
    assert post.image_candidates is not None
    assert len(post.image_candidates) == 2
    assert post.image_candidates[0]["selected"] is True
    assert post.image_candidates[1]["selected"] is False
    assert post.image_phashes == ["aaaa"]


@patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None)
@patch("app.channel.generator._create_generation_agent")
async def test_generator_with_none_composition(mock_agent_factory, _mock_usage, session_maker):
    """composition='none' → image_urls=[], image_candidates still populated (pool kept)."""
    agent = AsyncMock()
    agent.run = AsyncMock(side_effect=lambda *a, **kw: _fake_generate_agent_run())
    mock_agent_factory.return_value = agent

    pool = [ImageCandidate(url="https://x/a.jpg", source="og_image", quality_score=3)]
    decision = CompositionDecision(composition="none", selected_indices=[], reason="all weak")

    with (
        patch("app.channel.generator.build_candidates", new=AsyncMock(return_value=pool)),
        patch("app.channel.generator.pick_composition", new=AsyncMock(return_value=decision)),
    ):
        post = await generate_post(
            [_item()],
            api_key="k",
            model="m",
            language="Russian",
            channel_id=-100,
            session_maker=session_maker,
        )
    assert post is not None
    assert post.image_urls == []
    assert post.image_url is None
    assert post.image_candidates is not None
    assert len(post.image_candidates) == 1
    assert post.image_phashes == []


@patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None)
@patch("app.channel.generator._create_generation_agent")
async def test_generator_handles_pipeline_failure(mock_agent_factory, _mock_usage, session_maker):
    """Any exception from build_candidates → post still generated, no images."""
    agent = AsyncMock()
    agent.run = AsyncMock(side_effect=lambda *a, **kw: _fake_generate_agent_run())
    mock_agent_factory.return_value = agent

    with patch("app.channel.generator.build_candidates", new=AsyncMock(side_effect=RuntimeError("boom"))):
        post = await generate_post(
            [_item()],
            api_key="k",
            model="m",
            language="Russian",
            channel_id=-100,
            session_maker=session_maker,
        )
    assert post is not None
    assert post.image_urls == []
    assert post.image_candidates is None
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run -m pytest tests/unit/test_generator_image_pipeline.py -v
```
Expected: fails with missing params / import (`channel_id`, `session_maker` new kwargs; `build_candidates` / `pick_composition` not imported in `generator.py`).

- [ ] **Step 4: Modify `generator.py`**

Open `app/channel/generator.py`. Add to the `GeneratedPost` model right after `image_urls`:

```python
class GeneratedPost(BaseModel):
    """Output from the post generation agent."""

    text: str = Field(description="The post text in Markdown format")
    is_sensitive: bool = Field(default=False, description="Whether the post needs admin review")
    image_url: str | None = Field(default=None, description="Primary image URL (backward compat)")
    image_urls: list[str] = Field(default_factory=list, description="All image URLs for the post")
    image_candidates: list[dict[str, Any]] | None = Field(
        default=None, description="Full candidate pool with scores and metadata (for review agent)"
    )
    image_phashes: list[str] = Field(
        default_factory=list, description="pHashes of selected images (for future cross-post dedup)"
    )
```

Also add the `Any` import at the top:
```python
from typing import TYPE_CHECKING, Any
```

Update the `generate_post` signature to accept the new kwargs:

```python
async def generate_post(
    items: list[ContentItem],
    api_key: str,
    model: str,
    language: str = "Russian",
    feedback_context: str | None = None,
    footer: str = "",
    *,
    channel_name: str = "",
    channel_context: str = "",
    channel_id: int | None = None,
    session_maker: "async_sessionmaker[AsyncSession] | None" = None,
    vision_model: str = "",
    phash_threshold: int = 10,
    phash_lookback: int = 30,
) -> GeneratedPost | None:
```

At the top of the file add the import guard:
```python
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.channel.sources import ContentItem
```

Replace the existing `# Resolve images: ...` block at the end of `generate_post` (the block that calls `find_images_for_post`) with:

```python
        # Resolve images: new pipeline — filter, score, dedup, compose.
        # Best-effort: failure leaves post.image_urls = [].
        try:
            from app.channel.image_pipeline import build_candidates, pick_composition
            from app.channel.images import extract_rss_media_url, find_images_for_post

            # 1. Collect candidate URLs (existing extractor)
            source_urls = [item.url] if item.url else []
            article_urls = await find_images_for_post(
                keywords=item.title,
                source_urls=source_urls,
            )
            rss_url = None
            raw_entry = getattr(item, "raw_entry", None)
            if raw_entry is not None:
                rss_url = extract_rss_media_url(raw_entry)

            seen: set[str] = set()
            urls: list[str] = []
            source_map: dict[str, str] = {}
            if rss_url and rss_url not in seen:
                seen.add(rss_url)
                urls.append(rss_url)
                source_map[rss_url] = "rss_enclosure"
            for u in article_urls:
                if u in seen:
                    continue
                seen.add(u)
                urls.append(u)
                source_map[u] = "og_image" if u == article_urls[0] else "article_body"

            # 2. Run the pipeline (requires channel_id + session_maker)
            if channel_id is None or session_maker is None:
                # Legacy callers that don't supply these kwargs still work — skip pipeline.
                post.image_urls = urls[:3]
                post.image_url = urls[0] if urls else None
                post.image_candidates = None
                post.image_phashes = []
            else:
                pool = await build_candidates(
                    urls=urls,
                    title=item.title,
                    channel_id=channel_id,
                    session_maker=session_maker,
                    api_key=api_key,
                    vision_model=vision_model or "google/gemini-2.5-flash",
                    phash_threshold=phash_threshold,
                    phash_lookback=phash_lookback,
                    source_map=source_map,
                )
                decision = await pick_composition(
                    post_text=post.text,
                    candidates=[_pool_to_scored(c) for c in pool],
                    api_key=api_key,
                    model=vision_model or "google/gemini-2.5-flash",
                )
                # Mark selected candidates and build final lists
                for idx in decision.selected_indices:
                    pool[idx].selected = True
                post.image_urls = [pool[i].url for i in decision.selected_indices]
                post.image_url = post.image_urls[0] if post.image_urls else None
                post.image_candidates = [c.model_dump() for c in pool]
                post.image_phashes = [pool[i].phash for i in decision.selected_indices if pool[i].phash]
        except Exception:
            logger.warning("image_pipeline_failed", title=item.title[:60], exc_info=True)
            post.image_urls = []
            post.image_url = None
            post.image_candidates = None
            post.image_phashes = []
```

Add this helper near the bottom of `generator.py`:

```python
def _pool_to_scored(c: "ImageCandidate") -> "ScoredImage":
    """Re-wrap an ImageCandidate as a ScoredImage for pick_composition.
    We don't preserve bytes at this point — compose is text-only."""
    from app.channel.image_pipeline import ScoredImage

    return ScoredImage(
        url=c.url,
        width=c.width or 0,
        height=c.height or 0,
        bytes_=b"",
        quality_score=c.quality_score,
        relevance_score=c.relevance_score,
        is_logo=c.is_logo,
        is_text_slide=c.is_text_slide,
        description=c.description,
    )
```

Import at top:
```python
from app.channel.image_pipeline import ImageCandidate
from app.channel.image_pipeline.score import ScoredImage
```
(Put these under the existing imports; keep `TYPE_CHECKING`-guarded wherever possible.)

Update callers of `generate_post`:
- In `app/channel/workflow.py::generate_post` action (around line 348), pass the new kwargs:
  ```python
  post = await _generate(
      relevant[:1],
      api_key=api_key,
      model=config.generation_model,
      language=language,
      feedback_context=feedback_context,
      footer=footer,
      channel_name=channel.name,
      channel_context=channel_context,
      channel_id=channel_id,
      session_maker=session_maker,
      vision_model=config.vision_model,
      phash_threshold=config.image_phash_threshold,
      phash_lookback=config.image_phash_lookback_posts,
  )
  ```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run -m pytest tests/unit/test_generator_image_pipeline.py tests/unit/test_channel_agent.py -v
```
Expected: new tests pass. Existing `test_channel_agent.py` tests that patch `find_images_for_post` may fail — update those tests to patch `build_candidates` + `pick_composition` the same way as the new test file. Any test whose purpose is to exercise the old extractor directly should be rewritten or deleted.

- [ ] **Step 6: Commit**

```bash
git add app/channel/generator.py app/channel/workflow.py tests/unit/test_generator_image_pipeline.py tests/unit/test_channel_agent.py
git commit -m "feat(generator): wire image_pipeline + pick_composition into post generation"
```

---

### Task 13: Persist `image_candidates` + `image_phashes` through workflow

**Files:**
- Modify: `app/channel/review/service.py` (post-creation path)
- Modify: `app/channel/workflow.py:429-460` (direct-publish ChannelPost insert)

- [ ] **Step 1: Find the two ChannelPost construction sites**

```bash
uv run grep -n "ChannelPost(" app/channel/review/service.py app/channel/workflow.py
```

Expected: two matches — the review path in `service.py::_create_post_record` (search for `ChannelPost(` in that file), and the direct-publish path in `workflow.py::send_for_review` (around line 449).

- [ ] **Step 2: Write a regression test**

Append to `tests/unit/test_generator_image_pipeline.py`:

```python
@patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None)
@patch("app.channel.generator._create_generation_agent")
async def test_channel_post_persists_candidates_via_review_service(
    mock_agent_factory, _mock_usage, session_maker
):
    """review.service creates ChannelPost with image_candidates from GeneratedPost."""
    from app.channel.generator import GeneratedPost
    from app.channel.review.service import _create_post_record
    from app.db.models import ChannelPost
    from sqlalchemy import select

    post = GeneratedPost(
        text="Body.",
        image_urls=["https://x/a.jpg"],
        image_candidates=[{"url": "https://x/a.jpg", "source": "og_image", "selected": True}],
        image_phashes=["aaaa"],
    )

    async with session_maker() as session:
        channel_post_id = await _create_post_record(
            session=session,
            channel_id=-100,
            post=post,
            title="T",
            external_id="e1",
            source_url=None,
            source_items=None,
        )
        await session.commit()

        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == channel_post_id))).scalar_one()
        assert row.image_candidates == [{"url": "https://x/a.jpg", "source": "og_image", "selected": True}]
        assert row.image_phashes == ["aaaa"]
```

Note: if `_create_post_record` does not exist with that signature, adapt the call to whatever helper `review/service.py` exposes for building the `ChannelPost` record — open the file to find the function name.

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run -m pytest tests/unit/test_generator_image_pipeline.py::test_channel_post_persists_candidates_via_review_service -v
```
Expected: the DB row's `image_candidates` is `None` (because the existing code doesn't write the field).

- [ ] **Step 4: Thread the fields through review service**

In `app/channel/review/service.py`, locate the `ChannelPost(` construction inside the review-creation path (call sites you found in Step 1). Set the new fields after construction (since they're not `__init__` parameters):

```python
channel_post = ChannelPost(
    channel_id=channel_id,
    external_id=external_id,
    ...
    image_urls=post.image_urls or None,
    ...
)
channel_post.image_candidates = post.image_candidates
channel_post.image_phashes = post.image_phashes or None
```

Do the same in the direct-publish path in `app/channel/workflow.py` (around line 449):

```python
db_post = ChannelPost(
    channel_id=channel_id,
    external_id=f"direct:{ext_id}",
    title=relevant[0].title[:REVIEW_TITLE_MAX_CHARS] if relevant else "Direct publish",
    post_text=post.text,
    image_url=post.image_url,
    image_urls=post.image_urls or None,
    status=PostStatus.APPROVED,
    telegram_message_id=msg_id,
)
db_post.image_candidates = post.image_candidates
db_post.image_phashes = post.image_phashes or None
```

- [ ] **Step 5: Run the persistence test + all generator tests**

```bash
uv run -m pytest tests/unit/test_generator_image_pipeline.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/channel/review/service.py app/channel/workflow.py tests/unit/test_generator_image_pipeline.py
git commit -m "feat(channel): persist image_candidates and image_phashes via review + direct-publish paths"
```

---

### Task 14: Full-flow integration test

**Files:**
- Create: `tests/integration/test_image_pipeline_full_flow_pg.py`

- [ ] **Step 1: Write the test**

`tests/integration/test_image_pipeline_full_flow_pg.py`:

```python
"""Integration test: generator → pipeline → DB persist round-trip (PG)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.channel.generator import GeneratedPost, generate_post
from app.channel.sources import ContentItem
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select
from tests.fixtures.images import make_test_image

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _resp(data: bytes) -> httpx.Response:
    return httpx.Response(200, content=data, request=httpx.Request("GET", "https://x"))


def _good_vision(n: int) -> str:
    return json.dumps(
        [
            {"index": i, "quality_score": 8, "relevance_score": 8, "is_logo": False, "is_text_slide": False, "description": f"p{i}"}
            for i in range(n)
        ]
    )


def _compose_single() -> str:
    return json.dumps({"composition": "single", "selected_indices": [0], "reason": "best"})


async def test_full_happy_flow(pg_session_maker, monkeypatch):
    """End-to-end: build_candidates (real PG dedup) + pick_composition + generator + review persist."""
    data_a = make_test_image(width=900, height=700, colors=200, seed=1)

    async def fake_safe_fetch(url, **kwargs):
        return _resp(data_a)

    # Three LLM calls: generation (agent), vision_score, pick_composition.
    # Generation is the real agent — keep that working via monkeypatch on its run method.
    def fake_generate_agent_run(prompt, **kwargs):
        class R:
            output = GeneratedPost(text="Body text.\n\n——\n🔗 **Konnekt**", is_sensitive=False, image_urls=[])
            def all_messages(self):
                return []
        return R()

    class _FakeAgent:
        async def run(self, *a, **kw):
            return fake_generate_agent_run(*a, **kw)

    with (
        patch("app.channel.generator._create_generation_agent", return_value=_FakeAgent()),
        patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None),
        patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=fake_safe_fetch)),
        patch("app.channel.images.is_safe_url", new=AsyncMock(return_value=True)),
        patch("app.channel.images.get_http_client") as mock_http,
        patch(
            "app.channel.image_pipeline.score.openrouter_chat_completion",
            new=AsyncMock(return_value=_good_vision(1)),
        ),
        patch(
            "app.channel.image_pipeline.compose.openrouter_chat_completion",
            new=AsyncMock(return_value=_compose_single()),
        ),
    ):
        # Stub images.get_http_client so find_images_for_post returns one URL
        html_with_og = b'<meta property="og:image" content="https://x/a.jpg">'
        mock_resp = AsyncMock()
        mock_resp.text = html_with_og.decode()
        mock_resp.raise_for_status = lambda: None
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_http.return_value = mock_client

        item = ContentItem(
            source_url="https://src.example/article",
            external_id="e1",
            title="Students news",
            body="b",
            url="https://src.example/article",
        )
        post = await generate_post(
            [item],
            api_key="k",
            model="m",
            language="Russian",
            channel_id=-100,
            session_maker=pg_session_maker,
            vision_model="vm",
        )

    assert post is not None
    assert post.image_urls == ["https://x/a.jpg"]
    assert post.image_candidates is not None
    assert len(post.image_candidates) == 1
    assert post.image_candidates[0]["selected"] is True
    assert post.image_phashes and len(post.image_phashes[0]) == 16


async def test_second_generation_is_deduped(pg_session_maker):
    """Insert a prior post with phash of our canonical image → next pipeline run drops it."""
    from app.channel.image_pipeline.dedup import compute_phash

    data = make_test_image(width=900, height=700, colors=200, seed=1)
    async with pg_session_maker() as session:
        prior = ChannelPost(
            channel_id=-100,
            external_id="prior",
            title="t",
            post_text="b",
            status=PostStatus.APPROVED,
        )
        prior.image_phashes = [compute_phash(data)]
        session.add(prior)
        await session.commit()

    async def fake_safe_fetch(url, **kwargs):
        return _resp(data)

    class _FakeAgent:
        async def run(self, *a, **kw):
            class R:
                output = GeneratedPost(text="Body.\n\n——", is_sensitive=False, image_urls=[])
                def all_messages(self):
                    return []
            return R()

    with (
        patch("app.channel.generator._create_generation_agent", return_value=_FakeAgent()),
        patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None),
        patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=fake_safe_fetch)),
        patch("app.channel.images.is_safe_url", new=AsyncMock(return_value=True)),
        patch("app.channel.images.get_http_client") as mock_http,
        patch(
            "app.channel.image_pipeline.score.openrouter_chat_completion",
            new=AsyncMock(return_value=_good_vision(1)),
        ),
        patch(
            "app.channel.image_pipeline.compose.openrouter_chat_completion",
            new=AsyncMock(return_value=_compose_single()),
        ),
    ):
        html_with_og = b'<meta property="og:image" content="https://x/a.jpg">'
        mock_resp = AsyncMock()
        mock_resp.text = html_with_og.decode()
        mock_resp.raise_for_status = lambda: None
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_http.return_value = mock_client

        item = ContentItem(
            source_url="https://src.example/article", external_id="e2", title="News", body="b",
            url="https://src.example/article",
        )
        post = await generate_post(
            [item],
            api_key="k", model="m", language="Russian",
            channel_id=-100, session_maker=pg_session_maker, vision_model="vm",
        )

    # The candidate was a perfect duplicate → pipeline drops it → no images on the new post.
    assert post is not None
    assert post.image_urls == []
    assert post.image_candidates == []  # empty pool, not None
```

- [ ] **Step 2: Run test to verify it passes**

```bash
uv run -m pytest tests/integration/test_image_pipeline_full_flow_pg.py -v
```
Expected: both tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_image_pipeline_full_flow_pg.py
git commit -m "test(integration): full-flow image pipeline happy + dedup scenarios"
```

---

### PR #2 boundary — open pull request

- [ ] **Step 1: Push branch, open PR**

```bash
git push -u origin feat/image-pipeline-integration
gh pr create --title "feat(image): Sprint 1 pipeline — vision scoring + composition + generator wiring" --body "$(cat <<'EOF'
## Summary
- `vision_score` — batched multimodal scoring via OpenRouter (`gemini-2.5-flash`)
- `pick_composition` — LLM decides single / album / none + deterministic fallback
- `build_candidates` orchestrator: filter → score → dedup → pool
- `generator.py` now calls the pipeline; `image_urls` is the LLM-selected subset, full pool persisted to `image_candidates`
- `ChannelPost.image_phashes` populated for future cross-post dedup

## Behaviour change
Posts now pass filter+score+dedup before reaching review. Some images that previously went through (logos, text slides) are now filtered out. This is the goal — expect a 24 h smoke period before PR #3 to ensure we're not rejecting valid photos.

## Test plan
- [ ] Unit: vision_score, pick_composition, generator wiring, persistence
- [ ] Integration PG: build_candidates orchestrator, full-flow happy + dedup
- [ ] Manual smoke: `/generate_post` in the test channel, inspect 5+ posts

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: Wait for CI + merge once green**

```bash
gh pr checks --watch
gh pr merge --squash --admin --delete-branch
git checkout main && git pull
```

- [ ] **Step 3: 24 h smoke period — BEFORE starting PR #3**

Watch logs for 24 h:
- `image_pipeline_pool_built` — distribution of `post_filter` vs `post_dedup`
- `pick_composition` outcomes — ratio of `single` / `album` / `none`
- `vision_score_api_error` / `vision_score_parse_error` — should be < 5 %
- Visual check: 5–10 posts in the review group — is anything good being rejected?

If `composition="none"` > 40 %, edit `app/channel/image_pipeline/score.py` and lower `MIN_QUALITY` from 5 to 4. If vision errors are noisy, investigate rate limits / model routing at OpenRouter.

---

## PR #3 — Granular review agent tools

Branch off `main` once PR #2 smoke is clean. This PR rewrites the image-related tools in `review/agent.py` to work with the candidate pool persisted by PR #2.

- [ ] **PR #3 setup:** `git checkout main && git pull && git checkout -b feat/image-review-tools`

---

### Task 15: `image_tools.py` — business logic split

**Files:**
- Create: `app/channel/review/image_tools.py`
- Create: `tests/unit/test_image_review_tools.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_image_review_tools.py`:

```python
"""Unit tests for review image tools (business logic, no PydanticAI layer)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.channel.review.image_tools import (
    ImageToolsDeps,
    add_image_url_op,
    clear_images_op,
    find_and_add_image_op,
    list_images_op,
    remove_image_op,
    reorder_images_op,
    use_candidate_op,
)
from app.core.enums import PostStatus
from app.db.models import ChannelPost

pytestmark = pytest.mark.asyncio


async def _make_post(session_maker, *, pool: list[dict] | None = None, image_urls: list[str] | None = None) -> int:
    async with session_maker() as session:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="b",
            status=PostStatus.DRAFT,
        )
        p.image_urls = image_urls
        p.image_candidates = pool
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p.id


def _deps(post_id: int, session_maker) -> ImageToolsDeps:
    return ImageToolsDeps(
        session_maker=session_maker,
        post_id=post_id,
        channel_id=-100,
        api_key="k",
        vision_model="m",
        brave_api_key="",
    )


class TestListImages:
    async def test_empty(self, session_maker):
        pid = await _make_post(session_maker)
        out = await list_images_op(_deps(pid, session_maker))
        assert "no images" in out.lower() or "pool is empty" in out.lower()

    async def test_with_pool_and_selected(self, session_maker):
        pool = [
            {"url": "https://x/a.jpg", "source": "og_image", "quality_score": 8, "relevance_score": 7,
             "description": "a", "selected": True, "is_logo": False, "is_text_slide": False, "is_duplicate": False},
            {"url": "https://x/b.jpg", "source": "brave_image", "quality_score": 6, "relevance_score": 6,
             "description": "b", "selected": False, "is_logo": False, "is_text_slide": False, "is_duplicate": False},
        ]
        pid = await _make_post(session_maker, pool=pool, image_urls=["https://x/a.jpg"])
        out = await list_images_op(_deps(pid, session_maker))
        assert "a.jpg" in out
        assert "b.jpg" in out
        assert "selected" in out.lower() or "✓" in out


class TestUseCandidate:
    async def test_promotes_from_pool(self, session_maker):
        pool = [
            {"url": "https://x/a.jpg", "source": "og_image", "quality_score": 8, "selected": True,
             "relevance_score": 7, "description": "a", "is_logo": False, "is_text_slide": False, "is_duplicate": False},
            {"url": "https://x/b.jpg", "source": "brave_image", "quality_score": 7, "selected": False,
             "relevance_score": 7, "description": "b", "is_logo": False, "is_text_slide": False, "is_duplicate": False},
        ]
        pid = await _make_post(session_maker, pool=pool, image_urls=["https://x/a.jpg"])

        from sqlalchemy import select
        out = await use_candidate_op(_deps(pid, session_maker), pool_index=1)
        assert "b.jpg" in out
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.image_urls == ["https://x/a.jpg", "https://x/b.jpg"]
        assert row.image_candidates[1]["selected"] is True

    async def test_invalid_pool_index(self, session_maker):
        pid = await _make_post(session_maker, pool=[], image_urls=[])
        out = await use_candidate_op(_deps(pid, session_maker), pool_index=5)
        assert "invalid" in out.lower() or "out of range" in out.lower()


class TestRemoveImage:
    async def test_removes_by_position(self, session_maker):
        pid = await _make_post(
            session_maker,
            image_urls=["https://x/a.jpg", "https://x/b.jpg"],
            pool=[
                {"url": "https://x/a.jpg", "source": "og_image", "selected": True, "quality_score": 8,
                 "relevance_score": 7, "description": "a", "is_logo": False, "is_text_slide": False, "is_duplicate": False},
                {"url": "https://x/b.jpg", "source": "brave_image", "selected": True, "quality_score": 7,
                 "relevance_score": 7, "description": "b", "is_logo": False, "is_text_slide": False, "is_duplicate": False},
            ],
        )

        from sqlalchemy import select
        await remove_image_op(_deps(pid, session_maker), position=0)
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.image_urls == ["https://x/b.jpg"]
        assert row.image_candidates[0]["selected"] is False

    async def test_invalid_position(self, session_maker):
        pid = await _make_post(session_maker, image_urls=["https://x/a.jpg"], pool=[])
        out = await remove_image_op(_deps(pid, session_maker), position=9)
        assert "invalid" in out.lower() or "out of range" in out.lower()


class TestReorderImages:
    async def test_swaps(self, session_maker):
        pid = await _make_post(session_maker, image_urls=["a", "b", "c"], pool=[])

        from sqlalchemy import select
        await reorder_images_op(_deps(pid, session_maker), order=[2, 0, 1])
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.image_urls == ["c", "a", "b"]

    async def test_invalid_length(self, session_maker):
        pid = await _make_post(session_maker, image_urls=["a", "b"], pool=[])
        out = await reorder_images_op(_deps(pid, session_maker), order=[0])
        assert "length" in out.lower() or "invalid" in out.lower()


class TestClearImages:
    async def test_clears(self, session_maker):
        pool = [{"url": "https://x/a.jpg", "source": "og_image", "selected": True, "quality_score": 8,
                 "relevance_score": 7, "description": "a", "is_logo": False, "is_text_slide": False, "is_duplicate": False}]
        pid = await _make_post(session_maker, image_urls=["https://x/a.jpg"], pool=pool)
        from sqlalchemy import select
        await clear_images_op(_deps(pid, session_maker))
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.image_urls == []
        assert row.image_candidates[0]["selected"] is False  # pool kept, just deselected


class TestAddImageUrl:
    async def test_adds_after_passing_filter(self, session_maker):
        pid = await _make_post(session_maker, image_urls=[], pool=[])

        from app.channel.image_pipeline.filter import FilteredImage
        from app.channel.image_pipeline.score import ScoredImage
        from tests.fixtures.images import make_test_image

        data = make_test_image(width=900, height=700, colors=200, seed=1)
        filtered = [FilteredImage(url="https://x/new.jpg", width=900, height=700, bytes_=data)]
        scored = [ScoredImage(url="https://x/new.jpg", width=900, height=700, bytes_=data,
                              quality_score=8, relevance_score=7, description="ok")]

        with (
            patch("app.channel.review.image_tools.cheap_filter", new=AsyncMock(return_value=filtered)),
            patch("app.channel.review.image_tools.vision_score", new=AsyncMock(return_value=scored)),
        ):
            out = await add_image_url_op(_deps(pid, session_maker), url="https://x/new.jpg")
        assert "added" in out.lower()

        from sqlalchemy import select
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.image_urls == ["https://x/new.jpg"]
        assert row.image_candidates is not None and len(row.image_candidates) == 1

    async def test_rejects_when_filter_drops(self, session_maker):
        pid = await _make_post(session_maker, image_urls=[], pool=[])
        with patch("app.channel.review.image_tools.cheap_filter", new=AsyncMock(return_value=[])):
            out = await add_image_url_op(_deps(pid, session_maker), url="https://x/tiny.jpg")
        assert "rejected" in out.lower()


class TestFindAndAddImage:
    async def test_adds_top_search_result_to_pool(self, session_maker):
        pid = await _make_post(session_maker, image_urls=[], pool=[])

        from app.channel.image_pipeline.filter import FilteredImage
        from app.channel.image_pipeline.score import ScoredImage
        from tests.fixtures.images import make_test_image

        data = make_test_image(width=900, height=700, colors=200, seed=1)
        with (
            patch("app.channel.review.image_tools.brave_image_search",
                  new=AsyncMock(return_value=[{"url": "https://x/s.jpg"}])),
            patch("app.channel.review.image_tools.cheap_filter",
                  new=AsyncMock(return_value=[FilteredImage(url="https://x/s.jpg", width=900, height=700, bytes_=data)])),
            patch("app.channel.review.image_tools.vision_score",
                  new=AsyncMock(return_value=[ScoredImage(url="https://x/s.jpg", width=900, height=700, bytes_=data,
                                                          quality_score=8, relevance_score=7, description="photo")])),
        ):
            out = await find_and_add_image_op(_deps(pid, session_maker), query="students in Prague")

        assert "s.jpg" in out
        from sqlalchemy import select
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        # Added to pool but NOT auto-selected.
        assert row.image_urls in (None, [])
        assert row.image_candidates is not None and len(row.image_candidates) == 1
        assert row.image_candidates[0]["selected"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run -m pytest tests/unit/test_image_review_tools.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.channel.review.image_tools'`.

- [ ] **Step 3: Implement `image_tools.py`**

`app/channel/review/image_tools.py`:

```python
"""Business logic for review-agent image tools.

Kept as free functions (``*_op`` suffix) so they can be tested without the
PydanticAI tool wrapper. The ``agent.py`` file imports these and exposes them
as ``@agent.tool``s.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.channel.brave_search import brave_image_search
from app.channel.image_pipeline.filter import cheap_filter
from app.channel.image_pipeline.models import ImageCandidate
from app.channel.image_pipeline.score import vision_score
from app.core.enums import PostStatus
from app.core.logging import get_logger
from app.db.models import ChannelPost

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = get_logger("channel.review.image_tools")

MIN_POOL_QUALITY = 5
MIN_POOL_RELEVANCE = 4


@dataclass
class ImageToolsDeps:
    session_maker: "async_sessionmaker"
    post_id: int
    channel_id: int
    api_key: str
    vision_model: str
    brave_api_key: str


# ---------------------------------------------------------------------------
# list_images
# ---------------------------------------------------------------------------


async def list_images_op(deps: ImageToolsDeps) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."

    selected = post.image_urls or []
    pool = post.image_candidates or []

    if not selected and not pool:
        return "No images. Pool is empty. Use `find_and_add_image` or `add_image_url` to add some."

    lines = []
    if selected:
        lines.append(f"Selected ({len(selected)}):")
        for i, url in enumerate(selected):
            cand = _find_candidate(pool, url)
            desc = cand.description if cand else ""
            q = cand.quality_score if cand else None
            lines.append(f"  [{i}] {url}  q={q}  — {desc}")
    else:
        lines.append("Selected: (empty)")

    if pool:
        lines.append("")
        lines.append(f"Pool ({len(pool)} total):")
        for i, p in enumerate(pool):
            cand = ImageCandidate.model_validate(p)
            mark = "✓" if cand.selected else " "
            lines.append(
                f"  [{i}] {mark} q={cand.quality_score} r={cand.relevance_score} src={cand.source}"
                f"  — {cand.description}  ({cand.url})"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# use_candidate
# ---------------------------------------------------------------------------


async def use_candidate_op(deps: ImageToolsDeps, pool_index: int, position: int | None = None) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."

    pool = post.image_candidates or []
    if pool_index < 0 or pool_index >= len(pool):
        return f"Invalid pool_index {pool_index}: pool has {len(pool)} items."

    candidate = ImageCandidate.model_validate(pool[pool_index])
    urls = list(post.image_urls or [])
    if candidate.url in urls:
        return f"Image already selected at position {urls.index(candidate.url)}."

    if position is None or position >= len(urls):
        urls.append(candidate.url)
    else:
        urls.insert(max(position, 0), candidate.url)

    pool[pool_index]["selected"] = True
    await _save_and_refresh(deps, post, urls, pool)
    return f"Added candidate [{pool_index}] ({candidate.url}) to position {urls.index(candidate.url)}."


# ---------------------------------------------------------------------------
# add_image_url
# ---------------------------------------------------------------------------


async def add_image_url_op(deps: ImageToolsDeps, url: str, position: int | None = None) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."

    filtered = await cheap_filter([url])
    if not filtered:
        return f"Rejected: {url} did not pass quality heuristics (too small / wrong aspect / logo-like)."

    scored = await vision_score(
        filtered,
        title=post.title or "",
        api_key=deps.api_key,
        model=deps.vision_model,
    )
    if not scored:
        return f"Rejected: vision model flagged {url} as logo/text-slide/low-relevance."

    best = scored[0]
    new_cand = ImageCandidate(
        url=best.url,
        source="reviewer_added",
        width=best.width,
        height=best.height,
        quality_score=best.quality_score,
        relevance_score=best.relevance_score,
        is_logo=best.is_logo,
        is_text_slide=best.is_text_slide,
        description=best.description,
        selected=True,
    )
    pool = list(post.image_candidates or [])
    pool.append(new_cand.model_dump())

    urls = list(post.image_urls or [])
    if position is None or position >= len(urls):
        urls.append(new_cand.url)
    else:
        urls.insert(max(position, 0), new_cand.url)

    await _save_and_refresh(deps, post, urls, pool)
    return f"Added {new_cand.url} (q={new_cand.quality_score}, r={new_cand.relevance_score})."


# ---------------------------------------------------------------------------
# find_and_add_image
# ---------------------------------------------------------------------------


async def find_and_add_image_op(deps: ImageToolsDeps, query: str) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."
    if not deps.brave_api_key:
        return "Brave Image Search is not configured."

    results = await brave_image_search(deps.brave_api_key, query, count=6)
    if not results:
        return f"No image results for '{query}'."
    urls = [r.get("url") for r in results if r.get("url")]

    filtered = await cheap_filter(urls[:5])
    if not filtered:
        return f"No candidate from '{query}' passed quality heuristics."

    scored = await vision_score(
        filtered,
        title=post.title or "",
        api_key=deps.api_key,
        model=deps.vision_model,
    )
    if not scored:
        return f"All candidates from '{query}' were flagged by the vision model."

    best = scored[0]
    new_cand = ImageCandidate(
        url=best.url,
        source="brave_image",
        width=best.width,
        height=best.height,
        quality_score=best.quality_score,
        relevance_score=best.relevance_score,
        is_logo=best.is_logo,
        is_text_slide=best.is_text_slide,
        description=best.description,
        selected=False,  # not auto-selected
    )
    pool = list(post.image_candidates or [])
    pool.append(new_cand.model_dump())
    await _save_and_refresh(deps, post, post.image_urls or [], pool, changed_selection=False)
    return (
        f"Added to pool: {new_cand.url}  q={new_cand.quality_score}  r={new_cand.relevance_score}."
        f"  Call `use_candidate` to select it."
    )


# ---------------------------------------------------------------------------
# remove_image
# ---------------------------------------------------------------------------


async def remove_image_op(deps: ImageToolsDeps, position: int) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."

    urls = list(post.image_urls or [])
    if position < 0 or position >= len(urls):
        return f"Invalid position {position}: post has {len(urls)} images."

    removed_url = urls.pop(position)
    pool = list(post.image_candidates or [])
    for entry in pool:
        if entry.get("url") == removed_url:
            entry["selected"] = False
    await _save_and_refresh(deps, post, urls, pool)
    return f"Removed position {position} ({removed_url})."


# ---------------------------------------------------------------------------
# reorder_images
# ---------------------------------------------------------------------------


async def reorder_images_op(deps: ImageToolsDeps, order: list[int]) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."

    urls = list(post.image_urls or [])
    if len(order) != len(urls) or sorted(order) != list(range(len(urls))):
        return f"Invalid order length/values: got {order}, expected a permutation of 0..{len(urls) - 1}."

    new_urls = [urls[i] for i in order]
    await _save_and_refresh(deps, post, new_urls, post.image_candidates or [])
    return f"Reordered images: {new_urls}"


# ---------------------------------------------------------------------------
# clear_images
# ---------------------------------------------------------------------------


async def clear_images_op(deps: ImageToolsDeps) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."

    pool = list(post.image_candidates or [])
    for entry in pool:
        entry["selected"] = False
    await _save_and_refresh(deps, post, [], pool)
    return "All images removed from post (pool kept for re-use)."


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _load_post(deps: ImageToolsDeps) -> ChannelPost | None:
    async with deps.session_maker() as session:
        r = await session.execute(select(ChannelPost).where(ChannelPost.id == deps.post_id))
        return r.scalar_one_or_none()


async def _save_and_refresh(
    deps: ImageToolsDeps,
    post: ChannelPost,
    new_urls: list[str],
    new_pool: list[dict],
    changed_selection: bool = True,
) -> None:
    """Update DB with new image_urls + image_candidates in one transaction."""
    async with deps.session_maker() as session:
        r = await session.execute(select(ChannelPost).where(ChannelPost.id == deps.post_id))
        fresh = r.scalar_one_or_none()
        if fresh is None:
            return
        fresh.image_urls = new_urls or None
        fresh.image_url = new_urls[0] if new_urls else None
        fresh.image_candidates = new_pool or None
        await session.commit()


def _find_candidate(pool: list[dict], url: str) -> ImageCandidate | None:
    for entry in pool:
        if entry.get("url") == url:
            try:
                return ImageCandidate.model_validate(entry)
            except Exception:
                return None
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run -m pytest tests/unit/test_image_review_tools.py -v
```
Expected: all 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/channel/review/image_tools.py tests/unit/test_image_review_tools.py
git commit -m "feat(review): granular image tool ops (list/use/add/find/remove/reorder/clear)"
```

---

### Task 16: Replace tools in `review/agent.py`

**Files:**
- Modify: `app/channel/review/agent.py` (system prompt + tools)

- [ ] **Step 1: Inspect existing agent tests**

```bash
uv run -m pytest tests/unit/test_channel_agent.py -v -k "image" 2>&1 | head -60
```
Note which tests cover `replace_images`, `remove_images`, `find_new_images`. They will need updates.

- [ ] **Step 2: Update the system prompt**

In `app/channel/review/agent.py`, find `_SYSTEM_PROMPT_TEMPLATE` (around line 241). Replace the `## Tools available` block and the `6. If the admin asks about images...` line with:

```
## Tools available
- `get_current_post` — read the current post text from DB (ALWAYS call first)
- `web_search` — search the web for facts or context
- `update_post` — save the edited text (MUST call to apply text changes)
- `list_images` — show current images and the candidate pool with scores
- `use_candidate` — promote a pooled candidate to the post
- `add_image_url` — add an external URL (validated before accepting)
- `find_and_add_image` — search Brave Images, add best result to the pool
- `remove_image` — remove one image from the post by position
- `reorder_images` — change the order of images in the post
- `clear_images` — remove all images (pool preserved)

## Images workflow
- Use `list_images` first to see what's already in the post and in the pool.
- To add an image:
    * from the pool → `use_candidate(pool_index)`
    * from a fresh search → `find_and_add_image(query)` then `use_candidate(...)`
    * from an external URL → `add_image_url(url)`
- To remove → `remove_image(position)`.
- To change order → `reorder_images([2, 0, 1])`.
- Never go over 4 images in one post — quality > quantity.
- If the admin wants coherent images (album), compare descriptions in the pool first before searching.
```

Remove the step `6. If the admin asks about images, use find_new_images and then replace_images.`

- [ ] **Step 3: Replace the tools inside `create_review_agent`**

Still in `app/channel/review/agent.py`, inside `create_review_agent`: delete the three `@agent.tool` functions `replace_images`, `remove_images`, `find_new_images`, plus the helper `_refresh_review_message` callers for those specific tools (the helper stays).

Add the new tools (each a thin wrapper around the ops from `image_tools.py`):

```python
    # ------------------------------------------------------------------
    # Image tools (granular, backed by app.channel.review.image_tools)
    # ------------------------------------------------------------------

    def _image_deps(ctx: RunContext[ReviewAgentDeps]) -> "ImageToolsDeps":
        from app.channel.review.image_tools import ImageToolsDeps

        return ImageToolsDeps(
            session_maker=ctx.deps.session_maker,
            post_id=ctx.deps.post_id,
            channel_id=ctx.deps.channel_id,
            api_key=settings.openrouter.api_key,
            vision_model=settings.channel.vision_model,
            brave_api_key=settings.brave.api_key,
        )

    @agent.tool
    async def list_images(ctx: RunContext[ReviewAgentDeps]) -> str:
        """List current images + candidate pool."""
        from app.channel.review.image_tools import list_images_op

        return await list_images_op(_image_deps(ctx))

    @agent.tool
    async def use_candidate(
        ctx: RunContext[ReviewAgentDeps], pool_index: int, position: int | None = None
    ) -> str:
        """Promote a pool candidate into the post. Refreshes the review message."""
        from app.channel.review.image_tools import use_candidate_op

        out = await use_candidate_op(_image_deps(ctx), pool_index=pool_index, position=position)
        await _refresh_after_change(ctx)
        return out

    @agent.tool
    async def add_image_url(
        ctx: RunContext[ReviewAgentDeps], url: str, position: int | None = None
    ) -> str:
        """Add an external image URL to the post (validated)."""
        from app.channel.review.image_tools import add_image_url_op

        out = await add_image_url_op(_image_deps(ctx), url=url, position=position)
        await _refresh_after_change(ctx)
        return out

    @agent.tool
    async def find_and_add_image(ctx: RunContext[ReviewAgentDeps], query: str) -> str:
        """Search Brave for images matching ``query`` and add the best to the pool (not auto-selected)."""
        from app.channel.review.image_tools import find_and_add_image_op

        return await find_and_add_image_op(_image_deps(ctx), query=query)

    @agent.tool
    async def remove_image(ctx: RunContext[ReviewAgentDeps], position: int) -> str:
        """Remove the image at ``position`` from the post. Candidate stays in pool."""
        from app.channel.review.image_tools import remove_image_op

        out = await remove_image_op(_image_deps(ctx), position=position)
        await _refresh_after_change(ctx)
        return out

    @agent.tool
    async def reorder_images(ctx: RunContext[ReviewAgentDeps], order: list[int]) -> str:
        """Reorder selected images by current-position indices."""
        from app.channel.review.image_tools import reorder_images_op

        out = await reorder_images_op(_image_deps(ctx), order=order)
        await _refresh_after_change(ctx)
        return out

    @agent.tool
    async def clear_images(ctx: RunContext[ReviewAgentDeps]) -> str:
        """Remove all images from the post (pool kept for later re-use)."""
        from app.channel.review.image_tools import clear_images_op

        out = await clear_images_op(_image_deps(ctx))
        await _refresh_after_change(ctx)
        return out

    async def _refresh_after_change(ctx: RunContext[ReviewAgentDeps]) -> None:
        """Re-fetch the post and call the existing _refresh_review_message helper."""
        from sqlalchemy import select as _select

        async with ctx.deps.session_maker() as session:
            r = await session.execute(_select(ChannelPost).where(ChannelPost.id == ctx.deps.post_id))
            post = r.scalar_one_or_none()
        if post:
            await _refresh_review_message(ctx, post)
```

Ensure `channel_id` is present on `ReviewAgentDeps` (search the file — it already is). The `ImageToolsDeps` pulls `api_key` and `vision_model` from global `settings` to avoid threading them through agent construction.

- [ ] **Step 4: Run existing + new tests**

```bash
uv run -m pytest tests/unit/test_channel_agent.py tests/unit/test_image_review_tools.py -v
```
Expected: tests exercising the *removed* tools will fail. For each such test:
- If it tested `replace_images` → port to `use_candidate` or `add_image_url`
- If it tested `remove_images` → port to `clear_images`
- If it tested `find_new_images` → port to `find_and_add_image`
- If the scenario no longer makes sense under the new API → delete

The goal is all tests pass. Use the new tool names and the ops signatures.

- [ ] **Step 5: Commit**

```bash
git add app/channel/review/agent.py tests/unit/test_channel_agent.py
git commit -m "feat(review): swap coarse image tools for 7 granular ones backed by image_tools.py"
```

---

### Task 17: E2E test via `FakeTelegramServer`

**Files:**
- Create: `tests/e2e/test_review_image_tools_e2e.py`

- [ ] **Step 1: Check existing E2E patterns**

```bash
uv run ls tests/e2e/
```
Open one existing E2E test to see how `FakeTelegramServer` is wired in — pattern conventions, fixture usage.

- [ ] **Step 2: Write the E2E test**

`tests/e2e/test_review_image_tools_e2e.py`:

```python
"""E2E: admin edits images via the review agent.

Exercises the full agent → image_tools → DB → Telegram-refresh round trip
against the FakeTelegramServer and an in-memory SQLite DB.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.channel.image_pipeline.filter import FilteredImage
from app.channel.image_pipeline.score import ScoredImage
from app.channel.review.agent import ReviewAgentDeps, review_agent_turn
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select
from tests.fixtures.images import make_test_image

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


@pytest.fixture
async def post_with_pool(session_maker):
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=-100,
            external_id="e1",
            title="Students news",
            post_text="Body text.\n\n——",
            status=PostStatus.DRAFT,
        )
        post.image_urls = ["https://x/a.jpg"]
        post.image_candidates = [
            {
                "url": "https://x/a.jpg",
                "source": "og_image",
                "quality_score": 7,
                "relevance_score": 6,
                "description": "main photo",
                "is_logo": False,
                "is_text_slide": False,
                "is_duplicate": False,
                "selected": True,
            },
            {
                "url": "https://x/b.jpg",
                "source": "article_body",
                "quality_score": 8,
                "relevance_score": 8,
                "description": "second photo",
                "is_logo": False,
                "is_text_slide": False,
                "is_duplicate": False,
                "selected": False,
            },
        ]
        post.review_message_id = 5555
        post.review_chat_id = -1001
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post.id


async def test_admin_uses_second_candidate_and_reorders(post_with_pool, session_maker, fake_tg_bot):
    """Admin: `show me images` → `use candidate 1 and put it first` — works."""
    deps = ReviewAgentDeps(
        session_maker=session_maker,
        bot=fake_tg_bot,  # fixture from tests/e2e/conftest.py
        post_id=post_with_pool,
        channel_id=-100,
        channel_name="Konnekt",
        channel_username="konnekt_channel",
        footer="——\n🔗 **Konnekt**",
        review_chat_id=-1001,
    )

    # Simulate the admin telling the agent to promote the second candidate to position 0.
    # We stub the LLM in the agent to issue the exact tool calls.
    with patch("app.channel.review.agent.create_review_agent") as mock_factory:
        async def fake_run(prompt, deps, message_history=None):
            # First call: list_images. Second call: use_candidate(1, 0). Third: reorder.
            class R:
                output = "Использовал кандидата 1 и поставил его первым."
                def all_messages(self):
                    return []
            # Execute the ops via the real image_tools — that's the point of E2E.
            from app.channel.review.image_tools import ImageToolsDeps, use_candidate_op
            tool_deps = ImageToolsDeps(
                session_maker=deps.session_maker,
                post_id=deps.post_id,
                channel_id=deps.channel_id,
                api_key="k",
                vision_model="m",
                brave_api_key="",
            )
            await use_candidate_op(tool_deps, pool_index=1, position=0)
            return R()

        agent = AsyncMock()
        agent.run = AsyncMock(side_effect=fake_run)
        mock_factory.return_value = agent

        await review_agent_turn(
            post_id=post_with_pool,
            user_message="покажи фотки; возьми вторую и поставь первой",
            deps=deps,
        )

    async with session_maker() as session:
        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_with_pool))).scalar_one()
    assert row.image_urls == ["https://x/b.jpg", "https://x/a.jpg"]
```

**Note:** this test is a scaffold. If `tests/e2e/conftest.py` does not expose a `fake_tg_bot` fixture, adjust the fixture name to whatever is there, or skip the Telegram-refresh assertion. The key asserted behaviour is DB state after the tool ran.

- [ ] **Step 3: Run the E2E test**

```bash
uv run -m pytest tests/e2e/test_review_image_tools_e2e.py -v
```
Expected: passes. If the FakeTelegramServer fixture has a different name, update and re-run.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_review_image_tools_e2e.py
git commit -m "test(e2e): review agent image-tool round-trip via FakeTelegramServer"
```

---

### PR #3 boundary — open pull request

- [ ] **Step 1: Run the full test suite**

```bash
uv run -m pytest -x
```
Expected: all green. Coverage should be ≥ 58 %.

- [ ] **Step 2: Lint + type-check**

```bash
uv run ruff check app tests && uv run ruff format --check app tests
uv run ty check app tests
```
Expected: zero errors.

- [ ] **Step 3: Push + open PR**

```bash
git push -u origin feat/image-review-tools
gh pr create --title "feat(review): granular image tools (list / use / add / find / remove / reorder / clear)" --body "$(cat <<'EOF'
## Summary
- Seven granular image tools replace the coarse `replace_images` / `remove_images` / `find_new_images`.
- New `app/channel/review/image_tools.py` carries the business logic (testable without PydanticAI).
- System prompt rewritten with an explicit `## Images workflow` block.

## Changes visible to admins
- `list_images` shows the candidate pool (not just current images).
- `use_candidate`, `add_image_url`, `find_and_add_image` add images; `remove_image`, `reorder_images`, `clear_images` trim them.
- Every write tool re-renders the review message, as before.

## Test plan
- [ ] Unit: 12 image_tools tests + ported `test_channel_agent.py` tests
- [ ] E2E: review agent uses candidate + reorders via FakeTelegramServer

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Merge once CI is green**

```bash
gh pr checks --watch
gh pr merge --squash --admin --delete-branch
git checkout main && git pull
```

---

## Self-review checklist (run after completing all tasks)

- [ ] Every spec requirement has a task (cheap_filter, vision_score, phash_dedup, pick_composition, storage, review tools, error handling, testing) — verified ✓
- [ ] No placeholders — all code blocks contain real, runnable Python
- [ ] Method names consistent: `compute_phash`, `hamming_distance`, `phash_dedup_against`, `recent_phashes_for_channel`, `phash_dedup`, `cheap_filter`, `vision_score`, `pick_composition`, `fallback_composition`, `build_candidates` — no drift
- [ ] Config keys match spec: `vision_model`, `image_phash_lookback_posts`, `image_phash_threshold` ✓
- [ ] Pydantic models match spec: `ImageCandidate`, `VisionScore`, `CompositionDecision` ✓
- [ ] Tool names match spec: `list_images`, `use_candidate`, `add_image_url`, `find_and_add_image`, `remove_image`, `reorder_images`, `clear_images` ✓
