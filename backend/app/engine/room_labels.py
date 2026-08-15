"""Map free-text plan labels onto PlanForge RoomTypes.

The reverse-engineering corpus (docs/superpowers/specs/reverse_engr/) yields
231 distinct labels across 18 regional styles for 32 RoomTypes. Regional
synonyms matter: a Kerala plan writes OSARI, a Gujarati plan OTLA, a Bengali
plan ATTOLE — all a verandah. Attached/common toilet prefixes (C/A/AT/ATTACH/
ATTACHED/COM/COMMON) are an *attribute*, not a type, so they all collapse to
`toilet` — both the abbreviated form ("C TOILET") and the full-word form
("ATTACHED TOILET", "ATTACHED BATH") are covered, since "attached toilet" is
the single most common real-world spelling of the concept.
"""

import re

from app.engine.models import RoomType

# Ordered: first match wins, so put narrow patterns before broad ones.
_RULES: list[tuple[str, RoomType]] = [
    (r"^(SEMI[ -]?(COVERED|OPEN)[ -]?|OPEN[ -]?)?TERRACE", "terrace"),
    (r"^(OUTDOOR |LANDSCAPED? )?(GARDEN|LAWN)", "garden"),
    (r"^(OSARI|OTLA|OTTA|ATTOLE|VERANDAH?|SIT ?OUT)", "verandah"),
    (r"^(OUTDOOR )?(SEATING|CONVERSATION PIT)", "seating"),
    (r"^OPEN ?(SKYLIGHT|TO SKY)|^SKYLIGHT", "open_to_sky"),
    (r"^WASH ?BASIN|^W ?B$", "washbasin_nook"),
    (r"^(DUCT|SHAFT)", "duct"),
    (r"^(M|MASTER)\.? ?BED ?ROOM|^M BED", "master_bedroom"),
    (r"^BED ?ROOM|^GUEST BED", "bedroom"),
    (r"^(C|A|AT|ATT|ATTACH(ED)?|COM(MON)?|G) ?(T(OIL(ET)?)?|BATH)$", "toilet"),
    (r"^TOIL|^BATH|^WASH ?ROOM|^W\.? ?C\b", "toilet"),
    (r"^POWDER", "wc_only"),
    (r"^(W\.? ?W|W\.? ?WARD|WALK|WARDROBE|DRESS|L ?CLOSET|W ?CLOSET)", "wardrobe"),
    (r"^(POOJA|PUJA|MANDIR|PRAYER)", "pooja"),
    (
        r"^(FORMAL |INFORMAL |DOUBLE HEIGHT )?LIVING|^FAMILY|^DRAWING|^TV HALL|^LOUNGE|^HALL",
        "living",
    ),
    (r"^DINING", "dining"),
    (r"^KITCHEN", "kitchen"),
    (r"^UTILITY|^LAUNDRY", "utility"),
    (r"^(CAR ?)?(PORCH|PARKING)|^PARKING", "parking_4w"),
    (r"^(FOYER|ENTRY|ENTRANCE|LOBBY|VESTIBULE)", "foyer"),
    (r"^(COURT|CHOWK|ANGAN|PATIO)", "courtyard"),
    (r"^BALCON", "balcony"),
    (r"^STORE", "store_room"),
    (r"^STAIR|^MUMTY", "staircase"),
    (r"^(STUDY|LIBRARY)", "study"),
    (r"^(PASSAGE|CORRIDOR|CIRCULATION)", "passage"),
    (r"^GARAGE", "garage"),
    (r"^(SERVANT|MAID)", "servant_quarter"),
    (r"^GYM", "gym"),
    (r"^(HOME )?OFFICE|^WORK", "home_office"),
]


def normalize_room_label(label: str) -> RoomType | None:
    """Return the RoomType for a free-text plan label, or None if unrecognised."""
    s = re.sub(r"[^A-Za-z ]", " ", label).upper()
    s = re.sub(r"\s+", " ", s).strip()
    for pattern, rtype in _RULES:
        if re.match(pattern, s):
            return rtype
    return None
