"""Re-runnable A/B sweep behind Task 13's corpus-prior go/no-go decision.

Solves the same programme three ways and scores each with GCS
(`app.quality.ccqs.compute_gcs`) and the corpus-similarity diagnostic
(`app.quality.corpus_similarity.compute_corpus_similarity`):

    off   priors disabled                        -- the baseline
    style priors enabled, cfg.style_preset set    -- style-specific branch
    wide  priors enabled, cfg.style_preset=None   -- corpus-wide fallback

`style_preset` reaches the solver ONLY through `corpus_priors.py`'s accessors
(and the shape-usage gate), so the three arms differ in nothing but the
priors -- the room programme is identical, which is what makes the
adjacency component comparable within a cell (see `_adjacency_score`'s
docstring on why it is NOT comparable across programmes).

Every arm is scored against the STYLE's cfg regardless of which cfg solved
it, so `wide` and `style` are judged by the same yardstick. The `off` and
`wide` arms do not depend on the style at all, so they are solved once per
cell and reused across all 16 styles.

Usage:
    uv run python -m scripts.tune_corpus_priors            # full sweep
    uv run python -m scripts.tune_corpus_priors --styles Kerala Contemporary
    uv run python -m scripts.tune_corpus_priors --json out.json
    uv run python -m scripts.tune_corpus_priors --size-weight 10   # try a weight
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.engine import solver as S
from app.engine.corpus_priors import load_priors
from app.engine.models import PlotConfig
from app.quality.ccqs import compute_gcs
from app.quality.corpus_similarity import compute_corpus_similarity

# (plot_x, plot_y, bedrooms, toilets) -- two plot geometries so a finding is
# not an artefact of one envelope. 3BR appears on both.
CELLS: list[tuple[float, float, int, int]] = [
    (9.0, 15.0, 2, 2),
    (9.0, 15.0, 3, 2),
    (12.0, 18.0, 3, 3),
    (12.0, 18.0, 4, 3),
]


@dataclass
class ArmScore:
    gcs: float | None
    overall: float | None
    size: float | None
    adjacency: float | None
    position: float | None
    shape: float | None


def _cfg(
    plot_x: float,
    plot_y: float,
    bedrooms: int,
    toilets: int,
    *,
    style: str | None,
    priors: bool,
) -> PlotConfig:
    return PlotConfig(
        plot_x_extent=plot_x,
        plot_y_extent=plot_y,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=bedrooms,
        toilets=toilets,
        parking=True,
        road_side="S",
        style_preset=style,
        corpus_priors_enabled=priors,
    )


def _score(layout, score_cfg: PlotConfig) -> ArmScore:
    """Score `layout` against `score_cfg` -- always the style-bearing cfg."""
    if layout is None:
        return ArmScore(None, None, None, None, None, None)
    gcs = compute_gcs(layout.ground_floor, score_cfg)
    sim = compute_corpus_similarity(layout, score_cfg)
    return ArmScore(
        gcs=gcs.total,
        overall=sim.overall,
        size=sim.size_score,
        adjacency=sim.adjacency_score,
        position=sim.position_score,
        shape=sim.shape_score,
    )


def run_sweep(styles: list[str], cells: list[tuple[float, float, int, int]]) -> dict:
    rows: list[dict] = []
    for plot_x, plot_y, bedrooms, toilets in cells:
        cell = f"{plot_x:g}x{plot_y:g}/{bedrooms}BR"
        # Style-independent arms: solved once, reused for every style.
        t0 = time.time()
        off_layout = S.solve_layout(
            _cfg(plot_x, plot_y, bedrooms, toilets, style=None, priors=False)
        )
        wide_layout = S.solve_layout(
            _cfg(plot_x, plot_y, bedrooms, toilets, style=None, priors=True)
        )
        print(f"[{cell}] shared arms solved in {time.time() - t0:.1f}s", flush=True)

        for style in styles:
            score_cfg = _cfg(
                plot_x, plot_y, bedrooms, toilets, style=style, priors=False
            )
            t1 = time.time()
            style_layout = S.solve_layout(
                _cfg(plot_x, plot_y, bedrooms, toilets, style=style, priors=True)
            )
            rows.append(
                {
                    "cell": cell,
                    "style": style,
                    "off": asdict(_score(off_layout, score_cfg)),
                    "style_arm": asdict(_score(style_layout, score_cfg)),
                    "wide": asdict(_score(wide_layout, score_cfg)),
                }
            )
            print(f"[{cell}] {style} solved in {time.time() - t1:.1f}s", flush=True)
    return {"cells": [f"{c[0]:g}x{c[1]:g}/{c[2]}BR" for c in cells], "rows": rows}


def _fmt(v: float | None) -> str:
    return "  --" if v is None else f"{v:5.1f}"


def print_report(result: dict) -> None:
    rows = result["rows"]
    header = (
        f"{'cell':<14}{'style':<22}"
        f"{'GCS off':>8}{'GCS sty':>8}{'GCS wid':>8}"
        f"{'siz off':>8}{'siz sty':>8}{'siz wid':>8}"
        f"{'adj off':>8}{'adj sty':>8}{'adj wid':>8}"
        f"{'pos off':>8}{'pos sty':>8}{'pos wid':>8}"
        f"{'shp off':>8}{'shp sty':>8}{'shp wid':>8}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        line = f"{r['cell']:<14}{r['style']:<22}"
        for key in ("gcs", "size", "adjacency", "position", "shape"):
            for arm in ("off", "style_arm", "wide"):
                line += f"{_fmt(r[arm][key]):>8}"
        print(line)

    print()
    n_designs = {s: b["n_designs"] for s, b in load_priors()["by_style"].items()}
    for key in ("gcs", "size", "adjacency", "position", "shape"):
        deltas_style = [
            r["style_arm"][key] - r["off"][key]
            for r in rows
            if r["style_arm"][key] is not None and r["off"][key] is not None
        ]
        deltas_wide = [
            r["wide"][key] - r["off"][key]
            for r in rows
            if r["wide"][key] is not None and r["off"][key] is not None
        ]
        if deltas_style:
            print(
                f"{key:<10} style-vs-off  mean {sum(deltas_style) / len(deltas_style):+6.2f}"
                f"  min {min(deltas_style):+6.2f}  max {max(deltas_style):+6.2f}"
                f"  regressions {sum(1 for d in deltas_style if d < 0)}/{len(deltas_style)}"
            )
        if deltas_wide:
            print(
                f"{key:<10} wide-vs-off   mean {sum(deltas_wide) / len(deltas_wide):+6.2f}"
                f"  min {min(deltas_wide):+6.2f}  max {max(deltas_wide):+6.2f}"
                f"  regressions {sum(1 for d in deltas_wide if d < 0)}/{len(deltas_wide)}"
            )

    print()
    print("style-specific vs corpus-wide (both priors-on, scored on style cfg):")
    for key in ("gcs", "size", "adjacency", "position", "shape"):
        deltas = [
            r["style_arm"][key] - r["wide"][key]
            for r in rows
            if r["style_arm"][key] is not None and r["wide"][key] is not None
        ]
        if deltas:
            wins = sum(1 for d in deltas if d > 0.05)
            losses = sum(1 for d in deltas if d < -0.05)
            print(
                f"  {key:<10} mean {sum(deltas) / len(deltas):+6.2f}"
                f"  style wins {wins}  ties {len(deltas) - wins - losses}"
                f"  wide wins {losses}"
            )

    print()
    print("thin-data styles (n_designs < 10):")
    print(
        "  " + ", ".join(f"{s}(n={n})" for s, n in sorted(n_designs.items()) if n < 10)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--styles",
        nargs="*",
        default=None,
        help="style presets to sweep (default: every style in corpus_priors.json)",
    )
    parser.add_argument(
        "--json", type=Path, default=None, help="also write raw results as JSON here"
    )
    for name in ("size", "adjacency", "position"):
        parser.add_argument(
            f"--{name}-weight",
            type=int,
            default=None,
            help=f"override solver.{name.upper()}_PRIOR_WEIGHT for this sweep",
        )
    args = parser.parse_args()

    for name in ("size", "adjacency", "position"):
        override = getattr(args, f"{name}_weight")
        if override is not None:
            setattr(S, f"{name.upper()}_PRIOR_WEIGHT", override)
            print(f"override {name.upper()}_PRIOR_WEIGHT = {override}")

    styles = args.styles or sorted(load_priors()["by_style"])
    result = run_sweep(styles, CELLS)
    print()
    print_report(result)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n")
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
