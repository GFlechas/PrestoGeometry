"""Smoke tests for the internal geometry model."""

from presto_geometry.models.building import Building, Zone, Surface, Opening


def test_building_defaults():
    b = Building()
    assert b.name == "PrestoBuilding"
    assert b.num_floors == 1
    assert b.zones == []


def test_zone_surface_openings():
    win = Opening(opening_type="window", width=1.2, height=1.0)
    wall = Surface(surface_type="wall", openings=[win])
    zone = Zone(name="Zone_1", surfaces=[wall])
    b = Building(name="TestBuilding", zones=[zone])

    assert len(b.zones) == 1
    assert len(b.zones[0].surfaces[0].openings) == 1
    assert b.zones[0].surfaces[0].openings[0].width == 1.2
