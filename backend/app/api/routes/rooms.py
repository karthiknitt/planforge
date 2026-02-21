"""FastAPI room operation endpoints — used by the agentic chat interface.

Each endpoint validates geometry using Shapely, applies the change to the
in-memory layout state, and maintains a per-session undo stack.

Undo stack lives in module-level memory: {"{project_id}:{user_id}": deque[state]}.
Capped at 10 entries. TTL cleanup not yet implemented (Phase D MVP).
"""

from __future__ import annotations

import json
from collections import deque
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from shapely.geometry import box
from shapely.ops import unary_union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.project import Project
from app.models.user import User

router = APIRouter()

# ── In-memory room state + undo stack ────────────────────────────────────────
# Key: "{project_id}:{user_id}" → deque of serialised layout snapshots
_undo_stacks: dict[str, deque[str]] = {}
_layout_state: dict[str, dict] = {}   # live layout per session key
MAX_UNDO = 10


def _session_key(project_id: str, user_id: str) -> str:
    return f"{project_id}:{user_id}"


def _push_undo(key: str, state: dict) -> None:
    if key not in _undo_stacks:
        _undo_stacks[key] = deque(maxlen=MAX_UNDO)
    _undo_stacks[key].append(json.dumps(state))


def _pop_undo(key: str) -> dict | None:
    stack = _undo_stacks.get(key)
    if not stack:
        return None
    return json.loads(stack.pop())


# ── Auth helpers ──────────────────────────────────────────────────────────────
def _user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    return x_user_id


async def _get_plan_tier(user_id: str, db: AsyncSession) -> str:
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    return u.plan_tier if u else "free"


async def _get_project(project_id: str, user_id: str, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _to_float(v: Any) -> float:
    return float(v) if isinstance(v, Decimal) else float(v) if v is not None else 0.0


# ── Geometry helpers ──────────────────────────────────────────────────────────
def _buildable_box(project: Project):
    ewt = 0.23
    sx = _to_float(project.setback_left) + ewt
    sy = _to_float(project.setback_front) + ewt
    ex = _to_float(project.plot_width) - _to_float(project.setback_right) - ewt
    ey = _to_float(project.plot_length) - _to_float(project.setback_rear) - ewt
    return box(sx, sy, ex, ey)


def _check_placement(
    room_id: str, x: float, y: float, w: float, d: float,
    rooms: list[dict], project: Project
) -> tuple[bool, str]:
    new_poly = box(x, y, x + w, y + d)
    buildable = _buildable_box(project)
    if not buildable.contains(new_poly):
        return False, "Extends outside buildable area (setback violation)"
    for r in rooms:
        if r["id"] == room_id:
            continue
        r_poly = box(r["x"], r["y"], r["x"] + r["width"], r["y"] + r["depth"])
        if new_poly.intersects(r_poly) and not new_poly.touches(r_poly):
            return False, f"Overlaps with {r['name']}"
    return True, ""


def _get_state_rooms(state: dict, floor: str) -> list[dict]:
    floor_map = {"gf": "ground_floor", "ff": "first_floor", "sf": "second_floor", "basement": "basement_floor"}
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


# ── Helper: load/init state ───────────────────────────────────────────────────
async def _get_or_init_state(project_id: str, user_id: str, db: AsyncSession) -> dict:
    key = _session_key(project_id, user_id)
    if key not in _layout_state:
        # Generate fresh and cache first layout
        project = await _get_project(project_id, user_id, db)
        from decimal import Decimal
        from app.engine.generator import generate
        from app.engine.models import PlotConfig
        cfg = PlotConfig(
            plot_length=_to_float(project.plot_length),
            plot_width=_to_float(project.plot_width),
            setback_front=_to_float(project.setback_front),
            setback_rear=_to_float(project.setback_rear),
            setback_left=_to_float(project.setback_left),
            setback_right=_to_float(project.setback_right),
            num_bedrooms=project.num_bedrooms,
            toilets=project.toilets,
            parking=project.parking,
            city=getattr(project, "city", "other") or "other",
            vastu_enabled=getattr(project, "vastu_enabled", False) or False,
            road_width_m=_to_float(getattr(project, "road_width_m", 9.0) or 9.0),
            road_side=getattr(project, "road_side", "S") or "S",
        )
        layouts = generate(cfg)
        if not layouts:
            raise HTTPException(status_code=422, detail="No compliant layouts could be generated")
        layout = layouts[0]

        def _fp_to_dict(fp) -> dict:
            return {
                "floor": fp.floor,
                "floor_type": getattr(fp, "floor_type", "ground"),
                "rooms": [
                    {"id": r.id, "name": r.name, "type": r.type,
                     "x": r.x, "y": r.y, "width": r.width, "depth": r.depth, "area": r.area}
                    for r in fp.rooms
                ],
                "columns": [{"x": c.x, "y": c.y} for c in fp.columns],
            }

        _layout_state[key] = {
            "ground_floor": _fp_to_dict(layout.ground_floor),
            "first_floor": _fp_to_dict(layout.first_floor),
            "second_floor": _fp_to_dict(layout.second_floor) if layout.second_floor else None,
            "basement_floor": _fp_to_dict(layout.basement_floor) if layout.basement_floor else None,
        }
    return _layout_state[key]


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/rooms")
async def list_rooms(
    project_id: str,
    floor: str = "all",
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if tier != "pro":
        raise HTTPException(403, "Pro plan required for agentic chat")

    state = await _get_or_init_state(project_id, user_id, db)

    if floor == "all":
        rooms = []
        for fk in ("ground_floor", "first_floor", "second_floor", "basement_floor"):
            fp = state.get(fk)
            if fp:
                for r in fp.get("rooms", []):
                    rooms.append({**r, "floor": fk})
        return rooms

    return _get_state_rooms(state, floor)


@router.get("/projects/{project_id}/rooms/{room_id}")
async def get_room(
    project_id: str, room_id: str,
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if tier != "pro":
        raise HTTPException(403, "Pro plan required for agentic chat")

    state = await _get_or_init_state(project_id, user_id, db)
    room, floor_key = _find_room_and_floor(state, room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    return {"room": room, "floor": floor_key}


@router.post("/projects/{project_id}/rooms/{room_id}/move")
async def move_room(
    project_id: str, room_id: str, body: MoveRequest,
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if tier != "pro":
        raise HTTPException(403, "Pro plan required for agentic chat")

    project = await _get_project(project_id, user_id, db)
    state = await _get_or_init_state(project_id, user_id, db)
    key = _session_key(project_id, user_id)

    room, floor_key = _find_room_and_floor(state, room_id)
    if not room:
        raise HTTPException(404, "Room not found")

    all_rooms = state[floor_key]["rooms"]
    ok, err = _check_placement(room_id, body.x, body.y, room["width"], room["depth"], all_rooms, project)
    if not ok:
        return {"success": False, "error": err}

    _push_undo(key, json.loads(json.dumps(state)))
    room["x"] = body.x
    room["y"] = body.y
    return {"success": True, "room": room}


@router.post("/projects/{project_id}/rooms/{room_id}/resize")
async def resize_room(
    project_id: str, room_id: str, body: ResizeRequest,
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if tier != "pro":
        raise HTTPException(403, "Pro plan required for agentic chat")

    project = await _get_project(project_id, user_id, db)
    state = await _get_or_init_state(project_id, user_id, db)
    key = _session_key(project_id, user_id)

    room, floor_key = _find_room_and_floor(state, room_id)
    if not room:
        raise HTTPException(404, "Room not found")

    new_w = body.new_width or room["width"]
    new_d = body.new_depth or room["depth"]
    all_rooms = state[floor_key]["rooms"]
    ok, err = _check_placement(room_id, room["x"], room["y"], new_w, new_d, all_rooms, project)
    if not ok:
        return {"success": False, "error": err, "adjusted": False}

    _push_undo(key, json.loads(json.dumps(state)))
    room["width"] = new_w
    room["depth"] = new_d
    room["area"] = round(new_w * new_d, 2)
    return {"success": True, "room": room, "adjusted": False}


@router.post("/projects/{project_id}/rooms/swap")
async def swap_rooms(
    project_id: str, body: SwapRequest,
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if tier != "pro":
        raise HTTPException(403, "Pro plan required for agentic chat")

    state = await _get_or_init_state(project_id, user_id, db)
    key = _session_key(project_id, user_id)

    room_a, fk_a = _find_room_and_floor(state, body.room_id_a)
    room_b, fk_b = _find_room_and_floor(state, body.room_id_b)
    if not room_a or not room_b:
        raise HTTPException(404, "One or both rooms not found")
    if fk_a != fk_b:
        return {"success": False, "error": "Rooms must be on the same floor to swap"}

    _push_undo(key, json.loads(json.dumps(state)))
    ax, ay, aw, ad = room_a["x"], room_a["y"], room_a["width"], room_a["depth"]
    room_a["x"], room_a["y"], room_a["width"], room_a["depth"] = room_b["x"], room_b["y"], room_b["width"], room_b["depth"]
    room_a["area"] = round(room_b["width"] * room_b["depth"], 2)
    room_b["x"], room_b["y"], room_b["width"], room_b["depth"] = ax, ay, aw, ad
    room_b["area"] = round(aw * ad, 2)
    return {"success": True, "rooms": [room_a, room_b]}


@router.post("/projects/{project_id}/rooms")
async def add_room(
    project_id: str, body: AddRoomRequest,
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if tier != "pro":
        raise HTTPException(403, "Pro plan required for agentic chat")

    import json, uuid as _uuid
    from app.config import room_specs_path
    import pathlib

    specs_path = pathlib.Path(__file__).parent.parent.parent / "config" / "room_specs.json"
    specs = json.loads(specs_path.read_text())
    spec = specs.get(body.type, specs.get("utility"))

    project = await _get_project(project_id, user_id, db)
    state = await _get_or_init_state(project_id, user_id, db)
    key = _session_key(project_id, user_id)

    floor_map = {"gf": "ground_floor", "ff": "first_floor", "sf": "second_floor", "basement": "basement_floor"}
    floor_key = floor_map.get(body.floor, "ground_floor")
    if floor_key not in state or state[floor_key] is None:
        return {"success": False, "error": f"Floor '{body.floor}' does not exist in this layout"}

    w = body.width or spec["min_width_m"] * 1.5
    d = body.depth or spec["min_width_m"] * 1.5
    x = body.x or 0.0
    y = body.y or 0.0

    all_rooms = state[floor_key]["rooms"]
    ok, err = _check_placement("__new__", x, y, w, d, all_rooms, project)
    if not ok:
        return {"success": False, "error": err}

    _push_undo(key, json.loads(json.dumps(state)))
    new_room = {
        "id": f"custom_{_uuid.uuid4().hex[:8]}",
        "name": body.name or body.type.replace("_", " ").title(),
        "type": body.type,
        "x": x, "y": y, "width": w, "depth": d,
        "area": round(w * d, 2),
    }
    state[floor_key]["rooms"].append(new_room)
    return {"success": True, "room": new_room}


@router.delete("/projects/{project_id}/rooms/{room_id}")
async def delete_room(
    project_id: str, room_id: str,
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if tier != "pro":
        raise HTTPException(403, "Pro plan required for agentic chat")

    state = await _get_or_init_state(project_id, user_id, db)
    key = _session_key(project_id, user_id)
    room, floor_key = _find_room_and_floor(state, room_id)
    if not room:
        raise HTTPException(404, "Room not found")

    _push_undo(key, json.loads(json.dumps(state)))
    state[floor_key]["rooms"] = [r for r in state[floor_key]["rooms"] if r["id"] != room_id]
    return {"success": True}


@router.get("/projects/{project_id}/available-space")
async def available_space(
    project_id: str, floor: str = "gf",
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if tier != "pro":
        raise HTTPException(403, "Pro plan required for agentic chat")

    project = await _get_project(project_id, user_id, db)
    state = await _get_or_init_state(project_id, user_id, db)
    rooms = _get_state_rooms(state, floor)

    buildable = _buildable_box(project)
    if rooms:
        used = unary_union([box(r["x"], r["y"], r["x"] + r["width"], r["y"] + r["depth"]) for r in rooms])
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
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if tier != "pro":
        raise HTTPException(403, "Pro plan required for agentic chat")

    project = await _get_project(project_id, user_id, db)
    state = await _get_or_init_state(project_id, user_id, db)

    from app.engine.compliance import check, load_rules
    from app.engine.models import (Column, ComplianceResult, FloorPlan, Layout,
                                    PlotConfig, Room)

    def _state_to_floor(state_dict: dict | None, floor_num: int, ftype: str) -> FloorPlan | None:
        if not state_dict:
            return None
        return FloorPlan(
            floor=floor_num,
            floor_type=ftype,
            rooms=[Room(id=r["id"], name=r["name"], type=r["type"],
                        x=r["x"], y=r["y"], width=r["width"], depth=r["depth"])
                   for r in state_dict.get("rooms", [])],
            columns=[Column(x=c["x"], y=c["y"]) for c in state_dict.get("columns", [])],
        )

    cfg = PlotConfig(
        plot_length=_to_float(project.plot_length),
        plot_width=_to_float(project.plot_width),
        setback_front=_to_float(project.setback_front),
        setback_rear=_to_float(project.setback_rear),
        setback_left=_to_float(project.setback_left),
        setback_right=_to_float(project.setback_right),
        num_bedrooms=project.num_bedrooms,
        toilets=project.toilets, parking=project.parking,
        city=getattr(project, "city", "other") or "other",
        vastu_enabled=getattr(project, "vastu_enabled", False) or False,
        road_side=getattr(project, "road_side", "S") or "S",
    )
    layout = Layout(
        id="live", name="Live",
        ground_floor=_state_to_floor(state.get("ground_floor"), 0, "ground"),
        first_floor=_state_to_floor(state.get("first_floor"), 1, "first"),
        second_floor=_state_to_floor(state.get("second_floor"), 2, "second"),
        basement_floor=_state_to_floor(state.get("basement_floor"), -1, "basement"),
        compliance=ComplianceResult(passed=True),
    )
    rules = load_rules()
    result = check(layout, cfg, rules)
    return {"passed": result.passed, "violations": result.violations, "warnings": result.warnings}


@router.post("/projects/{project_id}/rooms/undo")
async def undo_last(
    project_id: str,
    user_id: str = Depends(_user_id),
    db: AsyncSession = Depends(get_db),
):
    tier = await _get_plan_tier(user_id, db)
    if tier != "pro":
        raise HTTPException(403, "Pro plan required for agentic chat")

    key = _session_key(project_id, user_id)
    prev = _pop_undo(key)
    if prev is None:
        return {"success": False, "error": "Nothing to undo"}
    _layout_state[key] = prev
    return {"success": True, "layout": prev}
