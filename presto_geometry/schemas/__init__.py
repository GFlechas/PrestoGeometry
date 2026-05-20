"""Vendored JSON schemas used by PrestoGeometry.

Schemas are copied from upstream sources and pinned to a specific commit.
See the ``_source`` and ``_source_commit`` fields inside each file for provenance.
"""

import json
from importlib import resources
from pathlib import Path


def _load(filename: str) -> dict:
    pkg = resources.files(__name__)
    return json.loads((pkg / filename).read_text(encoding="utf-8"))


def load_geometry_schema() -> dict:
    """Return the vendored floorspace.js geometry schema (JSON Schema Draft-04)."""
    return _load("floorspace_geometry_schema.json")


def load_default_library() -> dict:
    """Return the vendored floorspace.js default construction/space-type library."""
    return _load("floorspace_default_library.json")
