#!/usr/bin/env python3
"""
Building Geometry Assembly  (Interactive)
==========================================
Reads face-segment annotations produced by annotate_building.py,
assembles an initial rectangular 3-D model, then opens an interactive
editor where you can relax individual corner angles to close the polygon.

Usage
-----
    python notebooks/assemble_geometry.py [building_name]
                                          [--floors N]
                                          [--floor-height F]
                                          [--no-interactive]

    building_name choices:  UnivStThomas  UnivStThomas_1loop  LoringPark

Interactive editor
------------------
    Each corner of the floor plan is shown as a circle:
        GREEN  = fixed at 90 degrees
        YELLOW = free (will be computed by the solver)

    Left-click a corner   Toggle fixed <-> free
    [Solve]               Compute free angles so the polygon closes
    [Reset 90 deg]        Restore all corners to 90 degrees
    [Save PNG]            Write floor-plan + 3-D view to disk
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.widgets import Button, TextBox
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# ── Configuration ─────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent

# Ensure the repo root is on sys.path so presto_geometry is importable
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ANNOTATIONS_DIR = REPO_ROOT / 'data' / 'annotations'
OUTPUT_DIR_BASE = REPO_ROOT / 'data' / 'outputs' / 'geometry'

DEFAULT_N_FLOORS  = 5
DEFAULT_FLOOR_H_M = 3.4

FACE_COLORS = [
    '#E74C3C',  # 0 red
    '#3498DB',  # 1 blue
    '#2ECC71',  # 2 green
    '#F39C12',  # 3 orange
    '#9B59B6',  # 4 purple
    '#1ABC9C',  # 5 teal
    '#E67E22',  # 6 dark-orange
    '#E91E63',  # 7 pink
]

COLOR_RIGHT   = '#27AE60'   # green  – fixed 90°
COLOR_FREE    = '#F1C40F'   # yellow – free (any angle)
COLOR_ACUTE   = '#E67E22'   # orange – constrained < 90°
COLOR_OBTUSE  = '#3498DB'   # blue   – constrained > 90°

# Cycle order for corner mode on click
CORNER_MODES  = ('fixed', 'free', 'acute', 'obtuse')
CORNER_COLORS = {
    'fixed':  COLOR_RIGHT,
    'free':   COLOR_FREE,
    'acute':  COLOR_ACUTE,
    'obtuse': COLOR_OBTUSE,
}
CORNER_BOUNDS = {
    'free':   (2.,  178.),
    'acute':  (2.,   89.),
    'obtuse': (91., 178.),
}

# ── Annotation loading ─────────────────────────────────────────────────────────

def load_annotations(building: str) -> dict:
    ann_file = ANNOTATIONS_DIR / building / f'{building}.json'
    if not ann_file.exists():
        raise FileNotFoundError(
            f"No annotation file found at {ann_file}\n"
            "Run annotate_building.py first.")
    with ann_file.open(encoding='utf-8') as fh:
        return json.load(fh)


# ── Face geometry from segments ────────────────────────────────────────────────

class FaceGeometry:
    def __init__(self, face_id: int):
        self.face_id      = face_id
        self.h_segs: list = []
        self.v_segs: list = []
        self.all_segs: list = []
        # Per-image segment lists — key: image filename
        self._image_segs: dict = {}

    def add_segment(self, seg, img_name: str = ''):
        self.all_segs.append(seg)
        dx, dy = abs(seg[2]-seg[0]), abs(seg[3]-seg[1])
        if dx == 0 and dy == 0:
            return
        angle = np.degrees(np.arctan2(dy, dx))
        is_h = angle < 30
        is_v = angle > 60
        if is_h:
            self.h_segs.append(seg)
        elif is_v:
            self.v_segs.append(seg)

        # Track segments keyed by source image so aspect ratios are
        # computed per-image (avoids mixing coordinate scales from different photos)
        if img_name:
            if img_name not in self._image_segs:
                self._image_segs[img_name] = {'h': [], 'v': [], 'all': []}
            bucket = self._image_segs[img_name]
            bucket['all'].append(seg)
            if is_h:
                bucket['h'].append(seg)
            elif is_v:
                bucket['v'].append(seg)

    def _px_span(self, coords):
        return (max(coords) - min(coords)) if coords else None

    @property
    def px_width(self):
        xs = [c for s in self.h_segs for c in (s[0], s[2])]
        return self._px_span(xs)

    @property
    def px_height(self):
        ys = [c for s in self.v_segs for c in (s[1], s[3])]
        return self._px_span(ys)

    def _ratio_for_image(self, img_name: str):
        """Aspect ratio (width/height) from a single image's segments only."""
        bucket = self._image_segs.get(img_name, {})
        xs_h = [c for s in bucket.get('h', []) for c in (s[0], s[2])]
        ys_v = [c for s in bucket.get('v', []) for c in (s[1], s[3])]
        w = self._px_span(xs_h)
        h = self._px_span(ys_v)
        if w and h and h > 0:
            return w / h
        # Fall back to bounding box of all segments in this image
        all_s = bucket.get('all', [])
        if all_s:
            xs = [c for s in all_s for c in (s[0], s[2])]
            ys = [c for s in all_s for c in (s[1], s[3])]
            bw = max(xs) - min(xs)
            bh = max(ys) - min(ys)
            if bh > 0:
                return bw / bh
        return None

    def _per_image_ratios(self):
        """Return list of (img_name, ratio) for every image with a valid ratio."""
        out = []
        for img_name in self._image_segs:
            r = self._ratio_for_image(img_name)
            if r is not None and r > 0:
                out.append((img_name, r))
        return out

    def effective_aspect_ratio(self):
        """
        Best (maximum) per-image aspect ratio across all images that contain
        this face.

        Why max rather than median:
          Perspective foreshortening compresses a face's apparent pixel width by
          cos(θ), where θ is the angle between the camera's line of sight and the
          face normal.  Height is unaffected.  Therefore every image gives an
          aspect ratio ≤ the true value, and the image taken most-nearly
          perpendicular to the face gives the ratio closest to truth.  Taking the
          maximum is therefore the best estimate available from the raw pixel
          measurements alone.

        Falls back to the pooled global calculation when no per-image data exists.
        """
        per_img = self._per_image_ratios()
        if per_img:
            return float(max(r for _, r in per_img))
        # Global pooled fallback
        w, h = self.px_width, self.px_height
        if w and h and h > 0:
            return w / h
        if self.all_segs:
            xs = [c for s in self.all_segs for c in (s[0], s[2])]
            ys = [c for s in self.all_segs for c in (s[1], s[3])]
            bw = max(xs) - min(xs)
            bh = max(ys) - min(ys)
            if bh > 0:
                return bw / bh
        return None


def collect_face_geometries(ann: dict) -> dict:
    faces = {}
    for img_name, img_data in ann.items():
        if not isinstance(img_data, dict):
            continue
        for fid_str, segs in img_data.get('faces', {}).items():
            fid = int(fid_str)
            if fid not in faces:
                faces[fid] = FaceGeometry(fid)
            for seg in segs:
                faces[fid].add_segment(seg, img_name=img_name)
    return faces


# ── Directed adjacency ─────────────────────────────────────────────────────────

SNAP_DIST_ORIG_PX = 80


def build_directed_adjacency(ann: dict) -> dict:
    """
    Determine which face follows each face clockwise (the 'right' neighbour)
    by looking at where shared vertices fall within each face's image extent.
    """
    right_votes: dict = defaultdict(int)
    pairs: set = set()

    for img_data in ann.values():
        if not isinstance(img_data, dict):
            continue

        face_pts: dict = {}
        for fid_str, segs in img_data.get('faces', {}).items():
            fid = int(fid_str)
            pts = [(s[0], s[1]) for s in segs] + [(s[2], s[3]) for s in segs]
            if pts:
                face_pts[fid] = pts

        def _vote(fa, fb, sx):
            pairs.add((min(fa, fb), max(fa, fb)))
            fa_xs  = [p[0] for p in face_pts[fa]]
            fa_mid = (min(fa_xs) + max(fa_xs)) / 2
            if sx > fa_mid:
                right_votes[(fa, fb)] += 1
            else:
                right_votes[(fb, fa)] += 1

        fids = sorted(face_pts.keys())
        for i in range(len(fids)):
            for j in range(i + 1, len(fids)):
                fa, fb = fids[i], fids[j]
                sx = None
                for ax_, ay_ in face_pts[fa]:
                    for bx, by in face_pts[fb]:
                        if np.hypot(ax_ - bx, ay_ - by) < SNAP_DIST_ORIG_PX:
                            sx = (ax_ + bx) / 2.0
                            break
                    if sx is not None:
                        break
                if sx is not None:
                    _vote(fa, fb, sx)

        for se in img_data.get('shared_edges', []):
            f_list = se.get('faces', [])
            seg    = se.get('segment', [])
            if len(f_list) == 2 and len(seg) == 4:
                fa, fb = int(f_list[0]), int(f_list[1])
                if fa in face_pts and fb in face_pts:
                    _vote(fa, fb, (seg[0] + seg[2]) / 2.0)

    directed: dict = defaultdict(lambda: {'right': None, 'left': None})
    for (fa, fb) in pairs:
        if right_votes.get((fa, fb), 0) >= right_votes.get((fb, fa), 0):
            if directed[fa]['right'] is None:
                directed[fa]['right'] = fb
            if directed[fb]['left'] is None:
                directed[fb]['left'] = fa
        else:
            if directed[fb]['right'] is None:
                directed[fb]['right'] = fa
            if directed[fa]['left'] is None:
                directed[fa]['left'] = fb

    return dict(directed)


def build_chain(directed: dict, face_ids: list) -> list:
    """Return face IDs in clockwise assembly order."""
    root    = face_ids[0]
    chain   = [root]
    visited = {root}
    current = root
    for _ in range(len(face_ids)):
        nbr = directed.get(current, {}).get('right')
        if nbr is None or nbr in visited:
            break
        chain.append(nbr)
        visited.add(nbr)
        current = nbr
    for fid in face_ids:
        if fid not in visited:
            chain.append(fid)
    return chain


# ── Wall assembly with arbitrary corner angles ─────────────────────────────────

class Wall3D:
    def __init__(self, face_id, width_m, height_m, n_floors, p0, p1):
        self.face_id  = face_id
        self.width_m  = width_m
        self.height_m = height_m
        self.n_floors = n_floors
        self.p0       = p0.copy()
        self.p1       = p1.copy()
        self.verts    = np.array([
            [p0[0], p0[1], 0.0],
            [p1[0], p1[1], 0.0],
            [p1[0], p1[1], height_m],
            [p0[0], p0[1], height_m],
        ])


def walls_from_angles(chain, real_w, real_h, corner_angles_deg, n_floors):
    """
    Place walls in sequence.  corner_angles_deg[i] is the clockwise turn
    (in degrees) applied at the end of wall i before starting wall i+1.
    len(corner_angles_deg) must equal len(chain).
    """
    walls  = []
    pos    = np.array([0.0, 0.0])
    direc  = np.array([1.0, 0.0])

    for i, fid in enumerate(chain):
        w  = real_w[fid]
        p0 = pos.copy()
        p1 = pos + direc * w
        walls.append(Wall3D(fid, w, real_h[fid], n_floors, p0, p1))
        pos = p1.copy()

        theta  = np.radians(corner_angles_deg[i % len(corner_angles_deg)])
        ct, st = np.cos(theta), np.sin(theta)
        direc  = np.array([ct * direc[0] + st * direc[1],
                           -st * direc[0] + ct * direc[1]])
    return walls


def closure_error_m(chain, real_w, corner_angles_deg):
    """Return the 2-D gap vector (in metres) when the polygon is not closed."""
    pos   = np.array([0.0, 0.0])
    direc = np.array([1.0, 0.0])
    for i, fid in enumerate(chain):
        pos  = pos + direc * real_w[fid]
        theta = np.radians(corner_angles_deg[i % len(corner_angles_deg)])
        ct, st = np.cos(theta), np.sin(theta)
        direc  = np.array([ct * direc[0] + st * direc[1],
                           -st * direc[0] + ct * direc[1]])
    return pos   # distance from end back to origin


# ── Polygon validity helpers ───────────────────────────────────────────────────

def floor_plan_segments(chain, real_w, corner_angles_deg):
    """Return list of (p0, p1) ndarray pairs for each wall in 2-D."""
    pos   = np.array([0.0, 0.0])
    direc = np.array([1.0, 0.0])
    segs  = []
    for i, fid in enumerate(chain):
        p0 = pos.copy()
        pos = pos + direc * real_w[fid]
        segs.append((p0, pos.copy()))
        theta  = np.radians(corner_angles_deg[i % len(corner_angles_deg)])
        ct, st = np.cos(theta), np.sin(theta)
        direc  = np.array([ct * direc[0] + st * direc[1],
                           -st * direc[0] + ct * direc[1]])
    return segs


def _cross2(o, a, b):
    """2-D cross product (o→a) × (o→b)."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segs_intersect_strict(p1, p2, p3, p4):
    """Return True if segment p1-p2 strictly intersects p3-p4 (not just touches)."""
    d1 = _cross2(p3, p4, p1)
    d2 = _cross2(p3, p4, p2)
    d3 = _cross2(p1, p2, p3)
    d4 = _cross2(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def polygon_self_intersects(segs):
    """True if any two non-adjacent segments strictly intersect."""
    N = len(segs)
    for i in range(N):
        for j in range(i + 2, N):
            if i == 0 and j == N - 1:   # adjacent (share closing point)
                continue
            if _segs_intersect_strict(segs[i][0], segs[i][1],
                                       segs[j][0], segs[j][1]):
                return True
    return False


def signed_area(segs):
    """Signed area via shoelace.  Negative = clockwise winding."""
    area = 0.0
    for (p0, p1) in segs:
        area += p0[0] * p1[1] - p1[0] * p0[1]
    return area / 2.0


def solution_is_valid(chain, real_w, angles):
    """
    Return (is_valid: bool, reason: str).
    A solution is valid when:
      • All corner angles are in (2°, 178°)
      • No two non-adjacent walls intersect
      • The polygon winds clockwise (signed area < 0)
    """
    angles = np.asarray(angles, dtype=float)
    if np.any(angles < 2.0) or np.any(angles > 178.0):
        bad = [(i, a) for i, a in enumerate(angles) if a < 2 or a > 178]
        return False, f"angle out of range: {bad}"
    segs = floor_plan_segments(chain, real_w, angles)
    if polygon_self_intersects(segs):
        return False, "polygon self-intersects"
    if signed_area(segs) > 0:
        return False, "wrong winding (counter-clockwise)"
    return True, "OK"


# ── Polygon closure solver ─────────────────────────────────────────────────────

def solve_closure(chain, real_w, base_angles_deg, free_angle_indices,
                  flex_chain_idx=None, flex_tol=10.0,
                  angle_bounds_override=None, force_convex=False):
    """
    Find corner angles (and optionally a flex face width) that close the polygon
    and are physically valid (non-self-intersecting, clockwise winding).

    Parameters
    ----------
    chain              : face IDs in assembly order
    real_w             : dict  fid -> current width (m)
    base_angles_deg    : ndarray of current corner angles
    free_angle_indices : which corner-angle indices can vary
    flex_chain_idx     : index in *chain* of the flex face whose width may also
                         vary within +/-flex_tol to assist closure. None = angles only.
    flex_tol           : max width deviation allowed for the flex face (m)

    Returns
    -------
    (angles_deg, flex_width_or_none, is_valid, message)
    """
    try:
        from scipy.optimize import fsolve, minimize
    except ImportError:
        msg = "scipy not found — install with:  pip install scipy"
        return base_angles_deg.copy(), None, False, msg

    angles = base_angles_deg.copy().astype(float)
    fi     = list(free_angle_indices)
    N_ang  = len(fi)

    flex_fid    = chain[flex_chain_idx] if flex_chain_idx is not None else None
    flex_w_base = float(real_w[flex_fid]) if flex_fid is not None else None
    has_flex    = flex_fid is not None
    N_free      = N_ang + (1 if has_flex else 0)

    def make_params(fv):
        """Return (angle_array, width_dict) from the free-variable vector."""
        a = angles.copy()
        for k, idx in enumerate(fi):
            a[idx] = fv[k]
        w = dict(real_w)
        if has_flex:
            w[flex_fid] = float(fv[N_ang])
        return a, w

    def residual(fv):
        a, w = make_params(fv)
        return closure_error_m(chain, w, a)

    def score(fv):
        angle_sc = float(np.sum((fv[:N_ang] - 90.0) ** 2))
        flex_sc  = float((fv[N_ang] - flex_w_base) ** 2) * 0.1 if has_flex else 0.0
        return angle_sc + flex_sc

    CLOSURE_TOL = 0.5

    if angle_bounds_override is not None:
        angle_bounds = [tuple(b) for b in angle_bounds_override]
    else:
        angle_bounds = [(2.0, 178.0)] * N_ang
    flex_bounds  = [(max(0.1, flex_w_base - flex_tol),
                     flex_w_base + flex_tol)] if has_flex else []
    all_bounds   = angle_bounds + flex_bounds

    # fsolve doesn't support bounds — only use it for the unconstrained 2-angle case
    unconstrained = all(b == (2., 178.) for b in angle_bounds)
    use_fsolve = (N_free == 2 and not has_flex and unconstrained)

    def _try(x0):
        try:
            import warnings
            x0a = np.array(x0, dtype=float)
            if use_fsolve:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    fv = fsolve(residual, x0a, full_output=False)
            else:
                constraints = [
                    {'type': 'eq', 'fun': lambda fv: residual(fv)[0]},
                    {'type': 'eq', 'fun': lambda fv: residual(fv)[1]},
                ]
                if force_convex:
                    constraints.append(
                        {'type': 'eq',
                         'fun': lambda fv: float(np.sum(make_params(fv)[0])) - 360.0}
                    )
                r = minimize(
                    score, x0a,
                    method='SLSQP',
                    bounds=all_bounds,
                    constraints=constraints,
                    options={'ftol': 1e-9, 'maxiter': 3000},
                )
                fv = r.x
        except Exception:
            return None

        if np.linalg.norm(residual(fv)) > CLOSURE_TOL:
            return None

        a, w = make_params(fv)
        ok, reason = solution_is_valid(chain, w, a)
        return fv, score(fv), ok, reason

    # Build angle starting-point grid, respecting per-angle bounds
    def _grid_for_bound(lo, hi, n=5):
        """Return n evenly-spaced values inside [lo, hi]."""
        return list(np.linspace(lo + 1., hi - 1., n))

    per_ang_grids = [_grid_for_bound(*b) for b in angle_bounds]

    if N_ang == 0:
        angle_starts = [[]]
    elif N_ang == 1:
        lo, hi = angle_bounds[0]
        angle_starts = [[v] for v in np.linspace(lo + 1., hi - 1., 35)]
    elif N_ang == 2:
        angle_starts = [[a, b]
                        for a in per_ang_grids[0]
                        for b in per_ang_grids[1]]
    elif N_ang == 3:
        g = [_grid_for_bound(*b, n=3) for b in angle_bounds]
        angle_starts = [[a, b, c] for a in g[0] for b in g[1] for c in g[2]]
        base = angles[fi].tolist()
        for delta in [-20, -10, 10, 20]:
            candidate = [max(angle_bounds[k][0] + 1.,
                             min(angle_bounds[k][1] - 1., v + delta))
                         for k, v in enumerate(base)]
            angle_starts.append(candidate)
    else:
        rng = np.random.default_rng(42)
        angle_starts = []
        for _ in range(40):
            row = [float(rng.uniform(b[0] + 1., b[1] - 1.))
                   for b in angle_bounds]
            angle_starts.append(row)
        for v_list in [_grid_for_bound(*b, n=3) for b in angle_bounds]:
            angle_starts += [[v] * N_ang for v in v_list]

    # Append flex width starting values
    if has_flex:
        flex_tries = [flex_w_base,
                      flex_w_base - flex_tol * 0.5,
                      flex_w_base + flex_tol * 0.5]
        starts = [a_row + [fw] for a_row in angle_starts for fw in flex_tries]
    else:
        starts = angle_starts

    best_valid   = None
    best_invalid = None
    seen         = []
    TOL_DEDUP    = 1.0

    def is_new(fv):
        for prev in seen:
            if np.max(np.abs(np.array(fv) - np.array(prev))) < TOL_DEDUP:
                return False
        seen.append(list(fv))
        return True

    for x0 in starts:
        result = _try(x0)
        if result is None:
            continue
        fv, sc, ok, reason = result
        if not is_new(fv):
            continue
        a, w = make_params(fv)
        fw = float(fv[N_ang]) if has_flex else None
        if ok:
            if best_valid is None or sc < best_valid[0]:
                best_valid = (sc, a.copy(), fw)
        else:
            if best_invalid is None or sc < best_invalid[0]:
                best_invalid = (sc, a.copy(), fw, reason)

    if best_valid is not None:
        return best_valid[1], best_valid[2], True, "Valid solution found"

    if best_invalid is not None:
        return (best_invalid[1], best_invalid[2], False,
                f"No valid solution — best attempt: {best_invalid[3]}")

    return angles.copy(), None, False, "Solver found no solution at all"


# ── Interactive assembly editor ────────────────────────────────────────────────

class AssemblyEditor:
    """
    Interactive floor-plan + 3-D view.  Click corners on the floor plan to
    toggle them between fixed-90° (green) and free (yellow), then press
    [Solve] to find the angles that close the polygon.
    """

    CORNER_CLICK_RADIUS = 2.5   # metres – distance to register a corner click

    def __init__(self, building, chain, real_w, real_h, n_floors, output_dir):
        self.building   = building
        self.chain      = chain
        self.real_w     = real_w
        self.real_h     = real_h
        self.n_floors   = n_floors
        self.output_dir = output_dir

        N = len(chain)
        self.corner_angles = np.full(N, 90.0)   # degrees
        # 'fixed' | 'free' | 'acute' | 'obtuse'  (cycles on click)
        self.corner_mode   = ['fixed'] * N

        # Width locking: True = user has locked this face's width; solver won't touch it
        self.width_fixed        = [False] * N
        # Convexity enforcement: add sum(angles)==360 constraint to solver
        self.force_convex       = False
        # Flex face: allowed to stretch within tolerance to close the polygon
        self.flex_face_chain_idx = N - 1         # default: last face in chain
        self.flex_tolerance      = 10.0          # metres

        # Corner label: "F{a}-F{b}" where a=chain[i], b=chain[(i+1)%N]
        self.corner_labels = [
            f"F{chain[i]}-F{chain[(i+1) % N]}"
            for i in range(N)
        ]

        self._build_ui()
        self._build_width_inputs()
        self._solve_and_refresh()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        self.fig = plt.figure(figsize=(18, 11))
        self.fig.patch.set_facecolor('#1a1a2e')

        # Main axes — shifted up to leave room for three bottom strips:
        #   buttons (y=0.008), flex-face row (y=0.055), lock buttons (y=0.100),
        #   width text boxes (y=0.148), face labels (text ~y=0.208)
        self.ax2d = self.fig.add_axes([0.03, 0.218, 0.44, 0.773])
        self.ax3d = self.fig.add_axes([0.52, 0.218, 0.46, 0.773],
                                       projection='3d')

        for ax in (self.ax2d, self.ax3d):
            ax.set_facecolor('#16213e')

        # Bottom button bar  (5 buttons + status, evenly spaced)
        bh, by = 0.042, 0.008
        ax_solve   = self.fig.add_axes([0.03,  by, 0.095, bh])
        ax_reset   = self.fig.add_axes([0.13,  by, 0.095, bh])
        ax_save    = self.fig.add_axes([0.23,  by, 0.095, bh])
        ax_geom    = self.fig.add_axes([0.33,  by, 0.105, bh])
        ax_convex  = self.fig.add_axes([0.445, by, 0.095, bh])

        self._btn_solve  = Button(ax_solve,  'Solve',
                                  color='#1a4a1a', hovercolor='#2a7a2a')
        self._btn_reset  = Button(ax_reset,  'Reset 90°',
                                  color='#1a3a5c', hovercolor='#1e5080')
        self._btn_save   = Button(ax_save,   'Save PNG',
                                  color='#4a2a5c', hovercolor='#6a3a8c')
        self._btn_geom   = Button(ax_geom,   'Save Geometry',
                                  color='#4a3010', hovercolor='#7a5020')
        self._btn_convex = Button(ax_convex, 'Convex: OFF',
                                  color='#2a2a2a', hovercolor='#3a3a3a')
        for b in (self._btn_solve, self._btn_reset, self._btn_save,
                  self._btn_geom, self._btn_convex):
            b.label.set_color('white')
            b.label.set_fontsize(9)

        self._btn_solve.on_clicked(lambda _: self._on_solve())
        self._btn_reset.on_clicked(lambda _: self._on_reset())
        self._btn_save.on_clicked(lambda _: self._on_save())
        self._btn_geom.on_clicked(lambda _: self._on_save_geometry())
        self._btn_convex.on_clicked(lambda _: self._toggle_convex())

        # Status label
        self._status_ax = self.fig.add_axes([0.55, by, 0.44, bh])
        self._status_ax.axis('off')
        self._status_text = self._status_ax.text(
            0.0, 0.5, '', va='center', ha='left',
            color='white', fontsize=9,
            transform=self._status_ax.transAxes)

        # Click event
        self.fig.canvas.mpl_connect('button_press_event', self._on_click)

    # ── Face-width inputs ─────────────────────────────────────────────────

    def _build_width_inputs(self):
        """
        Build three horizontal strips between the button bar and the main axes:
          1. Face-ID labels  (text)
          2. Width TextBox   per face  — pre-populated, editable (Enter to commit)
          3. Lock toggle btn per face  — Fixed keeps solver from changing that width
        Plus a flex-face row below those:
          4. Flex face cycle button + tolerance TextBox
        """
        # --- Tear down previous widgets -----------------------------------
        for ax in getattr(self, '_wtb_axes', []):
            self.fig.delaxes(ax)
        for ax in getattr(self, '_lock_axes', []):
            self.fig.delaxes(ax)
        for ax in ([getattr(self, '_ax_flex_btn',  None),
                    getattr(self, '_ax_flex_tol',  None)]):
            if ax is not None:
                self.fig.delaxes(ax)
        for txt in getattr(self, '_wtb_label_artists', []):
            txt.remove()

        self._wtb_axes          = []
        self._lock_axes         = []
        self._wtb_label_artists = []
        self._wtb               = {}   # fid  -> TextBox
        self._lock_btns         = {}   # k    -> Button
        self._ax_flex_btn       = None
        self._ax_flex_tol       = None

        N = len(self.chain)
        if N == 0:
            return

        # Layout constants (figure-relative coordinates)
        left, right = 0.10, 0.98
        slot  = (right - left) / N
        lbl_y  = 0.208   # face-ID text labels
        box_y  = 0.153   # width text boxes
        box_h  = 0.048
        lock_y = 0.100   # lock toggle buttons
        lock_h = 0.044
        flex_y = 0.053   # flex-face row
        flex_h = 0.038

        # Section headers (left margin)
        for y, label in [
            (box_y  + box_h  / 2, 'WIDTH (m)\nEnter to set'),
            (lock_y + lock_h / 2, 'LOCK\nWIDTH'),
        ]:
            t = self.fig.text(0.003, y, label, va='center', ha='left',
                              fontsize=6, color='#aaaaaa', fontweight='bold',
                              transform=self.fig.transFigure)
            self._wtb_label_artists.append(t)

        # --- Per-face widgets -------------------------------------------
        for k, fid in enumerate(self.chain):
            box_x = left + k * slot + slot * 0.06
            box_w = slot * 0.88
            color = FACE_COLORS[fid % len(FACE_COLORS)]
            is_flex   = (k == self.flex_face_chain_idx)
            is_locked = self.width_fixed[k]

            # Face-ID label (append "[flex]" tag for the flex face)
            tag = ' [flex]' if is_flex else ''
            lbl = self.fig.text(
                box_x + box_w / 2, lbl_y, f'F{fid}{tag}',
                ha='center', va='bottom', color=color,
                fontsize=7.5, fontweight='bold',
                transform=self.fig.transFigure)
            self._wtb_label_artists.append(lbl)

            # Width text box — border brightens when locked
            ax_tb = self.fig.add_axes([box_x, box_y, box_w, box_h])
            border_lw = 2.2 if is_locked else 1.0
            for sp in ax_tb.spines.values():
                sp.set_edgecolor(color)
                sp.set_linewidth(border_lw)

            tb = TextBox(ax_tb, '',
                         initial=f'{self.real_w[fid]:.2f}',
                         color='#16213e', hovercolor='#1e3050')
            tb.text_disp.set_color('white')
            tb.text_disp.set_fontsize(9)
            tb.text_disp.set_ha('center')

            def _make_submit(face_id):
                def _cb(text):
                    try:
                        w = float(text)
                        if w > 0.0:
                            self.real_w[face_id] = w
                            print(f'  F{face_id} width: {w:.2f} m')
                            self._refresh(sync_inputs=False)
                    except ValueError:
                        pass
                return _cb

            tb.on_submit(_make_submit(fid))
            self._wtb[fid] = tb
            self._wtb_axes.append(ax_tb)

            # Lock toggle button
            ax_lock = self.fig.add_axes([box_x, lock_y, box_w, lock_h])
            lock_color = '#1a4a2a' if is_locked else '#2a2a2a'
            lock_hover = '#2a6a3a' if is_locked else '#3a3a3a'
            lock_label = 'Fixed' if is_locked else 'Free'
            btn = Button(ax_lock, lock_label,
                         color=lock_color, hovercolor=lock_hover)
            btn.label.set_color('white')
            btn.label.set_fontsize(7.5)

            def _make_toggle(chain_k):
                def _cb(_):
                    self._toggle_width_fixed(chain_k)
                return _cb

            btn.on_clicked(_make_toggle(k))
            self._lock_btns[k] = btn
            self._lock_axes.append(ax_lock)

        # --- Flex-face row ------------------------------------------------
        t = self.fig.text(0.003, flex_y + flex_h / 2,
                          'FLEX FACE', va='center', ha='left',
                          fontsize=6, color='#aaaaaa', fontweight='bold',
                          transform=self.fig.transFigure)
        self._wtb_label_artists.append(t)

        flex_fid   = self.chain[self.flex_face_chain_idx]
        flex_color = FACE_COLORS[flex_fid % len(FACE_COLORS)]

        self._ax_flex_btn = self.fig.add_axes([0.10, flex_y, 0.17, flex_h])
        self._btn_flex = Button(
            self._ax_flex_btn,
            f'F{flex_fid}  (click to cycle)',
            color='#0a3535', hovercolor='#185a5a')
        self._btn_flex.label.set_color(flex_color)
        self._btn_flex.label.set_fontsize(8)
        self._btn_flex.on_clicked(lambda _: self._cycle_flex_face())

        t = self.fig.text(0.285, flex_y + flex_h / 2,
                          'Tolerance +/- m:',
                          va='center', ha='left', fontsize=8,
                          color='#aaaaaa',
                          transform=self.fig.transFigure)
        self._wtb_label_artists.append(t)

        self._ax_flex_tol = self.fig.add_axes([0.395, flex_y, 0.075, flex_h])
        for sp in self._ax_flex_tol.spines.values():
            sp.set_edgecolor('#aaaaaa')
            sp.set_linewidth(1.2)
        self._tb_tol = TextBox(self._ax_flex_tol, '',
                               initial=f'{self.flex_tolerance:.1f}',
                               color='#16213e', hovercolor='#1e3050')
        self._tb_tol.text_disp.set_color('white')
        self._tb_tol.text_disp.set_fontsize(9)
        self._tb_tol.text_disp.set_ha('center')

        def _on_tol(text):
            try:
                t = float(text)
                if t >= 0:
                    self.flex_tolerance = t
                    print(f'  Flex tolerance: +/-{t:.1f} m')
            except ValueError:
                pass

        self._tb_tol.on_submit(_on_tol)

    def _toggle_width_fixed(self, chain_k: int):
        self.width_fixed[chain_k] = not self.width_fixed[chain_k]
        fid   = self.chain[chain_k]
        state = 'Fixed' if self.width_fixed[chain_k] else 'Free'
        print(f'  F{fid} width: {state}')
        self._build_width_inputs()
        self._refresh(sync_inputs=False)

    def _cycle_flex_face(self):
        N = len(self.chain)
        self.flex_face_chain_idx = (self.flex_face_chain_idx + 1) % N
        fid = self.chain[self.flex_face_chain_idx]
        print(f'  Flex face: F{fid}')
        self._build_width_inputs()
        self._refresh(sync_inputs=False)

    def _toggle_convex(self):
        self.force_convex = not self.force_convex
        if self.force_convex:
            self._btn_convex.label.set_text('Convex: ON')
            self._btn_convex.ax.set_facecolor('#1a4a2a')
            print('  Force convex: ON  (sum of corner angles must equal 360 deg)')
        else:
            self._btn_convex.label.set_text('Convex: OFF')
            self._btn_convex.ax.set_facecolor('#2a2a2a')
            print('  Force convex: OFF')
        self.fig.canvas.draw_idle()

    def _sync_width_inputs(self):
        """Push current real_w values back into the text boxes."""
        for fid, tb in getattr(self, '_wtb', {}).items():
            new_val = f'{self.real_w[fid]:.2f}'
            if tb.text != new_val:
                tb.set_val(new_val)
        # Sync tolerance box too
        tb_tol = getattr(self, '_tb_tol', None)
        if tb_tol is not None:
            new_tol = f'{self.flex_tolerance:.1f}'
            if tb_tol.text != new_tol:
                tb_tol.set_val(new_tol)

    # ── Rendering ─────────────────────────────────────────────────────────

    def _refresh(self, validity_msg: str = '', is_valid: bool | None = None,
                 sync_inputs: bool = True):
        walls = walls_from_angles(
            self.chain, self.real_w, self.real_h,
            self.corner_angles, self.n_floors)

        self._draw_2d(walls)
        self._draw_3d(walls)

        err   = closure_error_m(self.chain, self.real_w, self.corner_angles)
        err_m = float(np.linalg.norm(err))
        n_fixed  = sum(m == 'fixed'  for m in self.corner_mode)
        n_free   = sum(m == 'free'   for m in self.corner_mode)
        n_acute  = sum(m == 'acute'  for m in self.corner_mode)
        n_obtuse = sum(m == 'obtuse' for m in self.corner_mode)

        # Determine current validity if not supplied
        if is_valid is None:
            ok, reason = solution_is_valid(self.chain, self.real_w,
                                           self.corner_angles)
        else:
            ok = is_valid

        convex_tag = '  [Convex forced]' if self.force_convex else ''
        hint = validity_msg or ('Valid' if ok else 'Self-intersecting — adjust corner constraints and Solve again')
        hint += convex_tag
        status_color = 'white' if ok else '#FF6B6B'

        parts = [f"{n_fixed} fixed"]
        if n_free:   parts.append(f"{n_free} free")
        if n_acute:  parts.append(f"{n_acute} acute")
        if n_obtuse: parts.append(f"{n_obtuse} obtuse")
        self._status_text.set_text(
            f"Corners: {', '.join(parts)}  |  "
            f"Closure error: {err_m:.2f} m  |  {hint}"
        )
        self._status_text.set_color(status_color)

        # Keep text boxes in sync whenever real_w may have changed externally
        # (e.g. after solving or reset).  Skipped when the text box itself
        # triggered this refresh to avoid a redundant set_val round-trip.
        if sync_inputs:
            self._sync_width_inputs()

        self.fig.canvas.draw_idle()

    def _draw_2d(self, walls):
        self.ax2d.clear()
        self.ax2d.set_facecolor('#16213e')
        self.ax2d.set_aspect('equal')
        self.ax2d.set_title('Floor Plan — click corners to toggle',
                            color='white', fontsize=11, fontweight='bold')
        self.ax2d.tick_params(colors='white')
        self.ax2d.set_xlabel('X (m)', color='white', fontsize=9)
        self.ax2d.set_ylabel('Y (m)', color='white', fontsize=9)
        self.ax2d.grid(True, color='#2a3a5c', linewidth=0.4)
        for sp in self.ax2d.spines.values():
            sp.set_edgecolor('#444')

        # Wall lines
        for w in walls:
            color = FACE_COLORS[w.face_id % len(FACE_COLORS)]
            self.ax2d.plot([w.p0[0], w.p1[0]], [w.p0[1], w.p1[1]],
                           color=color, lw=3.5)
            mid  = (w.p0 + w.p1) / 2
            d    = w.p1 - w.p0
            norm = np.linalg.norm(d)
            perp = (np.array([-d[1], d[0]]) / norm * 1.5) if norm > 0 \
                   else np.array([0, 1.5])
            self.ax2d.text(mid[0] + perp[0], mid[1] + perp[1],
                           f"F{w.face_id}\n{w.width_m:.1f}m",
                           color=color, fontsize=7.5, ha='center',
                           va='center', fontweight='bold')

        # Corner circles and labels
        N = len(walls)
        self._corner_positions = []   # (x, y) in data coords
        mode_suffix = {'fixed': '', 'free': '', 'acute': ' <90', 'obtuse': ' >90'}
        radius = max(self.real_w.values()) * 0.025
        for i, w in enumerate(walls):
            cx, cy = w.p1
            self._corner_positions.append((cx, cy))
            mode  = self.corner_mode[i]
            color = CORNER_COLORS[mode]
            circle = plt.Circle((cx, cy), radius,
                                 color=color, zorder=5, alpha=0.9)
            self.ax2d.add_patch(circle)
            suffix    = mode_suffix[mode]
            angle_str = f"{self.corner_angles[i]:.1f}°{suffix}"
            self.ax2d.text(cx + radius * 1.6, cy,
                           f"{self.corner_labels[i]}\n{angle_str}",
                           color=color, fontsize=7, ha='left', va='center',
                           fontweight='bold',
                           bbox=dict(fc='#111', ec='none',
                                     alpha=0.7, pad=1))

        # Closing dashed line (gap indicator when not closed)
        if walls:
            last  = walls[-1].p1
            first = walls[0].p0
            gap   = np.linalg.norm(last - first)
            if gap > 0.05:
                self.ax2d.plot([last[0], first[0]], [last[1], first[1]],
                               '--', color='#aaaaaa', lw=1.0, alpha=0.5,
                               label=f'gap {gap:.1f} m')
                self.ax2d.legend(fontsize=8, facecolor='#222',
                                 labelcolor='white', edgecolor='#444')

        self.ax2d.autoscale_view()

    def _draw_3d(self, walls):
        self.ax3d.clear()
        self.ax3d.set_facecolor('#16213e')
        self.ax3d.set_title('3-D Building Model',
                            color='white', fontsize=11, fontweight='bold')
        for axis in (self.ax3d.xaxis, self.ax3d.yaxis, self.ax3d.zaxis):
            axis.label.set_color('white')
            axis.set_tick_params(labelcolor='white')

        for w in walls:
            color = FACE_COLORS[w.face_id % len(FACE_COLORS)]
            poly  = Poly3DCollection([[w.verts[k] for k in range(4)]],
                                     alpha=0.40, facecolor=color,
                                     edgecolor='#cccccc', linewidth=0.8)
            self.ax3d.add_collection3d(poly)

            if w.n_floors > 1:
                fh = w.height_m / w.n_floors
                for fl in range(1, w.n_floors):
                    z = fl * fh
                    self.ax3d.plot(
                        [w.verts[0, 0], w.verts[1, 0]],
                        [w.verts[0, 1], w.verts[1, 1]],
                        [z, z], color='#aaaaaa', lw=0.5, alpha=0.6)

            ctr = w.verts.mean(axis=0)
            self.ax3d.text(ctr[0], ctr[1], ctr[2],
                           f"F{w.face_id}", fontsize=8,
                           ha='center', color='white')

        if walls:
            roof = [w.verts[3] for w in walls]
            self.ax3d.add_collection3d(
                Poly3DCollection([roof], alpha=0.15,
                                 facecolor='#888', edgecolor='#ccc'))

            all_v = np.vstack([w.verts for w in walls])
            xs, ys, zs = all_v[:, 0], all_v[:, 1], all_v[:, 2]
            mg = max(xs.max()-xs.min(), ys.max()-ys.min()) * 0.15
            self.ax3d.set_xlim(xs.min()-mg, xs.max()+mg)
            self.ax3d.set_ylim(ys.min()-mg, ys.max()+mg)
            self.ax3d.set_zlim(0, zs.max() * 1.25)

        self.ax3d.set_xlabel('X (m)', fontsize=9)
        self.ax3d.set_ylabel('Y (m)', fontsize=9)
        self.ax3d.set_zlabel('Z (m)', fontsize=9)
        self.ax3d.view_init(elev=28, azim=-50)

    # ── Event handlers ─────────────────────────────────────────────────────

    def _on_click(self, event):
        if event.inaxes is not self.ax2d or event.xdata is None:
            return
        if event.button != 1:
            return
        cx, cy = event.xdata, event.ydata

        # Find nearest corner
        best_i, best_d = -1, self.CORNER_CLICK_RADIUS
        for i, (px, py) in enumerate(getattr(self, '_corner_positions', [])):
            d = np.hypot(cx - px, cy - py)
            if d < best_d:
                best_d, best_i = d, i

        if best_i < 0:
            return

        # Cycle through: fixed -> free -> acute -> obtuse -> fixed
        cur   = self.corner_mode[best_i]
        nxt   = CORNER_MODES[(CORNER_MODES.index(cur) + 1) % len(CORNER_MODES)]
        self.corner_mode[best_i] = nxt
        if nxt == 'fixed':
            self.corner_angles[best_i] = 90.0   # snap back to 90 when locking

        label = self.corner_labels[best_i]
        desc  = {'fixed': 'FIXED 90°', 'free': 'FREE (any)',
                 'acute': 'ACUTE (<90°)', 'obtuse': 'OBTUSE (>90°)'}[nxt]
        print(f"  Corner {label}: {desc}")
        self._refresh()

    def _on_solve(self):
        free_idx = [i for i, m in enumerate(self.corner_mode) if m != 'fixed']
        if len(free_idx) < 2:
            self._status_text.set_text(
                "Need at least 2 non-fixed corners to solve. "
                "Click green corners to cycle them to Free / Acute / Obtuse.")
            self._status_text.set_color('#FFD700')
            self.fig.canvas.draw_idle()
            return

        # Per-angle bounds derived from corner mode
        ang_bounds = [CORNER_BOUNDS[self.corner_mode[i]] for i in free_idx]

        flex_fid = self.chain[self.flex_face_chain_idx]
        labels   = [self.corner_labels[i] for i in free_idx]
        modes    = [self.corner_mode[i]   for i in free_idx]
        print(f"\nSolving {len(free_idx)} free angle(s):")
        for lbl, m, b in zip(labels, modes, ang_bounds):
            print(f"  {lbl}: {m}  bounds {b[0]:.0f}-{b[1]:.0f} deg")
        print(f"  Flex face: F{flex_fid}  (+/-{self.flex_tolerance:.1f} m)")
        print("  Searching over starting points — may take a few seconds...")

        solved, flex_w, is_valid, msg = solve_closure(
            self.chain, self.real_w, self.corner_angles, free_idx,
            flex_chain_idx=self.flex_face_chain_idx,
            flex_tol=self.flex_tolerance,
            angle_bounds_override=ang_bounds,
            force_convex=self.force_convex)
        self.corner_angles = solved

        for i in free_idx:
            print(f"  {self.corner_labels[i]}: {self.corner_angles[i]:.1f} deg")
        if flex_w is not None:
            old_w = self.real_w[flex_fid]
            self.real_w[flex_fid] = flex_w
            print(f"  F{flex_fid} (flex) width: {old_w:.2f} -> {flex_w:.2f} m")
        print(f"  {msg}")

        self._refresh(validity_msg=msg, is_valid=is_valid)

    def _on_reset(self):
        self.corner_angles[:] = 90.0
        self.corner_mode      = ['fixed'] * len(self.chain)
        self._solve_and_refresh()

    def _on_save(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f'{self.building}_geometry.png'
        self.fig.savefig(path, dpi=130, bbox_inches='tight',
                         facecolor=self.fig.get_facecolor())
        print(f"\nSaved: {path}")
        self._status_text.set_text(f"Saved: {path}")
        self.fig.canvas.draw_idle()

    def _on_save_geometry(self):
        try:
            path = self._save_floorspace()
            msg = f"Geometry saved  →  {path}"
            print(f"\n{'='*60}")
            print(f"  GEOMETRY SAVED")
            print(f"{'='*60}")
            print(f"  File : {path}")
            print(f"\n  NEXT STEPS")
            print(f"  ──────────────────────────────────────────────────")
            print(f"  1. Return to the PrestoGeometry Launcher.")
            print(f"  2. Use 'Open Output Folder' (Step 4) to locate the")
            print(f"     saved .json file.")
            print(f"  3. Load it in the Floorspace.js web editor to review")
            print(f"     and refine the floor plan visually:")
            print(f"     https://nrel.github.io/floorspace.js/")
            print(f"     (File → Import → select the .json)")
            print(f"  4. Share the .json with your team for IDF / OSM /")
            print(f"     HPXML export.")
            print(f"{'='*60}\n")
        except Exception as exc:
            msg = f"Save failed: {exc}"
            print(f"\nERROR saving floorspace.js: {exc}")
        self._status_text.set_text(msg)
        self.fig.canvas.draw_idle()

    def _save_floorspace(self) -> Path:
        from presto_geometry.models.building import (
            Building, Edge, Face, Geometry, Space, SpaceType, Story,
            ThermalZone, Vertex,
        )
        from presto_geometry.exporters.floorspace import building_to_floorspace_dict

        # Extract the ordered floor-plan corners from the current wall layout
        segs = floor_plan_segments(self.chain, self.real_w, self.corner_angles)
        polygon_xy = [list(seg[0]) for seg in segs]   # N corner (x, y) pairs

        # Build geometry (one face wrapping the full footprint)
        n = len(polygon_xy)
        face_id    = "f-s1-1"
        vertex_ids = [f"v-s1-{i}" for i in range(n)]
        edge_ids   = [f"e-s1-{i}" for i in range(n)]

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
        face     = Face(id=face_id, edge_ids=list(edge_ids), edge_order=[0] * n)
        geometry = Geometry(id="geom-s1", vertices=vertices, edges=edges, faces=[face])

        # Use the total building height as the single-story floor-to-ceiling height
        total_h = float(next(iter(self.real_h.values())))

        tz    = ThermalZone(id="tz-default",   name="Default Zone",      color="#88aadd")
        stype = SpaceType(  id="stype-default", name="Default Space Type", color="#dddddd")
        space = Space(
            id="space-s1-1", name="Ground Floor Space",
            face_id=face_id,
            thermal_zone_id=tz.id,
            space_type_id=stype.id,
        )
        story = Story(
            id="story-1", name="Floor 1",
            floor_to_ceiling_height=total_h,
            geometry=geometry,
            spaces=[space],
        )
        building = Building(name=self.building)
        building.thermal_zones.append(tz)
        building.space_types.append(stype)
        building.stories.append(story)

        doc = building_to_floorspace_dict(building)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / f'{self.building}.json'
        import json as _json
        with out_path.open('w', encoding='utf-8') as fh:
            _json.dump(doc, fh, indent=2)
        return out_path

    def _solve_and_refresh(self):
        self._refresh(validity_msg='', is_valid=None)

    def run(self):
        plt.show()


# ── Batch (non-interactive) output ────────────────────────────────────────────

def save_static(building, chain, real_w, real_h, n_floors, output_dir):
    """Save floor-plan + 3-D PNG without launching an interactive window."""
    corner_angles = np.full(len(chain), 90.0)
    walls = walls_from_angles(chain, real_w, real_h, corner_angles, n_floors)

    fig = plt.figure(figsize=(18, 8))
    fig.patch.set_facecolor('#1a1a2e')
    ax2d = fig.add_subplot(1, 2, 1)
    ax2d.set_facecolor('#16213e')
    ax2d.set_aspect('equal')
    ax2d.set_title('Floor Plan', color='white', fontsize=12, fontweight='bold')
    ax2d.tick_params(colors='white')
    ax2d.set_xlabel('X (m)', color='white')
    ax2d.set_ylabel('Y (m)', color='white')
    ax2d.grid(color='#2a3a5c', linewidth=0.4)

    for w in walls:
        color = FACE_COLORS[w.face_id % len(FACE_COLORS)]
        ax2d.plot([w.p0[0], w.p1[0]], [w.p0[1], w.p1[1]], color=color, lw=3.5)
        mid  = (w.p0 + w.p1) / 2
        d    = w.p1 - w.p0
        norm = np.linalg.norm(d)
        perp = np.array([-d[1], d[0]]) / norm * 1.5 if norm > 0 else np.array([0, 1.5])
        ax2d.text(mid[0]+perp[0], mid[1]+perp[1],
                  f"F{w.face_id}\n{w.width_m:.1f}m",
                  color=color, fontsize=8, ha='center', va='center',
                  fontweight='bold')
    ax2d.autoscale_view()

    ax3d = fig.add_subplot(1, 2, 2, projection='3d')
    ax3d.set_facecolor('#16213e')
    ax3d.set_title('3-D Building Model', color='white', fontsize=12, fontweight='bold')
    for axis in (ax3d.xaxis, ax3d.yaxis, ax3d.zaxis):
        axis.label.set_color('white')
        axis.set_tick_params(labelcolor='white')

    for w in walls:
        color = FACE_COLORS[w.face_id % len(FACE_COLORS)]
        ax3d.add_collection3d(
            Poly3DCollection([[w.verts[k] for k in range(4)]],
                             alpha=0.40, facecolor=color, edgecolor='#ccc', lw=0.8))

    if walls:
        roof = [w.verts[3] for w in walls]
        ax3d.add_collection3d(
            Poly3DCollection([roof], alpha=0.15, facecolor='#888', edgecolor='#ccc'))
        all_v = np.vstack([w.verts for w in walls])
        xs, ys, zs = all_v[:,0], all_v[:,1], all_v[:,2]
        mg = max(xs.max()-xs.min(), ys.max()-ys.min()) * 0.15
        ax3d.set_xlim(xs.min()-mg, xs.max()+mg)
        ax3d.set_ylim(ys.min()-mg, ys.max()+mg)
        ax3d.set_zlim(0, zs.max()*1.25)
    ax3d.set_xlabel('X (m)', fontsize=9)
    ax3d.set_ylabel('Y (m)', fontsize=9)
    ax3d.set_zlabel('Z (m)', fontsize=9)
    ax3d.view_init(elev=28, azim=-50)

    plt.suptitle(f'{building} — Building Geometry',
                 color='white', fontsize=14, fontweight='bold')
    plt.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f'{building}_geometry.png'
    plt.savefig(path, dpi=130, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    print(f"\nSaved: {path}")
    plt.show()


# ── CLI entry-point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Assemble 3-D building geometry from annotations.')
    parser.add_argument('building', nargs='?', default='UnivStThomas_1loop')
    parser.add_argument('--floors',        type=int,   default=DEFAULT_N_FLOORS)
    parser.add_argument('--floor-height',  type=float, default=DEFAULT_FLOOR_H_M,
                        dest='floor_height')
    parser.add_argument('--no-interactive', action='store_true',
                        help='Save static PNG without opening the editor')
    parser.add_argument('--widths', type=str, default='',
                        metavar='F0=13,F1=47,...',
                        help='Override face widths (metres) from a known source '
                             '(e.g. Google Earth).  Format: F0=13,F1=47,F3=40')
    args = parser.parse_args()

    building   = args.building
    n_floors   = args.floors
    floor_h_m  = args.floor_height
    output_dir = OUTPUT_DIR_BASE / building

    print(f"\n{'='*60}")
    print(f"  BUILDING GEOMETRY ASSEMBLY  -  {building}")
    print(f"{'='*60}")
    print(f"  Floors       : {n_floors}")
    print(f"  Floor height : {floor_h_m} m  ->  total {n_floors*floor_h_m:.1f} m")

    ann   = load_annotations(building)
    faces = collect_face_geometries(ann)
    if not faces:
        print("No face annotations found.  Run annotate_building.py first.")
        sys.exit(1)

    face_ids = sorted(faces.keys())
    print(f"\nAnnotated faces : {face_ids}")

    directed = build_directed_adjacency(ann)
    print("\nDirected adjacency:")
    for fid in face_ids:
        d = directed.get(fid, {})
        print(f"  Face {fid}:  left={d.get('left')}  right={d.get('right')}")

    chain = build_chain(directed, face_ids)
    print(f"\nAssembly chain  : {chain}")

    real_h = {fid: n_floors * floor_h_m for fid in face_ids}
    real_w = {}
    for fid, fg in faces.items():
        ar = fg.effective_aspect_ratio()
        real_w[fid] = real_h[fid] * ar if ar else real_h[fid] * 2.0

    # Apply any --widths overrides (e.g. from Google Earth measurements)
    width_overrides: dict = {}
    if args.widths:
        for token in args.widths.split(','):
            token = token.strip()
            if not token:
                continue
            try:
                key, val = token.split('=')
                fid_ov = int(key.strip().lstrip('Ff'))
                width_overrides[fid_ov] = float(val.strip())
            except ValueError:
                print(f"  WARNING: could not parse --widths token '{token}' "
                      f"(expected format F0=13.0) — skipping")
    if width_overrides:
        print("\nApplying manual width overrides:")
        for fid_ov, w_ov in sorted(width_overrides.items()):
            if fid_ov in real_w:
                print(f"  F{fid_ov}: {real_w[fid_ov]:.1f} m  ->  {w_ov:.1f} m  (manual)")
                real_w[fid_ov] = w_ov
            else:
                print(f"  WARNING: F{fid_ov} not in annotations — override ignored")

    print("\nFace dimensions:")
    for fid in chain:
        fg      = faces[fid]
        ar      = fg.effective_aspect_ratio()
        ar_str  = f'{ar:.3f}' if ar else 'N/A'
        per_img = fg._per_image_ratios()
        ratios  = [r for _, r in per_img]
        spread  = ''
        if len(ratios) > 1:
            lo = min(ratios) * real_h[fid]
            hi = max(ratios) * real_h[fid]
            med = float(np.median(ratios)) * real_h[fid]
            spread = f'  [per-image range {lo:.1f}–{hi:.1f} m, median {med:.1f} m]'
            if hi / lo > 1.5:
                spread += '  ** foreshortening suspected **'
        print(f"  F{fid}: {real_w[fid]:.1f} m wide x {real_h[fid]:.1f} m tall"
              f"  (best-image aspect {ar_str}){spread}")
        if len(per_img) > 1:
            for img_name, r in per_img:
                print(f"       [{img_name}]  ratio={r:.3f}"
                      f"  -> {real_h[fid] * r:.1f} m")

    if args.no_interactive:
        save_static(building, chain, real_w, real_h, n_floors, output_dir)
    else:
        editor = AssemblyEditor(building, chain, real_w, real_h,
                                n_floors, output_dir)
        print(f"\n  GETTING STARTED — ASSEMBLY EDITOR")
        print(f"  ──────────────────────────────────────────────────")
        print(f"  The floor plan is shown on the left; 3-D view on")
        print(f"  the right.  Face widths are estimated from photos.")
        print(f"\n  STEP A — Review dimensions")
        print(f"    Each face has a width text box at the bottom.")
        print(f"    If you know a dimension (e.g. from Google Earth),")
        print(f"    type it and press Enter, then click 'Fixed' to lock it.")
        print(f"\n  STEP B — Free the corners you want to adjust")
        print(f"    Click any green (90°) corner to cycle its mode:")
        print(f"      Green  = fixed at 90°")
        print(f"      Yellow = free  (solver picks the best angle)")
        print(f"      Orange = acute  (forced < 90°)")
        print(f"      Blue   = obtuse (forced > 90°)")
        print(f"    Need at least 2 non-fixed corners to solve.")
        print(f"\n  STEP C — Solve")
        print(f"    Click [Solve] to find angles that close the polygon.")
        print(f"    Enable 'Convex: ON' to force a convex (non-concave)")
        print(f"    building shape before solving.")
        print(f"    The flex face (shown as [flex] in the label row) is")
        print(f"    allowed to stretch ±tolerance to help close the shape.")
        print(f"\n  STEP D — Save")
        print(f"    [Save PNG]      — saves a floor-plan image")
        print(f"    [Save Geometry] — writes the Floorspace.js .json file")
        print(f"{'='*60}\n")
        editor.run()


if __name__ == '__main__':
    main()
