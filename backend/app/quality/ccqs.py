"""CCQS — CAD Quality Composite Score, deterministic components only (0-80).

Extracted from experiments/eval.py. The 5th component (vision-judged visual
quality) intentionally stays a dev-time tool — the CI gate and the user-facing
badge use ONLY these 4 deterministic, API-free components (locked decision,
docs/plans/2026-07-03-fable-stage1-phase0-plan.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz  # pymupdf

_DIM_PATTERN = re.compile(r"\d+'-?\d+\"|\d+\.\d+\s*m")
_FTIN_PATTERN = re.compile(r"\d+'-\d+\"")

DETERMINISTIC_MAX = 80


@dataclass
class CcqsResult:
    total: float
    monochrome: float
    dimension_density: float
    ft_in_labels: float
    layout_completeness: float
    debug: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "max": DETERMINISTIC_MAX,
            "monochrome": self.monochrome,
            "dimension_density": self.dimension_density,
            "ft_in_labels": self.ft_in_labels,
            "layout_completeness": self.layout_completeness,
        }


def _open(pdf_bytes: bytes) -> fitz.Document:
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def compute_monochromaticity(pdf_bytes: bytes) -> float:
    """Render page 0, mean pixel saturation -> 0-20 (low saturation = good)."""
    doc = _open(pdf_bytes)
    try:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.0, 1.0), colorspace=fitz.csRGB)
    finally:
        doc.close()
    samples = pix.samples
    n_pixels = len(samples) // 3
    if n_pixels == 0:
        return 0.0
    total_sat = 0.0
    for i in range(n_pixels):
        r = samples[i * 3] / 255.0
        g = samples[i * 3 + 1] / 255.0
        b = samples[i * 3 + 2] / 255.0
        mx = max(r, g, b)
        total_sat += (mx - min(r, g, b)) / mx if mx > 0 else 0.0
    mean_sat = total_sat / n_pixels
    return round(20 * (1.0 - min(mean_sat, 1.0)), 2)


def compute_text_scores(pdf_bytes: bytes) -> tuple[float, float, float, dict]:
    """Extract all text -> (dim_density, ft_in, completeness, debug)."""
    doc = _open(pdf_bytes)
    try:
        all_text = "".join(pg.get_text() for pg in doc)
    finally:
        doc.close()

    dim_count = len(_DIM_PATTERN.findall(all_text))
    ftin_count = len(_FTIN_PATTERN.findall(all_text))
    dim_score = min(20.0, round(dim_count * 2.0, 2))
    ftin_score = min(20.0, round(ftin_count * 4.0, 2))

    text_upper = all_text.upper()
    both_floors = ("GROUND FLOOR" in text_upper or "G.F" in text_upper) and (
        "FIRST FLOOR" in text_upper or "F.F" in text_upper or "FF" in text_upper
    )
    has_sqft = "SQFT" in text_upper or "SQ.FT" in text_upper or "SQ FT" in text_upper
    has_schedule = (
        "SCHEDULE" in text_upper
        or "STATEMENT" in text_upper
        or ("ROOM" in text_upper and "AREA" in text_upper)
    )
    has_totals = "TOTAL" in text_upper and (
        "AREA" in text_upper or "SQFT" in text_upper or "SQ.FT" in text_upper
    )
    has_compass = "NORTH" in text_upper or " N " in all_text

    completeness = float(
        (4 if both_floors else 0)
        + (4 if has_sqft else 0)
        + (4 if has_schedule else 0)
        + (4 if has_totals else 0)
        + (4 if has_compass else 0)
    )

    debug = {
        "dim_count": dim_count,
        "ftin_count": ftin_count,
        "both_floors": both_floors,
        "has_sqft": has_sqft,
        "has_schedule": has_schedule,
        "has_totals": has_totals,
        "has_compass": has_compass,
    }
    return dim_score, ftin_score, completeness, debug


def compute_ccqs_deterministic(pdf_bytes: bytes) -> CcqsResult:
    mono = compute_monochromaticity(pdf_bytes)
    dim_score, ftin_score, completeness, debug = compute_text_scores(pdf_bytes)
    total = round(mono + dim_score + ftin_score + completeness, 2)
    return CcqsResult(
        total=total,
        monochrome=mono,
        dimension_density=dim_score,
        ft_in_labels=ftin_score,
        layout_completeness=completeness,
        debug=debug,
    )
