"""Tests for the Flask pose-extraction endpoint with a stubbed pipeline."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

from presto_geometry.exporters.floorspace import building_to_floorspace_dict
from presto_geometry.reconstruction.floorspace_builder import build_building
from presto_geometry.reconstruction.footprint import FootprintResult
from presto_geometry.web import create_app


def _png_bytes() -> bytes:
    """Minimal valid 1x1 PNG."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c63600100000005000100200d0a2db40000000049454e44ae426082"
    )


def _stub_pipeline(_image_dir, _scale_ref, *, snap_orthogonal=True):  # noqa: ARG001
    footprint = FootprintResult(
        polygon_xy=[(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0)],
        floor_to_ceiling_height=3.0,
        n_stories=2,
        total_height=6.0,
        scale=1.0,
        transform_world_to_floorspace=np.eye(4),
    )
    return building_to_floorspace_dict(build_building(footprint))


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(data_dir=tmp_path)
    app.config.update(TESTING=True, POSE_EXTRACTION_RUNNER=_stub_pipeline)
    with app.test_client() as c:
        yield c


def _post_images(client, n: int, **form):
    data = {**form}
    for i in range(n):
        data.setdefault("images", []).append((io.BytesIO(_png_bytes()), f"img_{i}.png"))
    return client.post(
        "/api/pose-extraction",
        data=data,
        content_type="multipart/form-data",
    )


def test_status_endpoint(client):
    res = client.get("/api/pose-extraction/status")
    assert res.status_code == 200
    body = res.get_json()
    for key in ("cuda_available", "torch_available", "model_loaded"):
        assert key in body
    assert body["model_loaded"] is False


def test_pose_extraction_happy_path(client):
    res = _post_images(client, 5, scale_kind="total_height", scale_value="6",
                       floor_to_ceiling_height="3")
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["version"] == "0.7.0"
    assert len(body["stories"]) == 2
    assert len(body["stories"][0]["geometry"]["vertices"]) == 4


def test_pose_extraction_rejects_too_few_images(client):
    res = _post_images(client, 2, scale_kind="total_height", scale_value="6")
    assert res.status_code == 400
    assert res.get_json()["ok"] is False


def test_pose_extraction_rejects_bad_scale_kind(client):
    res = _post_images(client, 4, scale_kind="weird", scale_value="6")
    assert res.status_code == 400


def test_pose_extraction_rejects_non_image_extension(client):
    data = {"scale_kind": "total_height", "scale_value": "6"}
    files = [(io.BytesIO(b"not a png"), f"a{i}.gif") for i in range(4)]
    data["images"] = files
    res = client.post("/api/pose-extraction", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
