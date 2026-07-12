from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.engine.cad_elements import FloorDrawing, Opening, WallSegment
from app.engine.geometry import buildable_polygon
from app.engine.models import Layout, PlotConfig, Room
from app.engine.plan_geometry import build_floor_drawing
from app.engine.vertical_standards import VS, VerticalStandards, fmt_level


def _line_segments(geom: BaseGeometry) -> list[LineString]:
    if geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type in ("MultiLineString", "GeometryCollection"):
        return [g for g in geom.geoms if g.geom_type == "LineString"]
    return []


def section_cut_line(rooms: list[Room], buildable: Polygon) -> tuple[LineString, bool]:
    stair = next(r for r in rooms if r.type == "staircase")
    minx, miny, maxx, maxy = buildable.bounds
    along_y = stair.depth >= stair.width
    if along_y:
        cx = stair.x + stair.width / 2
        return LineString([(cx, miny - 1.0), (cx, maxy + 1.0)]), True
    cy = stair.y + stair.depth / 2
    return LineString([(minx - 1.0, cy), (maxx + 1.0, cy)]), False


def _intervals(line: LineString, poly: Polygon) -> list[tuple[float, float]]:
    out = []
    for seg in _line_segments(line.intersection(poly)):
        t0 = line.project(Point(seg.coords[0]))
        t1 = line.project(Point(seg.coords[-1]))
        if abs(t1 - t0) > 1e-6:
            out.append((min(t0, t1), max(t0, t1)))
    return sorted(out)


def wall_cut_intervals(
    line: LineString, wall: WallSegment
) -> list[tuple[float, float]]:
    h = wall.thickness / 2
    wall_box = box(
        min(wall.x1, wall.x2) - h,
        min(wall.y1, wall.y2) - h,
        max(wall.x1, wall.x2) + h,
        max(wall.y1, wall.y2) + h,
    )
    # skip walls the line runs along (parallel & coincident): interval far wider than thickness
    return [
        iv
        for iv in _intervals(line, wall_box)
        if (iv[1] - iv[0]) <= wall.thickness * 2.5
    ]


def room_interval(line: LineString, room: Room) -> tuple[float, float] | None:
    ivs = _intervals(
        line, box(room.x, room.y, room.x + room.width, room.y + room.depth)
    )
    return ivs[0] if ivs else None


@dataclass
class SectionPoly:
    poly: Polygon
    material: str  # "brick" | "rcc" | "pcc" | "earth"
    cut: bool = True


@dataclass
class LevelMark:
    s: float
    z: float
    label: str


@dataclass
class VDim:
    z1: float
    z2: float
    label: str  # mm, e.g. "3000"


@dataclass
class SectionDrawing:
    title: str
    polys: list[SectionPoly]
    labels: list[tuple[float, float, str]]  # room names (s, z, text)
    levels: list[LevelMark]
    vdims: list[VDim]
    gl_z: float
    bounds: tuple[float, float, float, float]  # (s_min, z_min, s_max, z_max)


def _as_polys(geom: BaseGeometry) -> list[Polygon]:
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [g for g in geom.geoms if g.geom_type == "Polygon" and not g.is_empty]
    return []


def _cut_opening(
    wall: WallSegment,
    openings: list[Opening],
    along_y: bool,
    line_x: float,
    line_y: float,
) -> Opening | None:
    for op in openings:
        if along_y:
            if not op.is_horizontal or abs(op.cy - wall.y1) > 0.1:
                continue
            if abs(op.cx - line_x) < op.width / 2:
                return op
        else:
            if op.is_horizontal or abs(op.cx - wall.x1) > 0.1:
                continue
            if abs(op.cy - line_y) < op.width / 2:
                return op
    return None


def _stair_profile(
    s0: float,
    direction: int,
    n_risers: int,
    riser: float,
    tread: float,
    waist: float,
) -> Polygon:
    pts: list[tuple[float, float]] = [(s0, 0.0)]
    s, z = s0, 0.0
    for i in range(n_risers):
        z += riser
        pts.append((s, z))
        if i < n_risers - 1:
            s += direction * tread
            pts.append((s, z))
    wv = waist * 1.4  # vertical offset of sloped waist underside
    pts += [(s, z - wv), (s0, -wv)]
    return Polygon(pts)


@dataclass
class ElevationDrawing:
    title: str
    silhouette: Polygon
    openings: list[Polygon]
    chajjas: list[Polygon]
    ref_lines: list[tuple[float, float, float, float]]  # dashed FFL lines (s1,z1,s2,z2)
    levels: list[LevelMark]
    vdims: list[VDim]  # incl. overall height GL->parapet top
    gl_z: float
    bounds: tuple[float, float, float, float]


def derive_elevation(
    layout: Layout, cfg: PlotConfig, vs: VerticalStandards = VS
) -> ElevationDrawing:
    ftf = vs.floor_to_floor_m
    gl = -vs.plinth_h_m
    lintel_h = vs.lintel_h_m
    chajja_t = vs.chajja_t_m
    parapet_h = vs.parapet_h_m

    # Rule 1 — floors and their finished-floor levels
    floors = [layout.ground_floor, layout.first_floor]
    if layout.second_floor is not None:
        floors.append(layout.second_floor)
    n_floors = len(floors)
    roof_z = n_floors * ftf

    def z_ffl(i: int) -> float:
        return i * ftf

    # Rule 1 — facade axis. Rooms are always laid out with the road at the
    # y-min edge (archetypes/vastu convention: y=0 is the road/front edge);
    # cfg.road_side only records the compass direction that edge faces. The
    # front facade is therefore always the y-min wall, running along x.
    buildable = buildable_polygon(cfg)
    minx, miny, maxx, _maxy = buildable.bounds
    along_x = True
    v_front = miny
    u_min, u_max = minx, maxx

    # Rule 2 — facade silhouette, GL to parapet top
    silhouette = box(u_min, gl, u_max, roof_z + parapet_h)

    drawings: list[FloorDrawing] = [build_floor_drawing(fp, cfg) for fp in floors]

    # Rules 3-4 — facade openings and their chajja bands, per floor
    opening_rects: list[Polygon] = []
    chajjas: list[Polygon] = []
    for i, fdw in enumerate(drawings):
        zf = z_ffl(i)
        for op in fdw.openings:
            if op.is_horizontal != along_x:
                continue
            perp = op.cy if along_x else op.cx
            if abs(perp - v_front) >= 0.3:
                continue
            u_c = op.cx if along_x else op.cy
            if op.kind == "door":
                z_lo, z_hi = zf, zf + vs.door_h_m
            elif op.kind == "window":
                z_lo, z_hi = zf + vs.sill_h_m, zf + lintel_h
            else:  # ventilator
                z_lo, z_hi = zf + vs.vent_sill_m, zf + lintel_h
            opening_rects.append(
                box(u_c - op.width / 2, z_lo, u_c + op.width / 2, z_hi)
            )
            chajjas.append(
                box(
                    u_c - op.width / 2 - 0.15,
                    zf + lintel_h,
                    u_c + op.width / 2 + 0.15,
                    zf + lintel_h + chajja_t,
                )
            )

    # Rule 5 — dashed FFL/roof reference lines spanning the facade width
    ref_zs = {0.0, roof_z}
    for k in range(1, n_floors):
        ref_zs.add(z_ffl(k))
    ref_lines = [(u_min, z, u_max, z) for z in sorted(ref_zs)]

    # Rule 6 — level marks and overall/plinth vertical dimensions
    s_lvl = u_max + 0.6
    levels = [
        LevelMark(s_lvl, gl, "G.L. " + fmt_level(gl)),
        LevelMark(s_lvl, 0.0, fmt_level(0.0)),
    ]
    for k in range(1, n_floors):
        levels.append(LevelMark(s_lvl, z_ffl(k), fmt_level(z_ffl(k))))
    levels.append(LevelMark(s_lvl, roof_z, fmt_level(roof_z)))
    levels.append(LevelMark(s_lvl, roof_z + parapet_h, fmt_level(roof_z + parapet_h)))

    vdims = [
        VDim(gl, roof_z + parapet_h, str(round((roof_z + parapet_h - gl) * 1000))),
        VDim(gl, 0.0, str(round(vs.plinth_h_m * 1000))),
    ]

    bounds = (u_min - 1.2, gl - 1.2, u_max + 1.2, roof_z + parapet_h + 1.2)

    return ElevationDrawing(
        title="FRONT ELEVATION",
        silhouette=silhouette,
        openings=opening_rects,
        chajjas=chajjas,
        ref_lines=ref_lines,
        levels=levels,
        vdims=vdims,
        gl_z=gl,
        bounds=bounds,
    )


def derive_section(
    layout: Layout, cfg: PlotConfig, vs: VerticalStandards = VS
) -> SectionDrawing:
    ftf = vs.floor_to_floor_m
    slab_t = vs.slab_t_m
    gl = -vs.plinth_h_m
    fd = vs.foundation_depth_m
    fw = vs.footing_w_m
    footing_t = vs.footing_t_m
    lintel_h = vs.lintel_h_m
    lintel_t = vs.lintel_t_m
    chajja_proj = vs.chajja_proj_m
    chajja_t = vs.chajja_t_m
    parapet_h = vs.parapet_h_m
    parapet_t = vs.parapet_t_m
    tread = vs.stair_tread_m
    waist = vs.waist_t_m

    # Rule 1 — floors and their finished-floor levels
    floors = [layout.ground_floor, layout.first_floor]
    if layout.second_floor is not None:
        floors.append(layout.second_floor)
    n_floors = len(floors)
    roof_z = n_floors * ftf

    def z_ffl(i: int) -> float:
        return i * ftf

    buildable = buildable_polygon(cfg)
    line, along_y = section_cut_line(layout.ground_floor.rooms, buildable)
    line_x, line_y = line.coords[0][0], line.coords[0][1]
    drawings: list[FloorDrawing] = [build_floor_drawing(fp, cfg) for fp in floors]
    gf = drawings[0]

    # S_MIN/S_MAX — outer faces of the outermost cut external walls on GF
    ext_ivs: list[tuple[float, float]] = []
    for w in gf.walls:
        if w.kind == "external":
            ext_ivs.extend(wall_cut_intervals(line, w))
    s_min = min(iv[0] for iv in ext_ivs)
    s_max = max(iv[1] for iv in ext_ivs)
    s_mid = (s_min + s_max) / 2

    polys: list[SectionPoly] = []
    labels: list[tuple[float, float, str]] = []

    # Rule 2 — full-height brick strips with opening voids, lintels and chajjas
    for i, fdw in enumerate(drawings):
        zf = z_ffl(i)
        for w in fdw.walls:
            for s0, s1 in wall_cut_intervals(line, w):
                strip = box(s0, zf, s1, zf + ftf)
                op = _cut_opening(w, fdw.openings, along_y, line_x, line_y)
                if op is None:
                    polys.append(SectionPoly(strip, "brick"))
                    continue
                if op.kind == "door":
                    gap = box(s0, zf, s1, zf + vs.door_h_m)
                elif op.kind == "window":
                    gap = box(s0, zf + vs.sill_h_m, s1, zf + lintel_h)
                else:  # ventilator
                    gap = box(s0, zf + vs.vent_sill_m, s1, zf + lintel_h)
                for piece in _as_polys(strip.difference(gap)):
                    polys.append(SectionPoly(piece, "brick"))
                polys.append(
                    SectionPoly(
                        box(s0, zf + lintel_h, s1, zf + lintel_h + lintel_t), "rcc"
                    )
                )
                if w.kind == "external":
                    if abs(s1 - s_mid) >= abs(s0 - s_mid):
                        outer, proj = s1, chajja_proj
                    else:
                        outer, proj = s0, -chajja_proj
                    polys.append(
                        SectionPoly(
                            box(
                                min(outer, outer + proj),
                                zf + lintel_h,
                                max(outer, outer + proj),
                                zf + lintel_h + chajja_t,
                            ),
                            "rcc",
                        )
                    )

    # Rule 3 — floor and roof slabs
    for z in {z_ffl(k) for k in range(1, n_floors + 1)} | {roof_z}:
        polys.append(SectionPoly(box(s_min, z - slab_t, s_max, z), "rcc"))

    # Rule 4 — foundation stem + PCC footing under each GF cut wall
    foundation: list[Polygon] = []
    for w in gf.walls:
        for s0, s1 in wall_cut_intervals(line, w):
            stem = box(s0, gl - fd + footing_t, s1, z_ffl(0))
            mid = (s0 + s1) / 2
            footing = box(mid - fw / 2, gl - fd, mid + fw / 2, gl - fd + footing_t)
            polys.append(SectionPoly(stem, "brick"))
            polys.append(SectionPoly(footing, "pcc"))
            foundation.extend((stem, footing))

    # Rule 5 — earth: side GL strips + plinth fill clipped by foundations
    polys.append(SectionPoly(box(s_min - 1.0, gl - 0.3, s_min, gl), "earth"))
    polys.append(SectionPoly(box(s_max, gl - 0.3, s_max + 1.0, gl), "earth"))
    plinth_fill: BaseGeometry = box(s_min, gl, s_max, 0.0)
    if foundation:
        plinth_fill = plinth_fill.difference(unary_union(foundation))
    for piece in _as_polys(plinth_fill):
        polys.append(SectionPoly(piece, "earth"))

    # Rule 6 — roof parapets, inner face aligned to each outer wall
    polys.append(
        SectionPoly(box(s_min, roof_z, s_min + parapet_t, roof_z + parapet_h), "brick")
    )
    polys.append(
        SectionPoly(box(s_max - parapet_t, roof_z, s_max, roof_z + parapet_h), "brick")
    )

    # Rule 7 — stepped RCC stair profile through the staircase
    stair_room = next(r for r in layout.ground_floor.rooms if r.type == "staircase")
    stair_iv = room_interval(line, stair_room)
    if gf.stair is not None and stair_iv is not None:
        n_r = round(ftf / vs.stair_riser_m)
        riser = ftf / n_r
        ax0, ay0, ax1, ay1 = gf.stair.arrow
        s_tail = line.project(Point(ax0, ay0))
        s_head = line.project(Point(ax1, ay1))
        direction = 1 if s_head >= s_tail else -1
        i0, i1 = stair_iv
        max_treads = max(1, int((i1 - i0) / tread))
        n_draw = max(2, min(n_r, max_treads + 1))
        s_start = i0 if direction > 0 else i1
        profile = _stair_profile(s_start, direction, n_draw, riser, tread, waist)
        if not profile.is_valid:
            profile = profile.buffer(0)
        for piece in _as_polys(profile):
            polys.append(SectionPoly(piece, "rcc"))
        s_lab = s_start + direction * (n_draw - 1) * tread / 2
        # below the waist underside so it clears the room label on the diagonal
        labels.append((s_lab, 0.7, f"{n_r}R @ {round(riser * 1000)}"))

    # Rule 8 — room labels per floor
    for i, fp in enumerate(floors):
        for room in fp.rooms:
            iv = room_interval(line, room)
            if iv is not None:
                labels.append(((iv[0] + iv[1]) / 2, z_ffl(i) + 1.5, room.name.upper()))

    # Rule 9 — level marks down the right margin
    s_lvl = s_max + 0.6
    levels = [
        LevelMark(s_lvl, gl, "G.L. " + fmt_level(gl)),
        LevelMark(s_lvl, 0.0, fmt_level(0.0)),
    ]
    for k in range(1, n_floors):
        levels.append(LevelMark(s_lvl, z_ffl(k), fmt_level(z_ffl(k))))
    levels.append(LevelMark(s_lvl, roof_z, fmt_level(roof_z)))
    levels.append(LevelMark(s_lvl, roof_z + parapet_h, fmt_level(roof_z + parapet_h)))

    # Rule 10 — vertical dimensions down the left margin (mm)
    vdims = [
        VDim(gl - fd, gl, str(round(fd * 1000))),
        VDim(gl, 0.0, str(round(vs.plinth_h_m * 1000))),
    ]
    for k in range(n_floors):
        vdims.append(VDim(z_ffl(k), z_ffl(k + 1), str(round(ftf * 1000))))
    vdims.append(VDim(roof_z, roof_z + parapet_h, str(round(parapet_h * 1000))))

    # Rule 11 — annotation-padded bounds (union of polys, levels and labels)
    all_s = (
        [p.poly.bounds[0] for p in polys]
        + [p.poly.bounds[2] for p in polys]
        + [lv.s for lv in levels]
        + [s for s, _, _ in labels]
    )
    all_z = (
        [p.poly.bounds[1] for p in polys]
        + [p.poly.bounds[3] for p in polys]
        + [lv.z for lv in levels]
        + [z for _, z, _ in labels]
    )
    s0b, z0b = min(all_s) - 1.2, min(all_z) - 1.2
    s1b, z1b = max(all_s) + 1.2, max(all_z) + 1.2

    return SectionDrawing(
        title="SECTION A-A",
        polys=polys,
        labels=labels,
        levels=levels,
        vdims=vdims,
        gl_z=gl,
        bounds=(s0b, z0b, s1b, z1b),
    )
