"""Tests for point-cloud-to-footprint extraction."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("shapely")
pytest.importorskip("scipy")

from presto_geometry.reconstruction.footprint import ScaleRef, extract_footprint


def _sample_box_points(width: float, depth: float, height: float, n: int, seed: int = 0) -> np.ndarray:
    """Sample points on the four walls of an axis-aligned box (no roof/floor)."""
    rng = np.random.default_rng(seed)
    pts = []
    per_face = n // 4
    for x_const in (0.0, width):
        ys = rng.uniform(0, depth, per_face)
        zs = rng.uniform(0, height, per_face)
        pts.append(np.stack([np.full(per_face, x_const), ys, zs], axis=1))
    for y_const in (0.0, depth):
        xs = rng.uniform(0, width, per_face)
        zs = rng.uniform(0, height, per_face)
        pts.append(np.stack([xs, np.full(per_face, y_const), zs], axis=1))
    return np.concatenate(pts, axis=0)


def test_extract_footprint_recovers_rectangle_area():
    width, depth, height = 40.0, 20.0, 9.0
    raw = _sample_box_points(width, depth, height, n=2000)
    rng = np.random.default_rng(1)
    raw += rng.normal(scale=0.02, size=raw.shape)
    scale_factor = 0.37
    points = raw * scale_factor  # simulate DUSt3R's arbitrary scale

    result = extract_footprint(
        points,
        scale_ref=ScaleRef(kind="total_height", value=height, floor_to_ceiling_height=3.0),
        snap_orthogonal=True,
    )

    assert result.n_stories == 3
    assert result.floor_to_ceiling_height == pytest.approx(3.0)
    assert abs(result.total_height - height) / height < 0.1

    from shapely.geometry import Polygon

    poly = Polygon(result.polygon_xy)
    assert poly.is_valid
    expected_area = width * depth
    assert abs(poly.area - expected_area) / expected_area < 0.20


def test_extract_footprint_rejects_too_few_points():
    with pytest.raises(ValueError, match="at least 50"):
        extract_footprint(np.zeros((10, 3)), scale_ref=ScaleRef())


def test_extract_footprint_rejects_bad_shape():
    with pytest.raises(ValueError, match="points_world"):
        extract_footprint(np.zeros((100, 2)), scale_ref=ScaleRef())
