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
    uniques = img.getcolors(maxcolors=1024)
    assert uniques is not None
    # JPEG introduces slight variance even in solid fills — allow up to 20.
    assert len(uniques) <= 20


def test_random_noise_has_high_entropy():
    data = make_test_image(width=800, height=600, fill=(120, 120, 120), colors=200)
    img = Image.open(BytesIO(data))
    uniques = img.getcolors(maxcolors=50000)
    assert uniques is not None
    assert len(uniques) > 50


def test_deterministic():
    a = make_test_image(width=500, height=400, colors=100)
    b = make_test_image(width=500, height=400, colors=100)
    assert a == b, "same inputs must produce byte-identical output"
