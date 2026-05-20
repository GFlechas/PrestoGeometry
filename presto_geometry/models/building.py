"""Internal geometry data model.

Terminology and structure follows the floorspace.js geometry schema (v0.7.0).
See presto_geometry/schemas/floorspace_geometry_schema.json for the full schema.

Key concepts
------------
Vertex / Edge / Face
    2-D topological primitives that make up the floor plan geometry for one Story.
    Vertices carry (x, y) coordinates; Edges connect two Vertices; Faces are
    closed polygons defined by an ordered list of Edges.

Space
    A single room / thermal space within a Story, associated with a Face.

Story
    One floor of a building.  Holds a Geometry (the 2-D plan) plus a list of
    Spaces, Windows, and Doors placed on that floor.

ThermalZone
    A named thermal zone that can be assigned to one or more Spaces.

WindowDefinition / DoorDefinition
    Reusable opening templates (size, type) placed on wall Edges within a Story.

Building
    Top-level container: project metadata + a list of Stories + zone/opening
    definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Coordinate primitives
# ---------------------------------------------------------------------------

# 2-D point (x, y) in metres — used in the per-story floor plan
Point2D = Tuple[float, float]

# 3-D point (x, y, z) in metres — used when reconstructing full surfaces
Point3D = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# 2-D geometry graph (one per Story)
# ---------------------------------------------------------------------------

@dataclass
class Vertex:
    """A 2-D point in the floor plan.

    Corresponds to ``Vertex`` in the floorspace.js schema.
    ``edge_ids`` are populated when the parent Geometry is assembled.
    """
    id: str
    x: float            # metres
    y: float            # metres
    edge_ids: List[str] = field(default_factory=list)


@dataclass
class Edge:
    """A directed line segment between exactly two Vertices.

    Corresponds to ``Edge`` in the floorspace.js schema.
    An Edge belongs to one or two Faces (interior walls are shared).
    """
    id: str
    vertex_ids: Tuple[str, str] = ("", "")   # [start_vertex_id, end_vertex_id]
    face_ids: List[str] = field(default_factory=list)


@dataclass
class Face:
    """A closed polygon in the floor plan, defined by an ordered ring of Edges.

    Corresponds to ``Face`` in the floorspace.js schema.
    ``edge_order`` mirrors each entry in ``edge_ids``: 0 = forward, 1 = reversed.
    """
    id: str
    edge_ids: List[str] = field(default_factory=list)
    edge_order: List[int] = field(default_factory=list)  # 0 = forward, 1 = reversed


@dataclass
class Geometry:
    """The complete 2-D topological graph for one Story.

    Corresponds to ``Geometry`` in the floorspace.js schema.
    """
    id: str
    vertices: List[Vertex] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    faces: List[Face] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Opening definitions (reusable templates)
# ---------------------------------------------------------------------------

@dataclass
class WindowDefinition:
    """Reusable window template placed on wall Edges.

    Corresponds to ``WindowDefinition`` in the floorspace.js schema.
    ``window_definition_mode`` choices: "Single Window" | "Repeating Windows" |
    "Window to Wall Ratio".
    """
    id: str
    name: Optional[str] = None
    window_definition_mode: str = "Single Window"
    width: float = 2.0          # metres (ip: ft)
    height: float = 4.0         # metres (ip: ft)
    sill_height: float = 0.9    # metres above floor (ip: ft)
    wwr: Optional[float] = None # window-to-wall ratio (0–1), used with WWR mode
    window_type: str = "Fixed"  # "Fixed" | "Operable"
    overhang_projection_factor: Optional[float] = None
    fin_projection_factor: Optional[float] = None


@dataclass
class DoorDefinition:
    """Reusable door template placed on wall Edges.

    Corresponds to ``DoorDefinition`` in the floorspace.js schema.
    """
    id: str
    name: Optional[str] = None
    width: float = 0.91         # metres (~3 ft)
    height: float = 2.03        # metres (~6.67 ft)
    door_type: str = "Door"     # "Door" | "Glass Door" | "Overhead Door"


# ---------------------------------------------------------------------------
# Thermal zones and space types
# ---------------------------------------------------------------------------

@dataclass
class ThermalZone:
    """A named thermal zone that Spaces can be assigned to.

    Corresponds to ``ThermalZone`` in the floorspace.js schema.
    Decoupled from geometry — multiple Spaces may share one ThermalZone.
    """
    id: str
    name: Optional[str] = None
    color: Optional[str] = None     # hex color, e.g. "#C0FFEE"


@dataclass
class SpaceType:
    """A named space-type category (e.g. "Office", "Corridor").

    Corresponds to ``SpaceType`` in the floorspace.js schema.
    """
    id: str
    name: Optional[str] = None
    color: Optional[str] = None


# ---------------------------------------------------------------------------
# Spaces within a Story
# ---------------------------------------------------------------------------

@dataclass
class Space:
    """A single room within a Story, associated with a 2-D Face.

    Corresponds to ``Space`` in the floorspace.js schema.
    Heights default to the parent Story values when not overridden.
    """
    id: str
    name: Optional[str] = None
    face_id: Optional[str] = None               # references a Face in Story.geometry
    thermal_zone_id: Optional[str] = None       # references a ThermalZone
    space_type_id: Optional[str] = None         # references a SpaceType
    floor_to_ceiling_height: Optional[float] = None  # metres; overrides Story default
    below_floor_plenum_height: Optional[float] = None
    above_ceiling_plenum_height: Optional[float] = None
    floor_offset: Optional[float] = None        # vertical offset from story floor
    open_to_below: bool = False


# ---------------------------------------------------------------------------
# Window / door placements on a Story
# ---------------------------------------------------------------------------

@dataclass
class WindowPlacement:
    """An instance of a WindowDefinition placed on a specific Edge.

    Corresponds to the window entries in ``Story.windows`` in the schema.
    ``alpha`` is the normalised position along the Edge (0 = start, 1 = end).
    """
    window_definition_id: str
    edge_id: str
    alpha: float = 0.5  # 0–1


@dataclass
class DoorPlacement:
    """An instance of a DoorDefinition placed on a specific Edge.

    Corresponds to the door entries in ``Story.doors`` in the schema.
    """
    door_definition_id: str
    edge_id: str
    alpha: float = 0.5  # 0–1


# ---------------------------------------------------------------------------
# Pitched roof
# ---------------------------------------------------------------------------

@dataclass
class PitchedRoof:
    """A pitched roof applied to one or more Spaces.

    Corresponds to ``PitchedRoof`` in the floorspace.js schema.
    """
    id: str
    name: Optional[str] = None
    pitched_roof_type: str = "Gable"    # "Gable" | "Hip" | "Shed"
    pitch: float = 6.0                  # rise-over-run (6 = 6-in-12 = 26.57°)
    shed_direction: Optional[float] = None  # degrees clockwise from +y
    color: Optional[str] = None


# ---------------------------------------------------------------------------
# Story
# ---------------------------------------------------------------------------

@dataclass
class Story:
    """One floor of the building.

    Corresponds to ``Story`` in the floorspace.js schema.
    ``geometry`` holds the 2-D plan; ``spaces`` assign thermal/type info to faces.
    """
    id: str
    name: Optional[str] = None
    floor_to_ceiling_height: float = 3.0    # metres (schema default: 8 ft)
    below_floor_plenum_height: float = 0.0  # metres
    above_ceiling_plenum_height: float = 0.0
    multiplier: int = 1                     # number of identical stacked floors
    color: Optional[str] = None
    geometry: Optional[Geometry] = None
    spaces: List[Space] = field(default_factory=list)
    windows: List[WindowPlacement] = field(default_factory=list)
    doors: List[DoorPlacement] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level building container
# ---------------------------------------------------------------------------

@dataclass
class Building:
    """Top-level building geometry container.

    Aggregates Stories (geometry + spaces) with the shared lookup tables for
    ThermalZones, SpaceTypes, WindowDefinitions, DoorDefinitions, and
    PitchedRoofs — matching the top-level structure of the floorspace.js schema.
    """
    name: str = "PrestoBuilding"
    north_axis: float = 0.0             # degrees clockwise from true north

    # Per-floor geometry
    stories: List[Story] = field(default_factory=list)

    # Shared lookup tables
    thermal_zones: List[ThermalZone] = field(default_factory=list)
    space_types: List[SpaceType] = field(default_factory=list)
    window_definitions: List[WindowDefinition] = field(default_factory=list)
    door_definitions: List[DoorDefinition] = field(default_factory=list)
    pitched_roofs: List[PitchedRoof] = field(default_factory=list)

    # Source material
    source_images: List[str] = field(default_factory=list)

    @property
    def num_floors(self) -> int:
        """Total number of modelled floor levels (accounting for multipliers)."""
        return sum(s.multiplier for s in self.stories)
