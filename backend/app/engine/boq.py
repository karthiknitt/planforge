"""
Bill of Quantities (BOQ) engine for PlanForge.

Calculates approximate material quantities for a G+1 residential building
based on layout geometry and NBC standard dimensions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import FloorPlan, Layout, PlotConfig


FLOOR_HEIGHT_M = 3.0     # floor-to-floor height (m)
SLAB_THICKNESS = 0.125   # 125 mm RC slab
COLUMN_SIZE    = 0.30    # 300 mm × 300 mm column
STEEL_PER_M3   = 80.0    # kg of steel per m³ of column/beam concrete (rule of thumb)
BRICK_VOLUME   = 0.001875  # per brick (m³) — standard Indian brick 190×90×90 + mortar
MORTAR_RATIO   = 1.0 / 6.0  # 1:6 mortar, mortar fraction ≈ 20% by volume


@dataclass
class BOQLineItem:
    item: str
    description: str
    quantity: float
    unit: str


@dataclass
class BOQResult:
    project_name: str
    layout_id: str
    line_items: list[BOQLineItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "layout_id": self.layout_id,
            "items": [
                {
                    "item":        li.item,
                    "description": li.description,
                    "quantity":    round(li.quantity, 3),
                    "unit":        li.unit,
                }
                for li in self.line_items
            ],
        }


class QuantityEngine:
    """Calculate material quantities for a G+1 layout."""

    def calculate(self, layout: Layout, cfg: PlotConfig,
                  project_name: str = "") -> BOQResult:
        result = BOQResult(project_name=project_name, layout_id=layout.id)
        ewt = 0.23  # external wall thickness
        iwt = 0.115  # internal wall thickness

        gf = layout.ground_floor
        ff = layout.first_floor

        # ── Floor areas ─────────────────────────────────────────────────────
        gf_area = sum(r.area for r in gf.rooms)
        ff_area = sum(r.area for r in ff.rooms)
        total_area = gf_area + ff_area

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
        col_steel = col_vol * STEEL_PER_M3

        result.line_items.append(BOQLineItem(
            "4", f"RCC columns ({col_count} nos, 300×300 mm)", round(col_vol, 3), "cum"))
        result.line_items.append(BOQLineItem(
            "5", "Reinforcement steel in columns (IS 456)", round(col_steel, 1), "kg"))

        # ── Brick masonry walls ─────────────────────────────────────────────
        ext_wall_len = 2 * (cfg.plot_width + cfg.plot_length) * 0.6  # approx exterior perimeter
        ext_wall_vol = ext_wall_len * FLOOR_HEIGHT_M * ewt * 2       # both floors
        int_wall_vol = self._internal_wall_volume(gf, ff, iwt)

        result.line_items.append(BOQLineItem(
            "6", "Brick masonry — external walls (230 mm)", round(ext_wall_vol, 3), "cum"))
        result.line_items.append(BOQLineItem(
            "7", "Brick masonry — internal walls (115 mm)", round(int_wall_vol, 3), "cum"))

        # ── Plaster ─────────────────────────────────────────────────────────
        plaster_area = (ext_wall_len * FLOOR_HEIGHT_M * 2 * 2
                        + self._internal_wall_area(gf, ff, iwt) * 2)  # both sides
        result.line_items.append(BOQLineItem(
            "8", "Cement plaster (12 mm thick, internal + external)", round(plaster_area, 1), "sqm"))

        # ── Flooring ────────────────────────────────────────────────────────
        result.line_items.append(BOQLineItem(
            "9", "Flooring (vitrified tiles, avg 600×600 mm)", round(total_area, 1), "sqm"))

        # ── Excavation for footings ─────────────────────────────────────────
        footing_vol = col_count * 1.5 * 1.5 * 1.0  # 1.5×1.5 m plan, 1 m deep
        result.line_items.append(BOQLineItem(
            "10", f"Excavation for column footings ({col_count} nos)", round(footing_vol, 1), "cum"))

        # ── PCC under footings ───────────────────────────────────────────────
        pcc_vol = col_count * 1.5 * 1.5 * 0.075  # 75 mm PCC
        result.line_items.append(BOQLineItem(
            "11", "PCC (1:4:8) under footings", round(pcc_vol, 3), "cum"))

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
