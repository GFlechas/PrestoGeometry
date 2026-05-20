"""Convert a DUSt3R world-frame point cloud into a 2-D building footprint.

The conversion stages are:
1. Pick the up axis (PCA, sign-corrected so the centroid is above the ground).
2. Fit the ground plane on the lowest slab of points (simple RANSAC).
3. Build a rigid transform that puts the ground at ``z = 0`` and aligns the
   dominant horizontal axis of the cloud with ``+x``.
4. Apply a metric scale derived from a user-supplied reference.
5. Project the points that sit between the ground and the roof onto ``z = 0``
   and recover a concave hull via an alpha shape, simplify it, and optionally
   snap the long edges towards orthogonality.

Window detection is intentionally left unimplemented — :func:`detect_windows`
is the placeholder hook that future work can fill in without changing the
public surface of this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional, Sequence, Tuple

import numpy as np


ScaleKind = Literal["total_height", "wall_length"]


@dataclass
class ScaleRef:
    """User-supplied metric reference used to scale the DUSt3R cloud.

    ``kind == "total_height"`` interprets ``value`` as the building's overall
    height (metres). ``kind == "wall_length"`` interprets ``value`` as the
    longest visible wall on the footprint.
    """

    kind: ScaleKind = "total_height"
    value: float = 9.0
    floor_to_ceiling_height: Optional[float] = 3.0


@dataclass
class WindowOnEdge:
    """Reserved placeholder for future window detection output."""

    edge_index: int
    alpha: float
    width_m: float
    height_m: float
    sill_height_m: float


@dataclass
class FootprintResult:
    """Output of :func:`extract_footprint`."""

    polygon_xy: List[Tuple[float, float]]
    floor_to_ceiling_height: float
    n_stories: int
    total_height: float
    scale: float
    transform_world_to_floorspace: np.ndarray  # (4, 4)
    windows: List[WindowOnEdge] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _principal_axes(points: np.ndarray) -> np.ndarray:
    """Return the 3x3 orthonormal PCA basis of ``points`` (columns = axes)."""
    centred = points - points.mean(axis=0, keepdims=True)
    cov = np.cov(centred.T)
    eig_vals, eig_vecs = np.linalg.eigh(cov)
    order = np.argsort(eig_vals)[::-1]
    return eig_vecs[:, order]


def _ransac_plane(points: np.ndarray, *, iters: int = 200, thresh: float = 0.05,
                  rng: Optional[np.random.Generator] = None) -> Tuple[np.ndarray, float]:
    """Fit a plane to ``points`` via RANSAC. Returns ``(normal, offset)``."""
    rng = rng or np.random.default_rng(0)
    n = points.shape[0]
    if n < 3:
        return np.array([0.0, 0.0, 1.0]), 0.0

    best_inliers = -1
    best_normal = np.array([0.0, 0.0, 1.0])
    best_offset = 0.0
    for _ in range(iters):
        idx = rng.choice(n, size=3, replace=False)
        p0, p1, p2 = points[idx]
        v1 = p1 - p0
        v2 = p2 - p0
        normal = np.cross(v1, v2)
        norm = np.linalg.norm(normal)
        if norm < 1e-9:
            continue
        normal = normal / norm
        offset = -float(normal @ p0)
        dists = np.abs(points @ normal + offset)
        inliers = int(np.sum(dists < thresh))
        if inliers > best_inliers:
            best_inliers = inliers
            best_normal = normal
            best_offset = offset
    return best_normal, best_offset


def _build_transform(points: np.ndarray) -> Tuple[np.ndarray, float]:
    """Return ``(T, height)`` transforming ``points`` into the floorspace frame.

    The returned 4x4 matrix maps world points to a frame in which the ground
    is ``z = 0``, the up axis is ``+z``, and the dominant horizontal direction
    is ``+x``. ``height`` is the (un-scaled) building height in the new frame.
    """
    axes = _principal_axes(points)
    up = axes[:, -1]
    centroid = points.mean(axis=0)

    projected = (points - centroid) @ up
    if np.mean(projected) < 0:
        up = -up

    lo, hi = np.percentile((points - centroid) @ up, [5, 95])
    ground_mask = ((points - centroid) @ up) < (lo + 0.3 * (hi - lo))
    ground_points = points[ground_mask] if ground_mask.sum() >= 50 else points

    normal, offset = _ransac_plane(ground_points)
    if normal @ up < 0:
        normal = -normal
        offset = -offset

    z_axis = normal / np.linalg.norm(normal)

    horiz = points - np.outer(points @ z_axis + offset, z_axis)
    horiz_centred = horiz - horiz.mean(axis=0, keepdims=True)
    cov = np.cov(horiz_centred.T)
    eig_vals, eig_vecs = np.linalg.eigh(cov)
    order = np.argsort(eig_vals)[::-1]
    x_candidate = eig_vecs[:, order[0]]
    x_candidate = x_candidate - (x_candidate @ z_axis) * z_axis
    x_axis = x_candidate / max(np.linalg.norm(x_candidate), 1e-9)
    y_axis = np.cross(z_axis, x_axis)

    R = np.stack([x_axis, y_axis, z_axis], axis=0)  # world -> local rotation
    t = np.array([0.0, 0.0, offset])

    transformed = points @ R.T
    transformed[:, 2] += offset
    transformed[:, 0] -= float(np.median(transformed[:, 0]))
    transformed[:, 1] -= float(np.median(transformed[:, 1]))

    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    T[0, 3] -= float(np.median((points @ R.T)[:, 0]))
    T[1, 3] -= float(np.median((points @ R.T)[:, 1]))

    height = float(np.percentile(transformed[:, 2], 99) - np.percentile(transformed[:, 2], 1))
    return T, max(height, 1e-6)


def _apply_transform(points: np.ndarray, T: np.ndarray) -> np.ndarray:
    homo = np.concatenate([points, np.ones((points.shape[0], 1))], axis=1)
    return (homo @ T.T)[:, :3]


def _alpha_shape(points_2d: np.ndarray, alpha: float):
    """Compute an alpha shape and return a single Shapely polygon."""
    from scipy.spatial import Delaunay
    from shapely.geometry import MultiLineString, Polygon
    from shapely.ops import polygonize, unary_union

    if points_2d.shape[0] < 4:
        from shapely.geometry import MultiPoint
        return MultiPoint(points_2d).convex_hull

    tri = Delaunay(points_2d)
    edges = set()
    for simplex in tri.simplices:
        pa, pb, pc = points_2d[simplex]
        a = np.linalg.norm(pb - pc)
        b = np.linalg.norm(pa - pc)
        c = np.linalg.norm(pa - pb)
        s = 0.5 * (a + b + c)
        area = max(s * (s - a) * (s - b) * (s - c), 1e-12) ** 0.5
        circum_r = a * b * c / (4.0 * area)
        if circum_r < 1.0 / alpha:
            for i, j in ((0, 1), (1, 2), (2, 0)):
                e = tuple(sorted((int(simplex[i]), int(simplex[j]))))
                edges.add(e)

    if not edges:
        from shapely.geometry import MultiPoint
        return MultiPoint(points_2d).convex_hull

    lines = MultiLineString([
        (tuple(points_2d[i]), tuple(points_2d[j])) for i, j in edges
    ])
    polys = list(polygonize(unary_union(lines)))
    if not polys:
        from shapely.geometry import MultiPoint
        return MultiPoint(points_2d).convex_hull
    return max(polys, key=lambda p: p.area)


def _snap_orthogonal(coords: Sequence[Tuple[float, float]],
                     tolerance_deg: float = 15.0) -> List[Tuple[float, float]]:
    """Snap polygon edges whose direction is within ``tolerance_deg`` of an axis."""
    pts = np.asarray(coords, dtype=float)
    if pts.shape[0] < 3:
        return [tuple(p) for p in pts]

    pts = pts.copy()
    n = pts.shape[0]
    angles_rad = np.deg2rad(tolerance_deg)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        delta = b - a
        length = np.linalg.norm(delta)
        if length < 1e-9:
            continue
        theta = np.arctan2(delta[1], delta[0])
        nearest = np.round(theta / (np.pi / 2)) * (np.pi / 2)
        if abs(((theta - nearest + np.pi) % np.pi) - 0) < angles_rad or \
           abs(((theta - nearest + np.pi) % np.pi) - np.pi) < angles_rad:
            new_delta = np.array([np.cos(nearest), np.sin(nearest)]) * length
            pts[(i + 1) % n] = a + new_delta
    return [tuple(p) for p in pts]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_footprint(
    points_world: np.ndarray,
    *,
    scale_ref: ScaleRef,
    snap_orthogonal: bool = True,
    simplify_tolerance_m: float = 0.2,
) -> FootprintResult:
    """Turn a world-frame point cloud into a footprint polygon and height.

    Parameters
    ----------
    points_world:
        ``(M, 3)`` array of points in the DUSt3R world frame (arbitrary scale).
    scale_ref:
        Metric reference used to scale the cloud into metres.
    snap_orthogonal:
        If True, snap nearly-axis-aligned edges to be exactly axis-aligned.
    simplify_tolerance_m:
        ``shapely.simplify`` tolerance in metres applied to the concave hull.
    """
    if points_world.ndim != 2 or points_world.shape[1] != 3:
        raise ValueError(f"points_world must be (M, 3), got {points_world.shape}")
    if points_world.shape[0] < 50:
        raise ValueError(f"Need at least 50 points, got {points_world.shape[0]}")

    T, raw_height = _build_transform(points_world)
    local = _apply_transform(points_world, T)

    # Scale into metres.
    if scale_ref.kind == "total_height":
        scale = float(scale_ref.value) / max(raw_height, 1e-6)
    elif scale_ref.kind == "wall_length":
        from shapely.geometry import MultiPoint

        slab = local[(local[:, 2] > 0.1 * raw_height) & (local[:, 2] < 0.6 * raw_height)]
        if slab.shape[0] < 20:
            slab = local
        hull = MultiPoint(slab[:, :2]).convex_hull
        if hasattr(hull, "exterior"):
            coords = np.asarray(hull.exterior.coords)
            diffs = np.linalg.norm(np.diff(coords, axis=0), axis=1)
            longest = float(np.max(diffs)) if diffs.size else 1.0
        else:
            longest = 1.0
        scale = float(scale_ref.value) / max(longest, 1e-6)
    else:
        raise ValueError(f"Unknown scale_ref.kind: {scale_ref.kind!r}")

    local = local * scale
    height = raw_height * scale

    from shapely.geometry import Polygon

    slab_mask = (local[:, 2] > 0.3) & (local[:, 2] < max(height - 0.3, 0.4))
    slab = local[slab_mask] if slab_mask.sum() >= 30 else local
    pts_2d = slab[:, :2]

    bbox = np.ptp(pts_2d, axis=0)
    alpha = 1.0 / max(0.05 * float(np.linalg.norm(bbox)), 0.5)
    shape = _alpha_shape(pts_2d, alpha=alpha)

    if not hasattr(shape, "exterior"):
        from shapely.geometry import MultiPoint
        shape = MultiPoint(pts_2d).convex_hull

    simplified = shape.simplify(simplify_tolerance_m, preserve_topology=True)
    if not hasattr(simplified, "exterior"):
        simplified = shape

    coords = list(simplified.exterior.coords)
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]

    if snap_orthogonal:
        coords = _snap_orthogonal(coords)
        cleaned = Polygon(coords)
        if cleaned.is_valid and cleaned.area > 0:
            coords = list(cleaned.exterior.coords)
            if len(coords) > 1 and coords[0] == coords[-1]:
                coords = coords[:-1]

    fch = scale_ref.floor_to_ceiling_height
    if fch and fch > 0:
        n_stories = max(1, int(round(height / fch)))
        floor_to_ceiling = fch
    else:
        n_stories = 1
        floor_to_ceiling = height

    return FootprintResult(
        polygon_xy=[(float(x), float(y)) for x, y in coords],
        floor_to_ceiling_height=float(floor_to_ceiling),
        n_stories=int(n_stories),
        total_height=float(height),
        scale=float(scale),
        transform_world_to_floorspace=T,
    )


def detect_windows(
    points_world: np.ndarray,
    poses_c2w: np.ndarray,
    intrinsics: np.ndarray,
    image_paths: Sequence[str],
    polygon_xy: Sequence[Tuple[float, float]],
) -> List[WindowOnEdge]:
    """Placeholder hook for future per-edge window detection.

    Currently returns an empty list; the signature is fixed so callers can
    wire this in without changing :func:`extract_footprint`.
    """
    return []


__all__ = [
    "ScaleRef",
    "ScaleKind",
    "WindowOnEdge",
    "FootprintResult",
    "extract_footprint",
    "detect_windows",
]
