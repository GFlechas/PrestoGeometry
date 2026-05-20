"""End-to-end ``photos -> floorspace.js JSON`` pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .floorspace_builder import build_building
from .footprint import ScaleRef, extract_footprint
from .pose_extractor import Dust3rPoseExtractor


def photos_to_floorspace(
    image_dir: str | Path,
    scale_ref: ScaleRef,
    *,
    model_path: Optional[str | Path] = None,
    device: Optional[str] = None,
    image_size: int = 512,
    snap_orthogonal: bool = True,
    iters: int = 100,
    extractor: Optional[Dust3rPoseExtractor] = None,
) -> dict:
    """Run the full DUSt3R + footprint + serializer pipeline.

    Returns a floorspace.js-schema-compliant dict (already validated).
    """
    from presto_geometry.exporters.floorspace import building_to_floorspace_dict

    if extractor is None:
        extractor = Dust3rPoseExtractor.load_model(
            model_path=model_path, device=device, image_size=image_size
        )

    result = extractor.extract(image_dir, iters=iters)
    footprint = extract_footprint(
        result.points_world,
        scale_ref=scale_ref,
        snap_orthogonal=snap_orthogonal,
    )
    building = build_building(footprint)
    return building_to_floorspace_dict(building)


__all__ = ["photos_to_floorspace"]
