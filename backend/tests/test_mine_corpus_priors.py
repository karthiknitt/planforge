import json
from pathlib import Path

import pytest

from scripts.mine_corpus_priors import RoomRecord, load_extracts


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
