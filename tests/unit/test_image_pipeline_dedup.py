"""Unit tests for pHash-based image deduplication (no DB)."""

from __future__ import annotations

from io import BytesIO

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
        with pytest.raises(ValueError, match="hash length mismatch"):
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

    def test_drops_at_threshold_boundary(self):
        """Hamming distance exactly == threshold → dropped (inclusive)."""
        data = make_test_image(width=800, height=600, colors=100)
        img = _make_filtered(data)
        own_hash = compute_phash(data)
        # Peer hash that differs by exactly 1 bit
        peer_int = int(own_hash, 16) ^ 1
        peer_hash = format(peer_int, "016x")
        kept = phash_dedup_against([img], [peer_hash], threshold=1)
        assert kept == []
        assert img.is_duplicate is True

    def test_keeps_just_over_threshold(self):
        """Hamming distance > threshold → kept."""
        data = make_test_image(width=800, height=600, colors=100)
        img = _make_filtered(data)
        own_hash = compute_phash(data)
        peer_int = int(own_hash, 16) ^ 1  # distance 1
        peer_hash = format(peer_int, "016x")
        kept = phash_dedup_against([img], [peer_hash], threshold=0)
        assert len(kept) == 1
        assert kept[0].is_duplicate is False

    def test_mutates_phash_even_when_kept(self):
        data = make_test_image(width=800, height=600, colors=100)
        img = _make_filtered(data)
        kept = phash_dedup_against([img], [], threshold=10)
        assert kept[0].phash is not None
