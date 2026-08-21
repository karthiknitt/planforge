"""Regional style presets mined from the reverse-engineering corpus.

Provenance: prevalence for the eight styles tabulated in
docs/superpowers/specs/solver_capability_gaps.md section 6 is verified
verbatim; the remaining ten styles' rows and every ``study`` value are
corpus-review estimates carried as authored (re-deriving them needs a visual
pass over ~300 plan images). ``median_plot_sqft`` / ``typical_bhk`` are
recomputed from the corpus ``*-data.json`` metadata (median Plot Size, modal
Type); Sivavela-01 has no data.json — its values come from its OCR
(32'10" x 36'1" plot, two bedrooms).

IMPORTANT: these are soft defaults, not programme rules. The corpus shows the
18 styles differ far more in elevation than in floor-plan programme — courtyard
prevalence tops out at 33% and is 18% corpus-wide. Every flag therefore carries
its real percentage so the UI can say "typical (30%)" rather than implying a
Kerala plan always has a courtyard. See spec section 6.
"""

from dataclasses import dataclass, field

from app.schemas.project import ProgrammeFlag

PRE_TICK_THRESHOLD = 25  # a feature below this is a bad default


@dataclass(frozen=True)
class StylePreset:
    name: str
    median_plot_sqft: int
    typical_bhk: str
    prevalence: dict[ProgrammeFlag, int] = field(default_factory=dict)


def _p(
    court: int, vrnd: int, porch: int, terr: int, pooja: int, study: int
) -> dict[ProgrammeFlag, int]:
    return {
        "courtyard": court,
        "verandah": vrnd,
        "car_porch_open": porch,
        "terrace": terr,
        "pooja": pooja,
        "study": study,
    }


STYLE_PRESETS: dict[str, StylePreset] = {
    "Assamese": StylePreset("Assamese", 2000, "2 BHK", _p(9, 0, 45, 18, 0, 0)),
    "Bengali": StylePreset("Bengali", 2000, "4 BHK", _p(23, 23, 38, 30, 23, 15)),
    "Chettinad": StylePreset("Chettinad", 1390, "3 BHK", _p(18, 9, 36, 45, 18, 0)),
    "Colonial": StylePreset("Colonial", 2400, "3 BHK", _p(30, 0, 70, 30, 10, 10)),
    "Contemporary": StylePreset("Contemporary", 2102, "3 BHK", _p(16, 4, 45, 29, 8, 8)),
    "European-Cottage": StylePreset(
        "European-Cottage", 2000, "3 BHK", _p(16, 0, 50, 33, 0, 16)
    ),
    "Goan": StylePreset("Goan", 2385, "4 BHK", _p(33, 8, 58, 16, 16, 0)),
    "Gujrati": StylePreset("Gujrati", 2345, "3 BHK", _p(13, 6, 40, 26, 0, 0)),
    "Kerala": StylePreset("Kerala", 2091, "4 BHK", _p(30, 10, 50, 30, 10, 0)),
    "Maratha": StylePreset("Maratha", 1200, "3 BHK", _p(16, 0, 50, 33, 8, 8)),
    "Mediterranean-Spanish": StylePreset(
        "Mediterranean-Spanish", 2002, "3 BHK", _p(12, 12, 37, 25, 12, 0)
    ),
    "Minimalist": StylePreset("Minimalist", 1979, "3 BHK", _p(27, 11, 61, 16, 5, 0)),
    "Modern": StylePreset("Modern", 2322, "3 BHK", _p(15, 4, 50, 25, 5, 5)),
    "Mughal": StylePreset("Mughal", 1972, "3 BHK", _p(14, 0, 57, 21, 0, 0)),
    "Pahari": StylePreset("Pahari", 2000, "4 BHK", _p(12, 0, 68, 37, 6, 0)),
    "Rajasthani-Haveli": StylePreset(
        "Rajasthani-Haveli", 2220, "4 BHK", _p(14, 0, 50, 35, 0, 7)
    ),
    "Sivavela": StylePreset("Sivavela", 1185, "2 BHK", _p(0, 0, 50, 25, 0, 0)),
    "Tibetan-Buddhist": StylePreset(
        "Tibetan-Buddhist", 1200, "4 BHK", _p(8, 0, 66, 16, 8, 0)
    ),
}


def preset_programme(style: str) -> set[ProgrammeFlag]:
    """Programme flags to pre-tick for a style — only those the corpus shows in
    at least PRE_TICK_THRESHOLD% of that style's designs."""
    preset = STYLE_PRESETS.get(style)
    if preset is None:
        return set()
    return {
        flag for flag, pct in preset.prevalence.items() if pct >= PRE_TICK_THRESHOLD
    }
