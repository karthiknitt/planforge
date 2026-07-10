"""Render bake-off: same layouts through every provider with a key set.

    cd backend && uv run python scripts/render_bakeoff.py [--providers gemini,openai,openrouter]

Reads keys from env (GEMINI_API_KEY / OPENAI_API_KEY / OPENROUTER_API_KEY).
Writes PNGs + bakeoff_results.json to ../experiments/renders/. Providers
without keys are skipped and reported — the script never fails on a missing
key. Total spend is a few test renders (~USD 0.5); the locked budget cap.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("INTERNAL_AUTH_SECRET", "test-secret-for-ci-0123456789abcdefgh")

from app.engine.generator import generate  # noqa: E402
from app.engine.models import PlotConfig  # noqa: E402
from app.engine.pdf import render_pdf  # noqa: E402
from app.engine.render_prompt import build_render_prompt  # noqa: E402
from app.quality.pdf_image import pdf_page_png  # noqa: E402
from app.services.layout_store import layout_out_from_engine  # noqa: E402
from app.services.render_providers import (  # noqa: E402
    RenderProviderError,
    render_image,
)

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "experiments" / "renders"

KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

CONFIGS = {
    "3bhk_rect": PlotConfig(
        plot_length=15.0,
        plot_width=9.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=3,
        toilets=2,
        parking=True,
        num_floors=2,
    ),
    "2bhk_compact": PlotConfig(
        plot_length=12.0,
        plot_width=8.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=2,
        toilets=1,
        parking=False,
        num_floors=2,
    ),
    "3bhk_lshape": PlotConfig(
        plot_length=16.0,
        plot_width=11.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=3,
        toilets=2,
        parking=True,
        num_floors=2,
        plot_shape="l_shaped",
        cutout_corner="NE",
        cutout_width=3.0,
        cutout_height=2.5,
    ),
}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", default="gemini,openai,openrouter")
    parser.add_argument(
        "--openrouter-models",
        default="",
        help="Comma list of OpenRouter model ids; each gets its own render "
        "per config (lets one OpenRouter key stand in for several vendors).",
    )
    args = parser.parse_args()
    wanted = [p.strip() for p in args.providers.split(",") if p.strip()]
    or_models = [m.strip() for m in args.openrouter_models.split(",") if m.strip()]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    runs: list[dict] = []
    skipped = [p for p in wanted if not os.environ.get(KEY_ENV.get(p, ""), "")]
    active = [p for p in wanted if p not in skipped]
    # (provider, model-or-None, output label)
    jobs: list[tuple[str, str | None, str]] = []
    for provider in active:
        if provider == "openrouter" and or_models:
            for m in or_models:
                jobs.append((provider, m, f"openrouter_{m.replace('/', '_')}"))
        else:
            jobs.append((provider, None, provider))
    print(
        f"providers: {active} (skipped, no key: {skipped}); jobs per config: "
        f"{[j[2] for j in jobs]}"
    )

    for cfg_name, cfg in CONFIGS.items():
        layouts = generate(cfg)
        if not layouts:
            runs.append({"config": cfg_name, "error": "no layouts generated"})
            continue
        layout = layouts[0]
        geometry = layout_out_from_engine(layout).model_dump()
        pdf_bytes = render_pdf(f"Bakeoff {cfg_name}", layout, cfg, cfg.num_bedrooms)
        reference_png = pdf_page_png(pdf_bytes, page_idx=0, scale=1.5)
        (OUT_DIR / f"{cfg_name}_reference.png").write_bytes(reference_png)
        prompt = build_render_prompt(
            geometry,
            plot_length_m=cfg.plot_length,
            plot_width_m=cfg.plot_width,
        )

        for provider, model, label in jobs:
            key = os.environ[KEY_ENV[provider]]
            try:
                result = await render_image(
                    prompt, reference_png, provider, api_key=key, model=model
                )
                out = OUT_DIR / f"{cfg_name}_{label}.png"
                out.write_bytes(result.image_png)
                runs.append(
                    {
                        "config": cfg_name,
                        "provider": provider,
                        "model": result.model,
                        "cost_usd": result.cost_usd,
                        "output": str(out),
                        "error": None,
                    }
                )
                print(f"OK   {cfg_name} x {label} -> {out.name}")
            except RenderProviderError as e:
                runs.append(
                    {
                        "config": cfg_name,
                        "provider": provider,
                        "model": model,
                        "cost_usd": None,
                        "output": None,
                        "error": str(e),
                    }
                )
                print(f"FAIL {cfg_name} x {label}: {e}")

    total_cost = sum(r["cost_usd"] or 0 for r in runs if r.get("cost_usd"))
    results = {
        "runs": runs,
        "skipped_providers": skipped,
        "est_total_cost_usd": total_cost,
    }
    (OUT_DIR / "bakeoff_results.json").write_text(json.dumps(results, indent=2))
    print(f"est total cost: ${total_cost:.2f} -> {OUT_DIR / 'bakeoff_results.json'}")


if __name__ == "__main__":
    asyncio.run(main())
