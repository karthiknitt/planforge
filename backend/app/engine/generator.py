from __future__ import annotations

from .archetypes import layout_a, layout_b, layout_c, layout_d, layout_e, layout_f
from .compliance import check, load_rules
from .models import Layout, PlotConfig
from .vastu import check_vastu


def generate(cfg: PlotConfig) -> list[Layout]:
    """Generate layout archetypes, run compliance checks, and return only passing layouts."""
    rules = load_rules()
    ewt = rules["external_wall_thickness_mm"] / 1000
    iwt = rules["internal_wall_thickness_mm"] / 1000

    layouts: list[Layout] = []
    generators = [layout_a, layout_b, layout_c, layout_d, layout_e]

    for fn in generators:
        layout = fn(cfg, ewt=ewt, iwt=iwt)
        layout.compliance = check(layout, cfg, rules)

        # Vastu check (appended to compliance result; does not affect passed/failed)
        if cfg.vastu_enabled:
            v_violations, v_warnings = check_vastu(layout, cfg, road_side=cfg.road_side)
            layout.compliance.violations.extend(v_violations)
            layout.compliance.warnings.extend(v_warnings)
            # Re-evaluate passed status including Vastu hard violations
            layout.compliance.passed = len(layout.compliance.violations) == 0

        if layout.compliance.passed:
            layouts.append(layout)

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
            if lf.compliance.passed:
                layouts.append(lf)

    return layouts
