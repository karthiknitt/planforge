"""Read-only exposure of the corpus-derived style presets.

The wizard's "Site & Style" step (Task 24) renders its style picker and
programme-checkbox helper text from this payload; it never hard-codes style
data. See `app/engine/style_presets.py` for provenance of every number.
"""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from app.engine.style_presets import STYLE_PRESETS

router = APIRouter()


@router.get("/style-presets")
async def list_style_presets() -> dict[str, dict[str, Any]]:
    return {name: asdict(preset) for name, preset in STYLE_PRESETS.items()}
