"""FastAPI room operation endpoints — agent chat + edit-mode write-back.

State lives in the persisted layouts table (app/models/layout.py), NOT in
process memory: Cloud Run scales to zero and runs multiple instances, so any
in-memory layout state was lost on cold start and inconsistent across
instances. Every mutation writes back to the stored layout so the viewer,
share view and exports all see the same geometry.

The undo stack persists in the `undo_stacks` table (capped at 10 entries),
not process memory — Cloud Run scales to zero and runs multiple instances,
so an in-memory stack was lost on cold start and inconsistent across them.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import box
from shapely.ops import unary_union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.models.layout import StoredLayout
from app.models.project import Project
from app.models.undo import UndoStack
from app.services import layout_store
from app.services.access import get_accessible_project
from app.services.plans import get_effective_plan_tier, tier_at_least

router = APIRouter()

MAX_UNDO = 10


async def _push_undo(
    db: AsyncSession, project_id: str, user_id: str, state: dict
) -> None:
    row = await db.get(UndoStack, (project_id, user_id))
    if row is None:
        row = UndoStack(project_id=project_id, user_id=user_id, stack=[])
        db.add(row)
    stack = list(row.stack)
    stack.append(json.dumps(state))
    row.stack = stack[-MAX_UNDO:]
    flag_modified(row, "stack")
    await db.commit()


async def _pop_undo(db: AsyncSession, project_id: str, user_id: str) -> dict | None:
    row = await db.get(UndoStack, (project_id, user_id))
    if row is None or not row.stack:
        return None
    stack = list(row.stack)
    state = json.loads(stack.pop())
    row.stack = stack
    flag_modified(row, "stack")
    await db.commit()
    return state


# ── Auth helpers ──────────────────────────────────────────────────────────────


async def _get_plan_tier(user_id: str, db: AsyncSession) -> str:
    return await get_effective_plan_tier(user_id, db)


async def _get_project(project_id: str, user_id: str, db: AsyncSession) -> Project:
    return await get_accessible_project(project_id, user_id, db)


def _to_float(v: Any) -> float:
    return float(v) if isinstance(v, Decimal) else float(v) if v is not None else 0.0


# ── Geometry helpers ──────────────────────────────────────────────────────────
def _buildable_box(project: Project):
    """Canonical buildable polygon — honours plot shape (L-cutouts, quads,
    trapezoids) and per-edge setbacks; the old version was a plain rectangle
    with a hardcoded wall thickness."""
    from app.engine.compliance import load_rules
    from app.engine.geometry import buildable_polygon
    from app.services.plot_config import plot_config_from_project

    ewt = load_rules()["external_wall_thickness_mm"] / 1000
    return buildable_polygon(plot_config_from_project(project), wall_clearance=ewt)


def _check_placement(
    room_id: str,
    x: float,
    y: float,
    w: float,
    d: float,
    rooms: list[dict],
    project: Project,
) -> tuple[bool, str]:
    # Area-based checks with a 1 mm² epsilon — exact intersects/touches
    # predicates reject float noise (1.23 + 4.147 == 5.377000000000001, so
    # two rooms sharing an edge "overlap" by ~1e-15 m and fail spuriously).
    _EPS_AREA = 1e-6
    new_poly = box(x, y, x + w, y + d)
    buildable = _buildable_box(project)
    if new_poly.difference(buildable).area > _EPS_AREA:
        return False, "Extends outside buildable area (setback violation)"
    for r in rooms:
        if r["id"] == room_id:
            continue
        r_poly = box(r["x"], r["y"], r["x"] + r["width"], r["y"] + r["depth"])
        if new_poly.intersection(r_poly).area > _EPS_AREA:
            return False, f"Overlaps with {r['name']}"
    return True, ""


def _get_state_rooms(state: dict, floor: str) -> list[dict]:
    floor_map = {
        "gf": "ground_floor",
        "ff": "first_floor",
        "sf": "second_floor",
        "basement": "basement_floor",
    }
    fp_key = floor_map.get(floor, "ground_floor")
    fp = state.get(fp_key)
    if not fp:
        return []
    return fp.get("rooms", [])


def _find_room_and_floor(state: dict, room_id: str) -> tuple[dict | None, str | None]:
    for floor_key in ("ground_floor", "first_floor", "second_floor", "basement_floor"):
        fp = state.get(floor_key)
        if not fp:
            continue
        for room in fp.get("rooms", []):
            if room["id"] == room_id:
                return room, floor_key
    return None, None


# ── Pydantic request models ───────────────────────────────────────────────────
class MoveRequest(BaseModel):
    x: float
    y: float


class ResizeRequest(BaseModel):
    new_width: float | None = None
    new_depth: float | None = None
    anchor: str = "top-left"


class AddRoomRequest(BaseModel):
    floor: str = "gf"
    type: str
    name: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    depth: float | None = None


class SwapRequest(BaseModel):
    room_id_a: str
    room_id_b: str


class RoomEditItem(BaseModel):
    id: str
    type: str
    name: str
    x: float
    y: float
    width: float
    height: float  # frontend sends "height" = backend "depth"
    floor: str = "gf"


class ComplianceCheckRequest(BaseModel):
    rooms: list[RoomEditItem] = Field(max_length=200)


class LayoutRoomsUpdate(BaseModel):
    rooms: list[RoomEditItem] = Field(min_length=1, max_length=200)


# ── Helper: load persisted layout state ──────────────────────────────────────
async def _load_layout_state(
    project_id: str, user_id: str, db: AsyncSession
) -> tuple[Project, StoredLayout, dict]:
    """Load the first stored layout — read-only, never solves on a miss.

    Agent-chat edits operate on the first layout; mutations are written back
    to the layouts table via layout_store.save_edited_geometry. Solving here
    ran up to 3 CP-SAT solves (~15s) inside a single agent tool call which,
    stacked on a Cloud Run cold start (~23s measured), blew past the frontend
    fetch budget and surfaced as a "connection error". Generation is an
    explicit action (POST /projects/{id}/generate-jobs); a store miss returns
    409 so callers can prompt the user to generate first.
    """
    project = await _get_project(project_id, user_id, db)
    stored = await layout_store.get_stored_layouts(project.id, db)
    if not stored:
        raise HTTPException(
            status_code=409,
            detail={"code": "no_layouts", "help": "Generate layouts first"},
        )
    row = stored[0]
    return project, row, row.geometry


FLOOR_MAP_IN = {
    "gf": ("ground_floor", 0, "ground"),
    "ff": ("first_floor", 1, "first"),
    "sf": ("second_floor", 2, "second"),
    "basement": ("basement_floor", -1, "basement"),
}


def _compliance_for_rooms(project: Project, layout_id: str, rooms: list[RoomEditItem]):
    """Run the compliance engine over a flat edited-rooms list.

    Returns (result, room_issues) where room_issues maps room id -> issues.
    """
    from app.engine.compliance import check, load_rules
    from app.engine.models import (
        ComplianceResult,
        FloorPlan,
        Layout,
        Room,
    )
    from app.services.plot_config import plot_config_from_project

    floor_rooms: dict[str, list[Room]] = {
        "ground_floor": [],
        "first_floor": [],
        "second_floor": [],
        "basement_floor": [],
    }
    for item in rooms:
        fk, _fnum, _ftype = FLOOR_MAP_IN.get(item.floor, ("ground_floor", 0, "ground"))
        floor_rooms[fk].append(
            Room(
                id=item.id,
                name=item.name,
                type=item.type,  # type: ignore[arg-type]
                x=item.x,
                y=item.y,
                width=item.width,
                depth=item.height,  # frontend uses "height"
            )
        )

    def _make_floor(key: str, fnum: int, ftype: str) -> FloorPlan:
        return FloorPlan(floor=fnum, floor_type=ftype, rooms=floor_rooms[key])

    layout = Layout(
        id=layout_id,
        name="Edit Check",
        ground_floor=_make_floor("ground_floor", 0, "ground"),
        first_floor=_make_floor("first_floor", 1, "first"),
        second_floor=_make_floor("second_floor", 2, "second")
        if floor_rooms["second_floor"]
        else None,
        basement_floor=_make_floor("basement_floor", -1, "basement")
        if floor_rooms["basement_floor"]
        else None,
        compliance=ComplianceResult(passed=True),
    )
    cfg = plot_config_from_project(project)
    result = check(layout, cfg, load_rules())

    room_issues: dict[str, list[str]] = {}
    names = {item.id: item.name for item in rooms}
    for issue in result.violations + result.warnings:
        for rid, rname in names.items():
            if issue.startswith(rname + ":") or issue.startswith(rname + " "):
                room_issues.setdefault(rid, []).append(issue)
    return result, room_issues


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/rooms")
async def list_rooms(
    project_id: str,
    floor: str = "all",
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    _project, _row, state = await _load_layout_state(project_id, user_id, db)

    if floor == "all":
        rooms = []
        for fk in ("ground_floor", "first_floor", "second_floor", "basement_floor"):
            fp = state.get(fk)
            if fp:
                for r in fp.get("rooms", []):
                    rooms.append({**r, "floor": fk})
        return rooms

    return _get_state_rooms(state, floor)


# NOTE: must be registered BEFORE /rooms/{room_id} — otherwise FastAPI matches
# "layout-state" as a room_id and this endpoint is unreachable (pre-existing bug).
@router.get("/projects/{project_id}/rooms/layout-state")
async def get_layout_state(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the current persisted layout state as a LayoutData-compatible dict.

    Called by the refresh_layout agent tool so the frontend SVG can re-render
    after room modifications.
    """
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    _project, _row, state = await _load_layout_state(project_id, user_id, db)
    return {"layout": _state_to_layout_dict(state)}


@router.get("/projects/{project_id}/rooms/{room_id}")
async def get_room(
    project_id: str,
    room_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    _project, _row, state = await _load_layout_state(project_id, user_id, db)
    room, floor_key = _find_room_and_floor(state, room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    return {"room": room, "floor": floor_key}


@router.post("/projects/{project_id}/rooms/{room_id}/move")
async def move_room(
    project_id: str,
    room_id: str,
    body: MoveRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    project, row, state = await _load_layout_state(project_id, user_id, db)

    room, floor_key = _find_room_and_floor(state, room_id)
    if not room:
        raise HTTPException(404, "Room not found")

    all_rooms = state[floor_key]["rooms"]
    ok, err = _check_placement(
        room_id, body.x, body.y, room["width"], room["depth"], all_rooms, project
    )
    if not ok:
        return {"success": False, "error": err}

    await _push_undo(db, project_id, user_id, state)
    room["x"] = body.x
    room["y"] = body.y
    await layout_store.save_edited_geometry(row, state, db)
    return {"success": True, "room": room}


@router.post("/projects/{project_id}/rooms/{room_id}/resize")
async def resize_room(
    project_id: str,
    room_id: str,
    body: ResizeRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    project, row, state = await _load_layout_state(project_id, user_id, db)

    room, floor_key = _find_room_and_floor(state, room_id)
    if not room:
        raise HTTPException(404, "Room not found")

    new_w = body.new_width or room["width"]
    new_d = body.new_depth or room["depth"]
    all_rooms = state[floor_key]["rooms"]
    ok, err = _check_placement(
        room_id, room["x"], room["y"], new_w, new_d, all_rooms, project
    )
    if not ok:
        return {"success": False, "error": err, "adjusted": False}

    await _push_undo(db, project_id, user_id, state)
    room["width"] = new_w
    room["depth"] = new_d
    room["area"] = round(new_w * new_d, 2)
    await layout_store.save_edited_geometry(row, state, db)
    return {"success": True, "room": room, "adjusted": False}


@router.post("/projects/{project_id}/rooms/swap")
async def swap_rooms(
    project_id: str,
    body: SwapRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    _project, row, state = await _load_layout_state(project_id, user_id, db)

    room_a, fk_a = _find_room_and_floor(state, body.room_id_a)
    room_b, fk_b = _find_room_and_floor(state, body.room_id_b)
    if not room_a or not room_b:
        raise HTTPException(404, "One or both rooms not found")
    if fk_a != fk_b:
        return {"success": False, "error": "Rooms must be on the same floor to swap"}

    await _push_undo(db, project_id, user_id, state)
    ax, ay, aw, ad = room_a["x"], room_a["y"], room_a["width"], room_a["depth"]
    room_a["x"], room_a["y"], room_a["width"], room_a["depth"] = (
        room_b["x"],
        room_b["y"],
        room_b["width"],
        room_b["depth"],
    )
    room_a["area"] = round(room_b["width"] * room_b["depth"], 2)
    room_b["x"], room_b["y"], room_b["width"], room_b["depth"] = ax, ay, aw, ad
    room_b["area"] = round(aw * ad, 2)
    await layout_store.save_edited_geometry(row, state, db)
    return {"success": True, "rooms": [room_a, room_b]}


@router.post("/projects/{project_id}/rooms")
async def add_room(
    project_id: str,
    body: AddRoomRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    import pathlib
    import uuid as _uuid

    specs_path = (
        pathlib.Path(__file__).parent.parent.parent / "config" / "room_specs.json"
    )
    specs = json.loads(specs_path.read_text())
    spec = specs.get(body.type, specs.get("utility"))

    project, row, state = await _load_layout_state(project_id, user_id, db)

    floor_map = {
        "gf": "ground_floor",
        "ff": "first_floor",
        "sf": "second_floor",
        "basement": "basement_floor",
    }
    floor_key = floor_map.get(body.floor, "ground_floor")
    if floor_key not in state or state[floor_key] is None:
        return {
            "success": False,
            "error": f"Floor '{body.floor}' does not exist in this layout",
        }

    w = body.width or spec["min_width_m"] * 1.5
    d = body.depth or spec["min_width_m"] * 1.5
    x = body.x or 0.0
    y = body.y or 0.0

    all_rooms = state[floor_key]["rooms"]
    ok, err = _check_placement("__new__", x, y, w, d, all_rooms, project)
    if not ok:
        return {"success": False, "error": err}

    await _push_undo(db, project_id, user_id, state)
    new_room = {
        "id": f"custom_{_uuid.uuid4().hex[:8]}",
        "name": body.name or body.type.replace("_", " ").title(),
        "type": body.type,
        "x": x,
        "y": y,
        "width": w,
        "depth": d,
        "area": round(w * d, 2),
    }
    state[floor_key]["rooms"].append(new_room)
    await layout_store.save_edited_geometry(row, state, db)
    return {"success": True, "room": new_room}


@router.delete("/projects/{project_id}/rooms/{room_id}")
async def delete_room(
    project_id: str,
    room_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    _project, row, state = await _load_layout_state(project_id, user_id, db)
    room, floor_key = _find_room_and_floor(state, room_id)
    if not room:
        raise HTTPException(404, "Room not found")

    await _push_undo(db, project_id, user_id, state)
    state[floor_key]["rooms"] = [
        r for r in state[floor_key]["rooms"] if r["id"] != room_id
    ]
    await layout_store.save_edited_geometry(row, state, db)
    return {"success": True}


@router.get("/projects/{project_id}/available-space")
async def available_space(
    project_id: str,
    floor: str = "gf",
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    project, _row, state = await _load_layout_state(project_id, user_id, db)
    rooms = _get_state_rooms(state, floor)

    buildable = _buildable_box(project)
    if rooms:
        used = unary_union(
            [
                box(r["x"], r["y"], r["x"] + r["width"], r["y"] + r["depth"])
                for r in rooms
            ]
        )
        free = buildable.difference(used)
    else:
        free = buildable

    return {
        "sqm": round(free.area, 2),
        "buildable_sqm": round(buildable.area, 2),
        "bounds": free.bounds,
    }


@router.get("/projects/{project_id}/compliance")
async def check_compliance(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    project, _row, state = await _load_layout_state(project_id, user_id, db)

    from app.engine.compliance import check, load_rules
    from app.engine.models import (
        Column,
        ComplianceResult,
        FloorPlan,
        Layout,
        Room,
    )
    from app.services.plot_config import plot_config_from_project

    def _state_to_floor(
        state_dict: dict | None, floor_num: int, ftype: str
    ) -> FloorPlan | None:
        if not state_dict:
            return None
        return FloorPlan(
            floor=floor_num,
            floor_type=ftype,
            rooms=[
                Room(
                    id=r["id"],
                    name=r["name"],
                    type=r["type"],
                    x=r["x"],
                    y=r["y"],
                    width=r["width"],
                    depth=r["depth"],
                )
                for r in state_dict.get("rooms", [])
            ],
            columns=[Column(x=c["x"], y=c["y"]) for c in state_dict.get("columns", [])],
        )

    cfg = plot_config_from_project(project)
    layout = Layout(
        id="live",
        name="Live",
        ground_floor=_state_to_floor(state.get("ground_floor"), 0, "ground"),
        first_floor=_state_to_floor(state.get("first_floor"), 1, "first"),
        second_floor=_state_to_floor(state.get("second_floor"), 2, "second"),
        basement_floor=_state_to_floor(state.get("basement_floor"), -1, "basement"),
        compliance=ComplianceResult(passed=True),
    )
    rules = load_rules()
    result = check(layout, cfg, rules)
    return {
        "passed": result.passed,
        "violations": result.violations,
        "warnings": result.warnings,
    }


@router.post("/layouts/{layout_id}/compliance-check")
async def compliance_check_rooms(
    layout_id: str,
    body: ComplianceCheckRequest,
    x_project_id: str = Header(..., alias="X-Project-Id"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Live compliance check for edited rooms (stateless — no write).

    Accepts a flat list of rooms (all floors) from the frontend edit mode.
    Returns violations/warnings plus per-room issue mapping so the UI can
    highlight specific rooms in red.
    """
    project = await _get_project(x_project_id, user_id, db)
    result, room_issues = _compliance_for_rooms(project, layout_id, body.rooms)
    return {
        "passed": result.passed,
        "violations": result.violations,
        "warnings": result.warnings,
        "room_issues": room_issues,
    }


@router.patch("/projects/{project_id}/layouts/{layout_key}")
async def update_layout_rooms(
    project_id: str,
    layout_key: str,
    body: LayoutRoomsUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Persist edited room geometry (positions AND sizes) for one layout.

    This is the edit-mode/canvas write-back path: floors present in the
    payload replace that floor's rooms. Placement is validated server-side,
    compliance re-runs, and the stored layout is marked source='edited' so
    exports and the share view pick the edits up.
    """
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for layout editing")

    project = await _get_project(project_id, user_id, db)
    row = await layout_store.get_stored_layout(project_id, layout_key, db)
    if row is None:
        raise HTTPException(404, "Layout not found")

    # Group payload rooms per floor and validate placement within each floor
    per_floor: dict[str, list[RoomEditItem]] = {}
    for item in body.rooms:
        fk, _fnum, _ftype = FLOOR_MAP_IN.get(item.floor, ("ground_floor", 0, "ground"))
        per_floor.setdefault(fk, []).append(item)

    for _fk, items in per_floor.items():
        room_dicts = [
            {
                "id": it.id,
                "name": it.name,
                "x": it.x,
                "y": it.y,
                "width": it.width,
                "depth": it.height,
            }
            for it in items
        ]
        for it in items:
            ok, err = _check_placement(
                it.id, it.x, it.y, it.width, it.height, room_dicts, project
            )
            if not ok:
                raise HTTPException(400, f"{it.name}: {err}")

    result, room_issues = _compliance_for_rooms(project, layout_key, body.rooms)

    geometry = json.loads(json.dumps(row.geometry))  # deep copy
    for fk, items in per_floor.items():
        fp = geometry.get(fk)
        if not fp:
            raise HTTPException(400, f"Floor '{fk}' does not exist in this layout")
        fp["rooms"] = [
            {
                "id": it.id,
                "name": it.name,
                "type": it.type,
                "x": it.x,
                "y": it.y,
                "width": it.width,
                "depth": it.height,
                "area": round(it.width * it.height, 2),
            }
            for it in items
        ]
    geometry["compliance"] = {
        "passed": result.passed,
        "violations": result.violations,
        "warnings": result.warnings,
    }

    await layout_store.save_edited_geometry(row, geometry, db)

    return {
        "passed": result.passed,
        "violations": result.violations,
        "warnings": result.warnings,
        "room_issues": room_issues,
        "layout": geometry,
    }


@router.post("/projects/{project_id}/rooms/undo")
async def undo_last(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(403, "Pro plan required for agentic chat")

    _project, row, _state = await _load_layout_state(project_id, user_id, db)
    prev = await _pop_undo(db, project_id, user_id)
    if prev is None:
        return {"success": False, "error": "Nothing to undo"}
    await layout_store.save_edited_geometry(row, prev, db)
    return {"success": True, "layout": _state_to_layout_dict(prev)}


def _state_to_layout_dict(state: dict) -> dict:
    """Convert a stored geometry dict to a LayoutData-compatible dict."""

    def _ensure_floor(fp: dict | None) -> dict | None:
        if fp is None:
            return None
        return {
            **fp,
            "needs_mech_ventilation": fp.get("needs_mech_ventilation", False),
        }

    return {
        "id": state.get("id", "current"),
        "name": state.get("name", "Current Layout"),
        "compliance": state.get(
            "compliance", {"passed": True, "violations": [], "warnings": []}
        ),
        "ground_floor": _ensure_floor(state.get("ground_floor")),
        "first_floor": _ensure_floor(state.get("first_floor")),
        "second_floor": _ensure_floor(state.get("second_floor")),
        "basement_floor": _ensure_floor(state.get("basement_floor")),
        "score": state.get("score"),
        "space_notes": state.get("space_notes", []),
    }
