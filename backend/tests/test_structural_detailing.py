"""Typed structural detailing model (Phase 7 / Task 31 — model commit).

structapi's wire payloads carry steel as strings ("6-16", "4-16φ",
"10 φ @ 150 c/c") and loosely-keyed nested dicts. The drawing set's four
member items now ALSO carry typed entities — BarGroup, Stirrup, Lap, Cover —
parsed once at the assembly boundary (build_structural_model). The raw
`bars` string and `design` dict stay alongside during the migration, so
renderers that have not yet been converted read exactly what they read
before.
"""

from app.engine.structural_data import (
    BarGroup,
    Cover,
    Lap,
    Stirrup,
    _build_beam_runs,
    _build_columns,
    _build_footings,
    _build_slab_panels,
    GridRef,
)

from tests.helpers.golden import golden_layout


# ── BarGroup parsing / round-trip ─────────────────────────────────────────


def test_bargroup_parses_canonical_wire_format():
    assert BarGroup.parse("6-16") == BarGroup(quantity=6, diameter_mm=16.0)


def test_bargroup_parses_phi_suffixed_variant():
    assert BarGroup.parse("4-16φ") == BarGroup(quantity=4, diameter_mm=16.0)


def test_bargroup_parses_is_callout_variant():
    # "3T20" (TOR steel callout) is how engineers *write* it; the wire
    # canonicalises to "3-20"
    assert BarGroup.parse("3T20") == BarGroup(quantity=3, diameter_mm=20.0)
    assert BarGroup.parse("3T20").callout == "3-20"


def test_bargroup_parses_x_separator_and_whitespace():
    assert BarGroup.parse("6x20") == BarGroup(quantity=6, diameter_mm=20.0)
    assert BarGroup.parse(" 8 - 25 ") == BarGroup(quantity=8, diameter_mm=25.0)


def test_bargroup_rejects_unparseable_and_placeholder_strings():
    assert BarGroup.parse("") is None
    assert BarGroup.parse("—") is None  # the assembly's missing-data sentinel
    assert BarGroup.parse("many bars") is None


def test_bargroup_callout_round_trips_canonical_format():
    for s in ("4-16", "6-20", "8-25"):
        g = BarGroup.parse(s)
        assert g is not None and g.callout == s


# ── Stirrup parsing / round-trip ─────────────────────────────────────────


def test_stirrup_parses_structapi_bar_string():
    s = Stirrup.parse("10 φ @ 150 c/c")
    assert s == Stirrup(diameter_mm=10.0, spacing_mm=150.0)


def test_stirrup_parses_compact_and_slash_variants():
    assert Stirrup.parse("8@125") == Stirrup(diameter_mm=8.0, spacing_mm=125.0)
    assert Stirrup.parse("12ø @ 200 c/c") == Stirrup(diameter_mm=12.0, spacing_mm=200.0)


def test_stirrup_rejects_unparseable_strings():
    assert Stirrup.parse("") is None
    assert Stirrup.parse("no steel") is None


def test_stirrup_callout_matches_the_sheet_render_format():
    # structural_sheets_foundation renders ties as f"{dia:.0f}@{spacing:.0f}"
    assert Stirrup(diameter_mm=8.0, spacing_mm=150.0).callout == "8@150"


def test_lap_is_is456_tension_lap_from_main_bars():
    lap = Lap.tension(BarGroup(quantity=6, diameter_mm=16.0))
    assert lap.length_mm == 800.0  # 50 × 16 (IS 456 Cl 26.2.5.1)
    assert lap.staggered is True


# ── assembly-time typed population ────────────────────────────────────────


def _grid() -> GridRef:
    return GridRef(x_lines_m=[1.0, 4.0, 7.0], y_lines_m=[1.5, 7.0, 13.0])


def test_columns_carry_typed_bars_ties_and_lap():
    columns_data = {
        "corner": {
            "b_mm": 300,
            "D_mm": 300,
            "bars": "6-16",
            "ties": {"dia": 8, "spacing": 150},
            "cover_mm": 40,
        },
        "edge": {"b_mm": 300, "D_mm": 350, "bars": "8-16"},  # no ties key
        "interior": {"b_mm": 350, "D_mm": 350, "bars": "8-20"},
    }
    layout = golden_layout()
    cols = _build_columns(_grid(), layout, columns_data)
    assert cols, "golden layout has gf columns"
    by_class = {c.col_class: c for c in cols}

    corner = by_class["corner"]
    assert corner.main_bars == BarGroup(quantity=6, diameter_mm=16.0)
    assert corner.ties == Stirrup(diameter_mm=8.0, spacing_mm=150.0)
    assert corner.cover == Cover(mm=40.0)
    assert corner.lap == Lap(length_mm=800.0, staggered=True)
    # migration: the raw payload stays readable
    assert corner.bars == "6-16"
    assert corner.design == columns_data["corner"]

    edge = by_class["edge"]
    assert edge.main_bars == BarGroup(quantity=8, diameter_mm=16.0)
    assert edge.ties is None  # absent in payload → renderer keeps its fallback
    assert edge.cover is None
    assert edge.lap and edge.lap.length_mm == 800.0


def test_column_with_missing_bars_stays_untyped_not_broken():
    cols = _build_columns(_grid(), golden_layout(), {"corner": {"b_mm": 300}})
    corner = next(c for c in cols if c.col_class == "corner")
    assert corner.bars == "—"
    assert corner.main_bars is None
    assert corner.lap is None


def test_footings_carry_typed_mesh_both_directions():
    columns_data = {"corner": {"b_mm": 300, "D_mm": 300, "bars": "6-16"}}
    cols = _build_columns(_grid(), golden_layout(), columns_data)
    footings_data = {
        "corner": {
            "data": {
                "L_m": 1.6,
                "B_m": 1.6,
                "D_overall_mm": 450,
                "bars_x": {"dia": 12, "spacing": 150},
                "bars_y": {"dia": 12, "spacing": 150},
            }
        }
    }
    fts = _build_footings(cols, footings_data)
    assert fts
    f = fts[0]
    assert f.mesh_x == Stirrup(diameter_mm=12.0, spacing_mm=150.0)
    assert f.mesh_y == Stirrup(diameter_mm=12.0, spacing_mm=150.0)
    assert f.design == footings_data["corner"]["data"]  # raw payload intact


def test_beam_runs_carry_typed_steel_when_payload_supplies_it():
    beams_data = {
        "x-span4.00-trib2.25": {
            "axis": "x",
            "b_mm": 230,
            "D_mm": 450,
            "span_m": 4.0,
            "grid_line_indices": [0, 1],
            "design": {
                "n_bars": 3,
                "bar_dia": 16,
                "doubly_reinforced": True,
                "n_bars_comp": 2,
                "bar_dia_comp": 12,
                "stirrups": {"sv_provided": 150, "dia": 8, "legs": 2},
                "cover_mm": 25,
            },
        }
    }
    runs = _build_beam_runs(_grid(), beams_data)
    assert len(runs) == 2  # one per grid line index
    run = runs[0]
    assert run.bottom_bars == BarGroup(quantity=3, diameter_mm=16.0)
    assert run.top_bars == BarGroup(quantity=2, diameter_mm=12.0)
    assert run.stirrups == Stirrup(diameter_mm=8.0, spacing_mm=150.0, legs=2)
    assert run.cover == Cover(mm=25.0)
    assert run.design["design"]["n_bars"] == 3  # raw payload intact


def test_beam_run_without_design_payload_stays_untyped():
    runs = _build_beam_runs(
        _grid(), {"x-span3.0-trib2.0": {"axis": "x", "span_m": 3.0}}
    )
    assert runs[0].bottom_bars is None
    assert runs[0].stirrups is None


def test_slab_panels_parse_one_way_string_steel():
    slabs_data = {
        "ow-1": {
            "type": "one-way",
            "lx_m": 3.0,
            "ly_m": 4.0,
            "D_mm": 125,
            "case_": "1",
            "panel_indices": [[0, 0]],
            "main": {"bar": "10 φ @ 150 c/c"},
            "distribution": {"bar": "8 φ @ 200 c/c"},
        }
    }
    panels = _build_slab_panels(_grid(), slabs_data)
    (p,) = panels
    assert p.main_steel == Stirrup(diameter_mm=10.0, spacing_mm=150.0)
    assert p.dist_steel == Stirrup(diameter_mm=8.0, spacing_mm=200.0)
    assert p.top_steel is None


def test_slab_panels_parse_two_way_strip_steel():
    slabs_data = {
        "tw-1": {
            "type": "two-way",
            "lx_m": 3.0,
            "ly_m": 3.0,
            "D_mm": 125,
            "panel_indices": [[0, 0]],
            "strips": {
                "short_span_bottom": {"bar": "10 φ @ 140 c/c"},
                "long_span_bottom": {"bar": "10 φ @ 180 c/c"},
            },
        }
    }
    (p,) = _build_slab_panels(_grid(), slabs_data)
    assert p.main_steel == Stirrup(diameter_mm=10.0, spacing_mm=140.0)
    assert p.dist_steel == Stirrup(diameter_mm=10.0, spacing_mm=180.0)


def test_slab_panels_parse_flat_keyed_steel():
    # the third encoding: {"main_bar_dia_mm": 8, "main_bar_spacing_mm": 150}
    slabs_data = {
        "ow-9": {
            "type": "one-way",
            "lx_m": 3.0,
            "ly_m": 3.0,
            "D_mm": 100,
            "panel_indices": [[0, 0]],
            "main_bar_dia_mm": 8,
            "main_bar_spacing_mm": 150,
            "dist_bar_dia_mm": 8,
            "dist_bar_spacing_mm": 250,
            "top_bar_dia_mm": 8,
            "top_bar_spacing_mm": 150,
        }
    }
    (p,) = _build_slab_panels(_grid(), slabs_data)
    assert p.main_steel == Stirrup(diameter_mm=8.0, spacing_mm=150.0)
    assert p.dist_steel == Stirrup(diameter_mm=8.0, spacing_mm=250.0)
    assert p.top_steel == Stirrup(diameter_mm=8.0, spacing_mm=150.0)


def test_slab_panel_without_steel_keys_stays_untyped():
    # mirrors test_sheet_slab_stair's "ow-2-nominal" fixture: the renderer's
    # nominal fallback must keep firing after the typed migration
    (p,) = _build_slab_panels(
        _grid(),
        {
            "ow-2": {
                "type": "one-way",
                "lx_m": 3.0,
                "ly_m": 4.0,
                "D_mm": 125,
                "panel_indices": [[0, 0]],
            }
        },
    )
    assert p.main_steel is None
    assert p.dist_steel is None
    assert p.top_steel is None
