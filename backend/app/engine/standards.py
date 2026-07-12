import json
import pathlib
from dataclasses import dataclass
from functools import lru_cache

_RULES_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "config" / "compliance_rules.json"
)


@dataclass(frozen=True)
class OpeningStandards:
    door_width_m: float = 0.9
    main_door_width_m: float = 1.07  # MD 3'6" leaf, NBC min clear 900 mm
    window_width_m: float = 1.2
    window_max_room_fraction: float = 0.6
    ventilator_width_m: float = 0.6


@lru_cache(maxsize=1)
def get_opening_standards() -> OpeningStandards:
    try:
        raw = json.loads(_RULES_PATH.read_text()).get("standard_openings", {})
    except (OSError, json.JSONDecodeError):
        raw = {}
    return OpeningStandards(
        door_width_m=raw.get("door_width_mm", 900) / 1000,
        main_door_width_m=raw.get("main_door_width_mm", 1070) / 1000,
        window_width_m=raw.get("window_width_mm", 1200) / 1000,
        window_max_room_fraction=raw.get("window_max_room_fraction", 0.6),
        ventilator_width_m=raw.get("ventilator_width_mm", 600) / 1000,
    )
