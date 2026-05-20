"""Internal geometry data model."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# A 2-D point (x, y) in metres relative to a building origin
Point2D = Tuple[float, float]
# A 3-D point (x, y, z) in metres
Point3D = Tuple[float, float, float]


@dataclass
class Opening:
    """A window or door on a surface."""
    opening_type: str           # "window" | "door"
    width: float                # metres
    height: float               # metres
    sill_height: float = 0.9    # metres above floor


@dataclass
class Surface:
    """A single planar building surface (wall, roof, floor)."""
    surface_type: str           # "wall" | "roof" | "floor"
    vertices: List[Point3D] = field(default_factory=list)
    openings: List[Opening] = field(default_factory=list)
    azimuth: Optional[float] = None   # degrees from north, walls only
    tilt: float = 90.0                # degrees; 0 = horizontal roof, 90 = vertical wall


@dataclass
class Zone:
    """A thermal zone (typically one per floor)."""
    name: str
    floor_area: float = 0.0     # m²
    ceiling_height: float = 3.0 # m
    surfaces: List[Surface] = field(default_factory=list)


@dataclass
class Building:
    """Top-level building geometry container."""
    name: str = "PrestoBuilding"
    footprint: List[Point2D] = field(default_factory=list)
    num_floors: int = 1
    zones: List[Zone] = field(default_factory=list)
    source_images: List[str] = field(default_factory=list)
