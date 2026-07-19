"""Tests for plinth_beam_design.design_plinth_beams."""

import pytest

from app.engine.cad_elements import WallSegment
from app.services import plinth_beam_design, structagent_client


@pytest.mark.asyncio
async def test_design_plinth_beams_groups_by_span_and_calls_calc_beam(monkeypatch):
    walls = [
        WallSegment(x1=0.0, y1=0.0, x2=3.5, y2=0.0, thickness=0.230, kind="external"),
        WallSegment(x1=0.0, y1=4.0, x2=3.5, y2=4.0, thickness=0.230, kind="external"),
        WallSegment(x1=0.0, y1=0.0, x2=0.0, y2=2.0, thickness=0.115, kind="internal"),
    ]
    calls = []

    async def fake_calc_beam(payload, **kw):
        calls.append(payload)
        return structagent_client.StructuralResult(
            ok=True,
            checks=[],
            data={"design": {"n_bars": 2, "bar_dia": 12}},
        )

    monkeypatch.setattr(structagent_client, "calc_beam", fake_calc_beam)

    results = await plinth_beam_design.design_plinth_beams(walls)

    # two unique external-wall spans of 3.5m should collapse to ONE calc_beam call
    external_spans = [p for p in calls if p["span_m"] == pytest.approx(3.5)]
    assert len(external_spans) == 1
    # the 2.0m internal wall span is a distinct group -> its own call
    assert any(p["span_m"] == pytest.approx(2.0) for p in calls)
    # results should be keyed per unique span, with count reflecting how many
    # wall segments were grouped into it
    assert (
        len(results) == 2
    )  # one group for the two 3.5m external walls, one for the 2.0m internal wall
    external_key = next(
        k for k, v in results.items() if v["span_m"] == pytest.approx(3.5)
    )
    assert results[external_key]["count"] == 2
    assert results[external_key]["kind"] == "external"
    assert results[external_key]["design"]["n_bars"] == 2


@pytest.mark.asyncio
async def test_design_plinth_beams_same_span_different_kind_no_key_collision(
    monkeypatch,
):
    """Regression: an external and internal wall with the SAME rounded span
    must not collide on the same output dict key -- kind must be part of it,
    or one beam design silently overwrites the other.
    """
    walls = [
        WallSegment(x1=0.0, y1=0.0, x2=3.0, y2=0.0, thickness=0.230, kind="external"),
        WallSegment(x1=0.0, y1=1.0, x2=3.0, y2=1.0, thickness=0.115, kind="internal"),
    ]

    async def fake_calc_beam(payload, **kw):
        return structagent_client.StructuralResult(
            ok=True,
            checks=[],
            data={"design": {"n_bars": 2, "bar_dia": 12}},
        )

    monkeypatch.setattr(structagent_client, "calc_beam", fake_calc_beam)

    results = await plinth_beam_design.design_plinth_beams(walls)

    assert len(results) == 2
    kinds = {v["kind"] for v in results.values()}
    assert kinds == {"external", "internal"}
    external_entry = next(v for v in results.values() if v["kind"] == "external")
    internal_entry = next(v for v in results.values() if v["kind"] == "internal")
    assert external_entry["b_mm"] == 230
    assert internal_entry["b_mm"] == 115
