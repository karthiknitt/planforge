from app.engine.standards import OpeningStandards, get_opening_standards


def test_defaults_come_from_compliance_rules_json():
    std = get_opening_standards()
    assert std.door_width_m == 0.9
    assert std.window_width_m == 1.2
    assert std.window_max_room_fraction == 0.6
    assert std.ventilator_width_m == 0.6


def test_missing_config_section_falls_back_to_defaults(monkeypatch, tmp_path):
    import app.engine.standards as standards

    empty = tmp_path / "rules.json"
    empty.write_text("{}")
    monkeypatch.setattr(standards, "_RULES_PATH", empty)
    standards.get_opening_standards.cache_clear()
    try:
        assert standards.get_opening_standards() == OpeningStandards()
    finally:
        standards.get_opening_standards.cache_clear()


def test_openings_use_configured_door_width():
    from app.engine.cad_primitives import _DOOR_WIDTH

    assert _DOOR_WIDTH == get_opening_standards().door_width_m
