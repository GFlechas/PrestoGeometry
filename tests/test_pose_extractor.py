"""Tests for the DUSt3R wrapper that don't require dust3r/torch to be installed."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from presto_geometry.reconstruction.pose_extractor import (
    Dust3rPoseExtractor,
    ExtractionResult,
    _discover_images,
)


def _make_images(dir_: Path, n: int) -> None:
    for i in range(n):
        (dir_ / f"img_{i:02d}.jpg").write_bytes(b"\x00")


def test_discover_images_validates_count_too_few(tmp_path: Path):
    _make_images(tmp_path, 3)
    with pytest.raises(ValueError, match="between 4 and 10"):
        _discover_images(tmp_path)


def test_discover_images_validates_count_too_many(tmp_path: Path):
    _make_images(tmp_path, 11)
    with pytest.raises(ValueError, match="between 4 and 10"):
        _discover_images(tmp_path)


def test_discover_images_returns_sorted_paths(tmp_path: Path):
    _make_images(tmp_path, 5)
    paths = _discover_images(tmp_path)
    assert len(paths) == 5
    assert [p.name for p in paths] == sorted(p.name for p in paths)


def test_extraction_result_to_json_dict_is_serializable():
    n = 4
    result = ExtractionResult(
        filenames=[f"a{i}.jpg" for i in range(n)],
        poses_c2w=np.tile(np.eye(4)[None], (n, 1, 1)),
        intrinsics=np.tile(np.eye(3)[None], (n, 1, 1)),
        points_world=np.zeros((10, 3)),
        image_sizes=[(512, 384)] * n,
    )
    payload = result.to_json_dict()
    json.dumps(payload)  # must not raise
    assert payload["image_count"] == n
    assert set(payload["images"].keys()) == set(result.filenames)
    assert payload["images"]["a0.jpg"]["image_size"] == [512, 384]


torch = pytest.importorskip("torch", reason="torch not installed; skipping device tests")


def test_resolve_device_cpu_fallback(monkeypatch):
    """When torch is importable but cuda missing, default device is cpu."""
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    extractor = Dust3rPoseExtractor(device=None)
    assert extractor.device == "cpu"


def test_resolve_device_explicit_cuda_raises_when_unavailable(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="cuda"):
        Dust3rPoseExtractor(device="cuda")
