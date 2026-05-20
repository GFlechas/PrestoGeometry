"""Build a :class:`Building` from a :class:`FootprintResult`.

The polygon vertices from the footprint stage become a single ring of
``Vertex``/``Edge`` records with one closing ``Face``; each story repeats the
same plan (we use a story per detected floor rather than a multiplier so the
React editor can show the actual floor count).
"""

from __future__ import annotations

from typing import List

from presto_geometry.exporters.floorspace import building_to_floorspace_dict
from presto_geometry.models.building import (
    Building,
    Edge,
    Face,
    Geometry,
    Space,
    SpaceType,
    Story,
    ThermalZone,
    Vertex,
)

from .footprint import FootprintResult


DEFAULT_TZ_ID = "tz-default"
DEFAULT_SPACE_TYPE_ID = "stype-default"


def _build_story_geometry(story_idx: int, polygon_xy):
    """Return a Geometry with one face wrapping ``polygon_xy``."""
    n = len(polygon_xy)
    if n < 3:
        raise ValueError(f"Polygon needs at least 3 vertices, got {n}")

    face_id = f"f-s{story_idx}-1"
    vertex_ids: List[str] = [f"v-s{story_idx}-{i}" for i in range(n)]
    edge_ids: List[str] = [f"e-s{story_idx}-{i}" for i in range(n)]

    vertices = [
        Vertex(
            id=vertex_ids[i],
            x=float(polygon_xy[i][0]),
            y=float(polygon_xy[i][1]),
            edge_ids=[edge_ids[(i - 1) % n], edge_ids[i]],
        )
        for i in range(n)
    ]
    edges = [
        Edge(
            id=edge_ids[i],
            vertex_ids=(vertex_ids[i], vertex_ids[(i + 1) % n]),
            face_ids=[face_id],
        )
        for i in range(n)
    ]
    face = Face(id=face_id, edge_ids=list(edge_ids), edge_order=[0] * n)

    return Geometry(id=f"geom-s{story_idx}", vertices=vertices, edges=edges, faces=[face]), face_id


def build_building(
    footprint: FootprintResult,
    *,
    name: str = "Imported from photos",
) -> Building:
    """Construct a :class:`Building` from a footprint result."""
    building = Building(name=name)
    building.thermal_zones.append(
        ThermalZone(id=DEFAULT_TZ_ID, name="Default Zone", color="#88aadd")
    )
    building.space_types.append(
        SpaceType(id=DEFAULT_SPACE_TYPE_ID, name="Default Space Type", color="#dddddd")
    )

    fch = float(footprint.floor_to_ceiling_height)
    for story_idx in range(1, footprint.n_stories + 1):
        geometry, face_id = _build_story_geometry(story_idx, footprint.polygon_xy)
        space = Space(
            id=f"space-s{story_idx}-1",
            name=f"Floor {story_idx} Space",
            face_id=face_id,
            thermal_zone_id=DEFAULT_TZ_ID,
            space_type_id=DEFAULT_SPACE_TYPE_ID,
        )
        story = Story(
            id=f"story-{story_idx}",
            name=f"Floor {story_idx}",
            floor_to_ceiling_height=fch,
            geometry=geometry,
            spaces=[space],
        )
        building.stories.append(story)

    return building


def footprint_to_floorspace_dict(footprint: FootprintResult, **kwargs) -> dict:
    """Convenience: ``footprint -> Building -> validated floorspace dict``."""
    return building_to_floorspace_dict(build_building(footprint, **kwargs))


__all__ = ["build_building", "footprint_to_floorspace_dict"]
