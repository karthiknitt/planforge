"""
Bill of Quantities (BOQ) engine for PlanForge.

Calculates approximate material quantities for a G+1 residential building
based on layout geometry and NBC standard dimensions.
Supports city-wise material rates for 8 Indian cities.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import FloorPlan, Layout, PlotConfig


FLOOR_HEIGHT_M = 3.0     # floor-to-floor height (m)
SLAB_THICKNESS = 0.125   # 125 mm RC slab
COLUMN_SIZE    = 0.30    # 300 mm × 300 mm column
STEEL_PER_M3   = 80.0    # kg of steel per m³ of column/beam concrete (rule of thumb)
BRICK_VOLUME   = 0.001875  # per brick (m³) — standard Indian brick 190×90×90 + mortar
MORTAR_RATIO   = 1.0 / 6.0  # 1:6 mortar, mortar fraction ≈ 20% by volume

_RATES_PATH = Path(__file__).parent.parent / "config" / "material_rates.json"

# SQM to sqft conversion
_SQM_TO_SQFT = 10.764
# CFT per cubic metre
_M3_TO_CFT = 35.315
# kg per tonne
_KG_PER_TON = 1000.0


def _load_rates(city: str) -> dict:
    """Load material rates for the given city from material_rates.json."""
    with _RATES_PATH.open() as f:
        data = json.load(f)
    cities = data.get("cities", {})
    if city in cities:
        return cities[city]
    return cities.get("Generic", {})


def _supported_cities() -> list[str]:
    with _RATES_PATH.open() as f:
        data = json.load(f)
    return list(data.get("cities", {}).keys())


@dataclass
class BOQLineItem:
    item: str
    description: str
    quantity: float
    unit: str
    rate: float = 0.0
    amount: float = 0.0


@dataclass
class BOQResult:
    project_name: str
    layout_id: str
    city: str = "Generic"
    rates_note: str = "Generic rates (2026)"
    total_cost: float = 0.0
    generic_total_cost: float = 0.0
    cost_difference: float = 0.0
    line_items: list[BOQLineItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "layout_id": self.layout_id,
            "city": self.city,
            "rates_note": self.rates_note,
            "total_cost": round(self.total_cost),
            "generic_total_cost": round(self.generic_total_cost) if self.city != "Generic" else None,
            "cost_difference": round(self.cost_difference) if self.city != "Generic" else None,
            "items": [
                {
                    "item":        li.item,
                    "description": li.description,
                    "quantity":    round(li.quantity, 3),
                    "unit":        li.unit,
                    "rate":        round(li.rate, 2),
                    "amount":      round(li.amount),
                }
                for li in self.line_items
            ],
        }


class QuantityEngine:
    """Calculate material quantities and costs for a G+1 layout."""

    def calculate(self, layout: Layout, cfg: PlotConfig,
                  project_name: str = "", city: str = "Generic") -> BOQResult:
        rates = _load_rates(city)
        result = BOQResult(
            project_name=project_name,
            layout_id=layout.id,
            city=city,
            rates_note=f"{city} rates (Mar 2026)",
        )
        ewt = 0.23  # external wall thickness
        iwt = 0.115  # internal wall thickness

        gf = layout.ground_floor
        ff = layout.first_floor

        # ── Floor areas ─────────────────────────────────────────────────────
        gf_area = sum(r.area for r in gf.rooms)
        ff_area = sum(r.area for r in ff.rooms)
        total_area = gf_area + ff_area
        total_area_sqft = total_area * _SQM_TO_SQFT

        result.line_items.append(BOQLineItem(
            "1", "Built-up area (Ground floor)", gf_area, "sqm"))
        result.line_items.append(BOQLineItem(
            "2", "Built-up area (First floor)", ff_area, "sqm"))

        # ── Concrete slab ───────────────────────────────────────────────────
        slab_vol = total_area * SLAB_THICKNESS
        result.line_items.append(BOQLineItem(
            "3", "RCC slab concrete (M20)", round(slab_vol, 3), "cum"))

        # ── Columns ─────────────────────────────────────────────────────────
        unique_cols = set()
        for plan in [gf, ff]:
            for col in plan.columns:
                unique_cols.add((round(col.x, 2), round(col.y, 2)))
        col_count = len(unique_cols)
        col_vol = col_count * COLUMN_SIZE * COLUMN_SIZE * FLOOR_HEIGHT_M * 2  # G+1
        col_steel_kg = col_vol * STEEL_PER_M3
        col_steel_ton = col_steel_kg / _KG_PER_TON

        col_steel_rate = rates.get("steel_per_ton", 58000)
        col_steel_amount = col_steel_ton * col_steel_rate

        result.line_items.append(BOQLineItem(
            "4", f"RCC columns ({col_count} nos, 300×300 mm)",
            round(col_vol, 3), "cum"))
        result.line_items.append(BOQLineItem(
            "5", "Reinforcement steel in columns (IS 456)",
            round(col_steel_kg, 1), "kg",
            rate=col_steel_rate / _KG_PER_TON,
            amount=col_steel_amount))

        # ── Brick masonry walls ─────────────────────────────────────────────
        ext_wall_len = 2 * (cfg.plot_width + cfg.plot_length) * 0.6  # approx exterior perimeter
        ext_wall_vol = ext_wall_len * FLOOR_HEIGHT_M * ewt * 2       # both floors
        int_wall_vol = self._internal_wall_volume(gf, ff, iwt)
        total_wall_vol_cft = (ext_wall_vol + int_wall_vol) * _M3_TO_CFT

        bricks_per_1000_rate = rates.get("bricks_per_1000", 6500)
        # Approximate: 500 bricks per cum of brickwork
        bricks_count = (ext_wall_vol + int_wall_vol) * 500
        brick_amount = (bricks_count / 1000) * bricks_per_1000_rate

        result.line_items.append(BOQLineItem(
            "6", "Brick masonry — external walls (230 mm)",
            round(ext_wall_vol, 3), "cum",
            rate=bricks_per_1000_rate,
            amount=round((ext_wall_vol * 500 / 1000) * bricks_per_1000_rate)))
        result.line_items.append(BOQLineItem(
            "7", "Brick masonry — internal walls (115 mm)",
            round(int_wall_vol, 3), "cum",
            rate=bricks_per_1000_rate,
            amount=round((int_wall_vol * 500 / 1000) * bricks_per_1000_rate)))

        # ── Plaster ─────────────────────────────────────────────────────────
        plaster_area = (ext_wall_len * FLOOR_HEIGHT_M * 2 * 2
                        + self._internal_wall_area(gf, ff, iwt) * 2)  # both sides
        result.line_items.append(BOQLineItem(
            "8", "Cement plaster (12 mm thick, internal + external)",
            round(plaster_area, 1), "sqm"))

        # ── Flooring ────────────────────────────────────────────────────────
        floor_rate_per_sqft = rates.get("tiles_floor_per_sqft", 55)
        floor_amount = total_area_sqft * floor_rate_per_sqft
        result.line_items.append(BOQLineItem(
            "9", "Flooring (vitrified tiles, avg 600×600 mm)",
            round(total_area, 1), "sqm",
            rate=floor_rate_per_sqft * _SQM_TO_SQFT,
            amount=round(floor_amount)))

        # ── Excavation for footings ─────────────────────────────────────────
        footing_vol = col_count * 1.5 * 1.5 * 1.0  # 1.5×1.5 m plan, 1 m deep
        result.line_items.append(BOQLineItem(
            "10", f"Excavation for column footings ({col_count} nos)",
            round(footing_vol, 1), "cum"))

        # ── PCC under footings ───────────────────────────────────────────────
        pcc_vol = col_count * 1.5 * 1.5 * 0.075  # 75 mm PCC
        result.line_items.append(BOQLineItem(
            "11", "PCC (1:4:8) under footings", round(pcc_vol, 3), "cum"))

        # ── Labour — civil ───────────────────────────────────────────────────
        labour_civil_rate = rates.get("labour_per_sqft_civil", 250)
        labour_civil_amount = total_area_sqft * labour_civil_rate
        result.line_items.append(BOQLineItem(
            "12", "Labour — civil works (masonry, concrete, plaster)",
            round(total_area_sqft, 1), "sqft",
            rate=labour_civil_rate,
            amount=round(labour_civil_amount)))

        # ── Labour — finishing ───────────────────────────────────────────────
        labour_finish_rate = rates.get("labour_per_sqft_finishing", 180)
        labour_finish_amount = total_area_sqft * labour_finish_rate
        result.line_items.append(BOQLineItem(
            "13", "Labour — finishing works (tiles, paint, carpentry)",
            round(total_area_sqft, 1), "sqft",
            rate=labour_finish_rate,
            amount=round(labour_finish_amount)))

        # ── Plumbing ─────────────────────────────────────────────────────────
        bathroom_count = sum(
            1 for r in list(gf.rooms) + list(ff.rooms) if r.type == "toilet"
        )
        if bathroom_count == 0:
            bathroom_count = 2  # fallback
        plumbing_rate = rates.get("plumbing_per_bathroom", 35000)
        plumbing_amount = bathroom_count * plumbing_rate
        result.line_items.append(BOQLineItem(
            "14", f"Plumbing and sanitary ({bathroom_count} bathrooms)",
            bathroom_count, "nos",
            rate=plumbing_rate,
            amount=round(plumbing_amount)))

        # ── Electrical ───────────────────────────────────────────────────────
        electrical_rate = rates.get("electrical_per_sqft", 85)
        electrical_amount = total_area_sqft * electrical_rate
        result.line_items.append(BOQLineItem(
            "15", "Electrical works (wiring, DB, fixtures)",
            round(total_area_sqft, 1), "sqft",
            rate=electrical_rate,
            amount=round(electrical_amount)))

        # ── River sand ───────────────────────────────────────────────────────
        sand_cft = (ext_wall_vol + int_wall_vol + slab_vol) * _M3_TO_CFT * 0.3  # approx
        sand_rate = rates.get("river_sand_per_cft", 55)
        sand_amount = sand_cft * sand_rate
        result.line_items.append(BOQLineItem(
            "16", "River sand (masonry + plaster + concrete)",
            round(sand_cft, 1), "cft",
            rate=sand_rate,
            amount=round(sand_amount)))

        # ── Aggregate ────────────────────────────────────────────────────────
        agg_cft = slab_vol * _M3_TO_CFT * 1.5  # approx
        agg_rate = rates.get("aggregate_20mm_per_cft", 45)
        agg_amount = agg_cft * agg_rate
        result.line_items.append(BOQLineItem(
            "17", "Coarse aggregate 20mm (concrete work)",
            round(agg_cft, 1), "cft",
            rate=agg_rate,
            amount=round(agg_amount)))

        # ── Cement ───────────────────────────────────────────────────────────
        # ~6 bags per cum concrete/masonry (rough average)
        cement_bags = (slab_vol + col_vol + ext_wall_vol + int_wall_vol) * 6
        cement_rate = rates.get("cement_per_bag_50kg", 380)
        cement_amount = cement_bags * cement_rate
        result.line_items.append(BOQLineItem(
            "18", "Cement (OPC 53 grade, 50kg bags)",
            round(cement_bags, 0), "bags",
            rate=cement_rate,
            amount=round(cement_amount)))

        # ── Compute totals ────────────────────────────────────────────────────
        result.total_cost = sum(li.amount for li in result.line_items)

        # ── City comparison — compute Generic total if city != Generic ────────
        if city != "Generic":
            generic_result = QuantityEngine().calculate(
                layout, cfg, project_name=project_name, city="Generic"
            )
            result.generic_total_cost = generic_result.total_cost
            result.cost_difference = result.total_cost - generic_result.total_cost
        else:
            result.generic_total_cost = result.total_cost
            result.cost_difference = 0.0

        return result

    # ── Private helpers ──────────────────────────────────────────────────────

    def _internal_wall_volume(self, gf: FloorPlan, ff: FloorPlan, iwt: float) -> float:
        total = 0.0
        for plan in [gf, ff]:
            xs = sorted({r.x for r in plan.rooms} | {r.x + r.width for r in plan.rooms})
            ys = sorted({r.y for r in plan.rooms} | {r.y + r.depth for r in plan.rooms})
            all_x = xs[1:-1]  # exclude outer edges
            all_y = ys[1:-1]
            for x in all_x:
                span_d = (max(r.y + r.depth for r in plan.rooms) -
                          min(r.y for r in plan.rooms))
                total += span_d * FLOOR_HEIGHT_M * iwt
            for y in all_y:
                span_w = (max(r.x + r.width for r in plan.rooms) -
                          min(r.x for r in plan.rooms))
                total += span_w * FLOOR_HEIGHT_M * iwt
        return total

    def _internal_wall_area(self, gf: FloorPlan, ff: FloorPlan, iwt: float) -> float:
        total = 0.0
        for plan in [gf, ff]:
            xs = sorted({r.x for r in plan.rooms} | {r.x + r.width for r in plan.rooms})
            ys = sorted({r.y for r in plan.rooms} | {r.y + r.depth for r in plan.rooms})
            for x in xs[1:-1]:
                span_d = (max(r.y + r.depth for r in plan.rooms) -
                          min(r.y for r in plan.rooms))
                total += span_d * FLOOR_HEIGHT_M
            for y in ys[1:-1]:
                span_w = (max(r.x + r.width for r in plan.rooms) -
                          min(r.x for r in plan.rooms))
                total += span_w * FLOOR_HEIGHT_M
        return total
