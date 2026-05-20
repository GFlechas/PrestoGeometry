"""Photogrammetric reconstruction utilities (DUSt3R wrapper + footprint -> floorspace.js)."""

from .floorspace_builder import build_building, footprint_to_floorspace_dict
from .footprint import (
    FootprintResult,
    ScaleKind,
    ScaleRef,
    WindowOnEdge,
    detect_windows,
    extract_footprint,
)
from .pipeline import photos_to_floorspace
from .pose_extractor import Dust3rPoseExtractor, ExtractionResult, discover_images

__all__ = [
    "Dust3rPoseExtractor",
    "ExtractionResult",
    "discover_images",
    "ScaleRef",
    "ScaleKind",
    "FootprintResult",
    "WindowOnEdge",
    "extract_footprint",
    "detect_windows",
    "build_building",
    "footprint_to_floorspace_dict",
    "photos_to_floorspace",
]
