"""Run the full DUSt3R -> floorspace.js pipeline on a folder of photos.

Usage:
    python examples/run_pose_extraction.py path/to/photos --height 9.0 --fch 3.0 \
        --out examples/imported.json

The resulting JSON can be loaded directly by the floorspace.js editor (also
served by ``presto_geometry/web`` under ``POST /api/floorplan``).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from presto_geometry.reconstruction import (
    Dust3rPoseExtractor,
    ScaleRef,
    photos_to_floorspace,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_dir", type=Path, help="Folder containing 4-10 images")
    parser.add_argument("--height", type=float, default=9.0,
                        help="Approximate total building height in metres")
    parser.add_argument("--fch", type=float, default=3.0,
                        help="Floor-to-ceiling height in metres (controls story count)")
    parser.add_argument("--scale-kind", choices=["total_height", "wall_length"],
                        default="total_height")
    parser.add_argument("--no-snap", action="store_true",
                        help="Disable orthogonal snapping of footprint edges")
    parser.add_argument("--out", type=Path, default=Path("imported_floorplan.json"))
    parser.add_argument("--model-path", type=Path, default=None,
                        help="Optional path to a local DUSt3R .pth checkpoint")
    parser.add_argument("--poses-only", action="store_true",
                        help="Skip floorspace build; just print poses/intrinsics.")
    args = parser.parse_args()

    if args.poses_only:
        extractor = Dust3rPoseExtractor.load_model(model_path=args.model_path)
        payload = extractor.extract_as_json(args.image_dir)
        for name, data in payload["images"].items():
            print(name)
            print("  pose:", data["pose_4x4"])
            print("  K:   ", data["intrinsic_3x3"])
        return

    scale_ref = ScaleRef(
        kind=args.scale_kind,
        value=args.height,
        floor_to_ceiling_height=args.fch,
    )
    floorplan = photos_to_floorspace(
        args.image_dir,
        scale_ref=scale_ref,
        model_path=args.model_path,
        snap_orthogonal=not args.no_snap,
    )
    args.out.write_text(json.dumps(floorplan, indent=2), encoding="utf-8")
    print(f"Wrote floorspace.js JSON to {args.out} "
          f"({len(floorplan['stories'])} stories, "
          f"{len(floorplan['stories'][0]['geometry']['vertices'])} footprint vertices)")


if __name__ == "__main__":
    main()
