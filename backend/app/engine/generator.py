from __future__ import annotations

from .archetypes import layout_a, layout_b, layout_c, layout_d, layout_e, layout_f
from .compliance import check, load_rules
from .models import Layout, PlotConfig


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
        if layout.compliance.passed:
            layouts.append(layout)

    # Layout F: courtyard — conditional on plot area >= 150 sqm
    plot_area = cfg.plot_width * cfg.plot_length
    if plot_area >= 150:
        lf = layout_f(cfg, ewt=ewt, iwt=iwt)
        if lf is not None:
            lf.compliance = check(lf, cfg, rules)
            if lf.compliance.passed:
                layouts.append(lf)

    return layouts
