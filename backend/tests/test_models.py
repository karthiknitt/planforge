import pytest
from app.engine.models import PlotConfig, Room


def _plot_config(**kw):
    base = dict(
        plot_y_extent=10.0,
        plot_x_extent=10.0,
        setback_front=1.0,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=1,
        toilets=1,
        parking=False,
    )
    base.update(kw)
    return PlotConfig(**base)


def test_plot_config_style_preset_defaults_to_none():
    cfg = _plot_config()
    assert cfg.style_preset is None


def test_plot_config_accepts_style_preset():
    cfg = _plot_config(style_preset="Kerala")
    assert cfg.style_preset == "Kerala"


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
