#!/usr/bin/env python3
"""
Building Face Annotation Tool
==============================
Walk through each photo in a building dataset and mark line segments
on visible building faces.  Saves annotations to JSON for 3-D geometry
assembly with assemble_geometry.py.

Usage
-----
    python notebooks/annotate_building.py [building_name]

    building_name choices:  UnivStThomas  UnivStThomas_1loop  LoringPark

Controls
--------
    1 – 8        Select active face (Face 0 – 7).
    Left-click   Place a point.  Each completed segment automatically
                 chains — the endpoint becomes the next start point.
                 The chain stops automatically when you close back to
                 the first point.
    Right-click  Break the chain (cancel the pending start point).
    Escape       Same as right-click.
    Scroll       Zoom in / out centred on cursor.
    Middle-drag  Pan the view.
    R            Reset zoom to fit the full image.
    U            Undo last segment on the active face.
    C            Clear ALL annotations on the current image.
    Space / →    Save and advance to the next image.
    ← / B        Go back to the previous image.
    H            Toggle this help overlay.
    Q            Quit and save everything.

Snapping
--------
    When your cursor comes within 18 px of any existing segment endpoint
    a yellow ring appears — click to snap exactly to that point.  Snapping
    the end of one face's segment onto the end of another face's segment
    records the shared corner, which assemble_geometry.py uses to determine
    which faces are adjacent and in what order.

Polygon closure
---------------
    The first point you place in a new chain is shown as a small square.
    When you hover back near that point the snap ring appears on it; click
    to close the polygon — the chain stops automatically.

Tips
----
    • Trace all four edges of each visible face (top, bottom, left, right).
    • At visible corners between two faces, snap your segment endpoint onto
      an endpoint of the adjacent face to record the shared corner.
    • Annotations auto-save after every segment.
"""

import json
import sys
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.widgets import Button
import numpy as np

# ── Configuration ─────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent

PHOTO_DIRS = {
    'UnivStThomas':        REPO_ROOT / 'photos' / 'UnivStThomas',
    'UnivStThomas_1loop':  REPO_ROOT / 'photos' / 'UnivStThomas_1loop',
    'LoringPark':          REPO_ROOT / 'photos' / 'LoringPark',
}

ANNOTATIONS_DIR = REPO_ROOT / 'data' / 'annotations'

MAX_FACES = 8
FACE_COLORS = [
    '#E74C3C',   # 0 – red
    '#3498DB',   # 1 – blue
    '#2ECC71',   # 2 – green
    '#F39C12',   # 3 – orange
    '#9B59B6',   # 4 – purple
    '#1ABC9C',   # 5 – teal
    '#E67E22',   # 6 – dark orange
    '#E91E63',   # 7 – pink
]

DISPLAY_MAX_PX = 1300   # longest edge for on-screen display
SNAP_RADIUS_PX = 18     # display-pixel radius for vertex snapping

# Fixed layout constants
BTN_X    = 0.008   # left edge of sidebar
BTN_W    = 0.112   # button width
BTN_H    = 0.055   # button height
BTN_GAP  = 0.006   # vertical gap between buttons
# Face buttons fill a fixed area at top; other controls live below
FACE_Y_TOP   = 0.93                                  # top of first face button
FACE_SLOT_H  = BTN_H + BTN_GAP                       # height per face slot
FACE_AREA_H  = MAX_FACES * FACE_SLOT_H               # total reserved height
OTHER_Y_TOP  = FACE_Y_TOP - FACE_AREA_H - BTN_GAP * 2  # top of non-face controls

HELP_TEXT = (
    "CONTROLS\n"
    "────────────────────\n"
    "  1-8     Select face\n"
    "  Click   Place point\n"
    "          (chains auto)\n"
    "  R-click Break chain\n"
    "  Esc     Break chain\n"
    "  Scroll  Zoom\n"
    "  Mid-drg Pan\n"
    "  R       Reset view\n"
    "  N       Normalize\n"
    "  U       Undo segment\n"
    "  C       Clear image\n"
    "  Space   Next image\n"
    "  B / <-  Prev image\n"
    "  H       Help\n"
    "  Q       Quit & save\n"
    "\n"
    "SNAP / CLOSE\n"
    "────────────────────\n"
    "  Yellow ring = snap\n"
    "  Square = chain start\n"
    "  Snap to square to\n"
    "  close the polygon."
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def seg_to_list(p1, p2):
    return [float(p1[0]), float(p1[1]), float(p2[0]), float(p2[1])]


def empty_annotation():
    return {'faces': {}, 'shared_edges': []}


def _dim_color(hex_color: str, factor: float = 0.35) -> tuple:
    h = hex_color.lstrip('#')
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    return (r * factor, g * factor, b * factor)


# ── Main annotator ────────────────────────────────────────────────────────────

class Annotator:

    def __init__(self, building: str, photo_dir: Path, ann_dir: Path,
                 n_faces: int = 4):
        self.building  = building
        self.photo_dir = photo_dir
        self.ann_file  = ann_dir / f'{building}.json'
        ann_dir.mkdir(parents=True, exist_ok=True)

        # Discover images
        paths = []
        for ext in ('*.jpg', '*.jpeg', '*.JPG', '*.JPEG', '*.png', '*.PNG'):
            paths.extend(photo_dir.glob(ext))
        self.image_paths = sorted(paths)
        if not self.image_paths:
            raise FileNotFoundError(f'No images found in {photo_dir}')

        # Load existing annotations (resumable)
        if self.ann_file.exists():
            with open(self.ann_file, encoding='utf-8') as f:
                raw = json.load(f)
            self.annotations: dict = {k: v for k, v in raw.items()
                                      if isinstance(v, dict)}
            n = sum(1 for a in self.annotations.values()
                    if a.get('faces') or a.get('shared_edges'))
            # Auto-detect face count from existing annotations
            used = set()
            for a in self.annotations.values():
                used.update(int(k) for k in a.get('faces', {}).keys())
            if used:
                n_faces = max(n_faces, max(used) + 1)
            print(f'Loaded existing annotations — {n} images already annotated.')
        else:
            self.annotations = {}

        # State
        self.idx            = 0
        self.active_face    = 0
        self.n_faces        = max(2, min(n_faces, MAX_FACES))
        self.pending_pt     = None   # first click of current segment chain
        self.chain_start    = None   # very first point of the chain (for closure)
        self.show_help      = True
        self._display_scale = 1.0
        self._cursor_line   = None
        self._snap_marker   = None
        self._pan_start     = None  # (x_disp, y_disp) for middle-button pan
        self._normalize     = False  # CLAHE contrast normalisation toggle
        self._view_idx      = -1     # which image index the current xlim/ylim belong to

        self._build_ui()
        self._redraw()

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.fig = plt.figure(figsize=(17, 9))
        self.fig.patch.set_facecolor('#16213e')

        # Image axes (right ~87 %)
        self.ax = self.fig.add_axes([0.135, 0.02, 0.855, 0.91])
        self.ax.axis('off')

        # ── Face buttons (top section, rebuilt on n_faces change) ─────────
        self._face_btns: list[Button] = []
        self._build_face_buttons()

        # ── Face count +/- (just below the face area) ─────────────────────
        y = OTHER_Y_TOP
        self.fig.text(BTN_X, y + BTN_H + 0.003,
                      'BUILDING FACES', color='#aaaaaa',
                      fontsize=7, fontweight='bold',
                      transform=self.fig.transFigure)
        half_w = (BTN_W - 0.004) / 2
        ax_add = self.fig.add_axes([BTN_X,             y, half_w, BTN_H])
        ax_rem = self.fig.add_axes([BTN_X + half_w + 0.004, y, half_w, BTN_H])
        self._add_face_btn = Button(ax_add, '+ Face', color='#1a3a2a',
                                    hovercolor='#2a5a3a')
        self._rem_face_btn = Button(ax_rem, '- Face', color='#3a1a1a',
                                    hovercolor='#5a2a2a')
        for b in (self._add_face_btn, self._rem_face_btn):
            b.label.set_color('white')
            b.label.set_fontsize(8)
        self._add_face_btn.on_clicked(lambda _: self._change_n_faces(+1))
        self._rem_face_btn.on_clicked(lambda _: self._change_n_faces(-1))
        y -= BTN_H + BTN_GAP * 3

        # ── Draw controls ─────────────────────────────────────────────────
        self.fig.text(BTN_X, y + BTN_H + 0.003, 'DRAW', color='#aaaaaa',
                      fontsize=7, fontweight='bold',
                      transform=self.fig.transFigure)
        ax_stop = self.fig.add_axes([BTN_X, y, BTN_W, BTN_H])
        self._stop_btn = Button(ax_stop, 'Stop  (Esc)', color='#223', hovercolor='#445')
        self._stop_btn.label.set_color('white')
        self._stop_btn.label.set_fontsize(8)
        self._stop_btn.on_clicked(lambda _: self._stop_drawing())
        y -= BTN_H + BTN_GAP * 3

        # ── Navigation ────────────────────────────────────────────────────
        self.fig.text(BTN_X, y + BTN_H + 0.003, 'NAVIGATE', color='#aaaaaa',
                      fontsize=7, fontweight='bold',
                      transform=self.fig.transFigure)
        ax_next = self.fig.add_axes([BTN_X, y, BTN_W, BTN_H])
        self._next_btn = Button(ax_next, 'Next  (Space)', color='#1a3a5c',
                                hovercolor='#1e5080')
        self._next_btn.label.set_color('white')
        self._next_btn.label.set_fontsize(8)
        self._next_btn.on_clicked(lambda _: self._go_next())
        y -= BTN_H + BTN_GAP
        ax_back = self.fig.add_axes([BTN_X, y, BTN_W, BTN_H])
        self._back_btn = Button(ax_back, 'Back  (B)', color='#1a3a5c',
                                hovercolor='#1e5080')
        self._back_btn.label.set_color('white')
        self._back_btn.label.set_fontsize(8)
        self._back_btn.on_clicked(lambda _: self._go_back())
        y -= BTN_H + BTN_GAP * 3

        # ── Edit ──────────────────────────────────────────────────────────
        self.fig.text(BTN_X, y + BTN_H + 0.003, 'EDIT', color='#aaaaaa',
                      fontsize=7, fontweight='bold',
                      transform=self.fig.transFigure)
        ax_undo = self.fig.add_axes([BTN_X, y, BTN_W, BTN_H])
        self._undo_btn = Button(ax_undo, 'Undo  (U)', color='#2c3e50',
                                hovercolor='#3d5166')
        self._undo_btn.label.set_color('white')
        self._undo_btn.label.set_fontsize(8)
        self._undo_btn.on_clicked(lambda _: self._undo())
        y -= BTN_H + BTN_GAP
        ax_clr = self.fig.add_axes([BTN_X, y, BTN_W, BTN_H])
        self._clear_btn = Button(ax_clr, 'Clear image  (C)',
                                 color='#5c1a1a', hovercolor='#8b2222')
        self._clear_btn.label.set_color('white')
        self._clear_btn.label.set_fontsize(8)
        self._clear_btn.on_clicked(lambda _: self._clear_image())
        y -= BTN_H + BTN_GAP
        ax_rst = self.fig.add_axes([BTN_X, y, BTN_W, BTN_H])
        self._reset_btn = Button(ax_rst, 'Reset view  (R)',
                                 color='#2c3e50', hovercolor='#3d5166')
        self._reset_btn.label.set_color('white')
        self._reset_btn.label.set_fontsize(8)
        self._reset_btn.on_clicked(lambda _: self._reset_view())
        y -= BTN_H + BTN_GAP
        ax_norm = self.fig.add_axes([BTN_X, y, BTN_W, BTN_H])
        self._norm_btn = Button(ax_norm, 'Normalize  (N)',
                                color='#1a3a3a', hovercolor='#2a5a5a')
        self._norm_btn.label.set_color('white')
        self._norm_btn.label.set_fontsize(8)
        self._norm_btn.on_clicked(lambda _: self._toggle_normalize())

        # ── Event connections ─────────────────────────────────────────────
        self.fig.canvas.mpl_connect('button_press_event',   self._on_click)
        self.fig.canvas.mpl_connect('button_release_event', self._on_release)
        self.fig.canvas.mpl_connect('motion_notify_event',  self._on_motion)
        self.fig.canvas.mpl_connect('key_press_event',      self._on_key)
        self.fig.canvas.mpl_connect('scroll_event',         self._on_scroll)

    def _build_face_buttons(self):
        """Create face-selector buttons for the current n_faces value."""
        for btn in self._face_btns:
            self.fig.delaxes(btn.ax)
        self._face_btns = []

        for i in range(self.n_faces):
            color = FACE_COLORS[i]
            y = FACE_Y_TOP - i * FACE_SLOT_H
            ax_b = self.fig.add_axes([BTN_X, y, BTN_W, BTN_H])
            lbl  = f'F{i}  (key {i+1})' if i < 8 else f'F{i}'
            btn  = Button(ax_b, lbl, color=color, hovercolor=color)
            btn.label.set_color('white')
            btn.label.set_fontsize(8.5)
            btn.on_clicked(lambda _, fid=i: self._select_face(fid))
            self._face_btns.append(btn)

        self._update_face_buttons()

    def _update_face_buttons(self):
        for i, btn in enumerate(self._face_btns):
            if i == self.active_face:
                btn.ax.set_facecolor(FACE_COLORS[i])
                for sp in btn.ax.spines.values():
                    sp.set_edgecolor('white')
                    sp.set_linewidth(2.2)
            else:
                btn.ax.set_facecolor(_dim_color(FACE_COLORS[i]))
                for sp in btn.ax.spines.values():
                    sp.set_edgecolor('#333')
                    sp.set_linewidth(0.8)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _current_key(self) -> str:
        return self.image_paths[self.idx].name

    def _current_ann(self) -> dict:
        key = self._current_key()
        if key not in self.annotations:
            self.annotations[key] = empty_annotation()
        return self.annotations[key]

    def _load_display_image(self):
        img = cv2.imread(str(self.image_paths[self.idx]))
        if img is None:
            raise IOError(f'Cannot read {self.image_paths[self.idx]}')
        h, w  = img.shape[:2]
        scale = min(DISPLAY_MAX_PX / max(h, w), 1.0)
        if scale < 1.0:
            img = cv2.resize(img, (int(w * scale), int(h * scale)),
                             interpolation=cv2.INTER_AREA)
        if self._normalize:
            # CLAHE on the L channel of LAB — boosts local contrast without
            # blowing out sky or crushing shadows, preserves hue.
            lab   = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l     = clahe.apply(l)
            img   = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB), scale

    def _to_orig(self, x, y):
        return x / self._display_scale, y / self._display_scale

    def _to_disp(self, x, y):
        return x * self._display_scale, y * self._display_scale

    def _all_snap_pts_disp(self):
        """
        Display-coord points eligible for snapping:
        all saved segment endpoints + the chain start (for closure).
        """
        ann = self._current_ann()
        pts = []
        for segs in ann['faces'].values():
            for seg in segs:
                pts.append(self._to_disp(seg[0], seg[1]))
                pts.append(self._to_disp(seg[2], seg[3]))
        if self.chain_start is not None:
            pts.append(self._to_disp(*self.chain_start))
        return pts

    def _find_snap(self, xd: float, yd: float):
        """Return (snapped_xd, snapped_yd) if within radius, else None."""
        best_d, best_pt = SNAP_RADIUS_PX, None
        for (ex, ey) in self._all_snap_pts_disp():
            d = np.hypot(xd - ex, yd - ey)
            if d < best_d:
                best_d, best_pt = d, (ex, ey)
        return best_pt

    # ─────────────────────────────────────────────────────────────────────────
    # Rendering
    # ─────────────────────────────────────────────────────────────────────────

    def _redraw(self):
        # Preserve zoom / pan only when redrawing the same image.
        # On first load (or after navigation) _view_idx != self.idx so we
        # always start at full zoom — avoiding the matplotlib-default-limits
        # bug that previously zoomed hard into the top-left corner.
        same_image = (self._view_idx == self.idx)
        if same_image:
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()

        self.ax.clear()
        self.ax.axis('off')
        self._cursor_line = None
        self._snap_marker = None

        img_rgb, self._display_scale = self._load_display_image()
        self.ax.imshow(img_rgb, aspect='auto')

        ann = self._current_ann()

        # ── Saved segments ────────────────────────────────────────────────
        for fid_str, segs in ann['faces'].items():
            color = FACE_COLORS[int(fid_str) % MAX_FACES]
            for seg in segs:
                x1d, y1d = self._to_disp(seg[0], seg[1])
                x2d, y2d = self._to_disp(seg[2], seg[3])
                self.ax.plot([x1d, x2d], [y1d, y2d], '-',
                             color=color, lw=2.2, alpha=0.9,
                             solid_capstyle='round')
                self.ax.plot([x1d, x2d], [y1d, y2d], 'o',
                             color=color, ms=5, alpha=0.9)

        # ── Legacy shared-edge markers ────────────────────────────────────
        for se in ann.get('shared_edges', []):
            s = se.get('segment', [])
            if len(s) == 4:
                x1d, y1d = self._to_disp(s[0], s[1])
                x2d, y2d = self._to_disp(s[2], s[3])
                self.ax.plot([x1d, x2d], [y1d, y2d], '--',
                             color='white', lw=1.8, alpha=0.6)

        # ── Chain start marker (square) ───────────────────────────────────
        if self.chain_start is not None:
            csx, csy = self._to_disp(*self.chain_start)
            self.ax.plot(csx, csy, 's',
                         color=FACE_COLORS[self.active_face], ms=12,
                         markeredgecolor='white', mew=2.0, alpha=0.9)

        # ── Pending point marker (circle) ─────────────────────────────────
        if self.pending_pt is not None and self.pending_pt != self.chain_start:
            pdx, pdy = self._to_disp(*self.pending_pt)
            self.ax.plot(pdx, pdy, 'o',
                         color=FACE_COLORS[self.active_face], ms=10,
                         markeredgecolor='white', mew=1.8)

        # ── Help overlay ──────────────────────────────────────────────────
        if self.show_help:
            self.ax.text(0.01, 0.99, HELP_TEXT,
                         transform=self.ax.transAxes,
                         va='top', ha='left', fontsize=7.5,
                         color='white', family='monospace',
                         bbox=dict(boxstyle='round,pad=0.5',
                                   fc='#111', ec='#444', alpha=0.88))

        # ── Legend ────────────────────────────────────────────────────────
        patches = []
        for fid in range(self.n_faces):
            color = FACE_COLORS[fid]
            n     = len(ann['faces'].get(str(fid), []))
            star  = '> ' if fid == self.active_face else '  '
            patches.append(mpatches.Patch(
                color=color, label=f'{star}F{fid}  ({n} segs)'))
        self.ax.legend(handles=patches, loc='upper right',
                       fontsize=8, framealpha=0.88,
                       facecolor='#16213e', labelcolor='white',
                       edgecolor='#444')

        # ── Title ─────────────────────────────────────────────────────────
        n_segs    = sum(len(v) for v in ann['faces'].values())
        annotated = sum(1 for a in self.annotations.values()
                        if isinstance(a, dict)
                        and (a.get('faces') or a.get('shared_edges')))
        chain_tag = '  [chaining]' if self.pending_pt is not None else ''
        title = (
            f'[{self.idx + 1}/{len(self.image_paths)}]  {self._current_key()}'
            f'   |  Face: F{self.active_face}'
            f'  |  segs: {n_segs}'
            f'  |  {annotated}/{len(self.image_paths)} annotated'
            f'  |  {self.n_faces} faces'
            f'{chain_tag}'
            f'   |  H=help  Space=next  Q=quit'
        )
        self.fig.suptitle(title, fontsize=8.5, color='white',
                          fontweight='bold', x=0.57,
                          bbox=dict(fc='#16213e', ec='none', pad=3))

        # Restore zoom / pan when staying on the same image; otherwise the
        # imshow auto-fit already gives us the correct full-image view.
        if same_image:
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)

        self._view_idx = self.idx   # mark which image these limits belong to
        self._update_face_buttons()
        self.fig.canvas.draw_idle()

    # ─────────────────────────────────────────────────────────────────────────
    # Event handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_click(self, event):
        if event.xdata is None:
            return

        # Middle-button pan: record start
        if event.button == 2:
            self._pan_start = (event.xdata, event.ydata)
            return

        if event.inaxes is not self.ax:
            return

        # Right-click: break chain
        if event.button == 3:
            self._stop_drawing()
            return
        if event.button != 1:
            return

        # Resolve snap
        snap = self._find_snap(event.xdata, event.ydata)
        if snap:
            x, y = self._to_orig(*snap)
        else:
            x, y = self._to_orig(event.xdata, event.ydata)

        # First click: start the chain
        if self.pending_pt is None:
            self.pending_pt  = (x, y)
            self.chain_start = (x, y)
            self._redraw()
            return

        # Second click: complete the segment
        p1, p2  = self.pending_pt, (x, y)
        ann     = self._current_ann()
        fid_str = str(self.active_face)
        ann['faces'].setdefault(fid_str, []).append(seg_to_list(p1, p2))
        print(f'  F{self.active_face}: '
              f'({p1[0]:.0f},{p1[1]:.0f}) -> ({p2[0]:.0f},{p2[1]:.0f})')
        self._save()

        # Check polygon closure: did we snap back to the chain start?
        closed = (
            self.chain_start is not None
            and snap is not None
            and np.hypot(x - self.chain_start[0],
                         y - self.chain_start[1]) < 3.0
        )
        if closed:
            print(f'  F{self.active_face}: polygon closed.')
            self.pending_pt  = None
            self.chain_start = None
        else:
            self.pending_pt = p2   # continue chain from end of this segment

        self._redraw()

    def _on_release(self, event):
        if event.button == 2:
            self._pan_start = None

    def _on_motion(self, event):
        # Middle-button pan
        if self._pan_start is not None and event.button == 2:
            if event.inaxes is self.ax and event.xdata is not None:
                dx = self._pan_start[0] - event.xdata
                dy = self._pan_start[1] - event.ydata
                self.ax.set_xlim(self.ax.get_xlim()[0] + dx,
                                 self.ax.get_xlim()[1] + dx)
                self.ax.set_ylim(self.ax.get_ylim()[0] + dy,
                                 self.ax.get_ylim()[1] + dy)
                self.fig.canvas.draw_idle()
            return

        if event.inaxes is not self.ax or event.xdata is None:
            # Remove transient artists if cursor leaves axes
            changed = False
            for attr in ('_cursor_line', '_snap_marker'):
                artist = getattr(self, attr)
                if artist is not None:
                    try:
                        artist.remove()
                    except Exception:
                        pass
                    setattr(self, attr, None)
                    changed = True
            if changed:
                self.fig.canvas.draw_idle()
            return

        # Remove previous transient artists
        for attr in ('_cursor_line', '_snap_marker'):
            artist = getattr(self, attr)
            if artist is not None:
                try:
                    artist.remove()
                except Exception:
                    pass
                setattr(self, attr, None)

        # Snap indicator
        snap = self._find_snap(event.xdata, event.ydata)
        if snap:
            sm, = self.ax.plot(snap[0], snap[1], 'o',
                               color='yellow', ms=18,
                               markerfacecolor='none',
                               markeredgewidth=2.5, alpha=0.9)
            self._snap_marker = sm

        # Rubber-band line
        if self.pending_pt is not None:
            pdx, pdy = self._to_disp(*self.pending_pt)
            tx = snap[0] if snap else event.xdata
            ty = snap[1] if snap else event.ydata
            line, = self.ax.plot([pdx, tx], [pdy, ty], '-',
                                 color=FACE_COLORS[self.active_face],
                                 lw=1.5, alpha=0.55)
            self._cursor_line = line

        self.fig.canvas.draw_idle()

    def _on_scroll(self, event):
        if event.inaxes is not self.ax or event.xdata is None:
            return
        factor = 0.85 if event.button == 'up' else 1.0 / 0.85
        cx, cy = event.xdata, event.ydata
        self.ax.set_xlim(cx + (self.ax.get_xlim()[0] - cx) * factor,
                         cx + (self.ax.get_xlim()[1] - cx) * factor)
        self.ax.set_ylim(cy + (self.ax.get_ylim()[0] - cy) * factor,
                         cy + (self.ax.get_ylim()[1] - cy) * factor)
        self.fig.canvas.draw_idle()

    def _on_key(self, event):
        k = event.key

        if k in ('1','2','3','4','5','6','7','8'):
            fid = int(k) - 1
            if fid < self.n_faces:
                self._select_face(fid)

        elif k == 'escape':
            self._stop_drawing()

        elif k in ('r', 'R'):
            self._reset_view()

        elif k in ('u', 'U'):
            self._undo()

        elif k in ('c', 'C'):
            self._clear_image()

        elif k in (' ', 'right'):
            self._go_next()

        elif k in ('b', 'B', 'left'):
            self._go_back()

        elif k in ('n', 'N'):
            self._toggle_normalize()

        elif k in ('h', 'H'):
            self.show_help = not self.show_help
            self._redraw()

        elif k in ('q', 'Q'):
            self._save()
            print(f'\nAll annotations saved -> {self.ann_file}')
            plt.close(self.fig)

    # ─────────────────────────────────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────────────────────────────────

    def _select_face(self, fid: int):
        self.active_face = fid
        self.pending_pt  = None
        self.chain_start = None
        self._redraw()

    def _change_n_faces(self, delta: int):
        new_n = max(2, min(self.n_faces + delta, MAX_FACES))
        if new_n == self.n_faces:
            return
        self.n_faces = new_n
        if self.active_face >= self.n_faces:
            self.active_face = self.n_faces - 1
        self._build_face_buttons()
        self._redraw()

    def _stop_drawing(self):
        self.pending_pt  = None
        self.chain_start = None
        self._redraw()

    def _toggle_normalize(self):
        self._normalize = not self._normalize
        label = 'Normalize ON  (N)' if self._normalize else 'Normalize  (N)'
        color = '#0a5a5a' if self._normalize else '#1a3a3a'
        self._norm_btn.label.set_text(label)
        self._norm_btn.ax.set_facecolor(color)
        print(f'  Normalisation: {"ON (CLAHE)" if self._normalize else "OFF"}')
        self._redraw()

    def _reset_view(self):
        img_rgb, _ = self._load_display_image()
        ih, iw = img_rgb.shape[:2]
        self.ax.set_xlim(-0.5, iw - 0.5)
        self.ax.set_ylim(ih - 0.5, -0.5)
        self.fig.canvas.draw_idle()

    def _go_next(self):
        self._save()
        if self.idx < len(self.image_paths) - 1:
            self.idx        += 1
            self.pending_pt  = None
            self.chain_start = None
            self._redraw()
        else:
            print('Last image — press Q to quit.')

    def _go_back(self):
        if self.idx > 0:
            self.idx        -= 1
            self.pending_pt  = None
            self.chain_start = None
            self._redraw()

    def _undo(self):
        ann     = self._current_ann()
        fid_str = str(self.active_face)
        if ann['faces'].get(fid_str):
            removed = ann['faces'][fid_str].pop()
            print(f'  Undo: F{self.active_face} segment removed')
        elif ann.get('shared_edges'):
            ann['shared_edges'].pop()
            print('  Undo: last shared edge')
        self.pending_pt  = None
        self.chain_start = None
        self._save()
        self._redraw()

    def _clear_image(self):
        self.annotations[self._current_key()] = empty_annotation()
        self.pending_pt  = None
        self.chain_start = None
        print(f'  Cleared all annotations for {self._current_key()}')
        self._save()
        self._redraw()

    # ─────────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────────

    def _save(self):
        with open(self.ann_file, 'w', encoding='utf-8') as f:
            json.dump(self.annotations, f, indent=2)

    def run(self):
        print(f"\nAnnotating '{self.building}'  ({len(self.image_paths)} images)")
        print(f"Annotations -> {self.ann_file}")
        print(f"Building faces: {self.n_faces}  (use +/- buttons to change)")
        print("Press H in the window to see controls.\n")
        plt.show()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Interactive building face annotation tool')
    parser.add_argument(
        'building', nargs='?', default='UnivStThomas_1loop',
        choices=list(PHOTO_DIRS.keys()),
        help='Building dataset to annotate')
    parser.add_argument(
        '--faces', type=int, default=4,
        help='Initial number of building faces to annotate (default: 4)')
    args = parser.parse_args()

    photo_dir = PHOTO_DIRS[args.building]
    if not photo_dir.exists():
        print(f'ERROR: Photo directory not found: {photo_dir}')
        sys.exit(1)

    ann_dir = ANNOTATIONS_DIR / args.building
    tool = Annotator(args.building, photo_dir, ann_dir, n_faces=args.faces)
    tool.run()


if __name__ == '__main__':
    main()
