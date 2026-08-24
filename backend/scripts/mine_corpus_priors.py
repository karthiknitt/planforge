"""Mine docs/superpowers/specs/reverse_engr/*-ocr.json into corpus_priors.json.

Offline, deterministic, rerunnable. Never called at generation time -- see
docs/plans/2026-08-24-corpus-learned-generation-priors-design.md for why.
"""

from __future__ import annotations

import json
import statistics
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


SizePriorKey = tuple[str | None, RoomType]


@dataclass(frozen=True)
class SizeStat:
    area_mean: float
    area_std: float
    aspect_mean: float
    aspect_std: float
    n: int
    is_fallback: bool


def bbox_looks_normalized(
    bbox: tuple[float, float, float, float], tol: float = 0.02
) -> bool:
    """True iff every bbox coordinate falls within [-tol, 1.0 + tol].

    Some corpus OCR extractions emit whole designs in pixel space instead of
    the normalized 0-1 scale the rest of the pipeline assumes (e.g. an entire
    floor's bboxes as raw pixel coordinates). Only 31% of these are caught by
    the existing `flagged` field, so any bbox-derived statistic (aspect ratio
    here; later adjacency/position mining too) must apply this guard itself
    rather than trusting `flagged` alone.
    """
    return all(-tol <= c <= 1.0 + tol for c in bbox)


def _aspect_ratio(bbox: tuple[float, float, float, float]) -> float:
    """Orientation-invariant aspect ratio, always >= 1.0."""
    width = abs(bbox[2] - bbox[0])
    height = abs(bbox[3] - bbox[1])
    if width <= 0 or height <= 0:
        return 1.0
    ratio = width / height
    return ratio if ratio >= 1.0 else 1.0 / ratio


def _usable_records(records: list[RoomRecord]) -> list[RoomRecord]:
    return [
        r
        for r in records
        if not r.flagged and r.area_sqft is not None and r.room_type is not None
    ]


def _size_stat(records: list[RoomRecord], *, is_fallback: bool) -> SizeStat:
    areas = [r.area_sqft for r in records if r.area_sqft is not None]
    aspects = [_aspect_ratio(r.bbox) for r in records if bbox_looks_normalized(r.bbox)]
    aspect_mean = statistics.fmean(aspects) if aspects else 1.0
    aspect_std = statistics.pstdev(aspects) if len(aspects) > 1 else 0.0
    return SizeStat(
        area_mean=statistics.fmean(areas),
        area_std=statistics.pstdev(areas) if len(areas) > 1 else 0.0,
        aspect_mean=aspect_mean,
        aspect_std=aspect_std,
        n=len(records),
        is_fallback=is_fallback,
    )


def mine_size_priors(
    records: list[RoomRecord], min_style_samples: int = 5
) -> dict[SizePriorKey, SizeStat]:
    """Mean/std area + aspect ratio per (style, RoomType), with corpus-wide fallback.

    Excludes flagged records and any record missing area_sqft or room_type. A
    style/RoomType bucket with fewer than min_style_samples records falls back
    to the corpus-wide (None, RoomType) stat, keeping its own n for visibility.
    Records whose bbox is not on the normalized 0-1 scale (see
    bbox_looks_normalized) are excluded from the aspect stats only -- area is
    independent of bbox scale, so those records still count toward area_mean
    and area_std, and toward n.
    """
    usable = _usable_records(records)

    by_type: dict[RoomType, list[RoomRecord]] = {}
    by_style_type: dict[tuple[str, RoomType], list[RoomRecord]] = {}
    for r in usable:
        assert r.room_type is not None
        by_type.setdefault(r.room_type, []).append(r)
        by_style_type.setdefault((r.style, r.room_type), []).append(r)

    table: dict[SizePriorKey, SizeStat] = {}
    for room_type, type_records in by_type.items():
        table[(None, room_type)] = _size_stat(type_records, is_fallback=False)

    for (style, room_type), style_records in by_style_type.items():
        if len(style_records) >= min_style_samples:
            table[(style, room_type)] = _size_stat(style_records, is_fallback=False)
        else:
            fallback = table.get((None, room_type))
            if fallback is not None:
                table[(style, room_type)] = SizeStat(
                    area_mean=fallback.area_mean,
                    area_std=fallback.area_std,
                    aspect_mean=fallback.aspect_mean,
                    aspect_std=fallback.aspect_std,
                    n=len(style_records),
                    is_fallback=True,
                )

    return table
