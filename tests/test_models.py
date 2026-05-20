"""Smoke tests for the internal geometry model."""

from presto_geometry.models.building import (
    Building,
    Story,
    Space,
    Geometry,
    Vertex,
    Edge,
    Face,
    ThermalZone,
    WindowDefinition,
    WindowPlacement,
    DoorDefinition,
)


def test_building_defaults():
    b = Building()
    assert b.name == "PrestoBuilding"
    assert b.num_floors == 0
    assert b.stories == []
    assert b.thermal_zones == []
    assert b.window_definitions == []


def test_story_space_structure():
    """A Story holds Spaces that reference Faces in a Geometry."""
    tz = ThermalZone(id="tz-1", name="Main Zone")

    vertex_a = Vertex(id="v-1", x=0.0, y=0.0)
    vertex_b = Vertex(id="v-2", x=10.0, y=0.0)
    vertex_c = Vertex(id="v-3", x=10.0, y=8.0)
    vertex_d = Vertex(id="v-4", x=0.0, y=8.0)

    edges = [
        Edge(id="e-1", vertex_ids=("v-1", "v-2"), face_ids=["f-1"]),
        Edge(id="e-2", vertex_ids=("v-2", "v-3"), face_ids=["f-1"]),
        Edge(id="e-3", vertex_ids=("v-3", "v-4"), face_ids=["f-1"]),
        Edge(id="e-4", vertex_ids=("v-4", "v-1"), face_ids=["f-1"]),
    ]
    face = Face(id="f-1", edge_ids=["e-1", "e-2", "e-3", "e-4"], edge_order=[0, 0, 0, 0])
    geom = Geometry(id="g-1", vertices=[vertex_a, vertex_b, vertex_c, vertex_d],
                    edges=edges, faces=[face])

    space = Space(id="sp-1", name="Living Room", face_id="f-1", thermal_zone_id="tz-1")
    story = Story(id="st-1", name="Ground Floor", floor_to_ceiling_height=3.0,
                  geometry=geom, spaces=[space])

    win_def = WindowDefinition(id="wd-1", name="Standard Window", width=1.2, height=1.0,
                               sill_height=0.9)
    win_placement = WindowPlacement(window_definition_id="wd-1", edge_id="e-2", alpha=0.5)
    story.windows.append(win_placement)

    b = Building(
        name="TestBuilding",
        stories=[story],
        thermal_zones=[tz],
        window_definitions=[win_def],
    )

    assert b.num_floors == 1
    assert len(b.stories) == 1
    assert b.stories[0].geometry.faces[0].id == "f-1"
    assert b.stories[0].spaces[0].thermal_zone_id == "tz-1"
    assert b.stories[0].windows[0].window_definition_id == "wd-1"
    assert b.window_definitions[0].width == 1.2
