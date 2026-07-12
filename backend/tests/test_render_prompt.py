from app.engine.render_prompt import build_render_prompt

GEOMETRY = {
    "id": "A",
    "name": "Layout A",
    "ground_floor": {
        "floor": 0,
        "rooms": [
            {
                "id": "gf-liv",
                "name": "Living Room",
                "type": "living",
                "x": 1.0,
                "y": 1.0,
                "width": 4.5,
                "depth": 3.6,
                "area": 16.2,
            },
            {
                "id": "gf-kit",
                "name": "Kitchen",
                "type": "kitchen",
                "x": 5.5,
                "y": 1.0,
                "width": 2.8,
                "depth": 3.0,
                "area": 8.4,
            },
        ],
        "columns": [],
    },
    "first_floor": {
        "floor": 1,
        "rooms": [
            {
                "id": "ff-bed1",
                "name": "Master Bedroom",
                "type": "bedroom",
                "x": 1.0,
                "y": 1.0,
                "width": 4.0,
                "depth": 3.5,
                "area": 14.0,
            },
        ],
        "columns": [],
    },
}


def test_prompt_names_every_room_with_dimensions():
    prompt = build_render_prompt(GEOMETRY, plot_length_m=15.0, plot_width_m=9.0)
    assert "Living Room" in prompt
    assert "4.5" in prompt and "3.6" in prompt
    assert "Kitchen" in prompt


def test_prompt_selects_floor():
    prompt = build_render_prompt(
        GEOMETRY, plot_length_m=15.0, plot_width_m=9.0, floor="first_floor"
    )
    assert "Master Bedroom" in prompt
    assert "Kitchen" not in prompt


def test_prompt_includes_plot_and_north():
    prompt = build_render_prompt(
        GEOMETRY, plot_length_m=15.0, plot_width_m=9.0, north_direction="NE"
    )
    assert "15.0" in prompt and "9.0" in prompt
    assert "NE" in prompt


def test_prompt_instructs_fidelity_to_reference():
    prompt = build_render_prompt(GEOMETRY, plot_length_m=15.0, plot_width_m=9.0)
    assert "reference" in prompt.lower()
    assert "exact" in prompt.lower() or "match" in prompt.lower()


def test_prompt_uses_r3f_instruction_when_reference_kind_is_r3f():
    prompt = build_render_prompt(
        GEOMETRY, plot_length_m=15.0, plot_width_m=9.0, reference_kind="r3f"
    )
    assert "3D geometric model" in prompt
    assert "exact CAD floor plan" not in prompt


def test_prompt_defaults_to_cad_instruction():
    prompt = build_render_prompt(GEOMETRY, plot_length_m=15.0, plot_width_m=9.0)
    assert "exact CAD floor plan" in prompt


def test_unknown_floor_raises():
    import pytest

    with pytest.raises(KeyError):
        build_render_prompt(
            GEOMETRY, plot_length_m=15.0, plot_width_m=9.0, floor="attic"
        )


def test_prompt_negative_constraints_no_parking():
    prompt = build_render_prompt(GEOMETRY, plot_length_m=15.0, plot_width_m=9.0)
    assert "NO parking" in prompt
    assert "do not draw a car" in prompt


def test_prompt_pins_staircase_position():
    geometry = {
        "ground_floor": {
            "floor": 0,
            "rooms": [
                {
                    "id": "gf-stair",
                    "name": "Staircase",
                    "type": "staircase",
                    "x": 1.2,
                    "y": 1.7,
                    "width": 0.9,
                    "depth": 3.0,
                    "area": 2.7,
                },
            ],
            "columns": [],
        },
    }
    prompt = build_render_prompt(geometry, plot_length_m=15.0, plot_width_m=9.0)
    assert "staircase occupies ONLY its marked position" in prompt
    assert "1.2m from the left" in prompt


def test_prompt_forbids_unlisted_rooms():
    prompt = build_render_prompt(GEOMETRY, plot_length_m=15.0, plot_width_m=9.0)
    assert "NOTHING that is not listed" in prompt
