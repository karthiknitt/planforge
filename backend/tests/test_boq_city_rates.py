"""
Tests for BOQ city-wise material rates (P2-1).

Financial data: wrong rates erode trust with users. These tests guard against:
  - Rate file structure integrity (all required fields present for each city)
  - City-specific rates differ from Generic baseline (i.e. the data isn't copy-pasted)
  - Fallback to Generic rates when unknown city is requested
  - BOQ QuantityEngine produces a non-zero total_cost for a real layout
  - Chennai is more expensive than Trichy (realistic India market expectation)
  - The rate file is not stale (last_updated field exists)
"""

import json
from pathlib import Path

import pytest

from app.engine.boq import QuantityEngine, _load_rates, _supported_cities
from app.engine.generator import generate
from app.engine.models import PlotConfig


RATES_PATH = Path(__file__).parent.parent / "app" / "config" / "material_rates.json"

REQUIRED_FIELDS = [
    "steel_per_ton",
    "cement_per_bag_50kg",
    "bricks_per_1000",
    "river_sand_per_cft",
    "aggregate_20mm_per_cft",
    "tiles_floor_per_sqft",
    "tiles_wall_per_sqft",
    "paint_per_litre",
    "labour_per_sqft_civil",
    "labour_per_sqft_finishing",
    "plumbing_per_bathroom",
    "electrical_per_sqft",
]

EXPECTED_CITIES = ["Generic", "Chennai", "Bangalore", "Hyderabad", "Pune", "Mumbai"]


# ── File-level structural checks ──────────────────────────────────────────────

def test_rates_file_exists():
    assert RATES_PATH.exists(), "material_rates.json is missing"


def test_rates_file_has_last_updated():
    data = json.loads(RATES_PATH.read_text())
    assert "last_updated" in data, "material_rates.json missing last_updated field"


def test_all_expected_cities_present():
    cities = json.loads(RATES_PATH.read_text())["cities"]
    for city in EXPECTED_CITIES:
        assert city in cities, f"City '{city}' missing from material_rates.json"


def test_all_required_fields_present_for_each_city():
    cities = json.loads(RATES_PATH.read_text())["cities"]
    for city, rates in cities.items():
        for field in REQUIRED_FIELDS:
            assert field in rates, f"City '{city}' missing field '{field}'"
            assert isinstance(rates[field], (int, float)), (
                f"City '{city}'.{field} must be numeric, got {type(rates[field])}"
            )
            assert rates[field] > 0, f"City '{city}'.{field} must be positive"


# ── Rate logic checks ─────────────────────────────────────────────────────────

def test_city_rates_differ_from_generic():
    """Each non-Generic city must have at least one field that differs from Generic."""
    cities = json.loads(RATES_PATH.read_text())["cities"]
    generic = cities["Generic"]
    for city, rates in cities.items():
        if city == "Generic":
            continue
        differs = any(rates[f] != generic[f] for f in REQUIRED_FIELDS)
        assert differs, f"City '{city}' rates are identical to Generic — data likely copy-pasted"


def test_load_rates_returns_generic_for_unknown_city():
    """Unknown city name falls back silently to Generic rates."""
    generic = _load_rates("Generic")
    unknown = _load_rates("Atlantis")
    assert unknown == generic


def test_supported_cities_includes_generic_and_majors():
    cities = _supported_cities()
    for city in EXPECTED_CITIES:
        assert city in cities


# ── Relative price ordering (market reality check) ────────────────────────────

def test_mumbai_more_expensive_than_trichy():
    """Mumbai labour cost must exceed Trichy — basic Indian market sanity check."""
    mumbai = _load_rates("Mumbai")
    trichy = _load_rates("Trichy")
    assert mumbai["labour_per_sqft_civil"] > trichy["labour_per_sqft_civil"]


def test_chennai_more_expensive_than_trichy():
    """Chennai (metro) must be pricier than Trichy (tier-2 city)."""
    chennai = _load_rates("Chennai")
    trichy = _load_rates("Trichy")
    assert chennai["steel_per_ton"] > trichy["steel_per_ton"]
    assert chennai["cement_per_bag_50kg"] > trichy["cement_per_bag_50kg"]


# ── Integration: BOQ produces valid output ────────────────────────────────────

def _base_cfg(city: str = "Generic") -> PlotConfig:
    return PlotConfig(
        plot_length=12.0,
        plot_width=9.0,
        setback_front=1.5,
        setback_rear=1.5,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=2,
        toilets=2,
        parking=False,
        city=city,
    )


def test_boq_engine_produces_nonzero_total(tmp_path):
    """BOQ on a generated layout must return a positive total cost."""
    cfg = _base_cfg("Chennai")
    layouts = generate(cfg)
    assert layouts, "generate() returned no layouts — solver or config issue"

    layout = layouts[0]
    engine = QuantityEngine()
    result = engine.calculate(layout, cfg, project_name="BOQ Test", city="Chennai")

    assert result.total_cost > 0, "BOQ total cost is zero — rate or quantity calculation broken"
    assert len(result.line_items) > 0, "BOQ has no line items"


def test_boq_engine_generic_cost_absent_for_generic_city():
    """When city=Generic, generic_total_cost should be None (no comparison needed)."""
    cfg = _base_cfg("Generic")
    layouts = generate(cfg)
    layout = layouts[0]
    engine = QuantityEngine()
    result = engine.calculate(layout, cfg, project_name="Generic Test", city="Generic")
    assert result.to_dict()["generic_total_cost"] is None


def test_boq_engine_city_total_higher_than_generic():
    """Mumbai rates should produce a higher BOQ total than Generic rates."""
    cfg_generic = _base_cfg("Generic")
    cfg_mumbai = _base_cfg("Mumbai")
    layouts = generate(cfg_generic)
    layout = layouts[0]

    engine = QuantityEngine()
    total_generic = engine.calculate(layout, cfg_generic, project_name="Generic", city="Generic").total_cost
    total_mumbai  = engine.calculate(layout, cfg_mumbai,  project_name="Mumbai",  city="Mumbai").total_cost

    assert total_mumbai > total_generic, (
        f"Mumbai BOQ ({total_mumbai}) should exceed Generic BOQ ({total_generic})"
    )
