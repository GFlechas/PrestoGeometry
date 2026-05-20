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
  ingestion/            # image loading, EXIF/GPS extraction
  reconstruction/       # geometry inference from images
  exporters/            # IDF, OSM, and HPXML writers
  models/               # internal geometry data model
tests/                  # pytest test suite
data/
  samples/              # sample input images for testing
  outputs/              # gitignored export artifacts
docs/                   # additional documentation
```

## Quickstart

```bash
# create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# install dependencies
pip install -r requirements.txt

# run on a folder of building photos
python -m presto_geometry --input data/samples/my_building --output data/outputs/
```

## License

MIT — see [LICENSE](LICENSE).
