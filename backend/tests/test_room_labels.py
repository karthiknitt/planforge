import pytest

from app.engine.room_labels import normalize_room_label


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("TERRACE", "terrace"),
        ("SEMI COVERED TERRACE", "terrace"),
        ("OUTDOOR GARDEN", "garden"),
        ("LANDSCAPED GARDEN", "garden"),
        ("OSARI", "verandah"),  # Kerala
        ("OTLA", "verandah"),  # Gujarati
        ("ATTOLE", "verandah"),  # Bengali
        ("CONVERSATION PIT", "seating"),
        ("OPEN SKYLIGHT", "open_to_sky"),
        ("WASH BASIN", "washbasin_nook"),
        ("SHAFT", "duct"),
        # aliases that must map to EXISTING types, not new ones
        ("C TOILET", "toilet"),
        ("ATTACH T", "toilet"),
        ("FORMAL LIVING ROOM", "living"),
        ("TV HALL", "living"),
        ("M.BED ROOM", "master_bedroom"),
        ("W.W.", "wardrobe"),
        ("MANDIR", "pooja"),
    ],
)
def test_label_normalisation(raw: str, expected: str) -> None:
    assert normalize_room_label(raw) == expected


def test_unknown_label_returns_none():
    assert normalize_room_label("ZORBLAX CHAMBER") is None


def test_normalisation_is_case_and_punctuation_insensitive():
    assert normalize_room_label("  m. bed-room 2 ") == "master_bedroom"
