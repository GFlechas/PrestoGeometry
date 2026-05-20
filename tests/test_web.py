"""Smoke tests for the Flask web app."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from presto_geometry.web import create_app, empty_floorplan


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(data_dir=tmp_path)
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert "version" in body


def test_schema(client):
    res = client.get("/api/schema")
    assert res.status_code == 200
    schema = res.get_json()
    assert schema["type"] == "object"
    assert "stories" in schema["properties"]


def test_get_floorplan_when_empty_returns_template(client):
    res = client.get("/api/floorplan")
    assert res.status_code == 200
    body = res.get_json()
    for key in (
        "version",
        "project",
        "stories",
        "window_definitions",
        "door_definitions",
    ):
        assert key in body


def test_post_then_get_roundtrip(client, tmp_path: Path):
    doc = empty_floorplan()
    doc["project"]["north_axis"] = 12.5
    res = client.post(
        "/api/floorplan",
        data=json.dumps(doc),
        content_type="application/json",
    )
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["ok"] is True

    saved = tmp_path / "current.json"
    assert saved.exists()
    with saved.open() as f:
        on_disk = json.load(f)
    assert on_disk["project"]["north_axis"] == 12.5

    res = client.get("/api/floorplan")
    assert res.status_code == 200
    assert res.get_json()["project"]["north_axis"] == 12.5


def test_post_invalid_payload_returns_400(client):
    bad = {"version": "0.7.0"}  # missing all the required keys
    res = client.post(
        "/api/floorplan",
        data=json.dumps(bad),
        content_type="application/json",
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["ok"] is False
    assert isinstance(body["errors"], list)
    assert len(body["errors"]) > 0


def test_post_non_json_returns_400(client):
    res = client.post("/api/floorplan", data="not json", content_type="text/plain")
    assert res.status_code == 400
