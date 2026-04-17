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
