"""Mine docs/superpowers/specs/reverse_engr/*-ocr.json into corpus_priors.json.

Offline, deterministic, rerunnable. Never called at generation time -- see
docs/plans/2026-08-24-corpus-learned-generation-priors-design.md for why.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from app.engine.models import RoomType
from app.engine.room_labels import normalize_room_label
from app.engine.vastu import zone_for_point


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


AdjacencyKey = tuple[RoomType, RoomType]


def _bboxes_touch(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    tol: float,
) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    x_gap = max(ax0, bx0) - min(ax1, bx1)
    y_gap = max(ay0, by0) - min(ay1, by1)
    return x_gap <= tol and y_gap <= tol


def mine_adjacency_priors(
    records: list[RoomRecord], touch_tol: float = 0.02
) -> dict[str | None, dict[AdjacencyKey, float]]:
    """Frequency (0-1) that two RoomTypes' bboxes touch/overlap on the same floor.

    Adjacency is only meaningful within one floor of one design, so records are
    first grouped by (style, design, floor). Bbox-touching in normalized 0-1
    sheet coordinates is a PROXY for real adjacency, not ground truth -- OCR
    bbox imprecision and differing sheet layouts across designs mean touch_tol
    is a tunable, not a fact. This feeds a soft CP-SAT objective term later,
    never a hard constraint.

    Records whose bbox fails bbox_looks_normalized() are excluded entirely --
    ~14.66% of the corpus has pixel-space bboxes (see mine_size_priors' fix),
    and only 31% of those are caught by `flagged`, so this guard is required
    independently rather than inherited for free. A pixel-space bbox can never
    meaningfully "touch" a normalized one, and comparing two pixel-space
    bboxes against a normalized-unit tolerance is equally meaningless.

    Pairs are stored with the lexicographically smaller RoomType first, so
    (a, b) and (b, a) never both appear. Same-RoomType pairs (e.g. two
    bedrooms) are excluded -- adjacency priors are for distinct room types.
    """
    floors: dict[tuple[str, str, str], list[RoomRecord]] = {}
    for r in records:
        if r.flagged or r.room_type is None or not bbox_looks_normalized(r.bbox):
            continue
        floors.setdefault((r.style, r.design, r.floor), []).append(r)

    def _count(keys: list[tuple[str, str, str]]) -> dict[AdjacencyKey, float]:
        touches: dict[AdjacencyKey, int] = {}
        totals: dict[AdjacencyKey, int] = {}
        for fkey in keys:
            for a, b in combinations(floors[fkey], 2):
                if a.room_type == b.room_type:
                    continue
                assert a.room_type is not None
                assert b.room_type is not None
                pair: AdjacencyKey = (
                    (a.room_type, b.room_type)
                    if a.room_type < b.room_type
                    else (b.room_type, a.room_type)
                )
                totals[pair] = totals.get(pair, 0) + 1
                if _bboxes_touch(a.bbox, b.bbox, touch_tol):
                    touches[pair] = touches.get(pair, 0) + 1
        return {pair: touches.get(pair, 0) / n for pair, n in totals.items()}

    result: dict[str | None, dict[AdjacencyKey, float]] = {
        None: _count(list(floors.keys()))
    }
    for style in {k[0] for k in floors}:
        result[style] = _count([k for k in floors if k[0] == style])
    return result


def _centroid(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def mine_position_priors(
    records: list[RoomRecord],
) -> dict[str | None, dict[RoomType, dict[str, float]]]:
    """Per-style, per-RoomType histogram over Vastu zone labels.

    Reuses vastu.py's zone_for_point() rather than re-deriving zone math. Room
    bboxes are normalized [0,1] SHEET coordinates, not real plot dimensions, so
    this calls zone_for_point with plot_w=plot_l=1.0 and the raw centroid as
    x/y -- zone_for_point's own normalization (x/plot_w, y/plot_l) then
    correctly centers/buckets it. This treats the full sheet as the plot,
    ignoring the plot_bbox offset some extracts carry for where the plot sits
    within the sheet -- an accepted approximation for a soft statistical prior
    feeding a soft CP-SAT objective term later, not a compliance check.

    North angle: the OCR extracts carry a floor-level, qualitative
    north_arrow_direction ("up"/"down"/"left"/"right"), which RoomRecord does
    not currently expose (it is floor-level, not room-level, and threading it
    through would touch the schema 3 already-shipped tasks depend on). This
    treats "up" as north universally (north_angle_deg=0.0), matching the
    design doc's own suggested fallback when a per-design angle isn't
    reliably available. A future task could thread north_arrow_direction
    through RoomRecord/load_extracts for a more accurate per-design angle.
    """

    def _histograms(group: list[RoomRecord]) -> dict[RoomType, dict[str, float]]:
        counts: dict[RoomType, dict[str, int]] = {}
        for r in group:
            if r.flagged or r.room_type is None or not bbox_looks_normalized(r.bbox):
                continue
            cx, cy = _centroid(r.bbox)
            zone = zone_for_point(cx, cy, 1.0, 1.0, 0.0)
            counts.setdefault(r.room_type, {}).setdefault(zone, 0)
            counts[r.room_type][zone] += 1
        return {
            rt: {z: c / sum(zc.values()) for z, c in zc.items()}
            for rt, zc in counts.items()
        }

    result: dict[str | None, dict[RoomType, dict[str, float]]] = {
        None: _histograms(records)
    }
    for style in {r.style for r in records}:
        result[style] = _histograms([r for r in records if r.style == style])
    return result


@dataclass(frozen=True)
class ShapeUsageStat:
    p_nonrect: float
    n: int


def _bbox_contained(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
    min_fraction: float = 0.7,
) -> bool:
    ix0, iy0, ix1, iy1 = inner
    ox0, oy0, ox1, oy1 = outer
    cx0, cy0 = max(ix0, ox0), max(iy0, oy0)
    cx1, cy1 = min(ix1, ox1), min(iy1, oy1)
    if cx1 <= cx0 or cy1 <= cy0:
        return False
    inter_area = (cx1 - cx0) * (cy1 - cy0)
    inner_area = (ix1 - ix0) * (iy1 - iy0)
    return inner_area > 0 and inter_area / inner_area >= min_fraction


def mine_shape_usage_priors(
    records: list[RoomRecord],
) -> dict[str | None, dict[RoomType, ShapeUsageStat]]:
    """Confidence signal for how often a RoomType looks non-rectangular per style.

    Detected via bbox containment: another room on the same floor whose bbox
    is mostly (>=70% of its own area) contained inside this room's bbox --
    e.g. a toilet carved into a bedroom -- is a real, detectable
    non-rectangularity signal from 2D bbox data alone. This function does
    NOT attempt to infer a specific L/T/U template or ratio -- that needs
    the actual plan image, not the OCR bbox. It only produces a confidence
    signal (how often is this RoomType non-rectangular for this style),
    nothing more.

    Excludes flagged and non-bbox_looks_normalized records (same guard as
    size/adjacency/position mining) -- a pixel-space bbox could spuriously
    "contain" many small normalized ones, or vice versa.
    """
    floors: dict[tuple[str, str, str], list[RoomRecord]] = {}
    for r in records:
        if r.flagged or r.room_type is None or not bbox_looks_normalized(r.bbox):
            continue
        floors.setdefault((r.style, r.design, r.floor), []).append(r)

    def _stats(keys: list[tuple[str, str, str]]) -> dict[RoomType, ShapeUsageStat]:
        nonrect: dict[RoomType, int] = {}
        total: dict[RoomType, int] = {}
        for fkey in keys:
            rooms = floors[fkey]
            for r in rooms:
                assert r.room_type is not None
                total[r.room_type] = total.get(r.room_type, 0) + 1
                has_carved_neighbour = any(
                    other is not r and _bbox_contained(other.bbox, r.bbox)
                    for other in rooms
                )
                if has_carved_neighbour:
                    nonrect[r.room_type] = nonrect.get(r.room_type, 0) + 1
        return {
            rt: ShapeUsageStat(nonrect.get(rt, 0) / n, n) for rt, n in total.items()
        }

    result: dict[str | None, dict[RoomType, ShapeUsageStat]] = {
        None: _stats(list(floors.keys()))
    }
    for style in {k[0] for k in floors}:
        result[style] = _stats([k for k in floors if k[0] == style])
    return result
