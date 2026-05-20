"""REST endpoints for the floorplan editor."""

from __future__ import annotations

import json
import tempfile
import traceback
from pathlib import Path

import jsonschema
from flask import Flask, Response, current_app, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from presto_geometry import __version__

_ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png"}
_MIN_IMAGES = 4
_MAX_IMAGES = 10


def _get_or_create_extractor():
    """Lazily instantiate a singleton :class:`Dust3rPoseExtractor` on the app."""
    from presto_geometry.reconstruction import Dust3rPoseExtractor

    ext = current_app.extensions.get("pose_extractor")
    if ext is None:
        ext = Dust3rPoseExtractor.load_model()
        current_app.extensions["pose_extractor"] = ext
    return ext


def _cuda_status() -> dict:
    try:
        import torch
        return {
            "cuda_available": bool(torch.cuda.is_available()),
            "torch_available": True,
        }
    except ImportError:
        return {"cuda_available": False, "torch_available": False}


def register(app: Flask) -> None:
    """Wire all routes onto the given app."""

    @app.get("/")
    def index() -> Response:
        static_dir = Path(app.static_folder or "")
        index_html = static_dir / "index.html"
        if not index_html.exists():
            return Response(
                "Frontend bundle not built. Run `npm run build` in frontend/, "
                "or use Vite dev server at http://localhost:5173 during development.",
                status=503,
                mimetype="text/plain",
            )
        return send_from_directory(static_dir, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", version=__version__)

    @app.get("/api/schema")
    def schema():
        return jsonify(current_app.config["GEOMETRY_SCHEMA"])

    @app.get("/api/floorplan")
    def get_floorplan():
        from . import empty_floorplan

        data_dir: Path = current_app.config["DATA_DIR"]
        current = data_dir / "current.json"
        if not current.exists():
            return jsonify(empty_floorplan())
        with current.open("r", encoding="utf-8") as f:
            return jsonify(json.load(f))

    @app.post("/api/floorplan")
    def save_floorplan():
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify(ok=False, errors=["request body must be JSON"]), 400

        schema_doc = current_app.config["GEOMETRY_SCHEMA"]
        validator = jsonschema.Draft4Validator(schema_doc)
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        if errors:
            return (
                jsonify(
                    ok=False,
                    errors=[
                        {"path": list(e.path), "message": e.message} for e in errors
                    ],
                ),
                400,
            )

        data_dir: Path = current_app.config["DATA_DIR"]
        target = data_dir / "current.json"
        with target.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return jsonify(ok=True, path=str(target))

    @app.get("/api/pose-extraction/status")
    def pose_extraction_status():
        ext = current_app.extensions.get("pose_extractor")
        status = _cuda_status()
        status["model_loaded"] = ext is not None
        status["device"] = ext.device if ext is not None else None
        return jsonify(status)

    @app.post("/api/pose-extraction")
    def pose_extraction():
        files = request.files.getlist("images")
        if not (_MIN_IMAGES <= len(files) <= _MAX_IMAGES):
            return (
                jsonify(
                    ok=False,
                    error=(
                        f"Expected between {_MIN_IMAGES} and {_MAX_IMAGES} images "
                        f"under field 'images', got {len(files)}."
                    ),
                ),
                400,
            )

        try:
            scale_kind = request.form.get("scale_kind", "total_height")
            scale_value = float(request.form.get("scale_value", "9.0"))
            fch_raw = request.form.get("floor_to_ceiling_height", "3.0")
            floor_to_ceiling_height = float(fch_raw) if fch_raw else None
            snap_orthogonal = request.form.get("snap_orthogonal", "true").lower() == "true"
        except (TypeError, ValueError) as exc:
            return jsonify(ok=False, error=f"Invalid scale parameters: {exc}"), 400

        if scale_kind not in ("total_height", "wall_length"):
            return jsonify(
                ok=False,
                error=f"scale_kind must be 'total_height' or 'wall_length', got {scale_kind!r}",
            ), 400

        upload_root: Path = current_app.config["UPLOAD_DIR"]
        upload_root.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=str(upload_root)) as tmp:
            tmp_path = Path(tmp)
            for f in files:
                raw_name = secure_filename(f.filename or "")
                if not raw_name:
                    return jsonify(ok=False, error="Each upload must have a filename."), 400
                ext = Path(raw_name).suffix.lower()
                if ext not in _ALLOWED_IMAGE_EXT:
                    return jsonify(
                        ok=False,
                        error=f"Unsupported image extension {ext!r}; allowed: {sorted(_ALLOWED_IMAGE_EXT)}",
                    ), 400
                f.save(tmp_path / raw_name)

            try:
                from presto_geometry.reconstruction import (
                    ScaleRef,
                    photos_to_floorspace,
                )

                runner = current_app.config.get("POSE_EXTRACTION_RUNNER")
                scale_ref = ScaleRef(
                    kind=scale_kind,
                    value=scale_value,
                    floor_to_ceiling_height=floor_to_ceiling_height,
                )
                if runner is not None:
                    floorplan = runner(tmp_path, scale_ref, snap_orthogonal=snap_orthogonal)
                else:
                    extractor = _get_or_create_extractor()
                    floorplan = photos_to_floorspace(
                        tmp_path,
                        scale_ref=scale_ref,
                        snap_orthogonal=snap_orthogonal,
                        extractor=extractor,
                    )
            except ValueError as exc:
                return jsonify(ok=False, error=str(exc)), 400
            except ImportError as exc:
                return jsonify(ok=False, error=str(exc)), 503
            except Exception as exc:  # noqa: BLE001 - surface unexpected errors
                current_app.logger.exception("pose extraction failed")
                return (
                    jsonify(
                        ok=False,
                        error=f"{type(exc).__name__}: {exc}",
                        traceback=traceback.format_exc(limit=3),
                    ),
                    500,
                )

        return jsonify(floorplan)
