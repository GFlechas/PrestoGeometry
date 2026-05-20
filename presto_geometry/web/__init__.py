"""Flask web app for the PrestoGeometry floorplan editor."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from presto_geometry.schemas import load_geometry_schema


def create_app(data_dir: str | os.PathLike | None = None) -> Flask:
    """Application factory.

    Parameters
    ----------
    data_dir:
        Directory where floorplan JSON files are read from / written to.
        Defaults to ``<repo_root>/data/floorplans``.
    """
    static_dir = Path(__file__).parent / "static"

    app = Flask(
        __name__,
        static_folder=str(static_dir),
        static_url_path="/static",
    )

    repo_root = Path(__file__).resolve().parents[2]
    if data_dir is None:
        data_dir = repo_root / "data" / "floorplans"
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    upload_dir = repo_root / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    app.config["DATA_DIR"] = data_path
    app.config["UPLOAD_DIR"] = upload_dir
    app.config["GEOMETRY_SCHEMA"] = load_geometry_schema()
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB upload cap

    from . import api
    api.register(app)

    return app


def empty_floorplan() -> dict:
    """Return a minimal floorplan dict that satisfies the geometry schema."""
    return {
        "version": "0.7.0",
        "application": {},
        "project": {
            "config": {"units": "si", "language": "EN-US"},
            "north_axis": 0,
            "ground": {"floor_offset": 0, "azimuth_angle": 0, "tilt_slope": 0},
            "grid": {"visible": True, "spacing": 0.5},
            "view": {"min_x": -50, "min_y": -50, "max_x": 50, "max_y": 50},
            "map": {
                "visible": False,
                "latitude": 39.7653,
                "longitude": -104.9863,
                "zoom": 4.5,
                "elevation": 0,
                "enabled": False,
                "initialized": False,
                "rotation": 0,
            },
            "previous_story": {"visible": True},
            "show_import_export": True,
        },
        "stories": [],
        "building_units": [],
        "thermal_zones": [],
        "space_types": [],
        "construction_sets": [],
        "window_definitions": [],
        "door_definitions": [],
        "daylighting_control_definitions": [],
        "pitched_roofs": [],
    }
