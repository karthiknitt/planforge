"""Mine docs/superpowers/specs/reverse_engr/*-ocr.json into corpus_priors.json.

Offline, deterministic, rerunnable. Never called at generation time -- see
docs/plans/2026-08-24-corpus-learned-generation-priors-design.md for why.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.engine.models import RoomType
from app.engine.room_labels import normalize_room_label


@dataclass(frozen=True)
class RoomRecord:
    style: str
    design: str
    floor: str
    label: str
    room_type: RoomType | None
    area_sqft: float | None
    bbox: tuple[float, float, float, float]
    flagged: bool


def load_extracts(corpus_root: Path) -> list[RoomRecord]:
    """Parse every *-ocr.json under corpus_root into RoomRecords.

    Style is inferred from the parent-of-parent directory name (e.g.
    corpus_root/Kerala/Kerala-03/kerala03-ocr.json -> style="Kerala"). Files
    directly under corpus_root with no style subdirectory (e.g. the
    standalone sivavela-01-ocr.json) are skipped -- they have no style bucket
    to mine into and the existing spec treats them as unclassified.
    """
    records: list[RoomRecord] = []
    for path in sorted(corpus_root.glob("*/*/*-ocr.json")):
        style = path.parent.parent.name
        data = json.loads(path.read_text())
        design = data.get("design", path.stem)
        for floor_name, floor in data.get("floors", {}).items():
            if not isinstance(floor, dict):
                continue
            rooms = floor.get("rooms", [])
            if not isinstance(rooms, list):
                continue
            for room in rooms:
                if not isinstance(room, dict):
                    continue
                label = room.get("label")
                bbox = room.get("bbox")
                if not label or not bbox or len(bbox) != 4:
                    continue
                records.append(
                    RoomRecord(
                        style=style,
                        design=design,
                        floor=floor_name,
                        label=label,
                        room_type=normalize_room_label(label),
                        area_sqft=room.get("area_sqft"),
                        bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
                        flagged=bool(room.get("flagged", False)),
                    )
                )
    return records
