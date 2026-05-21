#!/usr/bin/env python3
"""
PrestoGeometry Launcher
=======================
Step-by-step guide from photos to a Floorspace.js geometry file.
"""

import subprocess
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, font as tkfont

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT       = Path(__file__).resolve().parent.parent
TOOLS_DIR       = Path(__file__).resolve().parent
PYTHON_EXE      = sys.executable
ANNOTATE_SCRIPT = TOOLS_DIR / 'annotate_building.py'
ASSEMBLE_SCRIPT = TOOLS_DIR / 'assemble_geometry.py'
PHOTOS_ROOT     = REPO_ROOT / 'photos'
ANN_ROOT        = REPO_ROOT / 'data' / 'annotations'
OUT_ROOT        = REPO_ROOT / 'data' / 'outputs' / 'geometry'

FLOORSPACE_WEB  = 'https://nrel.github.io/floorspace.js/'

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

BG         = '#1a1a2e'
PANEL      = '#16213e'
PANEL2     = '#0f3460'
ACCENT     = '#e94560'
GRN        = '#27ae60'
BLUE       = '#3498db'
ORANGE     = '#e67e22'
TEXT       = '#ecedee'
DIM        = '#7f8c8d'
CHECK_ON   = '#2ecc71'
CHECK_OFF  = '#4a4a5a'

STEP_COLORS = ['#1a4a2a', '#1a3060', '#4a3010', '#2a1a4a']

# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------

class Launcher:

    POLL_MS = 2000   # how often to refresh status indicators (ms)

    def __init__(self):
        self.root = tk.Tk()
        self.root.title('PrestoGeometry')
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self._photos_dir    = tk.StringVar()
        self._building_name = tk.StringVar()
        self._n_faces       = tk.IntVar(value=4)
        self._status_var    = tk.StringVar(value='Select a photos folder to begin.')

        # status indicator labels (updated by _refresh_status)
        self._ind_ann  = None   # tk.Label for annotation indicator
        self._ind_geom = None   # tk.Label for geometry indicator
        self._btn_assemble_frame = None
        self._btn_open_frame = None

        self._build_ui()
        self.root.update_idletasks()
        self._center_window()
        self._refresh_status()
        self._building_name.trace_add('write', lambda *_: self._refresh_status())

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        # ── Title ──────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill='x', padx=20, pady=(16, 0))

        title_font = tkfont.Font(family='Helvetica', size=22, weight='bold')
        tk.Label(header, text='Presto', font=title_font,
                 fg=ORANGE, bg=BG).pack(side='left')
        tk.Label(header, text='Geometry', font=title_font,
                 fg=TEXT, bg=BG).pack(side='left')
        tk.Label(header,
                 text='  |  building photos  →  energy model geometry',
                 fg=DIM, bg=BG, font=('Helvetica', 10)).pack(side='left', pady=4)

        tk.Frame(self.root, bg=BLUE, height=2).pack(fill='x', padx=20, pady=(4, 12))

        # ── Step 1 – Photos folder ─────────────────────────────────────────
        self._step_block(
            number=1,
            title='Select a Photos Folder',
            desc='Point to a folder of walk-around photos of the building exterior.\n'
                 'Photos should circle the building so all exterior faces are captured.',
            color=STEP_COLORS[0],
            body_fn=self._build_step1_body,
        )

        # ── Step 2 – Annotate ──────────────────────────────────────────────
        self._step_block(
            number=2,
            title='Annotate Building Faces',
            desc='Trace the edges of each building face in the photos.\n'
                 'Snap shared corners between faces so the assembler knows the face order.',
            color=STEP_COLORS[1],
            body_fn=self._build_step2_body,
        )

        # ── Step 3 – Assemble ──────────────────────────────────────────────
        self._step_block(
            number=3,
            title='Assemble & Save Geometry',
            desc='Review estimated face dimensions, solve for a closed floor plan,\n'
                 'and save the Floorspace.js geometry file.',
            color=STEP_COLORS[2],
            body_fn=self._build_step3_body,
        )

        # ── Step 4 – Output ────────────────────────────────────────────────
        self._step_block(
            number=4,
            title='Use the Output',
            desc='The saved .json file is a valid Floorspace.js geometry.\n'
                 'Share it for further refinement into an EnergyPlus / OpenStudio model.',
            color=STEP_COLORS[3],
            body_fn=self._build_step4_body,
        )

        # ── Status bar ─────────────────────────────────────────────────────
        bar = tk.Frame(self.root, bg='#0d1726')
        bar.pack(fill='x', side='bottom')
        tk.Label(bar, textvariable=self._status_var,
                 fg=DIM, bg='#0d1726',
                 font=('Helvetica', 8), anchor='w').pack(fill='x', padx=10, pady=4)

    def _step_block(self, number, title, desc, color, body_fn):
        """Render one numbered step card."""
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill='x', padx=20, pady=(0, 8))

        # Left number badge
        badge = tk.Frame(outer, bg=color, width=36)
        badge.pack(side='left', fill='y')
        badge.pack_propagate(False)
        tk.Label(badge, text=str(number), font=('Helvetica', 16, 'bold'),
                 fg=TEXT, bg=color).pack(expand=True)

        # Right content
        content = tk.Frame(outer, bg=PANEL, padx=14, pady=10)
        content.pack(side='left', fill='x', expand=True)

        tk.Label(content, text=title,
                 font=('Helvetica', 11, 'bold'),
                 fg=TEXT, bg=PANEL, anchor='w').pack(fill='x')
        tk.Label(content, text=desc,
                 font=('Helvetica', 8),
                 fg=DIM, bg=PANEL, anchor='w', justify='left').pack(fill='x', pady=(2, 6))

        body_fn(content)

    # -- Step body builders --------------------------------------------------

    def _build_step1_body(self, parent):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill='x')

        entry = tk.Entry(row, textvariable=self._photos_dir, width=44,
                         bg='#0d1b2e', fg=TEXT, insertbackground=TEXT,
                         relief='flat', font=('Consolas', 9))
        entry.pack(side='left', padx=(0, 6), ipady=3)
        self._btn(row, 'Browse…', self._browse, PANEL2).pack(side='left')

        row2 = tk.Frame(parent, bg=PANEL)
        row2.pack(fill='x', pady=(6, 0))
        tk.Label(row2, text='Building name:', fg=DIM, bg=PANEL,
                 font=('Helvetica', 9)).pack(side='left')
        tk.Entry(row2, textvariable=self._building_name, width=28,
                 bg='#0d1b2e', fg=TEXT, insertbackground=TEXT,
                 relief='flat', font=('Consolas', 9)).pack(side='left', padx=(8, 0), ipady=3)

    def _build_step2_body(self, parent):
        # Settings row
        settings = tk.Frame(parent, bg=PANEL)
        settings.pack(fill='x', pady=(0, 6))
        tk.Label(settings, text='Max faces to annotate:',
                 fg=DIM, bg=PANEL, font=('Helvetica', 9)).pack(side='left')
        tk.Spinbox(settings, textvariable=self._n_faces,
                   from_=2, to=8, width=3,
                   bg='#0d1b2e', fg=TEXT, buttonbackground=PANEL,
                   relief='flat', font=('Consolas', 9)).pack(side='left', padx=(6, 0))
        tk.Label(settings,
                 text='  (1–8 faces; use the number keys in the tool to switch faces)',
                 fg=DIM, bg=PANEL, font=('Helvetica', 8)).pack(side='left')

        # Status indicator + button
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill='x')

        self._ind_ann = tk.Label(row, text='● No annotations yet',
                                 fg=CHECK_OFF, bg=PANEL,
                                 font=('Helvetica', 9))
        self._ind_ann.pack(side='left', padx=(0, 12))

        self._btn(row, 'Open Annotation Tool', self._launch_annotate, GRN).pack(side='left')

    def _build_step3_body(self, parent):
        # Status indicator + button
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill='x')

        self._ind_geom = tk.Label(row, text='● No geometry saved yet',
                                  fg=CHECK_OFF, bg=PANEL,
                                  font=('Helvetica', 9))
        self._ind_geom.pack(side='left', padx=(0, 12))

        self._btn(row, 'Open Assembly Tool', self._launch_assemble, BLUE).pack(side='left')

    def _build_step4_body(self, parent):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill='x')

        self._btn_open_frame = tk.Frame(row, bg=PANEL)
        self._btn_open_frame.pack(side='left', padx=(0, 10))

        self._btn(self._btn_open_frame, 'Open Output Folder',
                  self._open_output_folder, '#4a3a1a').pack(side='left')

        self._btn(row, 'Floorspace.js Web Editor ↗',
                  lambda: webbrowser.open(FLOORSPACE_WEB), '#2a1a4a').pack(side='left')

        note = tk.Frame(parent, bg=PANEL)
        note.pack(fill='x', pady=(6, 0))
        tk.Label(note,
                 text='The .json file in the output folder can be loaded into the\n'
                      'Floorspace.js web editor (File → Import) for visual review,\n'
                      'or passed directly to the IDF/OSM/HPXML export step.',
                 fg=DIM, bg=PANEL,
                 font=('Helvetica', 8), justify='left', anchor='w').pack(fill='x')

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _btn(self, parent, text, command, color):
        b = tk.Button(parent, text=text, command=command,
                      bg=color, fg=TEXT,
                      activebackground=color, activeforeground=TEXT,
                      relief='flat', padx=10, pady=4,
                      font=('Helvetica', 9))
        return b

    def _ann_file(self):
        name = self._building_name.get().strip()
        if not name:
            return None
        return ANN_ROOT / name / f'{name}.json'

    def _geom_file(self):
        name = self._building_name.get().strip()
        if not name:
            return None
        return OUT_ROOT / name / f'{name}.json'

    def _refresh_status(self, *_):
        """Update step-2 and step-3 status indicators based on file existence."""
        ann  = self._ann_file()
        geom = self._geom_file()

        if self._ind_ann is not None:
            if ann and ann.exists():
                self._ind_ann.config(text='✔ Annotations found', fg=CHECK_ON)
            else:
                self._ind_ann.config(text='● No annotations yet', fg=CHECK_OFF)

        if self._ind_geom is not None:
            if geom and geom.exists():
                self._ind_geom.config(text='✔ Geometry saved', fg=CHECK_ON)
            else:
                self._ind_geom.config(text='● No geometry saved yet', fg=CHECK_OFF)

        # Schedule next poll
        self.root.after(self.POLL_MS, self._refresh_status)

    def _center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f'+{(sw - w) // 2}+{(sh - h) // 2}')

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _browse(self):
        initial = str(PHOTOS_ROOT) if PHOTOS_ROOT.exists() else str(Path.home())
        chosen = filedialog.askdirectory(
            title='Select the folder containing building photos',
            initialdir=initial,
        )
        if not chosen:
            return
        p = Path(chosen)
        self._photos_dir.set(str(p))
        if not self._building_name.get().strip():
            self._building_name.set(p.name)
        self._status_var.set(f'Photos folder: {p}')

    def _validate(self):
        photos = self._photos_dir.get().strip()
        name   = self._building_name.get().strip()
        if not photos:
            return False, 'Please select a photos folder (Step 1).'
        if not Path(photos).exists():
            return False, f'Photos folder not found: {photos}'
        if not name:
            return False, 'Please enter a building name (Step 1).'
        return True, ''

    def _launch_annotate(self):
        ok, msg = self._validate()
        if not ok:
            self._status_var.set(f'Cannot launch: {msg}')
            return
        photos = self._photos_dir.get().strip()
        name   = self._building_name.get().strip()
        faces  = self._n_faces.get()
        cmd = [PYTHON_EXE, str(ANNOTATE_SCRIPT),
               name, '--photos-dir', photos, '--faces', str(faces)]
        self._status_var.set(f'Opened annotation tool for "{name}" — see the new window.')
        subprocess.Popen(cmd, cwd=str(REPO_ROOT))

    def _launch_assemble(self):
        ok, msg = self._validate()
        if not ok:
            self._status_var.set(f'Cannot launch: {msg}')
            return

        ann = self._ann_file()
        if ann is None or not ann.exists():
            self._status_var.set(
                f'No annotation file found for "{self._building_name.get().strip()}" — '
                'complete Step 2 first.')
            return

        name = self._building_name.get().strip()
        cmd = [PYTHON_EXE, str(ASSEMBLE_SCRIPT), name]
        self._status_var.set(f'Opened assembly tool for "{name}" — see the new window.')
        subprocess.Popen(cmd, cwd=str(REPO_ROOT))

    def _open_output_folder(self):
        name = self._building_name.get().strip()
        folder = OUT_ROOT / name if name else OUT_ROOT
        folder.mkdir(parents=True, exist_ok=True)
        import os
        os.startfile(str(folder))
        self._status_var.set(f'Opened: {folder}')

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    Launcher().run()
