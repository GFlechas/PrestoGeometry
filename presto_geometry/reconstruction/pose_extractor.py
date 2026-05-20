"""DUSt3R wrapper exposing camera poses, intrinsics, and a dense point cloud.

This module is a thin, dependency-light facade around Naver Labs' ``dust3r``
package. The heavy ``dust3r`` / ``torch`` imports happen lazily inside the
methods that need them so importing :mod:`presto_geometry` stays cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .weights import DEFAULT_WEIGHT_NAME, ensure_weights

_SUPPORTED_EXT = {".jpg", ".jpeg", ".png"}
_MIN_IMAGES = 4
_MAX_IMAGES = 10


def _require_dust3r():
    """Import the optional ``dust3r`` package or raise a helpful error."""
    try:
        import torch  # noqa: F401
        from dust3r.cloud_opt import GlobalAlignerMode, global_aligner
        from dust3r.image_pairs import make_pairs
        from dust3r.inference import inference
        from dust3r.model import AsymmetricCroCo3DStereo
        from dust3r.utils.image import load_images
    except ImportError as exc:
        raise ImportError(
            "DUSt3R is required for pose extraction. Install with "
            "`pip install -e .[dust3r]` and clone "
            "https://github.com/naver/dust3r alongside this project."
        ) from exc
    return {
        "GlobalAlignerMode": GlobalAlignerMode,
        "global_aligner": global_aligner,
        "make_pairs": make_pairs,
        "inference": inference,
        "AsymmetricCroCo3DStereo": AsymmetricCroCo3DStereo,
        "load_images": load_images,
    }


def _resolve_device(requested: Optional[str]) -> str:
    """Pick a torch device string, validating CUDA requests."""
    import torch

    if requested is None:
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError(
            f"Requested device {requested!r} but torch.cuda.is_available() is False."
        )
    return requested


def _discover_images(image_dir: Path) -> List[Path]:
    """Return a deterministically ordered list of supported image files."""
    paths = sorted(
        p for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _SUPPORTED_EXT
    )
    if not (_MIN_IMAGES <= len(paths) <= _MAX_IMAGES):
        raise ValueError(
            f"Expected between {_MIN_IMAGES} and {_MAX_IMAGES} images in "
            f"{image_dir}, found {len(paths)}."
        )
    return paths


@dataclass
class ExtractionResult:
    """In-memory result of a DUSt3R run."""

    filenames: List[str]
    poses_c2w: np.ndarray              # (N, 4, 4)
    intrinsics: np.ndarray             # (N, 3, 3)
    points_world: np.ndarray           # (M, 3)
    colors: Optional[np.ndarray] = None  # (M, 3) in [0, 1]
    image_sizes: List[Tuple[int, int]] = field(default_factory=list)  # (W, H)

    def to_json_dict(self) -> dict:
        """JSON-safe representation (matrices as nested lists)."""
        per_image = {}
        for i, name in enumerate(self.filenames):
            per_image[name] = {
                "pose_4x4": self.poses_c2w[i].tolist(),
                "intrinsic_3x3": self.intrinsics[i].tolist(),
                "image_size": list(self.image_sizes[i]) if i < len(self.image_sizes) else None,
            }
        return {
            "image_count": len(self.filenames),
            "images": per_image,
            "point_cloud": {
                "count": int(self.points_world.shape[0]),
            },
        }


class Dust3rPoseExtractor:
    """High-level wrapper around DUSt3R for unposed building exterior photos."""

    def __init__(
        self,
        model_path: Optional[str | Path] = None,
        device: Optional[str] = None,
        image_size: int = 512,
    ) -> None:
        self.model_path = Path(model_path) if model_path else None
        self.device = _resolve_device(device)
        self.image_size = int(image_size)
        self.model = None

    @classmethod
    def load_model(
        cls,
        model_path: Optional[str | Path] = None,
        device: Optional[str] = None,
        image_size: int = 512,
    ) -> "Dust3rPoseExtractor":
        """Construct an extractor and eagerly load the network weights."""
        self = cls(model_path=model_path, device=device, image_size=image_size)
        self._load_model()
        return self

    def _load_model(self) -> None:
        if self.model is not None:
            return
        d3r = _require_dust3r()
        weights = self.model_path or ensure_weights(DEFAULT_WEIGHT_NAME)
        model = d3r["AsymmetricCroCo3DStereo"].from_pretrained(str(weights)).to(self.device)
        model.eval()
        self.model = model

    def extract(
        self,
        image_dir: str | Path,
        *,
        iters: int = 100,
        schedule: str = "linear",
        lr: float = 0.01,
        init: str = "mst",
    ) -> ExtractionResult:
        """Run DUSt3R on a directory of 4–10 images and return geometry."""
        import torch

        image_dir = Path(image_dir)
        if not image_dir.is_dir():
            raise FileNotFoundError(f"Image directory not found: {image_dir}")

        paths = _discover_images(image_dir)
        filenames = [p.name for p in paths]

        d3r = _require_dust3r()
        self._load_model()

        images = d3r["load_images"]([str(p) for p in paths], size=self.image_size)
        pairs = d3r["make_pairs"](
            images, scene_graph="complete", prefilter=None, symmetrize=True
        )
        output = d3r["inference"](pairs, self.model, self.device, batch_size=1)

        aligner = d3r["global_aligner"](
            output, device=self.device, mode=d3r["GlobalAlignerMode"].PointCloudOptimizer
        )
        aligner.compute_global_alignment(
            init=init, niter=iters, schedule=schedule, lr=lr
        )

        poses = aligner.get_im_poses().detach().cpu().numpy()
        intrinsics = aligner.get_intrinsics().detach().cpu().numpy()
        per_view_pts = [p.detach().cpu().numpy() for p in aligner.get_pts3d()]
        try:
            masks = [m.detach().cpu().numpy() for m in aligner.get_masks()]
        except Exception:
            masks = [np.ones(p.shape[:-1], dtype=bool) for p in per_view_pts]

        try:
            per_view_colors = [c.detach().cpu().numpy() for c in aligner.imgs]
        except Exception:
            per_view_colors = None

        kept_pts: List[np.ndarray] = []
        kept_cols: List[np.ndarray] = []
        image_sizes: List[Tuple[int, int]] = []
        for i, pts in enumerate(per_view_pts):
            mask = masks[i].astype(bool)
            flat_pts = pts.reshape(-1, 3)
            flat_mask = mask.reshape(-1)
            kept_pts.append(flat_pts[flat_mask])
            if per_view_colors is not None:
                cols = np.asarray(per_view_colors[i])
                if cols.ndim == 3:
                    flat_cols = cols.reshape(-1, cols.shape[-1])
                    kept_cols.append(flat_cols[flat_mask])
            h, w = pts.shape[:2]
            image_sizes.append((int(w), int(h)))

        points_world = np.concatenate(kept_pts, axis=0) if kept_pts else np.zeros((0, 3))
        colors = (
            np.concatenate(kept_cols, axis=0)
            if kept_cols and len(kept_cols) == len(kept_pts)
            else None
        )

        del output, aligner
        if self.device.startswith("cuda"):
            torch.cuda.empty_cache()

        return ExtractionResult(
            filenames=filenames,
            poses_c2w=np.asarray(poses, dtype=np.float64),
            intrinsics=np.asarray(intrinsics, dtype=np.float64),
            points_world=np.asarray(points_world, dtype=np.float64),
            colors=np.asarray(colors, dtype=np.float64) if colors is not None else None,
            image_sizes=image_sizes,
        )

    def extract_as_json(self, image_dir: str | Path, **kwargs) -> dict:
        """Run :meth:`extract` and return a JSON-serialisable dict."""
        result = self.extract(image_dir, **kwargs)
        payload = result.to_json_dict()
        payload["device"] = self.device
        payload["model"] = str(self.model_path) if self.model_path else DEFAULT_WEIGHT_NAME
        return payload


def discover_images(image_dir: str | Path) -> List[Path]:
    """Public re-export of the image-discovery helper (used by Flask)."""
    return _discover_images(Path(image_dir))


__all__ = [
    "Dust3rPoseExtractor",
    "ExtractionResult",
    "discover_images",
]
