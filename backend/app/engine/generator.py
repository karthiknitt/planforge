from __future__ import annotations

from .archetypes import layout_a, layout_b, layout_c
from .compliance import check, load_rules
from .models import Layout, PlotConfig


def generate(cfg: PlotConfig) -> list[Layout]:
    """Generate all three layout archetypes and run compliance checks."""
    rules = load_rules()
    layouts: list[Layout] = []

    for fn in (layout_a, layout_b, layout_c):
        layout = fn(cfg)
        layout.compliance = check(layout, cfg, rules)
        layouts.append(layout)

    return layouts
