"""Rooms-only geometry hash + startup re-hash migration.

The approval geometry_hash must be scoped to room geometry only (id, type,
x, y, width, depth) — never derived fields like compliance/score/space_notes
or columns (columns are derived from rooms; including them re-breaks
approvals whenever column derivation changes, as happened in PR #30).
"""

from app.models.structural import ArchitecturalRevision
from app.services import structural_store

GEO_BASE = {
    "id": "A",
    "name": "Layout A",
    "compliance": {"passed": True, "violations": [], "warnings": []},
    "score": {"total": 82.5},
    "space_notes": ["auto-added utility"],
    "ground_floor": {
        "floor": 0,
        "rooms": [
            {
                "id": "r1",
                "name": "Living",
                "type": "living",
                "x": 0.0,
                "y": 0.0,
                "width": 4.0,
                "depth": 3.5,
                "area": 14.0,
            },
            {
                "id": "r2",
                "name": "Kitchen",
                "type": "kitchen",
                "x": 4.0,
                "y": 0.0,
                "width": 3.0,
                "depth": 3.5,
                "area": 10.5,
            },
        ],
        "columns": [{"x": 0.0, "y": 0.0}, {"x": 4.0, "y": 0.0}],
    },
    "first_floor": {
        "floor": 1,
        "rooms": [
            {
                "id": "r3",
                "name": "Bedroom",
                "type": "bedroom",
                "x": 0.0,
                "y": 0.0,
                "width": 4.0,
                "depth": 3.5,
                "area": 14.0,
            }
        ],
        "columns": [{"x": 0.0, "y": 0.0}],
    },
}


def test_derived_field_drift_does_not_change_hash():
    """Regression: scorer float drift / compliance re-run / column
    re-derivation must NOT flip the hash when rooms are unchanged."""
    drifted = {
        **GEO_BASE,
        "score": {"total": 79.999999},
        "compliance": {"passed": False, "violations": ["x"], "warnings": []},
        "space_notes": [],
        "ground_floor": {
            **GEO_BASE["ground_floor"],
            "columns": [{"x": 0.0, "y": 0.0}],  # columns changed / dropped
        },
        "first_floor": {
            **GEO_BASE["first_floor"],
            "columns": [],
        },
    }
    assert structural_store.geometry_hash(GEO_BASE) == structural_store.geometry_hash(
        drifted
    )


def test_room_field_change_changes_hash():
    moved = {
        **GEO_BASE,
        "ground_floor": {
            **GEO_BASE["ground_floor"],
            "rooms": [
                {**GEO_BASE["ground_floor"]["rooms"][0], "x": 0.5},
                GEO_BASE["ground_floor"]["rooms"][1],
            ],
        },
    }
    assert structural_store.geometry_hash(GEO_BASE) != structural_store.geometry_hash(
        moved
    )


def test_room_type_change_changes_hash():
    retyped = {
        **GEO_BASE,
        "ground_floor": {
            **GEO_BASE["ground_floor"],
            "rooms": [
                {**GEO_BASE["ground_floor"]["rooms"][0], "type": "dining"},
                GEO_BASE["ground_floor"]["rooms"][1],
            ],
        },
    }
    assert structural_store.geometry_hash(GEO_BASE) != structural_store.geometry_hash(
        retyped
    )


def test_room_width_change_changes_hash():
    resized = {
        **GEO_BASE,
        "ground_floor": {
            **GEO_BASE["ground_floor"],
            "rooms": [
                {**GEO_BASE["ground_floor"]["rooms"][0], "width": 5.0},
                GEO_BASE["ground_floor"]["rooms"][1],
            ],
        },
    }
    assert structural_store.geometry_hash(GEO_BASE) != structural_store.geometry_hash(
        resized
    )


def test_room_order_shuffle_is_canonicalized():
    shuffled = {
        **GEO_BASE,
        "ground_floor": {
            **GEO_BASE["ground_floor"],
            "rooms": list(reversed(GEO_BASE["ground_floor"]["rooms"])),
        },
    }
    assert structural_store.geometry_hash(GEO_BASE) == structural_store.geometry_hash(
        shuffled
    )


def test_missing_floor_keys_handled_gracefully():
    """Geometry with no floor keys present hashes deterministically without
    raising (defensive — malformed/partial data)."""
    h1 = structural_store.geometry_hash({"id": "x"})
    h2 = structural_store.geometry_hash({"id": "x", "unrelated": 1})
    assert h1 == h2


async def test_startup_migration_rehashes_old_rows(client_db):
    """A revision persisted with the OLD whole-dict hash gets corrected by
    the startup migration, and afterwards find_revision_for_hash matches it
    for the same geometry via the new rooms-only hash."""
    import hashlib
    import json

    client, SessionLocal = client_db

    old_style_hash = hashlib.sha256(
        json.dumps(GEO_BASE, sort_keys=True).encode()
    ).hexdigest()
    new_hash = structural_store.geometry_hash(GEO_BASE)
    assert old_style_hash != new_hash  # sanity: the bug is real

    async with SessionLocal() as s:
        rev = ArchitecturalRevision(
            project_id="proj-1",
            layout_key="A",
            geometry=GEO_BASE,
            geometry_hash=old_style_hash,
            approved_by="u1",
        )
        s.add(rev)
        await s.commit()
        rev_id = rev.id

    async with SessionLocal() as s:
        updated = await structural_store.rehash_architectural_revisions(s)
        assert updated == 1

    async with SessionLocal() as s:
        rev = await s.get(ArchitecturalRevision, rev_id)
        assert rev.geometry_hash == new_hash

        found = await structural_store.find_revision_for_hash(
            "proj-1", "A", new_hash, s
        )
        assert found is not None
        assert found.id == rev_id

    # idempotent: second run touches nothing
    async with SessionLocal() as s:
        updated_again = await structural_store.rehash_architectural_revisions(s)
        assert updated_again == 0


async def test_startup_migration_handles_empty_geometry(client_db):
    """Empty/malformed geometry: the migration recomputes without raising
    (an empty geometry canonicalizes to a stable hash, so a row seeded with
    a mismatched hash still gets corrected)."""
    client, SessionLocal = client_db

    async with SessionLocal() as s:
        rev = ArchitecturalRevision(
            project_id="proj-2",
            layout_key="A",
            geometry={},
            geometry_hash="deadbeef",
            approved_by="u1",
        )
        s.add(rev)
        await s.commit()
        rev_id = rev.id

    async with SessionLocal() as s:
        updated = await structural_store.rehash_architectural_revisions(s)
        assert updated == 1

    async with SessionLocal() as s:
        rev = await s.get(ArchitecturalRevision, rev_id)
        assert rev.geometry_hash == structural_store.geometry_hash({})
