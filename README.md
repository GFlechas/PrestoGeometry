# PrestoGeometry

> HackSimBuild 2026 — IBPSA SimBuild Hackathon

PrestoGeometry converts photos taken while walking around a building into representative geometry for building energy models.

## What it does

1. **Ingest** — upload a set of photos taken around a building exterior
2. **Reconstruct** — extract facade geometry, window/door openings, and floor counts using computer vision and photogrammetry
3. **Export** — write the resulting geometry to:
   - `.idf` (EnergyPlus)
   - `.osm` (OpenStudio)
   - `.hpxml` (Home Performance XML — residential)

The outputs are intended as a starting point for further model development, not a simulation-ready file.

## Project layout

```
presto_geometry/        # core Python package
  ingestion/            # image loading, EXIF/GPS extraction (planned)
  reconstruction/       # geometry inference from images (planned)
  exporters/            # IDF, OSM, and HPXML writers (planned)
  models/               # internal geometry data model
  schemas/              # vendored JSON schemas (floorspace.js)
  web/                  # Flask web server for the editor GUI
frontend/               # React + TypeScript editor (Vite)
tests/                  # pytest test suite
data/
  samples/              # sample input images for testing
  outputs/              # gitignored export artifacts
  floorplans/           # gitignored saved floorplan JSON (current.json)
docs/                   # additional documentation
```

## Quickstart — CLI

```bash
# create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# install dependencies
pip install -r requirements.txt

# run on a folder of building photos (pipeline not yet implemented)
python -m presto_geometry --input data/samples/my_building --output data/outputs/
```

## Quickstart — Editor GUI

The editor is a React + TypeScript SPA served by a small Flask app. The Flask
app also exposes a tiny JSON API (`/api/schema`, `/api/floorplan`) that the
frontend uses for validation, save, and load.

### Development mode (hot-reload)

Run two processes in parallel:

```bash
# Terminal 1 — Flask backend on :5000
python -m presto_geometry.web

# Terminal 2 — Vite dev server on :5173 with /api proxied to :5000
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

### Single-server build

```bash
cd frontend
npm install
npm run build       # outputs to ../presto_geometry/web/static
cd ..
python -m presto_geometry.web
```

Open <http://localhost:5000>.

### Editor controls

- **V** / **R** / **W** / **D** / **X** — Select / Draw Room / Place Window / Place Door / Erase
- **Wheel** — zoom around cursor; **Shift + drag** or middle-mouse drag — pan
- While drawing a room: click to add vertices, click the first vertex (or press
  **Enter**) to close, **Esc** to cancel
- Toggle between **2D Editor** and **3D Preview** with the tabs in the topbar

The editor uses the [floorspace.js geometry schema](presto_geometry/schemas/floorspace_geometry_schema.json)
as its data contract. Files exported from the editor are interchangeable with
the upstream FloorspaceJS app.

## Tests

```bash
# Python tests
pytest

# Frontend unit tests (geometry, snapping, wall shape)
cd frontend && npm run test
```

## License

MIT — see [LICENSE](LICENSE).
