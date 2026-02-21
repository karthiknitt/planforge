from __future__ import annotations

from .archetypes import layout_a, layout_b, layout_c, layout_d, layout_e, layout_f
from .compliance import check, load_rules
from .models import Layout, PlotConfig
from .scorer import rank_and_select
from .solver import solve_layouts
from .vastu import check_vastu


def generate(cfg: PlotConfig) -> list[Layout]:
    """Generate layouts using the CP-SAT solver (primary) with archetype fallback.

    Returns up to 3 passing layouts ranked by quality score.
    """
    rules = load_rules()
    ewt = rules["external_wall_thickness_mm"] / 1000
    iwt = rules["internal_wall_thickness_mm"] / 1000

    # ── Solver path (Phase A) ─────────────────────────────────────────────────
    solver_layouts: list[Layout] = []
    try:
        solver_layouts = solve_layouts(cfg, ewt)
    except Exception:
        pass  # always fall through to archetypes

    solver_ids = {l.id for l in solver_layouts}

    # ── Archetype fallback ────────────────────────────────────────────────────
    archetype_layouts: list[Layout] = []
    generators = [layout_a, layout_b, layout_c, layout_d, layout_e]

    for fn in generators:
        layout = fn(cfg, ewt=ewt, iwt=iwt)
        layout.compliance = check(layout, cfg, rules)

        if cfg.vastu_enabled:
            v_violations, v_warnings = check_vastu(layout, cfg, road_side=cfg.road_side)
            layout.compliance.violations.extend(v_violations)
            layout.compliance.warnings.extend(v_warnings)
            layout.compliance.passed = len(layout.compliance.violations) == 0

        if layout.compliance.passed and layout.id not in solver_ids:
            archetype_layouts.append(layout)

    # Layout F: courtyard — conditional on plot area >= 150 sqm
    plot_area = cfg.plot_width * cfg.plot_length
    if plot_area >= 150:
        lf = layout_f(cfg, ewt=ewt, iwt=iwt)
        if lf is not None:
            lf.compliance = check(lf, cfg, rules)
            if cfg.vastu_enabled:
                v_violations, v_warnings = check_vastu(lf, cfg, road_side=cfg.road_side)
                lf.compliance.violations.extend(v_violations)
                lf.compliance.warnings.extend(v_warnings)
                lf.compliance.passed = len(lf.compliance.violations) == 0
            if lf.compliance.passed and lf.id not in solver_ids:
                archetype_layouts.append(lf)

    all_layouts = solver_layouts + archetype_layouts

    # ── Score and select top 3 ────────────────────────────────────────────────
    return rank_and_select(all_layouts, cfg, top_n=3)
