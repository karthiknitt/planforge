import pytest
from app.engine.models import Room


def test_room_defaults_to_fully_enclosed():
    r = Room(id="r1", name="Living", type="living", x=0, y=0, width=4, depth=3)
    assert r.open_sides == frozenset()
    assert r.is_open is False


def test_room_accepts_open_sides():
    r = Room(
        id="p1",
        name="Car Porch",
        type="parking_4w",
        x=0,
        y=0,
        width=3,
        depth=5,
        open_sides=frozenset({"S", "E"}),
    )
    assert r.open_sides == frozenset({"S", "E"})
    assert r.is_open is True


def test_room_rejects_unknown_side():
    with pytest.raises(ValueError, match="open_sides"):
        Room(
            id="p2",
            name="Bad",
            type="parking_4w",
            x=0,
            y=0,
            width=3,
            depth=5,
            open_sides=frozenset({"UP"}),
        )


def test_room_rejects_all_four_sides_open():
    with pytest.raises(ValueError, match="all four"):
        Room(
            id="p3",
            name="Floating",
            type="parking_4w",
            x=0,
            y=0,
            width=3,
            depth=5,
            open_sides=frozenset({"N", "S", "E", "W"}),
        )
