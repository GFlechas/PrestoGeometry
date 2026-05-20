"""
Generate edge_detection_prototype.ipynb using nbformat.
Run this script any time you want to regenerate the notebook from scratch.

Usage:
    python notebooks/generate_prototype.py
"""

import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell
from pathlib import Path

HERE = Path(__file__).parent


# ── helpers ──────────────────────────────────────────────────────────────────

def md(text: str):
    return new_markdown_cell(text.strip())


def code(text: str):
    return new_code_cell(text.strip())


# ── cells ────────────────────────────────────────────────────────────────────

cells = []

# ── 0: Title ─────────────────────────────────────────────────────────────────
cells.append(md("""
# Building Edge Detection — Prototype Notebook

**PrestoGeometry · HackSimBuild 2026**

Iterative prototype for extracting building geometry (facade outlines + window
openings) from a sequence of walk-around photos.

---

### Running from the command line

Execute all cells non-interactively and save the results.
**Run from the `notebooks/` directory** so nbconvert resolves output paths correctly:

```bash
cd notebooks
jupyter nbconvert --to notebook --execute edge_detection_prototype.ipynb \\
    --ExecutePreprocessor.kernel_name=python3 \\
    --ExecutePreprocessor.timeout=300
```

The executed copy is saved as `edge_detection_prototype_executed.ipynb` (gitignored).
Annotated output images are always written to `data/outputs/edge_detection/`
regardless of how the notebook is run.

---

### Pipeline stages

| Stage | What it does |
|-------|-------------|
| 0 | Lens normalisation cascade (Lensfun → self-cal → heuristic → passthrough) |
| 1 | Sky / ground masking |
| 2 | Line-segment extraction (Canny + Hough) |
| 3 | Vanishing-point analysis |
| 4 | Sequential facade grouping |
| 5 | Collinear gap bridging (occlusion recovery) |
| 6 | Window candidate detection |
"""))

# ── 1: Imports & env check ───────────────────────────────────────────────────
cells.append(md("## Setup"))

cells.append(code("""
import sys, warnings
warnings.filterwarnings('ignore')

import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.cm as cm
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from collections import Counter

from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d

try:
    import lensfunpy
    LENSFUN_AVAILABLE = True
except ImportError:
    LENSFUN_AVAILABLE = False

print(f"cv2        {cv2.__version__}")
print(f"numpy      {np.__version__}")
print(f"lensfunpy  {'ok' if LENSFUN_AVAILABLE else 'NOT INSTALLED — will use fallback'}")
print(f"Python     {sys.version.split()[0]}")
"""))

# ── 2: Configuration ─────────────────────────────────────────────────────────
cells.append(md("""## Configuration

All tunable parameters live here.

| Switch | Effect |
|--------|--------|
| `ACTIVE_BUILDING` | Which photo set to run (`'UnivStThomas'` or `'LoringPark'`) |
| `DEV_MODE = True` | Shrinks images to `DEV_MAX_DIM` px wide, caps sequence at `DEV_MAX_IMAGES` — fast iteration on low-memory hardware |
| `DEV_MODE = False` | Full-resolution, full sequence — for final comparison runs |
"""))

cells.append(code("""
# ── Dev / full mode toggle ────────────────────────────────────────────────────
# Set DEV_MODE = True on low-memory machines (Surface Pro 8, etc.) for fast
# iteration.  All algorithm parameters below auto-scale to the working resolution.

DEV_MODE       = True    # ← flip to False for full-resolution runs
DEV_MAX_DIM    = 800     # longest edge in pixels when DEV_MODE is on
DEV_MAX_IMAGES = 6       # cap sequence length (pick a spread: first + last + middle)

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path('..').resolve()          # notebook lives one level below repo root

PHOTO_DIRS = {
    'UnivStThomas': REPO_ROOT / 'photos' / 'UnivStThomas',
    'LoringPark':   REPO_ROOT / 'photos' / 'LoringPark',
}
OUTPUT_DIR = REPO_ROOT / 'data' / 'outputs' / 'edge_detection'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Change this to switch buildings
ACTIVE_BUILDING = 'UnivStThomas'

# ── Line detection ─────────────────────────────────────────────────────────────
# Base values are tuned for full resolution (~3000 px wide).
# In DEV_MODE they scale down proportionally with the image.
_BASE_WIDTH      = 3000
CANNY_LOW        = 50
CANNY_HIGH       = 150
HOUGH_THRESHOLD  = 50    # minimum Hough accumulator votes
HOUGH_MIN_LEN    = 60    # px — minimum segment length to keep
HOUGH_MAX_GAP    = 15    # px — max in-segment gap to bridge during Hough
VERT_TOL_DEG     = 12    # degrees from vertical
HORIZ_TOL_DEG    = 15    # degrees from horizontal

# ── Sky detection (HSV) ───────────────────────────────────────────────────────
SKY_HUE_LO,  SKY_HUE_HI   = 90, 130   # blue hue band
SKY_SAT_MIN, SKY_VAL_MIN   = 50, 150   # clear-sky thresholds
OVERCAST_SAT_MAX            = 30        # near-white overcast sky
OVERCAST_VAL_MIN            = 200

# ── Heuristic k1 distortion by 35mm-equivalent focal length ───────────────────
DISTORTION_HEURISTIC: Dict[Tuple[int,int], float] = {
    (0,  14): -0.30,
    (14, 18): -0.22,
    (18, 22): -0.15,
    (22, 28): -0.07,
    (28, 35): -0.03,
    (35, 999): -0.01,
}

# ── Facade grouping ───────────────────────────────────────────────────────────
VP_SHIFT_THRESHOLD  = 0.35  # normalised VP-x shift in smoothed trajectory → new facade
VP_SMOOTH_WINDOW    = 3     # rolling-median window for VP trajectory smoothing
VP_MIN_FACADE_IMGS  = 2     # merge any facade shorter than this into its neighbour

# ── Gap bridging (base values at _BASE_WIDTH; scaled at load time) ─────────────
COLLINEAR_Y_TOL   = 10     # px: max y-distance between segments in same group
BRIDGE_MAX_GAP_PX = 100    # px: max gap between collinear segments to bridge

# ── Scale calibration ─────────────────────────────────────────────────────────
FLOOR_HEIGHT_M_COMMERCIAL  = 3.5   # m — commercial / office
FLOOR_HEIGHT_M_RESIDENTIAL = 2.7   # m — residential
BUILDING_TYPE = 'commercial'       # 'commercial' | 'residential'

# ── Print active config ───────────────────────────────────────────────────────
mode_str = (f"DEV  (max {DEV_MAX_DIM}px / {DEV_MAX_IMAGES} images)"
            if DEV_MODE else "FULL (original resolution)")
print(f"Mode            : {mode_str}")
print(f"Active building : {ACTIVE_BUILDING}")
print(f"Output dir      : {OUTPUT_DIR}")
"""))

# ── 3: Data structures ───────────────────────────────────────────────────────
cells.append(md("## Data structures"))

cells.append(code("""
@dataclass
class LensProfile:
    device_make:            str
    device_model:           str
    focal_length_physical:  float           # mm (from EXIF)
    focal_length_35mm:      int             # 35mm-equiv (from EXIF)
    image_width:            int
    image_height:           int
    camera_matrix:          Optional[np.ndarray] = None   # 3x3 K
    distortion_coeffs:      np.ndarray = field(default_factory=lambda: np.zeros(5))
    correction_method:      str = 'none'    # lensfun | self_calibration | heuristic | none
    correction_confidence:  str = 'none'    # high | medium | low | none


@dataclass
class ImageRecord:
    path:          Path
    building:      str
    timestamp:     str
    lens_profile:  Optional[LensProfile]  = None
    undistorted:   Optional[np.ndarray]  = None   # BGR after normalisation
    sky_mask:      Optional[np.ndarray]  = None   # bool H×W
    line_segments: Optional[np.ndarray]  = None   # N×5  [x1 y1 x2 y2 class]
                                                   # class: 0=H 1=V 2=diag
    facade_id:     Optional[int]         = None
    vp:            Optional[Tuple[float,float]] = None
"""))

# ── 4: Image loading + EXIF ──────────────────────────────────────────────────
cells.append(md("## Image loading & EXIF"))

cells.append(code("""
def load_exif(path: Path) -> dict:
    img = Image.open(path)
    raw = img._getexif() or {}
    return {TAGS.get(k, k): v for k, v in raw.items()}


def _dev_resize(img: np.ndarray, max_dim: int) -> np.ndarray:
    \"\"\"Uniformly scale image so its longest edge equals max_dim.\"\"\"
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_dim:
        return img
    scale = max_dim / longest
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _dev_subsample(paths: list, n: int) -> list:
    \"\"\"Pick n paths spread evenly across the full sequence.\"\"\"
    if len(paths) <= n:
        return paths
    indices = [round(i * (len(paths) - 1) / (n - 1)) for i in range(n)]
    return [paths[i] for i in sorted(set(indices))]


def load_image_sequence(building: str) -> List[ImageRecord]:
    folder    = PHOTO_DIRS[building]
    all_paths = sorted(folder.glob('*.jpg'))

    if DEV_MODE:
        all_paths = _dev_subsample(list(all_paths), DEV_MAX_IMAGES)

    records = []
    for p in all_paths:
        exif    = load_exif(p)
        fl_phys = float(exif.get('FocalLength', 0) or 0)
        fl_35   = int(exif.get('FocalLengthIn35mmFilm', 0) or 0)
        make    = exif.get('Make', 'unknown').strip()
        model   = exif.get('Model', 'unknown').strip()
        img_cv  = cv2.imread(str(p))

        if DEV_MODE:
            img_cv = _dev_resize(img_cv, DEV_MAX_DIM)

        h, w = img_cv.shape[:2]

        # Scale Hough parameters proportionally to working resolution
        scale_f = w / _BASE_WIDTH
        rec = ImageRecord(
            path=p,
            building=building,
            timestamp=exif.get('DateTime', p.stem),
            lens_profile=LensProfile(
                device_make=make,
                device_model=model,
                focal_length_physical=fl_phys,
                focal_length_35mm=fl_35,
                image_width=w,
                image_height=h,
            ),
        )
        records.append(rec)

    # Re-derive scaled Hough params from actual working width
    if records:
        actual_w = records[0].lens_profile.image_width
        scale_f  = actual_w / _BASE_WIDTH
        global HOUGH_MIN_LEN, HOUGH_MAX_GAP, HOUGH_THRESHOLD
        global COLLINEAR_Y_TOL, BRIDGE_MAX_GAP_PX
        HOUGH_MIN_LEN     = max(20, int(60  * scale_f))
        HOUGH_MAX_GAP     = max(5,  int(15  * scale_f))
        HOUGH_THRESHOLD   = max(20, int(50  * scale_f))
        COLLINEAR_Y_TOL   = max(4,  int(10  * scale_f))
        BRIDGE_MAX_GAP_PX = max(20, int(100 * scale_f))

    n_wide = sum(1 for r in records if r.lens_profile.focal_length_35mm <= 20)
    n_std  = len(records) - n_wide
    res    = f"{records[0].lens_profile.image_width}x{records[0].lens_profile.image_height}" if records else "n/a"
    print(f"Loaded {len(records)} images for '{building}'  [{res}]")
    print(f"  ultra-wide (<=20 mm eq.): {n_wide}   standard (>20 mm eq.): {n_std}")
    print(f"  Hough params scaled to {res}: min_len={HOUGH_MIN_LEN}  max_gap={HOUGH_MAX_GAP}  threshold={HOUGH_THRESHOLD}")
    return records


records = load_image_sequence(ACTIVE_BUILDING)
"""))

cells.append(code("""
# ── Thumbnail overview ────────────────────────────────────────────────────────
n     = len(records)
ncols = min(n, 8)
nrows = (n + ncols - 1) // ncols

fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 2.4, nrows * 2.0))
axes = np.array(axes).flatten()

for i, rec in enumerate(records):
    img = cv2.cvtColor(cv2.imread(str(rec.path)), cv2.COLOR_BGR2RGB)
    axes[i].imshow(img)
    fl    = rec.lens_profile.focal_length_35mm
    color = '#e74c3c' if fl <= 20 else '#27ae60'
    axes[i].set_title(f"{rec.path.stem[-6:]}\\n{fl}mm", fontsize=7, color=color)
    axes[i].axis('off')

for ax in axes[n:]:
    ax.axis('off')

plt.suptitle(
    f"{ACTIVE_BUILDING} — sequence overview  "
    f"(\\033[31mred\\033[0m = ultra-wide  green = standard)",
    fontsize=11
)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_00_sequence_overview.png', bbox_inches='tight', dpi=100)
plt.show()
print(f"Saved → {OUTPUT_DIR / f'{ACTIVE_BUILDING}_00_sequence_overview.png'}")
"""))

# ── 5: Stage 0 — Lens normalisation ─────────────────────────────────────────
cells.append(md("""
---
## Stage 0 — Lens Normalisation

Four-level cascade, attempted in order from highest to lowest fidelity.
Every image exits the chain with the same `LensProfile` structure regardless
of which level succeeded.

```
Level 1  Lensfun / manufacturer database      confidence: high
Level 2  Self-calibration from building lines  confidence: medium–high
Level 3  Heuristic from focal-length table     confidence: low
Level 4  Pass-through (no correction)          confidence: none
```
"""))

cells.append(code("""
# ── Camera matrix estimation from EXIF ───────────────────────────────────────

def estimate_camera_matrix(lp: LensProfile) -> np.ndarray:
    \"\"\"Estimate intrinsic matrix K from EXIF focal lengths + image resolution.\"\"\"
    w, h = lp.image_width, lp.image_height
    if lp.focal_length_physical > 0 and lp.focal_length_35mm > 0:
        # crop_factor = 35mm-equiv / physical focal length
        crop       = lp.focal_length_35mm / lp.focal_length_physical
        # sensor diagonal (mm) from 35mm standard diagonal (43.27 mm)
        sens_diag  = 43.27 / crop
        # assume 4:3 physical sensor aspect
        phys_ar    = w / h
        sens_h     = sens_diag / np.sqrt(1.0 + phys_ar ** 2)
        sens_w     = sens_h * phys_ar
        fx = lp.focal_length_physical * w / sens_w
        fy = lp.focal_length_physical * h / sens_h
    else:
        fx = fy = float(max(w, h))   # safe fallback

    K = np.array([[fx,  0, w / 2],
                  [ 0, fy, h / 2],
                  [ 0,  0,     1]], dtype=np.float64)
    return K


# Quick sanity check on our two lens types
for rec in records[:2]:
    lp = rec.lens_profile
    K  = estimate_camera_matrix(lp)
    print(f"{lp.focal_length_35mm}mm eq. → fx={K[0,0]:.0f}  fy={K[1,1]:.0f}  "
          f"cx={K[0,2]:.0f}  cy={K[1,2]:.0f}")
"""))

cells.append(code("""
# ── Level 1: Lensfun database ─────────────────────────────────────────────────

def _level1_lensfun(lp: LensProfile) -> Optional[np.ndarray]:
    \"\"\"
    Look up distortion coefficients via the Lensfun database.
    Returns (k1, k2, p1, p2, k3) array on success, None otherwise.
    \"\"\"
    if not LENSFUN_AVAILABLE:
        return None
    try:
        db   = lensfunpy.Database()
        cams = db.find_cameras(lp.device_make, lp.device_model, loose_search=True)
        if not cams:
            return None
        cam   = cams[0]
        lenses = db.find_lenses(cam, loose_search=True)
        if not lenses:
            return None
        lens = lenses[0]

        mod = lensfunpy.Modifier(lens, cam.crop_factor, lp.image_width, lp.image_height)
        mod.initialize(lp.focal_length_physical, 0.0, 1.0)

        # Extract polynomial distortion parameters from the lens object
        # lensfunpy exposes them as lens.distortion; fall back to zero if absent
        dist_terms = getattr(lens, 'distortion', None)
        if dist_terms is None:
            return None

        # Map lensfun k1/k2/k3 → OpenCV [k1, k2, p1, p2, k3]
        k1 = float(getattr(dist_terms, 'k1', 0.0))
        k2 = float(getattr(dist_terms, 'k2', 0.0))
        k3 = float(getattr(dist_terms, 'k3', 0.0))
        return np.array([k1, k2, 0.0, 0.0, k3])

    except Exception as exc:
        print(f"    Lensfun error: {exc}")
        return None
"""))

cells.append(code("""
# ── Level 2: Self-calibration from detected line straightness ─────────────────

def _level2_self_calibration(img_bgr: np.ndarray,
                               lp: LensProfile) -> Optional[np.ndarray]:
    \"\"\"
    Estimate radial distortion by measuring how much detected long horizontal
    line segments deviate from straightness.  Requires at least 5 segments
    spanning ≥1/3 of the image width.

    Returns [k1, 0, 0, 0, 0] on success, None if insufficient coverage.
    \"\"\"
    gray    = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges   = cv2.Canny(blurred, CANNY_LOW, CANNY_HIGH)

    min_len = lp.image_width // 3          # segments must span at least 1/3 width
    raw     = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                               minLineLength=min_len, maxLineGap=20)
    if raw is None:
        return None

    # Keep only near-horizontal segments
    h_lines = []
    for seg in raw:
        x1, y1, x2, y2 = seg[0]
        angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if angle < HORIZ_TOL_DEG or angle > 180 - HORIZ_TOL_DEG:
            h_lines.append((x1, y1, x2, y2))

    if len(h_lines) < 5:
        return None

    cx = lp.image_width  / 2.0
    cy = lp.image_height / 2.0
    r_norm = np.sqrt(cx ** 2 + cy ** 2)   # normalisation radius

    deviations, weights = [], []
    for x1, y1, x2, y2 in h_lines:
        # Midpoint deviation from the chord connecting endpoints
        xm = (x1 + x2) / 2.0
        ym = (y1 + y2) / 2.0
        y_chord = y1 + (y2 - y1) * ((xm - x1) / max(abs(x2 - x1), 1))
        dy_mid  = ym - y_chord   # positive = bows downward (barrel pulls outward)

        r  = np.sqrt((xm - cx) ** 2 + (ym - cy) ** 2) / r_norm
        wt = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)  # weight by length
        deviations.append((r, dy_mid))
        weights.append(wt)

    rs  = np.array([d[0] for d in deviations])
    dys = np.array([d[1] for d in deviations])
    wts = np.array(weights)

    # Model: dy_mid ≈ k1 * r^2 * scale_factor
    # Scale factor converts pixel deviation to normalised coords
    scale = cy   # approx: at r=1 a deviation of cy pixels is "1 unit"
    A    = (rs ** 2 * scale).reshape(-1, 1)
    b    = dys
    k1   = float(np.linalg.lstsq(A * wts[:, None], b * wts, rcond=None)[0][0])
    k1   = float(np.clip(k1, -0.5, 0.0))   # barrel only (negative k1)

    return np.array([k1, 0.0, 0.0, 0.0, 0.0])
"""))

cells.append(code("""
# ── Level 3: Heuristic from focal-length table ────────────────────────────────

def _level3_heuristic(lp: LensProfile) -> np.ndarray:
    \"\"\"Return k1 estimate from the focal-length lookup table.\"\"\"
    fl = lp.focal_length_35mm
    for (lo, hi), k1 in DISTORTION_HEURISTIC.items():
        if lo <= fl < hi:
            return np.array([k1, 0.0, 0.0, 0.0, 0.0])
    return np.array([-0.01, 0.0, 0.0, 0.0, 0.0])
"""))

cells.append(code("""
# ── Undistort helper ──────────────────────────────────────────────────────────

def _apply_undistort(img_bgr: np.ndarray,
                     K: np.ndarray,
                     dist: np.ndarray) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    new_K, roi = cv2.getOptimalNewCameraMatrix(K, dist, (w, h), alpha=1, newImgSize=(w, h))
    out         = cv2.undistort(img_bgr, K, dist, None, new_K)
    x, y, rw, rh = roi
    if rw > 0 and rh > 0:
        out = out[y:y + rh, x:x + rw]
        out = cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR)
    return out
"""))

cells.append(code("""
# ── Full cascade ──────────────────────────────────────────────────────────────

def run_normalisation_cascade(rec: ImageRecord) -> ImageRecord:
    \"\"\"
    Work through the four levels.  Attaches the winning LensProfile fields and
    sets rec.undistorted (BGR ndarray, same resolution as original).
    \"\"\"
    lp  = rec.lens_profile
    img = cv2.imread(str(rec.path))
    K   = estimate_camera_matrix(lp)
    lp.camera_matrix = K

    dist, method, confidence = None, 'none', 'none'

    # Level 1 — Lensfun
    dist = _level1_lensfun(lp)
    if dist is not None:
        method, confidence = 'lensfun', 'high'

    # Level 2 — self-calibration
    if dist is None:
        dist = _level2_self_calibration(img, lp)
        if dist is not None:
            method, confidence = 'self_calibration', 'medium'

    # Level 3 — heuristic
    if dist is None:
        dist = _level3_heuristic(lp)
        method, confidence = 'heuristic', 'low'

    lp.distortion_coeffs    = dist
    lp.correction_method    = method
    lp.correction_confidence = confidence

    # Level 4 — passthrough (distortion negligible for standard lens)
    if abs(dist[0]) < 0.005:
        lp.correction_method    = 'none'
        lp.correction_confidence = 'none'
        rec.undistorted = img
    else:
        rec.undistorted = _apply_undistort(img, K, dist)

    return rec


# Run cascade on every image
print(f"Running lens normalisation cascade on {len(records)} images ...\\n")
for rec in records:
    run_normalisation_cascade(rec)
    fl  = rec.lens_profile.focal_length_35mm
    k1  = rec.lens_profile.distortion_coeffs[0]
    mtd = rec.lens_profile.correction_method
    print(f"  {rec.path.name:<30} {fl:>3}mm eq.  k1={k1:+.3f}  [{mtd}]")

summary = Counter(r.lens_profile.correction_method for r in records)
print("\\nMethod summary:")
for m, n in summary.items():
    print(f"  {m}: {n} images")
"""))

cells.append(code("""
# ── Visualise normalisation effect ────────────────────────────────────────────
# Show one ultra-wide and one standard image, before/after

wide_recs = [r for r in records if r.lens_profile.focal_length_35mm <= 20]
std_recs  = [r for r in records if r.lens_profile.focal_length_35mm >  20]
samples   = []
if wide_recs: samples.append(wide_recs[len(wide_recs) // 2])
if std_recs:  samples.append(std_recs[len(std_recs) // 2])

fig, axes = plt.subplots(len(samples), 2, figsize=(16, 5 * len(samples)))
if len(samples) == 1:
    axes = [axes]

for row, rec in enumerate(samples):
    orig  = cv2.cvtColor(cv2.imread(str(rec.path)), cv2.COLOR_BGR2RGB)
    fixed = cv2.cvtColor(rec.undistorted, cv2.COLOR_BGR2RGB)
    fl    = rec.lens_profile.focal_length_35mm
    k1    = rec.lens_profile.distortion_coeffs[0]
    mtd   = rec.lens_profile.correction_method

    axes[row][0].imshow(orig)
    axes[row][0].set_title(f"Original  —  {rec.path.name}\\n{fl} mm eq.", fontsize=9)
    axes[row][0].axis('off')

    axes[row][1].imshow(fixed)
    axes[row][1].set_title(f"Corrected  —  method: {mtd}\\nk1 = {k1:+.3f}", fontsize=9)
    axes[row][1].axis('off')

plt.suptitle("Stage 0 — Lens Normalisation", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_01_normalisation.png', bbox_inches='tight', dpi=100)
plt.show()
"""))

# ── 6: Stage 1 — Sky/ground masking ─────────────────────────────────────────
cells.append(md("""
---
## Stage 1 — Sky / Ground Masking

Remove regions that cannot contain the target building before running edge
detection.  Masking first dramatically reduces false Hough lines from the sky
gradient and road surface.
"""))

cells.append(code("""
def make_sky_mask(img_bgr: np.ndarray) -> np.ndarray:
    \"\"\"
    Return a boolean mask (True = sky pixel) based on HSV colour thresholds
    plus a spatial prior that sky comes from the top of the image.
    \"\"\"
    h, w = img_bgr.shape[:2]
    hsv  = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    # Clear-sky blue band
    blue_sky = (
        (hsv[:, :, 0] >= SKY_HUE_LO) & (hsv[:, :, 0] <= SKY_HUE_HI) &
        (hsv[:, :, 1] >  SKY_SAT_MIN) &
        (hsv[:, :, 2] >  SKY_VAL_MIN)
    )
    # Overcast / white sky
    white_sky = (
        (hsv[:, :, 1] < OVERCAST_SAT_MAX) &
        (hsv[:, :, 2] > OVERCAST_VAL_MIN)
    )
    raw = (blue_sky | white_sky).astype(np.uint8)

    # Spatial prior: grow sky downward from the top third only
    top_seed = raw[:h // 3, :].copy()
    kernel   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
    grown    = cv2.dilate(top_seed, kernel, iterations=3)
    combined = (raw & np.pad(grown, ((0, h - h // 3), (0, 0)),
                              mode='constant', constant_values=0))

    # Fill holes and smooth boundary
    kernel2  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel2)
    return combined.astype(bool)


def make_ground_mask(img_bgr: np.ndarray) -> np.ndarray:
    \"\"\"
    Return a boolean mask (True = likely ground / road pixel).
    Operates on the lower half of the image only.
    \"\"\"
    h, w = img_bgr.shape[:2]
    hsv  = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    dark_pavement = (hsv[:, :, 2] < 120) & (hsv[:, :, 1] < 70)
    road_markings = (
        (hsv[:, :, 0] >= 18) & (hsv[:, :, 0] <= 38) & (hsv[:, :, 1] > 50)
    )
    raw  = (dark_pavement | road_markings).astype(np.uint8)
    # Restrict to lower half
    raw[:h // 2, :] = 0
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    raw    = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, kernel)
    return raw.astype(bool)


# Apply to all records
for rec in records:
    rec.sky_mask = make_sky_mask(rec.undistorted)

print("Sky masks computed.")
"""))

cells.append(code("""
# ── Visualise masks ───────────────────────────────────────────────────────────
step     = max(1, len(records) // 4)
show_recs = records[::step][:4]

fig, axes = plt.subplots(len(show_recs), 2, figsize=(16, 4.5 * len(show_recs)))
if len(show_recs) == 1:
    axes = [axes]

for row, rec in enumerate(show_recs):
    img_rgb = cv2.cvtColor(rec.undistorted, cv2.COLOR_BGR2RGB)
    overlay = img_rgb.copy()

    sky_color    = np.array([135, 206, 235], dtype=np.uint8)   # sky blue
    ground_color = np.array([160, 120,  80], dtype=np.uint8)   # earthy brown

    overlay[rec.sky_mask]                                  = sky_color
    overlay[make_ground_mask(rec.undistorted)]             = ground_color

    axes[row][0].imshow(img_rgb)
    axes[row][0].set_title(f"Original — {rec.path.name[-10:]}", fontsize=9)
    axes[row][0].axis('off')

    axes[row][1].imshow(overlay)
    axes[row][1].set_title("Masks: sky (blue) · ground (brown)", fontsize=9)
    axes[row][1].axis('off')

plt.suptitle("Stage 1 — Sky / Ground Masking", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_02_masks.png', bbox_inches='tight', dpi=100)
plt.show()
"""))

# ── 7: Stage 2 — Line extraction ─────────────────────────────────────────────
cells.append(md("""
---
## Stage 2 — Line Segment Extraction

Canny edges → Probabilistic Hough → axis-angle filter.

- **Horizontal** (class 0, green): within ±15° of horizontal — floor/ceiling bands, roofline, window sills
- **Vertical** (class 1, blue): within ±12° of vertical — building corners, window jambs
- **Diagonal** (class 2, orange): kept only in the upper third of the frame — pitched rooflines
"""))

cells.append(code("""
def classify_angle(angle_deg: float) -> Optional[int]:
    \"\"\"
    Return class id: 0=horizontal, 1=vertical, 2=diagonal (upper-frame only),
    or None to discard.
    \"\"\"
    a = abs(angle_deg) % 180
    if a > 90:
        a = 180.0 - a          # fold into 0–90 range
    if a < HORIZ_TOL_DEG:
        return 0               # horizontal
    if a > (90.0 - VERT_TOL_DEG):
        return 1               # vertical
    return 2                   # diagonal (caller checks spatial position)


def extract_line_segments(rec: ImageRecord) -> np.ndarray:
    \"\"\"
    Return N×5 float32 array [x1, y1, x2, y2, class_id].
    Returns empty (0, 5) array if nothing found.
    \"\"\"
    img = rec.undistorted
    h, w = img.shape[:2]

    gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Suppress sky before edge detection
    masked = blurred.copy()
    if rec.sky_mask is not None:
        masked[rec.sky_mask] = 0

    edges = cv2.Canny(masked, CANNY_LOW, CANNY_HIGH)

    raw = cv2.HoughLinesP(
        edges,
        rho=1, theta=np.pi / 180,
        threshold=HOUGH_THRESHOLD,
        minLineLength=HOUGH_MIN_LEN,
        maxLineGap=HOUGH_MAX_GAP,
    )
    if raw is None:
        return np.empty((0, 5), dtype=np.float32)

    out = []
    for line in raw:
        x1, y1, x2, y2 = line[0]
        angle    = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        class_id = classify_angle(angle)

        if class_id is None:
            continue
        if class_id == 2 and min(y1, y2) > h // 3:
            # Diagonal only kept in upper third (pitched roof zone)
            continue

        length = np.hypot(x2 - x1, y2 - y1)
        if length < HOUGH_MIN_LEN:
            continue

        out.append([float(x1), float(y1), float(x2), float(y2), float(class_id)])

    return np.array(out, dtype=np.float32) if out else np.empty((0, 5), dtype=np.float32)


# Run on all images
for rec in records:
    rec.line_segments = extract_line_segments(rec)

totals = {0: 0, 1: 0, 2: 0}
for rec in records:
    for cls in range(3):
        mask = rec.line_segments[:, 4] == cls if len(rec.line_segments) else []
        totals[cls] += int(np.sum(mask))

print(f"Total segments across all images:")
print(f"  Horizontal : {totals[0]}")
print(f"  Vertical   : {totals[1]}")
print(f"  Diagonal   : {totals[2]}")
"""))

cells.append(code("""
# ── Visualise line segments ───────────────────────────────────────────────────
CLS_COLORS = {0: (0, 200, 50), 1: (50, 100, 255), 2: (255, 165, 0)}  # H=green V=blue D=orange

step      = max(1, len(records) // 4)
show_recs = records[::step][:4]

fig, axes = plt.subplots(1, len(show_recs), figsize=(22, 6))
if len(show_recs) == 1:
    axes = [axes]

for col, rec in enumerate(show_recs):
    vis = cv2.cvtColor(rec.undistorted.copy(), cv2.COLOR_BGR2RGB)
    for seg in rec.line_segments:
        x1, y1, x2, y2, cls = seg.astype(int)
        cv2.line(vis, (x1, y1), (x2, y2), CLS_COLORS[cls], 2)
    n_h = int(np.sum(rec.line_segments[:, 4] == 0)) if len(rec.line_segments) else 0
    n_v = int(np.sum(rec.line_segments[:, 4] == 1)) if len(rec.line_segments) else 0
    fl  = rec.lens_profile.focal_length_35mm
    axes[col].imshow(vis)
    axes[col].set_title(f"{rec.path.stem[-6:]}  ({fl}mm)\\nH={n_h}  V={n_v}", fontsize=9)
    axes[col].axis('off')

patches = [mpatches.Patch(color='#00c832', label='Horizontal'),
           mpatches.Patch(color='#3264ff', label='Vertical'),
           mpatches.Patch(color='#ffa500', label='Diagonal (roof)')]
fig.legend(handles=patches, loc='lower center', ncol=3, fontsize=10, framealpha=0.8)
plt.suptitle("Stage 2 — Line Segment Extraction", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_03_line_segments.png', bbox_inches='tight', dpi=100)
plt.show()
"""))

# ── 8: Stage 3 — Vanishing point ─────────────────────────────────────────────
cells.append(md("""
---
## Stage 3 — Vanishing Point Analysis

Horizontal segments from the same facade converge at a vanishing point on the
horizon. We find it by collecting pairwise intersections of horizontal segments
and taking the median — robust against the outliers from road markings, awnings,
and partial background edges.

The normalised VP x-position (0–1 across frame width) is the key signal used
for facade grouping in Stage 4.
"""))

cells.append(code("""
def _line_intersection_2d(s1: np.ndarray, s2: np.ndarray) -> Optional[Tuple[float, float]]:
    \"\"\"Intersection of two infinite lines through s1=(x1,y1,x2,y2) and s2.\"\"\"
    x1, y1, x2, y2 = s1[:4]
    x3, y3, x4, y4 = s2[:4]
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-6:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def detect_vp(segs: np.ndarray,
               img_shape: Tuple[int, int],
               max_pairs: int = 600) -> Optional[Tuple[float, float]]:
    \"\"\"
    Detect the dominant horizontal vanishing point using random-pair voting.
    Returns (vp_x, vp_y) in pixel coords, or None if too few segments.
    \"\"\"
    h, w = img_shape[:2]
    h_segs = segs[segs[:, 4] == 0] if len(segs) else np.empty((0, 5))
    if len(h_segs) < 4:
        return None

    rng = np.random.default_rng(seed=42)
    n   = len(h_segs)
    all_pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    if len(all_pairs) > max_pairs:
        chosen = rng.choice(len(all_pairs), max_pairs, replace=False)
        all_pairs = [all_pairs[k] for k in chosen]

    pts = []
    for i, j in all_pairs:
        pt = _line_intersection_2d(h_segs[i], h_segs[j])
        if pt is None:
            continue
        vx, vy = pt
        # Discard intersections that are physically unreasonable
        if abs(vy) > h * 4:     # horizon can't be 4× frame heights away
            continue
        if abs(vx) > w * 25:    # allow very distant lateral VPs
            continue
        pts.append(pt)

    if len(pts) < 3:
        return None

    arr = np.array(pts)
    return tuple(np.median(arr, axis=0))


# Detect VP for every image
for rec in records:
    if len(rec.line_segments):
        rec.vp = detect_vp(rec.line_segments, rec.undistorted.shape)

found = sum(1 for r in records if r.vp is not None)
print(f"VP detected in {found} / {len(records)} images")
"""))

cells.append(code("""
# ── Visualise vanishing points ────────────────────────────────────────────────
vp_recs   = [r for r in records if r.vp is not None]
step      = max(1, len(vp_recs) // 4)
show_recs = vp_recs[::step][:4]

fig, axes = plt.subplots(1, len(show_recs), figsize=(22, 6))
if len(show_recs) == 1:
    axes = [axes]

for col, rec in enumerate(show_recs):
    vis = cv2.cvtColor(rec.undistorted.copy(), cv2.COLOR_BGR2RGB)
    h, w = vis.shape[:2]

    h_segs = rec.line_segments[rec.line_segments[:, 4] == 0]
    for seg in h_segs:
        x1, y1, x2, y2 = seg[:4].astype(int)
        cv2.line(vis, (x1, y1), (x2, y2), (0, 200, 0), 1)

    vx, vy = rec.vp
    # Draw a sample of lines extended toward VP
    for seg in h_segs[::max(1, len(h_segs) // 6)][:6]:
        mx, my = int((seg[0] + seg[2]) / 2), int((seg[1] + seg[3]) / 2)
        cv2.arrowedLine(vis, (mx, my),
                        (int(np.clip(vx, -w, 2*w)),
                         int(np.clip(vy, -h, 2*h))),
                        (255, 120, 0), 1, tipLength=0.04)

    # Mark VP if within frame
    if 0 <= vx < w and 0 <= vy < h:
        cv2.drawMarker(vis, (int(vx), int(vy)), (220, 0, 0),
                       cv2.MARKER_CROSS, 40, 3)

    vp_norm = vx / w
    axes[col].imshow(vis)
    axes[col].set_title(
        f"{rec.path.stem[-6:]}\\nVP=({vx:.0f}, {vy:.0f})  norm_x={vp_norm:.2f}",
        fontsize=9
    )
    axes[col].axis('off')

plt.suptitle("Stage 3 — Vanishing Point Analysis", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_04_vanishing_points.png', bbox_inches='tight', dpi=100)
plt.show()
"""))

# ── 9: Stage 4 — Facade grouping ─────────────────────────────────────────────
cells.append(md("""
---
## Stage 4 — Sequential Facade Grouping

As the photographer walks around the building the normalised VP x-position drifts
slowly then jumps when a corner is passed.  A large VP shift (or sign flip)
between consecutive images marks a facade transition.
"""))

cells.append(code("""
def group_by_facade(records: List[ImageRecord]) -> List[int]:
    \"\"\"
    Assign a facade id (0, 1, 2, …) to each image based on VP consistency.

    Steps:
      1. Normalise VP x to [0, 1] relative to frame width.
      2. Smooth the trajectory with a rolling median to suppress per-frame noise
         and the mid-sequence lens switch.
      3. Trigger a new facade only when the smoothed shift exceeds VP_SHIFT_THRESHOLD.
      4. Merge any facade shorter than VP_MIN_FACADE_IMGS into its left neighbour.
    \"\"\"
    def norm_vp(rec):
        if rec.vp is None:
            return None
        return rec.vp[0] / rec.undistorted.shape[1]

    raw_vps = [norm_vp(r) for r in records]

    # ── Step 1: fill None gaps with nearest neighbour so smoothing works ───────
    filled = list(raw_vps)
    for i, v in enumerate(filled):
        if v is None:
            # look ahead for next valid value
            for j in range(i + 1, len(filled)):
                if filled[j] is not None:
                    filled[i] = filled[j]
                    break
            if filled[i] is None and i > 0:
                filled[i] = filled[i - 1]

    # ── Step 2: rolling-median smooth ─────────────────────────────────────────
    half  = VP_SMOOTH_WINDOW // 2
    smoothed = []
    for i in range(len(filled)):
        window = [filled[j] for j in range(max(0, i - half),
                                            min(len(filled), i + half + 1))
                  if filled[j] is not None]
        smoothed.append(float(np.median(window)) if window else 0.0)

    # ── Step 3: threshold on smoothed shifts ──────────────────────────────────
    facade_ids = [0] * len(records)
    current    = 0
    for i in range(1, len(records)):
        facade_ids[i] = current
        shift     = abs(smoothed[i] - smoothed[i - 1])
        sign_flip = (smoothed[i] * smoothed[i - 1] < 0) and shift > 0.45
        if shift > VP_SHIFT_THRESHOLD or sign_flip:
            current += 1
            facade_ids[i] = current
            print(f"  Corner after image {i-1}  ({records[i-1].path.name})  "
                  f"smoothed shift={shift:.3f}  sign_flip={sign_flip}")

    # ── Step 4: merge short facades into left neighbour ───────────────────────
    changed = True
    while changed:
        changed = False
        counts  = Counter(facade_ids)
        for f, cnt in sorted(counts.items()):
            if cnt < VP_MIN_FACADE_IMGS and f > 0:
                facade_ids = [f - 1 if v == f else v for v in facade_ids]
                # Re-number to keep ids contiguous
                uniq   = sorted(set(facade_ids))
                remap  = {old: new for new, old in enumerate(uniq)}
                facade_ids = [remap[v] for v in facade_ids]
                changed = True
                break

    return facade_ids


facade_ids = group_by_facade(records)
for rec, fid in zip(records, facade_ids):
    rec.facade_id = fid

n_facades = max(facade_ids) + 1
print(f"\\nDetected {n_facades} facade(s):")
for f in range(n_facades):
    imgs = [r for r in records if r.facade_id == f]
    print(f"  Facade {f}: {len(imgs):2d} images  "
          f"({imgs[0].path.name} … {imgs[-1].path.name})")
"""))

cells.append(code("""
# ── Visualise facade timeline ─────────────────────────────────────────────────
PALETTE = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c']

fig, (ax_bar, ax_vp) = plt.subplots(2, 1, figsize=(16, 5), sharex=True,
                                     gridspec_kw={'height_ratios': [1, 2]})

# Colour bar: one bar per image
for i, rec in enumerate(records):
    color = PALETTE[rec.facade_id % len(PALETTE)]
    ax_bar.barh(0, 1, left=i, color=color, edgecolor='white', height=0.8)
    ax_bar.text(i + 0.5, 0, rec.path.stem[-4:], ha='center', va='center',
                fontsize=6, color='white', fontweight='bold')

ax_bar.set_xlim(0, len(records))
ax_bar.set_yticks([])
ax_bar.set_title("Facade assignment per image", fontsize=10)

# VP x trajectory
for i, rec in enumerate(records):
    if rec.vp is not None:
        vp_norm = rec.vp[0] / rec.undistorted.shape[1]
        color   = PALETTE[rec.facade_id % len(PALETTE)]
        ax_vp.scatter(i, vp_norm, color=color, s=40, zorder=3)

# Connect dots per facade
for f in range(n_facades):
    fi = [(i, records[i].vp[0] / records[i].undistorted.shape[1])
          for i, r in enumerate(records)
          if r.facade_id == f and r.vp is not None]
    if fi:
        xs, ys = zip(*fi)
        ax_vp.plot(xs, ys, color=PALETTE[f % len(PALETTE)], alpha=0.5, linewidth=1.5)

ax_vp.axhline(0, color='grey', linestyle=':', linewidth=0.8)
ax_vp.set_ylabel("Normalised VP x", fontsize=9)
ax_vp.set_xlabel("Image index (chronological)", fontsize=9)

legend_patches = [mpatches.Patch(color=PALETTE[f % len(PALETTE)], label=f'Facade {f}')
                  for f in range(n_facades)]
ax_vp.legend(handles=legend_patches, fontsize=9, loc='best')

plt.suptitle("Stage 4 — Sequential Facade Grouping", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_05_facade_groups.png', bbox_inches='tight', dpi=100)
plt.show()

# Representative image per facade
fig2, axes2 = plt.subplots(1, n_facades, figsize=(7 * n_facades, 5))
if n_facades == 1:
    axes2 = [axes2]
for f in range(n_facades):
    fr    = [r for r in records if r.facade_id == f]
    mid   = fr[len(fr) // 2]
    img_r = cv2.cvtColor(mid.undistorted, cv2.COLOR_BGR2RGB)
    axes2[f].imshow(img_r)
    axes2[f].set_title(f"Facade {f}  ({len(fr)} images)\\n{mid.path.name[-12:]}", fontsize=10)
    axes2[f].axis('off')
plt.suptitle("Facade representative images", fontsize=11)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_06_facade_reps.png', bbox_inches='tight', dpi=100)
plt.show()
"""))

# ── 10: Stage 5 — Gap bridging ───────────────────────────────────────────────
cells.append(md("""
---
## Stage 5 — Collinear Gap Bridging

Within each image, horizontal segments that share the same approximate y-position
belong to the same architectural line (floor band, window sill, roofline).
Gaps between them are bridged when the gap region contains high-frequency
texture typical of foliage or vehicles (Laplacian variance > threshold).

Yellow markers show bridged gaps; each colour group is one collinear family.
"""))

cells.append(code("""
def find_collinear_groups(segs: np.ndarray,
                           y_tol: Optional[float] = None,
                           min_members: int = 2) -> List[List[int]]:
    if y_tol is None:
        y_tol = float(COLLINEAR_Y_TOL)
    \"\"\"
    Group horizontal segment indices by midpoint y (within y_tol pixels).
    Returns list of groups, each group is a list of segment indices.
    \"\"\"
    h_idx = [i for i, s in enumerate(segs) if s[4] == 0]
    if not h_idx:
        return []

    sorted_idx = sorted(h_idx, key=lambda i: (segs[i][1] + segs[i][3]) / 2)
    groups, cur_grp = [], [sorted_idx[0]]
    cur_y = (segs[sorted_idx[0]][1] + segs[sorted_idx[0]][3]) / 2

    for idx in sorted_idx[1:]:
        my = (segs[idx][1] + segs[idx][3]) / 2
        if abs(my - cur_y) <= y_tol:
            cur_grp.append(idx)
            cur_y = np.mean([(segs[i][1] + segs[i][3]) / 2 for i in cur_grp])
        else:
            if len(cur_grp) >= min_members:
                groups.append(cur_grp)
            cur_grp = [idx]
            cur_y   = my

    if len(cur_grp) >= min_members:
        groups.append(cur_grp)

    return groups


def _is_occlusion_gap(img_bgr: np.ndarray,
                       x_start: int, x_end: int, y_mid: int,
                       band: int = 12,
                       lap_threshold: float = 180.0) -> bool:
    \"\"\"
    Return True when the gap region contains high-frequency texture
    characteristic of a tree or vehicle (rather than a genuine wall gap).
    \"\"\"
    h, w = img_bgr.shape[:2]
    y0 = max(0,     y_mid - band)
    y1 = min(h - 1, y_mid + band)
    x0 = max(0,     x_start)
    x1 = min(w - 1, x_end)
    if x1 <= x0 or y1 <= y0:
        return False
    patch    = cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    lap_var  = cv2.Laplacian(patch, cv2.CV_64F).var()
    return float(lap_var) > lap_threshold


def bridge_collinear_group(segs: np.ndarray,
                            group_indices: List[int],
                            img_bgr: np.ndarray,
                            max_gap_px: Optional[int] = None
                            ) -> List[Tuple]:
    if max_gap_px is None:
        max_gap_px = int(BRIDGE_MAX_GAP_PX)
    \"\"\"
    Sort group members by x, bridge occluded gaps.
    Returns list of (x1, y1, x2, y2, is_bridge:bool).
    \"\"\"
    members = []
    for i in group_indices:
        x1, y1, x2, y2 = segs[i][:4].astype(int)
        if x1 > x2:
            x1, y1, x2, y2 = x2, y2, x1, y1
        members.append((x1, y1, x2, y2))
    members.sort(key=lambda s: s[0])

    result = []
    for k, (x1, y1, x2, y2) in enumerate(members):
        result.append((x1, y1, x2, y2, False))
        if k < len(members) - 1:
            nx1, ny1, nx2, ny2 = members[k + 1]
            gap   = nx1 - x2
            y_mid = int((y2 + ny1) / 2)
            if 0 < gap <= max_gap_px and _is_occlusion_gap(img_bgr, x2, nx1, y_mid):
                result.append((x2, y_mid, nx1, y_mid, True))

    return result
"""))

cells.append(code("""
# ── Visualise gap bridging ────────────────────────────────────────────────────
# Focus on images near the middle of the sequence where trees are most prominent
n_mid     = len(records) // 2
mid_slice = records[max(0, n_mid - 1): n_mid + 2]

fig, axes = plt.subplots(1, len(mid_slice), figsize=(8 * len(mid_slice), 6))
if len(mid_slice) == 1:
    axes = [axes]

for col, rec in enumerate(mid_slice):
    vis    = cv2.cvtColor(rec.undistorted.copy(), cv2.COLOR_BGR2RGB)
    segs   = rec.line_segments
    groups = find_collinear_groups(segs)

    n_bridged = 0
    for g_idx, group in enumerate(groups):
        hue   = g_idx / max(len(groups), 1)
        rgba  = cm.hsv(hue)
        color = tuple(int(c * 220) for c in rgba[:3])

        bridged_segs = bridge_collinear_group(segs, group, rec.undistorted)
        for x1, y1, x2, y2, is_bridge in bridged_segs:
            if is_bridge:
                cv2.line(vis, (x1, y1), (x2, y2), (255, 240, 0), 3)
                cv2.putText(vis, chr(0x21D4),   # ⇔
                            (int((x1 + x2) / 2) - 8, y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 240, 0), 1)
                n_bridged += 1
            else:
                cv2.line(vis, (x1, y1), (x2, y2), color, 2)

    axes[col].imshow(vis)
    axes[col].set_title(
        f"{rec.path.stem[-6:]}\\n"
        f"{len(groups)} collinear groups  |  {n_bridged} bridged gaps",
        fontsize=9
    )
    axes[col].axis('off')

patches = [mpatches.Patch(color='yellow', label='Bridged gap (occlusion)'),
           mpatches.Patch(color='cyan',   label='Collinear segment group')]
fig.legend(handles=patches, loc='lower center', ncol=2, fontsize=10)
plt.suptitle("Stage 5 — Collinear Gap Bridging", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_07_gap_bridging.png', bbox_inches='tight', dpi=100)
plt.show()
"""))

# ── 11: Stage 6 — Window detection ──────────────────────────────────────────
cells.append(md("""
---
## Stage 6 — Window Candidate Detection

Working in the undistorted image:

1. Find dominant horizontal lines (floor / window-sill bands) using peak detection
   on a y-histogram of horizontal segment midpoints.
2. For each inter-line band, scan for vertical segments (window jambs) to pair up
   into window bounding boxes. Fall back to Otsu contour detection when jamb
   segments are sparse.
3. Filter candidates by aspect ratio and band-relative area.
"""))

cells.append(code("""
def detect_windows(rec: ImageRecord) -> List[Dict]:
    \"\"\"
    Returns list of dicts: {x, y, w, h, confidence, method}
    x, y = top-left corner in image pixels.
    \"\"\"
    # Apply sky mask: replace sky pixels with mid-grey so they don't confuse
    # Otsu thresholding or the y-histogram of horizontal segments.
    img = rec.undistorted.copy()
    if rec.sky_mask is not None:
        img[rec.sky_mask] = 128

    h, w = img.shape[:2]
    segs = rec.line_segments
    if len(segs) == 0:
        return []

    # ── Step 1: y-histogram of horizontal segment midpoints ──────────────────
    # Only count segments whose midpoint is NOT in the sky mask
    h_segs = segs[segs[:, 4] == 0]
    if rec.sky_mask is not None:
        keep = []
        for seg in h_segs:
            my = int(np.clip((seg[1] + seg[3]) / 2, 0, h - 1))
            mx = int(np.clip((seg[0] + seg[2]) / 2, 0, w - 1))
            if not rec.sky_mask[my, mx]:
                keep.append(seg)
        h_segs = np.array(keep, dtype=np.float32) if keep else np.empty((0, 5), dtype=np.float32)

    if len(h_segs) < 2:
        return []

    mid_ys  = (h_segs[:, 1] + h_segs[:, 3]) / 2
    lengths = np.hypot(h_segs[:, 2] - h_segs[:, 0], h_segs[:, 3] - h_segs[:, 1])

    y_hist = np.zeros(h, dtype=float)
    for y, length in zip(mid_ys, lengths):
        yi = int(np.clip(y, 0, h - 1))
        y_hist[yi] += length

    smoothed = gaussian_filter1d(y_hist, sigma=12)
    if smoothed.max() == 0:
        return []

    min_height = np.percentile(smoothed[smoothed > 0], 40)
    peaks, _   = find_peaks(smoothed, height=min_height, distance=25)

    if len(peaks) < 2:
        return []

    # ── Step 2: scan bands between consecutive peaks ──────────────────────────
    windows = []
    v_segs  = segs[segs[:, 4] == 1]   # vertical segments

    for k in range(len(peaks) - 1):
        y_top   = int(peaks[k])
        y_bot   = int(peaks[k + 1])
        band_h  = y_bot - y_top
        if band_h < 20 or band_h > h // 2:
            continue

        # Vertical segments whose y-midpoint falls in this band
        v_mid_y = (v_segs[:, 1] + v_segs[:, 3]) / 2
        in_band = v_segs[(v_mid_y >= y_top) & (v_mid_y <= y_bot)]

        if len(in_band) >= 2:
            # Cluster vertical segment x-positions (centre x)
            xs   = np.sort((in_band[:, 0] + in_band[:, 2]) / 2)
            bins = np.round(xs / 20) * 20   # 20 px buckets
            uniq = sorted(set(bins.astype(int)))

            for j in range(len(uniq) - 1):
                xl      = uniq[j]
                xr      = uniq[j + 1]
                win_w   = xr - xl
                ar      = win_w / max(band_h, 1)
                area_r  = (win_w * band_h) / (w * h)
                if 0.3 < ar < 4.0 and 0.005 < area_r < 0.25:
                    windows.append({'x': xl, 'y': y_top,
                                    'w': win_w, 'h': band_h,
                                    'confidence': 0.65, 'method': 'jamb_pair'})
        else:
            # Fallback: Otsu contour in this band
            band_img = cv2.cvtColor(img[y_top:y_bot, :], cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(band_img, 0, 255,
                                       cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            cnts, _   = cv2.findContours(thresh,
                                          cv2.RETR_EXTERNAL,
                                          cv2.CHAIN_APPROX_SIMPLE)
            for cnt in cnts:
                rx, ry, rw, rh = cv2.boundingRect(cnt)
                ar     = rw / max(rh, 1)
                area_r = (rw * rh) / (w * band_h)
                if 0.4 < ar < 3.5 and 0.01 < area_r < 0.30:
                    windows.append({'x': rx, 'y': y_top + ry,
                                    'w': rw, 'h': rh,
                                    'confidence': 0.40, 'method': 'contour'})

    return windows
"""))

cells.append(code("""
# ── Visualise window detection ────────────────────────────────────────────────
fig, axes = plt.subplots(n_facades, 2, figsize=(18, 7 * n_facades))
if n_facades == 1:
    axes = [axes]

for f in range(n_facades):
    fr   = [r for r in records if r.facade_id == f]
    # Pick the image with the most horizontal segments in this facade
    best = max(fr, key=lambda r: int(np.sum(r.line_segments[:, 4] == 0))
               if len(r.line_segments) else 0)

    wins = detect_windows(best)

    # Left: floor-line bands
    vis_bands = cv2.cvtColor(best.undistorted.copy(), cv2.COLOR_BGR2RGB)
    h_segs    = best.line_segments[best.line_segments[:, 4] == 0]
    for seg in h_segs:
        x1, y1, x2, y2 = seg[:4].astype(int)
        cv2.line(vis_bands, (x1, y1), (x2, y2), (0, 180, 255), 2)

    # Right: window boxes
    vis_wins = cv2.cvtColor(best.undistorted.copy(), cv2.COLOR_BGR2RGB)
    for win in wins:
        color = (50, 220, 80) if win['confidence'] >= 0.6 else (255, 200, 0)
        cv2.rectangle(vis_wins,
                      (win['x'], win['y']),
                      (win['x'] + win['w'], win['y'] + win['h']),
                      color, 2)

    axes[f][0].imshow(vis_bands)
    axes[f][0].set_title(
        f"Facade {f} — horizontal bands  ({best.path.name[-12:]})", fontsize=10)
    axes[f][0].axis('off')

    axes[f][1].imshow(vis_wins)
    axes[f][1].set_title(
        f"Facade {f} — window candidates: {len(wins)}", fontsize=10)
    axes[f][1].axis('off')

plt.suptitle("Stage 6 — Window Candidate Detection", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_08_windows.png', bbox_inches='tight', dpi=100)
plt.show()
"""))

# ── 12: Stage 7 — Facade rectification ──────────────────────────────────────
cells.append(md("""
---
## Stage 7 — Facade Rectification

Each facade's best image is warped to an approximately orthographic view using
the camera intrinsic matrix K (computed in Stage 0) and the vanishing point
(Stage 3).

The VP gives us the 3-D direction of horizontal lines.  Together with the
assumption that the building is plumb (true verticals are vertical), we
can derive a rotation matrix whose columns are the facade's **right**, **up**,
and **normal** vectors.  The rectifying homography is then H = K R K⁻¹.
"""))

cells.append(code("""
from mpl_toolkits.mplot3d import Axes3D          # noqa: F401 (registers 3d projection)
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def rectify_facade_image(img_bgr: np.ndarray,
                          vp: Tuple[float, float],
                          K: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    \"\"\"
    Compute a rectifying homography H = K R K^{-1} from the VP and return
    (rectified_image, H).  Falls back to identity if K is degenerate.
    \"\"\"
    h, w = img_bgr.shape[:2]
    try:
        K_inv = np.linalg.inv(K)
    except np.linalg.LinAlgError:
        return img_bgr.copy(), np.eye(3)

    # Vanishing point → 3-D direction of horizontal lines
    vp_h     = np.array([vp[0], vp[1], 1.0])
    right_3d = K_inv @ vp_h
    right_3d /= np.linalg.norm(right_3d)

    # "Up" in camera coords ≈ -Y (valid for a roughly level, forward-facing camera)
    up_3d = np.array([0.0, -1.0, 0.0])
    up_3d = up_3d - np.dot(up_3d, right_3d) * right_3d   # orthogonalise
    norm  = np.linalg.norm(up_3d)
    if norm < 1e-6:
        return img_bgr.copy(), np.eye(3)
    up_3d /= norm

    normal_3d = np.cross(right_3d, up_3d)

    # Rotation: columns = right, up, normal
    R = np.column_stack([right_3d, up_3d, normal_3d])
    H = K @ R @ K_inv

    rectified = cv2.warpPerspective(img_bgr, H, (w, h),
                                     flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_REPLICATE)
    return rectified, H


# ── Pick best image per facade (most horizontal segments, has a VP) ───────────
def best_record_for_facade(records: List[ImageRecord], facade_id: int) -> Optional[ImageRecord]:
    fr = [r for r in records if r.facade_id == facade_id and r.vp is not None]
    if not fr:
        fr = [r for r in records if r.facade_id == facade_id]
    if not fr:
        return None
    return max(fr, key=lambda r: int(np.sum(r.line_segments[:, 4] == 0))
               if len(r.line_segments) else 0)


facade_best   = {f: best_record_for_facade(records, f) for f in range(n_facades)}
facade_rect   = {}   # facade_id → rectified BGR image
facade_H      = {}   # facade_id → homography

for f, rec in facade_best.items():
    if rec is None or rec.vp is None or rec.lens_profile.camera_matrix is None:
        facade_rect[f] = rec.undistorted if rec else None
        facade_H[f]    = np.eye(3)
        continue
    img_r, H = rectify_facade_image(rec.undistorted, rec.vp,
                                     rec.lens_profile.camera_matrix)
    facade_rect[f] = img_r
    facade_H[f]    = H
    print(f"Facade {f}: rectified  ({rec.path.name})  "
          f"VP=({rec.vp[0]:.0f}, {rec.vp[1]:.0f})")
"""))

cells.append(code("""
# ── Visualise rectification ────────────────────────────────────────────────────
fig, axes = plt.subplots(n_facades, 2, figsize=(16, 6 * n_facades))
if n_facades == 1:
    axes = [axes]

for f in range(n_facades):
    rec  = facade_best[f]
    orig = cv2.cvtColor(rec.undistorted, cv2.COLOR_BGR2RGB) if rec else None
    rect = cv2.cvtColor(facade_rect[f],  cv2.COLOR_BGR2RGB) if facade_rect[f] is not None else None

    axes[f][0].imshow(orig)
    axes[f][0].set_title(f"Facade {f} — original", fontsize=10)
    axes[f][0].axis('off')

    axes[f][1].imshow(rect)
    axes[f][1].set_title(f"Facade {f} — rectified (H = K R K⁻¹)", fontsize=10)
    axes[f][1].axis('off')

plt.suptitle("Stage 7 — Facade Rectification", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_09_rectified.png', bbox_inches='tight', dpi=100)
plt.show()
"""))

# ── 13: Stage 8 — Building outline per facade ─────────────────────────────────
cells.append(md("""
---
## Stage 8 — Building Outline per Facade

Working in the **rectified** image, we detect four boundaries that define the
usable facade rectangle:

- **Roofline** — topmost strong horizontal line below the sky mask
- **Ground line** — bottommost horizontal line (or image bottom as fallback)
- **Left / right extents** — outermost near-vertical line segments

The number of floors is counted from the horizontal floor-band peaks already
found in Stage 6, restricted to the region between roofline and ground.
"""))

cells.append(code("""
@dataclass
class FacadeOutline:
    facade_id:    int
    roofline_y:   int     # px in rectified image
    ground_y:     int     # px
    left_x:       int     # px
    right_x:      int     # px
    n_floors:     int
    pixel_height: int     # ground_y - roofline_y
    pixel_width:  int     # right_x  - left_x
    real_height_m: float  # calibrated metres
    real_width_m:  float  # calibrated metres


def detect_facade_outline(rect_img: np.ndarray,
                           segs: np.ndarray,
                           sky_mask: Optional[np.ndarray],
                           H: np.ndarray) -> FacadeOutline:
    \"\"\"
    Detect the four bounding lines of a facade in the rectified image.
    segs and sky_mask are from the *original* image and are warped by H.
    \"\"\"
    h, w = rect_img.shape[:2]

    # Warp the sky mask into rectified coords
    if sky_mask is not None:
        rect_sky = cv2.warpPerspective(sky_mask.astype(np.uint8), H, (w, h)) > 0
    else:
        rect_sky = np.zeros((h, w), dtype=bool)

    # Warp each segment endpoint and re-extract lines in rectified space
    rect_gray    = cv2.cvtColor(rect_img, cv2.COLOR_BGR2GRAY)
    rect_masked  = rect_gray.copy()
    rect_masked[rect_sky] = 0
    rect_edges   = cv2.Canny(cv2.GaussianBlur(rect_masked, (5, 5), 0),
                              CANNY_LOW, CANNY_HIGH)
    rect_raw     = cv2.HoughLinesP(rect_edges, 1, np.pi / 180,
                                    threshold=HOUGH_THRESHOLD,
                                    minLineLength=HOUGH_MIN_LEN,
                                    maxLineGap=HOUGH_MAX_GAP)

    h_lines, v_lines = [], []
    if rect_raw is not None:
        for line in rect_raw:
            x1, y1, x2, y2 = line[0]
            angle  = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            cls_id = classify_angle(angle)
            if cls_id == 0:
                h_lines.append((x1, y1, x2, y2))
            elif cls_id == 1:
                v_lines.append((x1, y1, x2, y2))

    # ── Roofline: topmost H-line below the sky ───────────────────────────────
    non_sky_h = [(x1, y1, x2, y2) for x1, y1, x2, y2 in h_lines
                 if not rect_sky[int(np.clip((y1 + y2) / 2, 0, h-1)),
                                  int(np.clip((x1 + x2) / 2, 0, w-1))]]
    if non_sky_h:
        # Sort by y and take the topmost cluster (lines within 5% of frame height)
        sorted_h  = sorted(non_sky_h, key=lambda l: (l[1] + l[3]) / 2)
        top_y     = (sorted_h[0][1] + sorted_h[0][3]) / 2
        cluster   = [l for l in sorted_h
                     if abs((l[1] + l[3]) / 2 - top_y) < h * 0.05]
        lengths   = [np.hypot(l[2]-l[0], l[3]-l[1]) for l in cluster]
        roofline_y = int(np.average([(l[1]+l[3])/2 for l in cluster],
                                     weights=lengths))
    else:
        roofline_y = int(h * 0.15)   # fallback: 15% from top

    # ── Ground line: bottommost H-line in lower half ──────────────────────────
    lower_h = [(x1, y1, x2, y2) for x1, y1, x2, y2 in h_lines
               if (y1 + y2) / 2 > h * 0.55]
    if lower_h:
        sorted_lo  = sorted(lower_h, key=lambda l: -(l[1]+l[3])/2)
        ground_y   = int((sorted_lo[0][1] + sorted_lo[0][3]) / 2)
    else:
        ground_y = int(h * 0.88)   # fallback

    # ── Left / right extents: outermost V-lines in building zone ──────────────
    bldg_v = [(x1, y1, x2, y2) for x1, y1, x2, y2 in v_lines
              if roofline_y <= (y1+y2)/2 <= ground_y]
    if bldg_v:
        xs     = [(x1 + x2) / 2 for x1, y1, x2, y2 in bldg_v]
        left_x  = int(min(xs))
        right_x = int(max(xs))
    else:
        left_x  = int(w * 0.05)
        right_x = int(w * 0.95)

    # ── Floor count from horizontal band peaks ────────────────────────────────
    zone_h = [l for l in non_sky_h
              if roofline_y <= (l[1]+l[3])/2 <= ground_y]
    zone_ys  = np.array([(l[1]+l[3])/2 for l in zone_h]) if zone_h else np.array([])
    if len(zone_ys) >= 2:
        y_hist  = np.zeros(h, dtype=float)
        for l in zone_h:
            yi = int(np.clip((l[1]+l[3])/2, 0, h-1))
            y_hist[yi] += np.hypot(l[2]-l[0], l[3]-l[1])
        smoothed = gaussian_filter1d(y_hist, sigma=max(8, COLLINEAR_Y_TOL*2))
        peaks, _ = find_peaks(smoothed[roofline_y:ground_y],
                               height=smoothed[roofline_y:ground_y].max()*0.2,
                               distance=max(15, (ground_y-roofline_y)//8))
        n_floors = max(1, len(peaks) - 1) if len(peaks) >= 2 else 1
    else:
        n_floors = 1

    pixel_h = max(1, ground_y - roofline_y)
    pixel_w = max(1, right_x  - left_x)

    # ── Scale calibration ─────────────────────────────────────────────────────
    fh_m = (FLOOR_HEIGHT_M_COMMERCIAL if BUILDING_TYPE == 'commercial'
            else FLOOR_HEIGHT_M_RESIDENTIAL)
    real_h = n_floors * fh_m
    m_per_px = real_h / pixel_h
    real_w   = pixel_w * m_per_px

    return FacadeOutline(
        facade_id=0,
        roofline_y=roofline_y, ground_y=ground_y,
        left_x=left_x, right_x=right_x,
        n_floors=n_floors,
        pixel_height=pixel_h, pixel_width=pixel_w,
        real_height_m=round(real_h, 2),
        real_width_m=round(real_w, 2),
    )


# Run outline detection for every facade
facade_outlines: Dict[int, FacadeOutline] = {}
for f in range(n_facades):
    rec = facade_best[f]
    if rec is None:
        continue
    segs     = rec.line_segments if len(rec.line_segments) else np.empty((0, 5))
    outline  = detect_facade_outline(facade_rect[f], segs,
                                      rec.sky_mask, facade_H[f])
    outline.facade_id = f
    facade_outlines[f] = outline
    print(f"Facade {f}: roofline_y={outline.roofline_y}  ground_y={outline.ground_y}  "
          f"left_x={outline.left_x}  right_x={outline.right_x}  "
          f"floors={outline.n_floors}  "
          f"W={outline.real_width_m:.1f}m  H={outline.real_height_m:.1f}m")
"""))

cells.append(code("""
# ── Visualise outlines on rectified images ────────────────────────────────────
fig, axes = plt.subplots(1, n_facades, figsize=(9 * n_facades, 6))
if n_facades == 1:
    axes = [axes]

for f, outline in facade_outlines.items():
    vis = cv2.cvtColor(facade_rect[f].copy(), cv2.COLOR_BGR2RGB)
    h_vis, w_vis = vis.shape[:2]

    # Roofline — red
    cv2.line(vis, (outline.left_x, outline.roofline_y),
             (outline.right_x, outline.roofline_y), (220, 30, 30), 3)
    # Ground line — brown
    cv2.line(vis, (outline.left_x, outline.ground_y),
             (outline.right_x, outline.ground_y), (139, 100, 20), 3)
    # Left / right extents — blue
    cv2.line(vis, (outline.left_x, outline.roofline_y),
             (outline.left_x, outline.ground_y), (30, 80, 220), 3)
    cv2.line(vis, (outline.right_x, outline.roofline_y),
             (outline.right_x, outline.ground_y), (30, 80, 220), 3)

    # Dimension annotations
    cx = (outline.left_x + outline.right_x) // 2
    cv2.putText(vis, f"{outline.real_width_m:.1f} m",
                (cx - 40, outline.ground_y + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (139, 100, 20), 2)
    cv2.putText(vis, f"{outline.real_height_m:.1f} m  ({outline.n_floors} fl)",
                (outline.right_x + 8, (outline.roofline_y + outline.ground_y) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 30, 30), 2)

    axes[f].imshow(vis)
    axes[f].set_title(
        f"Facade {f}  —  {outline.real_width_m:.1f} m wide  ×  "
        f"{outline.real_height_m:.1f} m tall  ({outline.n_floors} floors)",
        fontsize=10
    )
    axes[f].axis('off')

plt.suptitle("Stage 8 — Building Outline Detection", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_10_outlines.png', bbox_inches='tight', dpi=100)
plt.show()
"""))

# ── 14: Stage 9 — 3D footprint assembly ──────────────────────────────────────
cells.append(md("""
---
## Stage 9 — 3D Footprint & Geometry Assembly

With per-facade widths and heights in hand we can assemble a 3-D building model.

**Assumptions for this prototype:**
- Rectangular building (90° corners between adjacent facades)
- Constant building height across all facades
- Facades are walked in order (the sequence direction determines the winding)

The floor plan polygon is built by walking the facade sequence and turning 90°
at each corner. The polygon is then extruded vertically to produce wall surfaces.
Windows from Stage 6 are projected into the rectified facade coordinate system
and attached to their walls.

For buildings with non-90° corners (L-shapes, etc.) the corner angle can be
estimated from the VP directions of adjacent facades — that refinement is noted
as a `TODO` below.
"""))

cells.append(code("""
@dataclass
class Wall3D:
    \"\"\"One facade wall as four 3-D corner vertices (counter-clockwise when viewed from outside).\"\"\"
    facade_id:  int
    verts:      np.ndarray    # shape (4, 3)  — BL, BR, TR, TL  (x, y, z metres)
    width_m:    float
    height_m:   float
    n_floors:   int
    windows:    List[Dict]    # raw pixel dicts from Stage 6 (to be projected)


def assemble_3d_building(outlines: Dict[int, FacadeOutline],
                          records:  List[ImageRecord],
                          corner_angle_deg: float = 90.0
                          ) -> Tuple[List[Wall3D], np.ndarray]:
    \"\"\"
    Build Wall3D objects for all detected facades.
    Returns (walls, footprint_polygon) where footprint is an (N+1, 2) array
    of (x, y) metres that closes back to the origin.

    TODO: replace corner_angle_deg=90 with VP-pair estimation for non-rectangular buildings.
    \"\"\"
    walls    = []
    pos      = np.array([0.0, 0.0])
    angle_deg = 0.0   # current facing direction (degrees CCW from +X)
    footprint = [pos.copy()]

    # Use maximum building height across facades for a uniform roofline
    all_heights = [o.real_height_m for o in outlines.values()]
    H_building  = float(np.median(all_heights)) if all_heights else 10.0

    for f, outline in sorted(outlines.items()):
        W = outline.real_width_m
        direction = np.array([np.cos(np.radians(angle_deg)),
                               np.sin(np.radians(angle_deg))])
        far_pos   = pos + direction * W

        # 4 corners: bottom-left, bottom-right, top-right, top-left
        BL = np.array([pos[0],     pos[1],     0.0])
        BR = np.array([far_pos[0], far_pos[1], 0.0])
        TR = np.array([far_pos[0], far_pos[1], H_building])
        TL = np.array([pos[0],     pos[1],     H_building])
        verts = np.stack([BL, BR, TR, TL])

        # Collect windows for this facade from the best image
        rec  = best_record_for_facade(records, f)
        wins = detect_windows(rec) if rec is not None else []

        walls.append(Wall3D(
            facade_id=f,
            verts=verts,
            width_m=W,
            height_m=H_building,
            n_floors=outline.n_floors,
            windows=wins,
        ))

        pos = far_pos.copy()
        footprint.append(pos.copy())
        angle_deg += corner_angle_deg   # turn at corner

    # Close the polygon
    footprint.append(footprint[0].copy())
    return walls, np.array(footprint)


walls, footprint_poly = assemble_3d_building(facade_outlines, records)

print(f"Assembled {len(walls)} wall(s):")
for w in walls:
    print(f"  Facade {w.facade_id}: {w.width_m:.1f} m wide  x  {w.height_m:.1f} m tall  "
          f"({w.n_floors} floors)  {len(w.windows)} window candidates")

print(f"\\nFootprint polygon ({len(footprint_poly)-1} vertices):")
for i, pt in enumerate(footprint_poly[:-1]):
    print(f"  P{i}: ({pt[0]:.2f}, {pt[1]:.2f}) m")
"""))

# ── 15: Stage 10 — 3D Visualisation ──────────────────────────────────────────
cells.append(md("""
---
## Stage 10 — 3D Visualisation

Two views of the assembled building geometry:
1. **Floor plan** — 2-D top-down footprint with facade labels
2. **3-D perspective** — extruded walls with the rectified facade texture mapped onto each wall
"""))

cells.append(code("""
# ── Floor plan view ───────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 8))

fp = footprint_poly
ax.plot(fp[:, 0], fp[:, 1], 'k-', linewidth=2)
ax.fill(fp[:-1, 0], fp[:-1, 1], alpha=0.15, color='steelblue')

for w in walls:
    mid = (w.verts[0, :2] + w.verts[1, :2]) / 2
    direction = w.verts[1, :2] - w.verts[0, :2]
    perp      = np.array([-direction[1], direction[0]])
    perp     /= (np.linalg.norm(perp) + 1e-9)
    label_pos = mid + perp * 1.0   # offset label 1 m outside the wall
    ax.annotate(
        f"F{w.facade_id}\\n{w.width_m:.1f} m",
        xy=mid, xytext=label_pos,
        ha='center', va='center', fontsize=9,
        arrowprops=dict(arrowstyle='->', color='gray', lw=0.8),
        color=PALETTE[w.facade_id % len(PALETTE)],
    )
    # Wall line in facade colour
    ax.plot([w.verts[0,0], w.verts[1,0]],
            [w.verts[0,1], w.verts[1,1]],
            color=PALETTE[w.facade_id % len(PALETTE)], linewidth=3)

ax.set_aspect('equal')
ax.set_xlabel('X (m)')
ax.set_ylabel('Y (m)')
ax.set_title(f"{ACTIVE_BUILDING} — Floor Plan Footprint", fontsize=12)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_11_footprint.png', bbox_inches='tight', dpi=100)
plt.show()
"""))

cells.append(code("""
# ── 3-D perspective view ──────────────────────────────────────────────────────
fig  = plt.figure(figsize=(14, 8))
ax3d = fig.add_subplot(111, projection='3d')

facade_colors = [PALETTE[w.facade_id % len(PALETTE)] for w in walls]

for w, color in zip(walls, facade_colors):
    # Wall polygon (4 verts, counter-clockwise from outside)
    poly  = Poly3DCollection([[w.verts[i] for i in range(4)]],
                               alpha=0.35, facecolor=color, edgecolor='#333333',
                               linewidth=0.8)
    ax3d.add_collection3d(poly)

    # Label at wall centre
    ctr = w.verts.mean(axis=0)
    ax3d.text(ctr[0], ctr[1], ctr[2],
              f"F{w.facade_id}\\n{w.width_m:.1f}m",
              fontsize=8, ha='center', color='black')

    # Sketch floor-band lines on the wall
    if w.n_floors > 1:
        floor_h = w.height_m / w.n_floors
        dir_vec = (w.verts[1, :2] - w.verts[0, :2])
        for fl in range(1, w.n_floors):
            z = fl * floor_h
            ax3d.plot([w.verts[0,0], w.verts[1,0]],
                      [w.verts[0,1], w.verts[1,1]],
                      [z, z], color='#555555', linewidth=0.6, alpha=0.6)

# Roof polygon
if walls:
    roof_verts = [w.verts[3] for w in walls] + [walls[0].verts[2]]
    # Close with BR of last wall connecting back to TL of first
    roof_pts   = [w.verts[3] for w in walls]
    roof_poly  = Poly3DCollection([roof_pts],
                                   alpha=0.20, facecolor='#aaaaaa', edgecolor='#333333')
    ax3d.add_collection3d(roof_poly)

# Axes formatting
all_verts = np.vstack([w.verts for w in walls])
xs, ys, zs = all_verts[:,0], all_verts[:,1], all_verts[:,2]
margin = max(all_verts.ptp(axis=0)[:2]) * 0.15
ax3d.set_xlim(xs.min() - margin, xs.max() + margin)
ax3d.set_ylim(ys.min() - margin, ys.max() + margin)
ax3d.set_zlim(0, zs.max() * 1.2)
ax3d.set_xlabel('X (m)', fontsize=9)
ax3d.set_ylabel('Y (m)', fontsize=9)
ax3d.set_zlabel('Z (m)', fontsize=9)
ax3d.set_title(f"{ACTIVE_BUILDING} — 3-D Building Geometry (prototype)",
               fontsize=12, fontweight='bold')
ax3d.view_init(elev=25, azim=-50)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / f'{ACTIVE_BUILDING}_12_3d_geometry.png', bbox_inches='tight', dpi=120)
plt.show()
"""))

# ── 16: Stage 11 — Populate Building model ────────────────────────────────────
cells.append(md("""
---
## Stage 11 — Populate the Building Data Model

Translate the assembled 3-D geometry into a `Building` object that follows the
**floorspace.js** schema (`presto_geometry/models/building.py`).

Each detected facade becomes:
- A `Story` per floor (sharing the same `Geometry`)
- A `Space` per story occupying the full floor-plan face
- `WindowPlacement` entries on the wall edges

This object is the handoff point to the IDF, OSM, and HPXML exporters.
"""))

cells.append(code("""
import sys
sys.path.insert(0, str(REPO_ROOT))

from presto_geometry.models.building import (
    Building, Story, Space, Geometry,
    Vertex, Edge, Face,
    ThermalZone, WindowDefinition, WindowPlacement,
)


def walls_to_building(walls: List[Wall3D], building_name: str = None) -> Building:
    \"\"\"
    Convert the 3-D wall list into a floorspace.js-aligned Building object.
    One Story per detected floor, one Space per story, geometry from footprint.
    \"\"\"
    name = building_name or ACTIVE_BUILDING

    # ── Shared geometry: 2-D floor plan ──────────────────────────────────────
    # Vertices = floor plan corners (one per wall start-point)
    vertices, edges, faces = [], [], []
    vmap: Dict[str, int] = {}   # vertex_id → index

    floor_pts = [tuple(w.verts[0, :2].round(3)) for w in walls]   # (x, y) metres

    for i, (x, y) in enumerate(floor_pts):
        vid = f"v-{i}"
        vertices.append(Vertex(id=vid, x=float(x), y=float(y)))
        vmap[vid] = i

    # Edges: connect consecutive vertices (closed polygon)
    face_edge_ids = []
    n_pts = len(floor_pts)
    for i in range(n_pts):
        eid = f"e-{i}"
        v_start = f"v-{i}"
        v_end   = f"v-{(i + 1) % n_pts}"
        edges.append(Edge(id=eid, vertex_ids=(v_start, v_end), face_ids=["f-0"]))
        face_edge_ids.append(eid)
        # Back-fill edge_ids on vertices
        vertices[i].edge_ids.append(eid)
        vertices[(i + 1) % n_pts].edge_ids.append(eid)

    face = Face(id="f-0", edge_ids=face_edge_ids,
                edge_order=[0] * len(face_edge_ids))
    geom = Geometry(id="g-0", vertices=vertices, edges=edges, faces=[face])

    # ── Thermal zones: one per detected facade ────────────────────────────────
    thermal_zones = [ThermalZone(id=f"tz-{w.facade_id}",
                                  name=f"Zone_Facade_{w.facade_id}")
                     for w in walls]

    # ── Window definitions ─────────────────────────────────────────────────────
    if walls and walls[0].windows:
        sample_win = walls[0].windows[0]
        # Convert pixel dimensions to metres using facade scale
        outline = facade_outlines[walls[0].facade_id]
        m_per_px = outline.real_height_m / outline.pixel_height
        win_w_m  = round(sample_win['w'] * m_per_px, 2)
        win_h_m  = round(sample_win['h'] * m_per_px, 2)
    else:
        win_w_m, win_h_m = 1.2, 1.0   # sensible defaults

    window_defs = [WindowDefinition(
        id="wd-0", name="Detected Window",
        width=win_w_m, height=win_h_m, sill_height=0.9,
    )]

    # ── Stories: one per floor ────────────────────────────────────────────────
    n_floors_max = max((w.n_floors for w in walls), default=1)
    fh_m = (FLOOR_HEIGHT_M_COMMERCIAL if BUILDING_TYPE == 'commercial'
            else FLOOR_HEIGHT_M_RESIDENTIAL)
    stories = []
    for fl in range(n_floors_max):
        story_id = f"st-{fl}"
        spaces   = []
        for w in walls:
            if fl < w.n_floors:
                sp = Space(
                    id=f"sp-{fl}-{w.facade_id}",
                    name=f"Floor_{fl}_Facade_{w.facade_id}",
                    face_id="f-0",
                    thermal_zone_id=f"tz-{w.facade_id}",
                    floor_to_ceiling_height=fh_m,
                )
                spaces.append(sp)

        # Window placements on wall edges for this floor
        win_placements = []
        for w in walls:
            edge_id = f"e-{w.facade_id}"
            for win in w.windows:
                # alpha = centre x of window / facade pixel width
                alpha = float(np.clip(
                    (win['x'] + win['w'] / 2) / max(facade_outlines[w.facade_id].pixel_width, 1),
                    0.05, 0.95
                ))
                win_placements.append(WindowPlacement(
                    window_definition_id="wd-0",
                    edge_id=edge_id,
                    alpha=alpha,
                ))

        stories.append(Story(
            id=story_id,
            name=f"Floor_{fl}",
            floor_to_ceiling_height=fh_m,
            geometry=geom,
            spaces=spaces,
            windows=win_placements,
        ))

    building = Building(
        name=name,
        footprint=[tuple(pt) for pt in footprint_poly[:-1]],
        num_floors=n_floors_max,
        zones=thermal_zones,
        stories=stories,
        source_images=[str(r.path) for r in records],
    )
    return building


building = walls_to_building(walls)

print(f"Building: {building.name}")
print(f"  num_floors : {building.num_floors}")
print(f"  stories    : {len(building.stories)}")
print(f"  zones      : {len(building.zones)}")
print(f"  footprint  : {len(building.footprint)} vertices")
total_spaces  = sum(len(s.spaces)  for s in building.stories)
total_windows = sum(len(s.windows) for s in building.stories)
print(f"  spaces     : {total_spaces}")
print(f"  windows    : {total_windows}")
print(f"\\nFootprint coords (x, y) metres:")
for i, pt in enumerate(building.footprint):
    print(f"  [{i}] ({pt[0]:.2f}, {pt[1]:.2f})")
"""))

# ── 17: Summary (updated) ─────────────────────────────────────────────────────
cells.append(md("""
---
## Summary & Next Steps
"""))

cells.append(code("""
print("=" * 62)
print(f"  EDGE DETECTION + 3D GEOMETRY  —  {ACTIVE_BUILDING}")
print("=" * 62)

print(f"\\nImages processed : {len(records)}")
n_wide = sum(1 for r in records if r.lens_profile.focal_length_35mm <= 20)
print(f"  ultra-wide     : {n_wide}")
print(f"  standard       : {len(records) - n_wide}")

print("\\nLens correction  :")
for m, n in Counter(r.lens_profile.correction_method for r in records).items():
    print(f"  {m:<20} {n} images")

print(f"\\nFacades detected : {n_facades}")
for f, outline in facade_outlines.items():
    print(f"  Facade {f}: {outline.real_width_m:.1f} m wide  x  "
          f"{outline.real_height_m:.1f} m tall  ({outline.n_floors} floors)")

print(f"\\nBuilding model:")
print(f"  stories  : {len(building.stories)}")
print(f"  zones    : {len(building.zones)}")
print(f"  windows  : {sum(len(s.windows) for s in building.stories)}")
print(f"  footprint: {len(building.footprint)} pts")

print(f"\\nOutputs saved to: {OUTPUT_DIR}")
out_files = sorted(OUTPUT_DIR.glob(f'{ACTIVE_BUILDING}_*.png'))
for f in out_files:
    print(f"  {f.name}")

print(\"\"\"
Next steps
----------
  [x] Lens normalisation cascade
  [x] Sky / ground masking
  [x] Line segment extraction
  [x] Vanishing point analysis
  [x] Sequential facade grouping
  [x] Collinear gap bridging
  [x] Window candidate detection
  [x] Facade rectification (K R K^-1)
  [x] Building outline + scale calibration
  [x] 3-D footprint + wall assembly
  [x] Building data model population
  [ ] Cross-image line aggregation in rectified coords
  [ ] Corner-angle estimation from VP pairs (non-rectangular buildings)
  [ ] Rooftop geometry (pitched roofs from Loring Park)
  [ ] Export Building -> IDF / OSM / HPXML
\"\"\")
"""))

cells.append(code("""
print("=" * 62)
print(f"  EDGE DETECTION PROTOTYPE  —  {ACTIVE_BUILDING}")
print("=" * 62)

print(f"\\nImages processed : {len(records)}")
n_wide = sum(1 for r in records if r.lens_profile.focal_length_35mm <= 20)
print(f"  ultra-wide     : {n_wide}")
print(f"  standard       : {len(records) - n_wide}")

print("\\nLens correction  :")
for m, n in Counter(r.lens_profile.correction_method for r in records).items():
    print(f"  {m:<20} {n} images")

print(f"\\nFacades detected : {n_facades}")
for f in range(n_facades):
    fr    = [r for r in records if r.facade_id == f]
    n_h   = sum(int(np.sum(r.line_segments[:, 4] == 0))
                for r in fr if len(r.line_segments))
    n_v   = sum(int(np.sum(r.line_segments[:, 4] == 1))
                for r in fr if len(r.line_segments))
    wins  = detect_windows(
        max(fr, key=lambda r: int(np.sum(r.line_segments[:, 4] == 0))
            if len(r.line_segments) else 0)
    )
    print(f"  Facade {f}: {len(fr):2d} images  H={n_h}  V={n_v}  "
          f"window candidates={len(wins)}")

print(f"\\nOutputs → {OUTPUT_DIR}")
out_files = sorted(OUTPUT_DIR.glob(f'{ACTIVE_BUILDING}_*.png'))
for f in out_files:
    print(f"  {f.name}")

print(\"\"\"
Next steps
----------
  [ ] Facade rectification via homography from VP pair
  [ ] Cross-image line aggregation in rectified facade coords
  [ ] Roofline extraction + building corner detection
  [ ] 2-D footprint polygon assembly (closure check)
  [ ] Export Building → IDF / OSM / HPXML
\"\"\")
"""))

# ── Assemble and write notebook ──────────────────────────────────────────────
nb = new_notebook(cells=cells)
nb.metadata['kernelspec'] = {
    'display_name': 'Python 3',
    'language': 'python',
    'name': 'python3',
}
nb.metadata['language_info'] = {
    'name': 'python',
    'version': '3.11',
}

out_path = HERE / 'edge_detection_prototype.ipynb'
with open(out_path, 'w', encoding='utf-8') as fh:
    nbformat.write(nb, fh)

print(f"Notebook written -> {out_path}")
