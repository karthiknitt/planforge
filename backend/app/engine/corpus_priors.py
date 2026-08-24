"""Typed accessors over backend/app/config/corpus_priors.json.

Generated offline by backend/scripts/mine_corpus_priors.py (run via
`uv run python -m scripts.mine_corpus_priors` from backend/ -- the bare
`python scripts/mine_corpus_priors.py` invocation fails on the app import).
Never mutated at runtime, never triggers a VLM/LLM call. See
docs/plans/2026-08-24-corpus-learned-generation-priors-design.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import PlotConfig, RoomType

_PRIORS_PATH = Path(__file__).parent.parent / "config" / "corpus_priors.json"


@dataclass(frozen=True)
class SizePrior:
    area_mean: float
    area_std: float
    aspect_mean: float
    aspect_std: float


def load_priors() -> dict:
    return json.loads(_PRIORS_PATH.read_text())


def _style_block(data: dict, style: str | None) -> dict | None:
    if style is None:
        return None
    return data["by_style"].get(style)


def get_size_prior(cfg: PlotConfig, room_type: RoomType) -> SizePrior | None:
    data = load_priors()
    block = _style_block(data, cfg.style_preset)
    entry = block["rooms"].get(room_type) if block is not None else None
    if entry is None:
        entry = data["corpus_wide"].get(room_type)
    if entry is None:
        return None
    return SizePrior(
        area_mean=entry["area"]["mean"],
        area_std=entry["area"]["std"],
        aspect_mean=entry["aspect"]["mean"],
        aspect_std=entry["aspect"]["std"],
    )


def get_adjacency_prior(cfg: PlotConfig, a: RoomType, b: RoomType) -> float:
    data = load_priors()
    key = "|".join(sorted((a, b)))
    block = _style_block(data, cfg.style_preset)
    if block is not None and key in block["adjacency"]:
        return block["adjacency"][key]
    return data["adjacency_corpus_wide"].get(key, 0.0)


def get_position_prior(cfg: PlotConfig, room_type: RoomType, zone: str) -> float:
    data = load_priors()
    block = _style_block(data, cfg.style_preset)
    if block is not None:
        hist = block["position"].get(room_type, {})
        if hist:
            return hist.get(zone, 0.0)
    return 0.0


def get_shape_usage_prior(cfg: PlotConfig, room_type: RoomType) -> float:
    data = load_priors()
    block = _style_block(data, cfg.style_preset)
    if block is not None:
        entry = block["shape_usage"].get(room_type)
        if entry is not None:
            return entry["p_nonrect"]
    return 0.0
