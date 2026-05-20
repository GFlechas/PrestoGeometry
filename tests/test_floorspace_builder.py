"""Tests for footprint -> Building -> floorspace.js dict."""

from __future__ import annotations

import numpy as np

from presto_geometry.exporters.floorspace import (
    building_to_floorspace_dict,
    floorspace_dict_to_building,
)
from presto_geometry.reconstruction.floorspace_builder import build_building
from presto_geometry.reconstruction.footprint import FootprintResult


def _rect_footprint(width: float = 40, depth: float = 20, n_stories: int = 3) -> FootprintResult:
    polygon = [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]
    return FootprintResult(
        polygon_xy=polygon,
        floor_to_ceiling_height=3.0,
        n_stories=n_stories,
        total_height=3.0 * n_stories,
        scale=1.0,
        transform_world_to_floorspace=np.eye(4),
    )


def test_build_building_creates_one_story_per_floor():
    footprint = _rect_footprint(n_stories=3)
    b = build_building(footprint)
    assert len(b.stories) == 3
    for story in b.stories:
        assert story.geometry is not None
        assert len(story.geometry.vertices) == 4
        assert len(story.geometry.edges) == 4
        assert len(story.geometry.faces) == 1
        assert story.floor_to_ceiling_height == 3.0


def test_floorspace_dict_is_schema_valid():
    footprint = _rect_footprint()
    b = build_building(footprint)
    doc = building_to_floorspace_dict(b)  # validates internally; raises on failure
    assert doc["version"] == "0.7.0"
    assert len(doc["stories"]) == footprint.n_stories
    story = doc["stories"][0]
    assert len(story["geometry"]["vertices"]) == 4
    assert len(story["geometry"]["edges"]) == 4
    assert len(story["geometry"]["faces"]) == 1
    assert story["geometry"]["faces"][0]["edge_order"] == [0, 0, 0, 0]


def test_roundtrip_preserves_polygon():
    footprint = _rect_footprint(width=30, depth=15, n_stories=2)
    doc = building_to_floorspace_dict(build_building(footprint))
    b2 = floorspace_dict_to_building(doc)
    assert len(b2.stories) == 2
    verts = b2.stories[0].geometry.vertices
    coords = [(v.x, v.y) for v in verts]
    assert coords == footprint.polygon_xy
