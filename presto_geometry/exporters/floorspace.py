"""Serialise the :class:`Building` dataclass to/from floorspace.js JSON.

The output dict matches the floorspace.js geometry schema (v0.7.0) and is
validated against :func:`presto_geometry.schemas.load_geometry_schema` before
being returned, so callers can rely on the result being acceptable to both
the Flask API and the React editor.
"""

from __future__ import annotations

from typing import Any, Dict, List

import jsonschema

from presto_geometry.models.building import (
    Building,
    DoorPlacement,
    Edge,
    Face,
    Geometry,
    Space,
    Story,
    Vertex,
    WindowPlacement,
)
from presto_geometry.schemas import load_geometry_schema


SCHEMA_VERSION = "0.7.0"
DEFAULT_STORY_COLOR = "#D4E8C2"


def _default_project() -> Dict[str, Any]:
    return {
        "config": {"units": "si", "language": "EN-US"},
        "north_axis": 0,
        "ground": {"floor_offset": 0, "azimuth_angle": 0, "tilt_slope": 0},
        "grid": {"visible": True, "spacing": 0.5},
        "view": {"min_x": -50, "min_y": -50, "max_x": 50, "max_y": 50},
        "map": {
            "visible": False,
            "latitude": 39.7653,
            "longitude": -104.9863,
            "zoom": 4.5,
            "elevation": 0,
            "enabled": False,
            "initialized": False,
            "rotation": 0,
        },
        "previous_story": {"visible": True},
        "show_import_export": True,
    }


def _space_to_dict(space: Space) -> Dict[str, Any]:
    return {
        "id": space.id,
        "handle": None,
        "name": space.name,
        "face_id": space.face_id,
        "building_unit_id": None,
        "thermal_zone_id": space.thermal_zone_id,
        "space_type_id": space.space_type_id,
        "construction_set_id": None,
        "pitched_roof_id": None,
        "daylighting_controls": [],
        "below_floor_plenum_height": space.below_floor_plenum_height,
        "floor_to_ceiling_height": space.floor_to_ceiling_height,
        "above_ceiling_plenum_height": space.above_ceiling_plenum_height,
        "floor_offset": space.floor_offset,
        "open_to_below": space.open_to_below,
        "building_type_id": None,
        "template": None,
    }


def _geometry_to_dict(geom: Geometry) -> Dict[str, Any]:
    return {
        "id": geom.id,
        "vertices": [
            {"id": v.id, "x": v.x, "y": v.y, "edge_ids": list(v.edge_ids)}
            for v in geom.vertices
        ],
        "edges": [
            {
                "id": e.id,
                "vertex_ids": list(e.vertex_ids),
                "face_ids": list(e.face_ids),
            }
            for e in geom.edges
        ],
        "faces": [
            {
                "id": f.id,
                "edge_ids": list(f.edge_ids),
                "edge_order": list(f.edge_order),
            }
            for f in geom.faces
        ],
    }


def _story_to_dict(story: Story) -> Dict[str, Any]:
    return {
        "id": story.id,
        "handle": None,
        "name": story.name or story.id,
        "image_visible": True,
        "below_floor_plenum_height": story.below_floor_plenum_height,
        "floor_to_ceiling_height": story.floor_to_ceiling_height,
        "above_ceiling_plenum_height": story.above_ceiling_plenum_height,
        "multiplier": story.multiplier,
        "color": story.color or DEFAULT_STORY_COLOR,
        "geometry": _geometry_to_dict(story.geometry) if story.geometry else {
            "id": f"{story.id}-geom", "vertices": [], "edges": [], "faces": [],
        },
        "images": [],
        "spaces": [_space_to_dict(s) for s in story.spaces],
        "shading": [],
        "windows": [
            {
                "window_definition_id": w.window_definition_id,
                "edge_id": w.edge_id,
                "alpha": w.alpha,
            }
            for w in story.windows
        ],
        "doors": [
            {
                "door_definition_id": d.door_definition_id,
                "edge_id": d.edge_id,
                "alpha": d.alpha,
            }
            for d in story.doors
        ],
    }


def building_to_floorspace_dict(b: Building, *, validate: bool = True) -> Dict[str, Any]:
    """Convert ``b`` to a floorspace.js-schema-compliant dict."""
    project = _default_project()
    project["north_axis"] = b.north_axis

    doc: Dict[str, Any] = {
        "version": SCHEMA_VERSION,
        "application": {},
        "project": project,
        "stories": [_story_to_dict(s) for s in b.stories],
        "building_units": [],
        "thermal_zones": [
            {"id": tz.id, "handle": None, "name": tz.name or tz.id, "color": tz.color or "#88aadd"}
            for tz in b.thermal_zones
        ],
        "space_types": [
            {"id": st.id, "handle": None, "name": st.name or st.id, "color": st.color or "#dddddd"}
            for st in b.space_types
        ],
        "construction_sets": [],
        "window_definitions": [
            {
                "id": wd.id,
                "name": wd.name or wd.id,
                "window_definition_mode": wd.window_definition_mode,
                "width": wd.width,
                "height": wd.height,
                "sill_height": wd.sill_height,
                "wwr": wd.wwr,
                "window_type": wd.window_type,
                "overhang_projection_factor": wd.overhang_projection_factor,
                "fin_projection_factor": wd.fin_projection_factor,
            }
            for wd in b.window_definitions
        ],
        "door_definitions": [
            {
                "id": dd.id,
                "name": dd.name or dd.id,
                "width": dd.width,
                "height": dd.height,
                "door_type": dd.door_type,
            }
            for dd in b.door_definitions
        ],
        "daylighting_control_definitions": [],
        "pitched_roofs": [],
    }

    if validate:
        validator = jsonschema.Draft4Validator(load_geometry_schema())
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        if errors:
            messages = "; ".join(
                f"{list(e.path) or '<root>'}: {e.message}" for e in errors[:5]
            )
            raise ValueError(f"Building serialisation failed schema validation: {messages}")
    return doc


def floorspace_dict_to_building(doc: Dict[str, Any]) -> Building:
    """Inverse of :func:`building_to_floorspace_dict` (used in tests)."""
    b = Building(name="Imported", north_axis=float(doc.get("project", {}).get("north_axis", 0)))

    for s in doc.get("stories", []):
        geom_doc = s.get("geometry") or {}
        geometry = Geometry(
            id=geom_doc.get("id", f"{s['id']}-geom"),
            vertices=[
                Vertex(id=v["id"], x=float(v["x"]), y=float(v["y"]),
                       edge_ids=list(v.get("edge_ids", [])))
                for v in geom_doc.get("vertices", [])
            ],
            edges=[
                Edge(id=e["id"], vertex_ids=tuple(e["vertex_ids"]),
                     face_ids=list(e.get("face_ids", [])))
                for e in geom_doc.get("edges", [])
            ],
            faces=[
                Face(id=f["id"], edge_ids=list(f["edge_ids"]),
                     edge_order=list(f["edge_order"]))
                for f in geom_doc.get("faces", [])
            ],
        )
        story = Story(
            id=s["id"],
            name=s.get("name"),
            floor_to_ceiling_height=float(s.get("floor_to_ceiling_height") or 3.0),
            below_floor_plenum_height=float(s.get("below_floor_plenum_height") or 0.0),
            above_ceiling_plenum_height=float(s.get("above_ceiling_plenum_height") or 0.0),
            multiplier=int(s.get("multiplier") or 1),
            color=s.get("color"),
            geometry=geometry,
            spaces=[
                Space(
                    id=sp["id"],
                    name=sp.get("name"),
                    face_id=sp.get("face_id"),
                    thermal_zone_id=sp.get("thermal_zone_id"),
                    space_type_id=sp.get("space_type_id"),
                )
                for sp in s.get("spaces", [])
            ],
            windows=[
                WindowPlacement(
                    window_definition_id=w["window_definition_id"],
                    edge_id=w["edge_id"],
                    alpha=float(w["alpha"]) if not isinstance(w["alpha"], list) else float(w["alpha"][0]),
                )
                for w in s.get("windows", [])
            ],
            doors=[
                DoorPlacement(
                    door_definition_id=d["door_definition_id"],
                    edge_id=d["edge_id"],
                    alpha=float(d["alpha"]),
                )
                for d in s.get("doors", [])
            ],
        )
        b.stories.append(story)
    return b


__all__ = ["building_to_floorspace_dict", "floorspace_dict_to_building"]
