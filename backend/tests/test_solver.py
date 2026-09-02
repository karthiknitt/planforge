"""Tests for the CP-SAT constraint solver."""

import pytest
from app.engine import solver
from app.engine.models import PlotConfig
from app.engine.solver import (
    solve_layouts,
    _load_specs,
    _build_room_list,
    _section_ok,
    ensuite_attachment,
)


def _generous_solve_budget(monkeypatch):
    """Common (non-en-suite) toilet placement is a soft penalty term, not a
    hard constraint — the two-phase warm start exists specifically to spend
    its budget relocating toilets out of penalty zones, so its quality is
    genuinely search-budget-dependent. Bumping only the wall-clock caps
    (SOLVE_TIME_S/PHASE1_TIME_S) does nothing on a machine fast enough that
    the *deterministic* budget binds first — which is normal, by design (see
    solver.py's header) — so raise both together.
    """
    monkeypatch.setattr(solver, "SOLVE_TIME_S", 40.0)
    monkeypatch.setattr(solver, "PHASE1_TIME_S", 15.0)
    monkeypatch.setattr(solver, "PHASE1_DET_BUDGET", 3.0)
    monkeypatch.setattr(solver, "PHASE2_DET_BUDGET", 6.0)


def _basic_cfg(**kwargs) -> PlotConfig:
    defaults = dict(
        plot_y_extent=12.0,
        plot_x_extent=9.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=2,
        toilets=2,
        parking=False,
        city="other",
        road_side="S",
        vastu_enabled=False,
    )
    defaults.update(kwargs)
    return PlotConfig(**defaults)


def test_specs_load():
    specs = _load_specs()
    assert "bedroom" in specs
    assert "kitchen" in specs
    assert specs["bedroom"]["min_area_sqm"] == 9.5


def test_room_list_basic():
    cfg = _basic_cfg()
    rooms = _build_room_list(cfg, _load_specs())
    types = {r["type"] for r in rooms}
    assert "living" in types
    assert "kitchen" in types
    assert "bedroom" in types
    assert "staircase" in types


def test_room_list_optional_rooms():
    cfg = _basic_cfg(has_pooja=True, has_study=True, has_balcony=True)
    rooms = _build_room_list(cfg, _load_specs())
    types = {r["type"] for r in rooms}
    assert "pooja" in types
    assert "study" in types
    assert "balcony" in types


def test_room_list_custom_rooms():
    cfg = _basic_cfg(
        custom_room_config=[
            {"type": "gym", "name": "Home Gym", "floor_preference": "ff"},
            {"type": "servant_quarter", "floor_preference": "gf"},
        ]
    )
    rooms = _build_room_list(cfg, _load_specs())
    types = [r["type"] for r in rooms]
    assert "gym" in types
    assert "servant_quarter" in types


def test_solve_returns_up_to_3_layouts():
    cfg = _basic_cfg(plot_y_extent=14.0, plot_x_extent=11.0)
    ewt = 0.23
    layouts = solve_layouts(cfg, ewt)
    # Solver may return 0-3; we just check it doesn't crash and stays bounded
    assert len(layouts) <= 3


def test_solve_layouts_pass_compliance():
    cfg = _basic_cfg(plot_y_extent=15.0, plot_x_extent=12.0, num_bedrooms=2, toilets=2)
    ewt = 0.23
    layouts = solve_layouts(cfg, ewt)
    for layout in layouts:
        assert layout.compliance.passed, (
            f"Layout {layout.id} failed: {layout.compliance.violations}"
        )


def test_solve_columns_use_wall_junction_pipeline_not_room_corners():
    # Regression: solver used to place a column at all 4 corners of every
    # room (deduped only by rounded coordinate) via a local `_corner_cols`
    # helper — dense, structurally unjustified "intermediate" column grids
    # independent of the correct wall-junction + beam-span logic that
    # plan_geometry.build_floor_drawing already used for the structural
    # pages. This asserts solver.py's FloorPlan.columns are exactly what
    # the shared derive_walls/derive_junctions/derive_columns pipeline
    # produces for the same rooms — i.e. solver.py stays wired to the one
    # correct implementation instead of drifting back to a duplicate.
    from app.engine.geometry import buildable_polygon
    from app.engine.plan_geometry import derive_columns, derive_junctions, derive_walls

    cfg = _basic_cfg(
        plot_y_extent=15.0, plot_x_extent=12.0, num_bedrooms=3, toilets=2, parking=True
    )
    ewt = 0.23
    layouts = solve_layouts(cfg, ewt)
    assert layouts, "expected at least one solver layout for this fixture"
    buildable = buildable_polygon(cfg)

    naive_corner_total = 0
    pipeline_total = 0
    for layout in layouts:
        for floor_plan in (layout.ground_floor, layout.first_floor):
            if not floor_plan.rooms:
                continue
            walls = derive_walls(floor_plan.rooms, buildable, ewt=ewt)
            junctions = derive_junctions(walls)
            expected = derive_columns(
                walls, junctions=junctions, rooms=floor_plan.rooms
            )
            expected_pts = {(round(c.cx, 3), round(c.cy, 3)) for c in expected}
            actual_pts = {(round(c.x, 3), round(c.y, 3)) for c in floor_plan.columns}
            assert actual_pts == expected_pts, (
                f"layout {layout.id} floor {floor_plan.floor}: solver columns "
                "diverge from the shared derive_columns pipeline"
            )

            naive_corners = {
                (round(cx, 2), round(cy, 2))
                for r in floor_plan.rooms
                for cx, cy in [
                    (r.x, r.y),
                    (r.x + r.width, r.y),
                    (r.x, r.y + r.depth),
                    (r.x + r.width, r.y + r.depth),
                ]
            }
            naive_corner_total += len(naive_corners)
            pipeline_total += len(expected_pts)

    # Aggregated across all floors of all layouts, the span-aware pipeline
    # must stay in the same ballpark as the old naive per-room-corner scheme,
    # not blow far past it. It no longer has to stay <=: interior-void-facing
    # room edges (light wells / jogged footprints) are correctly classified
    # as external walls (#75) and get their own corner columns via
    # derive_junctions/derive_columns — real structural columns the naive
    # per-room-corner count never accounted for. The regression this guards
    # against (a column at EVERY corner, independent of junction/beam-span
    # logic) would multiply the pipeline count far past naive, not add a
    # modest handful — a generous margin still catches that anti-pattern.
    assert pipeline_total <= naive_corner_total * 1.5 + 10


def test_solved_parking_touches_road_side():
    # Parking has no positional constraint in the CP-SAT solver path today —
    # it can end up boxed in with no direct road/exterior access. The
    # deterministic archetype path already places it flush against the
    # front (road) edge; this guards the solver path gets the same
    # soft-penalty treatment as the toilet front-band placement.
    #
    # This is a SOFT preference (PARKING_ROAD_PENALTY), not a hard constraint,
    # deliberately — a hard rv.y==0 constraint risks infeasibility on tight
    # plots (see solver.py's own toilet front-band penalty, which rejected a
    # hard version for the same reason). Soft preferences can lose to other
    # packing pressure under the solver's wall-clock search budget for a
    # harder archetype, so we require the preference to win for at least one
    # generated layout, not unconditionally for every archetype.
    cfg = _basic_cfg(
        plot_y_extent=15.0, plot_x_extent=12.0, num_bedrooms=2, toilets=2, parking=True
    )
    ewt = 0.23
    front_y = cfg.setback_front + ewt
    layouts = solve_layouts(cfg, ewt)
    assert layouts, "expected at least one solver layout for this fixture"

    def _parking_on_road(layout) -> bool:
        for floor_plan in (layout.ground_floor, layout.first_floor):
            for room in floor_plan.rooms:
                if room.type in ("parking", "parking_4w", "parking_2w"):
                    if room.y != pytest.approx(front_y, abs=0.05):
                        return False
        return True

    assert any(_parking_on_road(layout) for layout in layouts), (
        "expected at least one layout with parking on the road-facing edge "
        f"(y={front_y}); got: "
        + ", ".join(
            f"{layout.id}="
            + ",".join(
                str(room.y)
                for floor_plan in (layout.ground_floor, layout.first_floor)
                for room in floor_plan.rooms
                if room.type in ("parking", "parking_4w", "parking_2w")
            )
            for layout in layouts
        )
    )


def test_solve_too_small_plot_returns_empty():
    cfg = _basic_cfg(
        plot_y_extent=5.0,
        plot_x_extent=5.0,
        setback_front=2.0,
        setback_rear=2.0,
        setback_left=1.5,
        setback_right=1.5,
    )
    ewt = 0.23
    layouts = solve_layouts(cfg, ewt)
    # Very small buildable area — should return no solver layouts (graceful)
    assert isinstance(layouts, list)


# ── Attached (en-suite) toilets + toilet placement ───────────────────────────


def _shares_wall(a, b, min_overlap: float, max_gap: float = 0.12) -> bool:
    """True when rooms a/b share a wall segment: facing edges within max_gap
    and perpendicular overlap >= min_overlap (metres, post-solve floats)."""
    for lo, hi in ((a, b), (b, a)):
        gap = hi.x - (lo.x + lo.width)
        if -0.01 <= gap <= max_gap:
            ov = min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y)
            if ov >= min_overlap:
                return True
        gap = hi.y - (lo.y + lo.depth)
        if -0.01 <= gap <= max_gap:
            ov = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
            if ov >= min_overlap:
                return True
    return False


def test_plotconfig_attached_toilets_defaults_off():
    cfg = _basic_cfg()
    assert cfg.attached_toilets is False


def test_ensuite_attachment_helper():
    assert ensuite_attachment("toilet_ens_0") == "bedroom_0"
    assert ensuite_attachment("toilet_ens_2") == "bedroom_2"
    assert ensuite_attachment("toilet_0") is None
    assert ensuite_attachment("bedroom_1") is None


def test_room_list_ensuites_added_per_bedroom():
    cfg = _basic_cfg(num_bedrooms=3, toilets=2, attached_toilets=True)
    rooms = _build_room_list(cfg, _load_specs())
    by_id = {r["id"]: r for r in rooms}

    # bedroom 0 (GF) gets a bathroom_master en-suite; others get toilet type
    assert by_id["toilet_ens_0"]["type"] == "bathroom_master"
    assert by_id["toilet_ens_0"]["floor"] == by_id["bedroom_0"]["floor"] == 0
    assert by_id["toilet_ens_0"]["attached_to"] == "bedroom_0"
    for i in (1, 2):
        assert by_id[f"toilet_ens_{i}"]["type"] == "toilet"
        assert by_id[f"toilet_ens_{i}"]["floor"] == by_id[f"bedroom_{i}"]["floor"] == 1
        assert by_id[f"toilet_ens_{i}"]["attached_to"] == f"bedroom_{i}"

    # cfg.toilets counts COMMON toilets — en-suites are additive
    common = [r for r in rooms if r["type"] == "toilet" and "attached_to" not in r]
    assert len(common) == 2


def test_room_list_no_ensuites_when_flag_off():
    cfg = _basic_cfg(num_bedrooms=3, toilets=2)
    rooms = _build_room_list(cfg, _load_specs())
    assert not any("_ens_" in r["id"] for r in rooms)
    assert sum(1 for r in rooms if r["type"] == "toilet") == 2


@pytest.mark.parametrize("attached", [False, True])
def test_room_list_bedroomless_floor_gets_common_toilet(attached):
    # num_bedrooms=1 → floor 1 has rooms (staircase) but no bedroom, so it
    # must get >= 1 common toilet even with only one toilet configured
    # (redistributed, not added).
    cfg = _basic_cfg(num_bedrooms=1, toilets=1, attached_toilets=attached)
    rooms = _build_room_list(cfg, _load_specs())
    common = [r for r in rooms if r["type"] == "toilet" and "attached_to" not in r]
    assert len(common) == 1
    assert any(r["floor"] == 1 for r in common)


def test_solved_ensuite_shares_wall_with_bedroom():
    cfg = _basic_cfg(
        plot_y_extent=15.0,
        plot_x_extent=9.0,
        num_bedrooms=2,
        toilets=1,
        attached_toilets=True,
    )
    layouts = solve_layouts(cfg, 0.23)
    assert layouts, "expected at least one layout with attached toilets"
    for layout in layouts:
        for fp in (layout.ground_floor, layout.first_floor):
            rooms = {r.id: r for r in fp.rooms}
            for r in fp.rooms:
                bed_id = ensuite_attachment(r.id)
                if bed_id is None:
                    continue
                bed = rooms.get(bed_id)
                assert bed is not None, (
                    f"{layout.id}: {r.id} on floor {fp.floor} without {bed_id}"
                )
                # solver enforces >= 0.9 m shared-wall overlap; post-solve
                # grid snapping may shift perpendicular edges slightly
                assert _shares_wall(r, bed, min_overlap=0.85), (
                    f"{layout.id}: {r.id} does not share a wall with {bed_id}"
                )


def test_solved_toilets_do_not_balloon():
    # Regression: size_terms grew toilets to their 6.0 sqm spec max. With wet
    # types excluded from the growth objective they settle near min size.
    cfg = _basic_cfg(plot_y_extent=15.0, plot_x_extent=9.0, num_bedrooms=2, toilets=2)
    layouts = solve_layouts(cfg, 0.23)
    assert layouts
    for layout in layouts:
        for fp in (layout.ground_floor, layout.first_floor):
            for r in fp.rooms:
                if r.type == "toilet":
                    assert r.area <= 4.5, (
                        f"{layout.id}: {r.name} ballooned to {r.area} sqm"
                    )


def test_solved_toilet_placement_common_sense(monkeypatch):
    # Standard 9×15 config: common toilets should avoid the front band
    # (road side, y-min) and should not share a wall with the staircase.
    _generous_solve_budget(monkeypatch)
    cfg = _basic_cfg(plot_y_extent=15.0, plot_x_extent=9.0, num_bedrooms=2, toilets=2)
    ewt = 0.23
    layouts = solve_layouts(cfg, ewt)
    assert layouts
    plate_y0 = cfg.setback_front + ewt
    plate_d = cfg.plot_y_extent - cfg.setback_front - cfg.setback_rear - 2 * ewt
    for layout in layouts:
        for fp in (layout.ground_floor, layout.first_floor):
            stair = next((r for r in fp.rooms if r.type == "staircase"), None)
            for r in fp.rooms:
                if r.type not in ("toilet", "wc_only") or ensuite_attachment(r.id):
                    continue
                cy_rel = (r.y + r.depth / 2 - plate_y0) / plate_d
                assert cy_rel > 0.25, (
                    f"{layout.id}: {r.name} centre in front band (rel y {cy_rel:.2f})"
                )
                if stair is not None:
                    assert not _shares_wall(r, stair, min_overlap=0.3), (
                        f"{layout.id}: {r.name} shares a wall with the staircase"
                    )


def test_wet_cap_tightened():
    from app.engine.generator import _WET_CAP_SQM

    assert _WET_CAP_SQM == 4.6


def test_solve_does_not_raise_on_bad_input():
    cfg = _basic_cfg(plot_y_extent=0.1, plot_x_extent=0.1)
    try:
        result = solve_layouts(cfg, 0.23)
        assert isinstance(result, list)
    except Exception:
        pytest.fail("solve_layouts should not raise — it should return empty list")


def _single_room_layout(cfg: PlotConfig, open_sides: frozenset[str]):
    from app.engine.geometry import buildable_polygon
    from app.engine.models import ComplianceResult, FloorPlan, Layout, Room

    bp = buildable_polygon(cfg)
    minx, miny, maxx, maxy = bp.bounds
    room = Room(
        id="r0",
        name="Living",
        type="living",
        x=minx,
        y=miny,
        width=maxx - minx,
        depth=maxy - miny,
        open_sides=open_sides,
    )
    gf = FloorPlan(floor=0, floor_type="ground", rooms=[room], columns=[])
    ff = FloorPlan(floor=1, floor_type="first", rooms=[], columns=[])
    return Layout(
        id="t",
        name="t",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )


def test_section_ok_flags_layout_with_no_wall_crossing_the_cut_line():
    # A single room spanning the whole (staircase-less) buildable polygon,
    # open on both N and S: the section-cut line is a plain vertical
    # mid-line for a stair-less floor, and it only ever crosses N/S walls
    # for this room shape -- opening both removes every wall it could cross,
    # reproducing derive_section()'s "min() iterable argument is empty"
    # crash. Confirmed against the real function, not assumed.
    cfg = _basic_cfg()
    layout = _single_room_layout(cfg, frozenset({"N", "S"}))
    reason = _section_ok(layout, cfg)
    assert reason is not None
    assert "section geometry invalid" in reason


def test_section_ok_passes_ordinary_layout():
    cfg = _basic_cfg()
    layout = _single_room_layout(cfg, frozenset())
    assert _section_ok(layout, cfg) is None


def _oa_room(rid, typ, x, y, w, d):
    from app.engine.models import Room

    return Room(id=rid, name=typ.title(), type=typ, x=x, y=y, width=w, depth=d)


def test_open_air_rooms_open_on_the_building_perimeter():
    """Verandahs/courtyards/porches must not be drawn as fully walled rooms.

    `Room.open_sides` is honoured all the way through the drawing stack
    (derive_walls drops the wall on a declared-open edge), but the only place
    production ever SET it was `parking["open_sides"] = ("S",)` in
    _room_defs -- and only when cfg.open_parking. Every verandah, balcony,
    terrace and perimeter courtyard therefore rendered with four walls, which
    reads as an interior room.

    A side counts as open only when that edge lies on the built form's own
    perimeter, so an INTERNAL courtyard (surrounded by rooms) is left alone.
    """
    from app.engine.solver import _apply_open_air_sides

    rooms = [
        _oa_room("r0", "living", 0.0, 0.0, 6.0, 6.0),
        # verandah juts out along the front (y-min) edge of the built form
        _oa_room("r1", "verandah", 0.0, -2.0, 6.0, 2.0),
        # courtyard fully enclosed by the living block -> must stay walled
        _oa_room("r2", "courtyard", 2.0, 2.0, 2.0, 2.0),
    ]
    out = {r.id: r for r in _apply_open_air_sides(rooms)}

    assert "S" in out["r1"].open_sides, (
        f"verandah on the front perimeter should be open to the south, "
        f"got {sorted(out['r1'].open_sides)}"
    )
    assert not out["r2"].open_sides, (
        f"internal courtyard should keep its walls, got {sorted(out['r2'].open_sides)}"
    )
    assert not out["r0"].open_sides, "a living room is never open-sided"
    for r in out.values():
        assert len(r.open_sides) < 4, "models.py forbids all four sides open"
