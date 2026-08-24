import json
from pathlib import Path

import pytest

from scripts.mine_corpus_priors import (
    RoomRecord,
    bbox_looks_normalized,
    load_extracts,
    mine_adjacency_priors,
    mine_position_priors,
    mine_size_priors,
)


@pytest.fixture
def fixture_corpus(tmp_path: Path) -> Path:
    style_dir = tmp_path / "Kerala" / "Kerala-03"
    style_dir.mkdir(parents=True)
    (style_dir / "kerala03-ocr.json").write_text(
        json.dumps(
            {
                "design": "Kerala-03",
                "floors": {
                    "ground": {
                        "north_arrow_direction": "up",
                        "road_side": "bottom (south)",
                        "rooms": [
                            {
                                "label": "M BEDROOM",
                                "dims_raw": "14' 6\" x 11'9\"",
                                "area_sqft": 167.75,
                                "bbox": [0.22, 0.18, 0.38, 0.41],
                                "position_hint": "top-left",
                                "flagged": False,
                                "flag_reasons": [],
                            },
                            {
                                "label": "TOILET",
                                "dims_raw": "5' 3\" x 3'9\"",
                                "area_sqft": 18.38,
                                "bbox": [0.25, 0.18, 0.35, 0.27],
                                "position_hint": "inside M BEDROOM",
                                "flagged": True,
                                "flag_reasons": ["areal_scale_outlier"],
                            },
                            {
                                "label": "ZORBLAX",
                                "dims_raw": None,
                                "area_sqft": None,
                                "bbox": [0.0, 0.0, 0.1, 0.1],
                                "position_hint": "unknown",
                                "flagged": False,
                                "flag_reasons": [],
                            },
                        ],
                    }
                },
            }
        )
    )
    return tmp_path


def test_load_extracts_reads_every_room(fixture_corpus: Path) -> None:
    records = load_extracts(fixture_corpus)
    assert len(records) == 3


def test_load_extracts_infers_style_from_directory(fixture_corpus: Path) -> None:
    records = load_extracts(fixture_corpus)
    assert all(r.style == "Kerala" for r in records)


def test_load_extracts_normalises_room_type(fixture_corpus: Path) -> None:
    records = load_extracts(fixture_corpus)
    bedroom = next(r for r in records if r.label == "M BEDROOM")
    assert bedroom.room_type == "master_bedroom"


def test_load_extracts_preserves_flagged(fixture_corpus: Path) -> None:
    records = load_extracts(fixture_corpus)
    toilet = next(r for r in records if r.label == "TOILET")
    assert toilet.flagged is True


def test_load_extracts_unrecognised_label_gets_none_room_type(
    fixture_corpus: Path,
) -> None:
    records = load_extracts(fixture_corpus)
    unknown = next(r for r in records if r.label == "ZORBLAX")
    assert unknown.room_type is None


def test_load_extracts_skips_standalone_files_without_style_dir(
    fixture_corpus: Path,
) -> None:
    (fixture_corpus / "standalone-ocr.json").write_text(
        json.dumps({"design": "Standalone", "floors": {}})
    )
    records = load_extracts(fixture_corpus)
    assert len(records) == 3


def test_load_extracts_returns_room_record_instances(fixture_corpus: Path) -> None:
    records = load_extracts(fixture_corpus)
    assert all(isinstance(r, RoomRecord) for r in records)


def _write_malformed_corpus(tmp_path: Path, floors: dict) -> Path:
    style_dir = tmp_path / "Kerala" / "Kerala-99"
    style_dir.mkdir(parents=True)
    (style_dir / "kerala99-ocr.json").write_text(
        json.dumps({"design": "Kerala-99", "floors": floors})
    )
    return tmp_path


def test_load_extracts_skips_room_missing_label(tmp_path: Path) -> None:
    corpus = _write_malformed_corpus(
        tmp_path,
        {
            "ground": {
                "rooms": [
                    {
                        "dims_raw": None,
                        "area_sqft": None,
                        "bbox": [0.1, 0.1, 0.2, 0.2],
                        "flagged": False,
                    }
                ]
            }
        },
    )
    assert load_extracts(corpus) == []


def test_load_extracts_skips_room_with_malformed_bbox(tmp_path: Path) -> None:
    corpus = _write_malformed_corpus(
        tmp_path,
        {
            "ground": {
                "rooms": [
                    {"label": "KITCHEN", "bbox": [0.1, 0.2], "flagged": False},
                    {"label": "KITCHEN", "flagged": False},
                ]
            }
        },
    )
    assert load_extracts(corpus) == []


def test_load_extracts_skips_non_dict_floor(tmp_path: Path) -> None:
    corpus = _write_malformed_corpus(tmp_path, {"ground": None, "first": []})
    assert load_extracts(corpus) == []


def test_load_extracts_skips_non_dict_room_entry(tmp_path: Path) -> None:
    corpus = _write_malformed_corpus(
        tmp_path, {"ground": {"rooms": ["not a room", 42, None]}}
    )
    assert load_extracts(corpus) == []


def test_load_extracts_skips_non_list_rooms(tmp_path: Path) -> None:
    corpus = _write_malformed_corpus(
        tmp_path, {"ground": {"rooms": {"label": "KITCHEN"}}}
    )
    assert load_extracts(corpus) == []


def test_load_extracts_recovers_valid_rooms_alongside_malformed_ones(
    tmp_path: Path,
) -> None:
    corpus = _write_malformed_corpus(
        tmp_path,
        {
            "ground": None,
            "first": {
                "rooms": [
                    "not a room",
                    {"dims_raw": "5x5"},
                    {
                        "label": "KITCHEN",
                        "area_sqft": 100.0,
                        "bbox": [0.1, 0.1, 0.2, 0.2],
                        "flagged": False,
                    },
                ]
            },
            "second": {"rooms": {"not": "a list"}},
        },
    )
    records = load_extracts(corpus)
    assert len(records) == 1
    assert records[0].label == "KITCHEN"


def test_size_priors_excludes_flagged_rooms(fixture_corpus: Path) -> None:
    records = load_extracts(fixture_corpus)
    table = mine_size_priors(records, min_style_samples=1)
    # Only M BEDROOM is usable (TOILET flagged, ZORBLAX has no room_type/area).
    assert ("Kerala", "master_bedroom") in table
    assert table[("Kerala", "master_bedroom")].n == 1


def test_size_priors_falls_back_below_min_samples() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="KITCHEN",
            room_type="kitchen",
            area_sqft=100.0,
            bbox=(0.0, 0.0, 0.2, 0.1),
            flagged=False,
        ),
    ]
    table = mine_size_priors(records, min_style_samples=5)
    assert table[("Kerala", "kitchen")].is_fallback is True
    assert table[("Kerala", "kitchen")].area_mean == table[(None, "kitchen")].area_mean


def test_aspect_ratio_is_always_at_least_one() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="KITCHEN",
            room_type="kitchen",
            area_sqft=100.0,
            bbox=(0.0, 0.0, 0.1, 0.4),  # tall, narrow bbox
            flagged=False,
        ),
    ]
    table = mine_size_priors(records, min_style_samples=1)
    assert table[("Kerala", "kitchen")].aspect_mean >= 1.0


def test_size_priors_empty_records_returns_empty_table() -> None:
    assert mine_size_priors([], min_style_samples=1) == {}


def test_size_priors_zero_width_bbox_defaults_to_unit_aspect() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="KITCHEN",
            room_type="kitchen",
            area_sqft=100.0,
            bbox=(0.1, 0.1, 0.1, 0.4),  # zero width
            flagged=False,
        ),
    ]
    table = mine_size_priors(records, min_style_samples=1)
    assert table[("Kerala", "kitchen")].aspect_mean == 1.0


def test_bbox_looks_normalized_accepts_0_to_1_range() -> None:
    assert bbox_looks_normalized((0.0, 0.1, 0.9, 1.0)) is True


def test_bbox_looks_normalized_rejects_pixel_space() -> None:
    assert bbox_looks_normalized((0.39, 150, 0.58, 370)) is False


def test_pixel_space_bbox_excluded_from_aspect_but_kept_for_area() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="KITCHEN",
            room_type="kitchen",
            area_sqft=100.0,
            bbox=(0.2, 0.2, 0.4, 0.3),  # normalized, aspect 2.0
            flagged=False,
        ),
        RoomRecord(
            style="Kerala",
            design="d2",
            floor="ground",
            label="KITCHEN",
            room_type="kitchen",
            area_sqft=200.0,
            bbox=(0.39, 150, 0.58, 370),  # pixel-space, must not pollute aspect
            flagged=False,
        ),
    ]
    table = mine_size_priors(records, min_style_samples=1)
    stat = table[("Kerala", "kitchen")]
    # area stats: both records count.
    assert stat.n == 2
    assert stat.area_mean == 150.0
    # aspect stats: only the normalized-bbox record counts.
    assert stat.aspect_mean == pytest.approx(2.0)


def test_adjacency_detects_touching_bboxes() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="KITCHEN",
            room_type="kitchen",
            area_sqft=100.0,
            bbox=(0.0, 0.0, 0.2, 0.2),
            flagged=False,
        ),
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="DINING",
            room_type="dining",
            area_sqft=100.0,
            bbox=(0.2, 0.0, 0.4, 0.2),  # shares the x=0.2 edge
            flagged=False,
        ),
    ]
    table = mine_adjacency_priors(records)
    key = tuple(sorted(("kitchen", "dining")))
    assert table["Kerala"][key] == 1.0


def test_adjacency_zero_for_non_touching_rooms() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="KITCHEN",
            room_type="kitchen",
            area_sqft=100.0,
            bbox=(0.0, 0.0, 0.1, 0.1),
            flagged=False,
        ),
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="BEDROOM",
            room_type="bedroom",
            area_sqft=100.0,
            bbox=(0.5, 0.5, 0.6, 0.6),
            flagged=False,
        ),
    ]
    table = mine_adjacency_priors(records)
    key = tuple(sorted(("kitchen", "bedroom")))
    assert table["Kerala"].get(key, 0.0) == 0.0


def test_adjacency_excludes_pixel_space_bboxes() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="KITCHEN",
            room_type="kitchen",
            area_sqft=100.0,
            bbox=(0.39, 150, 0.58, 370),  # pixel-space
            flagged=False,
        ),
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="DINING",
            room_type="dining",
            area_sqft=100.0,
            bbox=(0.39, 150, 0.78, 370),  # would "touch" the above naively
            flagged=False,
        ),
    ]
    table = mine_adjacency_priors(records)
    key = tuple(sorted(("kitchen", "dining")))
    assert key not in table.get("Kerala", {})
    assert key not in table.get(None, {})


def test_adjacency_single_room_floor_has_no_pairs() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="KITCHEN",
            room_type="kitchen",
            area_sqft=100.0,
            bbox=(0.0, 0.0, 0.2, 0.2),
            flagged=False,
        ),
    ]
    table = mine_adjacency_priors(records)
    assert table["Kerala"] == {}


def test_adjacency_excludes_same_room_type_pairs() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="BEDROOM",
            room_type="bedroom",
            area_sqft=100.0,
            bbox=(0.0, 0.0, 0.2, 0.2),
            flagged=False,
        ),
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="BEDROOM 2",
            room_type="bedroom",
            area_sqft=100.0,
            bbox=(0.2, 0.0, 0.4, 0.2),
            flagged=False,
        ),
    ]
    table = mine_adjacency_priors(records)
    assert table["Kerala"] == {}


_VASTU_ZONE_LABELS = {"N", "NE", "E", "SE", "S", "SW", "W", "NW", "C"}


def test_position_priors_bucket_by_existing_vastu_zones() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="M BEDROOM",
            room_type="master_bedroom",
            area_sqft=100.0,
            bbox=(0.1, 0.1, 0.2, 0.2),
            flagged=False,
        ),
    ]
    table = mine_position_priors(records)
    zones = table["Kerala"]["master_bedroom"]
    assert set(zones) <= _VASTU_ZONE_LABELS
    assert sum(zones.values()) == pytest.approx(1.0)


def test_position_priors_excludes_flagged_and_pixel_space_records() -> None:
    records = [
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="TOILET",
            room_type="toilet",
            area_sqft=20.0,
            bbox=(0.1, 0.1, 0.2, 0.2),
            flagged=True,
        ),
        RoomRecord(
            style="Kerala",
            design="d1",
            floor="ground",
            label="KITCHEN",
            room_type="kitchen",
            area_sqft=100.0,
            bbox=(0.39, 150, 0.58, 370),  # pixel-space
            flagged=False,
        ),
    ]
    table = mine_position_priors(records)
    assert "toilet" not in table["Kerala"]
    assert "kitchen" not in table["Kerala"]
    assert table[None] == {}
