"""Frozen golden fixture accessors (never re-solves; CP-SAT is not deterministic)."""

import json
from pathlib import Path

from app.engine.models import Layout, PlotConfig
from app.services.layout_store import engine_layout_from_geometry

_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "ccqs_fixture.json"
)


def _fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text())


def golden_config() -> PlotConfig:
    return PlotConfig(**_fixture()["cfg"])


def golden_layout() -> Layout:
    return engine_layout_from_geometry(_fixture()["geometry"])
