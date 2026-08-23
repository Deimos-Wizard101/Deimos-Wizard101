"""Collision geometry math for collision-based teleporting.

Goal: teleport as *close to the target as possible while guaranteeing the spot is
walkable*. We take the real walkable navmesh (the actual triangle faces, not a convex
hull), carve out the wall footprints dilated by the player's clearance, and pick the
point of that region nearest the target. Because the result is on the navmesh and a
clear radius from every wall, the body can't clip — a single, decisive teleport.

(The earlier version hulled the mesh — ~2.3x too big, so it placed teleports in
non-walkable courtyards — and eroded that inflated area by the player radius, which
closed narrow corridors and flung points far from the target. Both are fixed here.)

The lower-level cube/transform helpers (toCubeVertices, transformCube, toMultidim)
come from PeechezNCreem / CIick and are shared with the shape builders below.
"""

import heapq
import math
from typing import List, TypeAlias

import numpy as np
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.ops import unary_union, nearest_points
from shapely.prepared import prep
from shapely.strtree import STRtree
from wizwalker import XYZ

from .collision import CollisionWorld, ProxyType, CollisionFlag


Matrix3x3: TypeAlias = tuple[
    float, float, float,
    float, float, float,
    float, float, float,
]

SimpleVert: TypeAlias = tuple[float, float, float]
Vector3D: TypeAlias = tuple[float, float, float]

CubeVertices = tuple[Vector3D, Vector3D, Vector3D, Vector3D, Vector3D, Vector3D, Vector3D, Vector3D]


def cube_to_xyz(cube: list) -> List[XYZ]:
    return [XYZ(v[0], v[1], v[2]) for v in cube]


def subtract_xyz(xyz2: XYZ, xyz1: XYZ) -> XYZ:
    # b - a = (bx - ax, by - ay, bz - az)
    return XYZ((xyz2.x - xyz1.x), (xyz2.y - xyz1.y), (xyz2.z - xyz1.z))


def multiply_xyz(a: XYZ, b: XYZ) -> float:
    # a dot b = ax*bx + ay*by + az*bz
    return a.x * b.x + a.y * b.y + a.z * b.z


def toCubeVertices(dimensions: Vector3D) -> CubeVertices:
    l, w, d = dimensions
    l /= 2
    w /= 2
    d /= 2
    return (
        (-l, -w, -d),
        (l, -w, -d),
        (l, -w, d),
        (-l, -w, d),

        (-l, w, -d),
        (l, w, -d),
        (l, w, d),
        (-l, w, d),
    )


def toMultidim(mat: Matrix3x3):
    # Transposed: the cubes come out distorted otherwise.
    return (
        (mat[0], mat[3], mat[6]),
        (mat[1], mat[4], mat[7]),
        (mat[2], mat[5], mat[8]),
    )


def transformCube(cube, location, rotation):
    tpoints = [np.dot((p,), toMultidim(rotation))[0] for p in cube]
    for p in tpoints:
        p[0] += location[0]
        p[1] += location[1]
        p[2] += location[2]
    return tpoints


def filter_valid_polygons(shapes) -> List[Polygon]:
    """Keep only non-empty 2D Polygons, flattening MultiPolygons.

    Degenerate inputs (collinear vertices) can make ``.convex_hull`` return a
    LineString or Point; those would break ``unary_union``/``difference``, so we
    drop them here.
    """
    valid = []
    for shape in shapes:
        if shape is None or shape.is_empty:
            continue
        if shape.geom_type == "Polygon":
            valid.append(shape)
        elif shape.geom_type == "MultiPolygon":
            valid.extend(poly for poly in shape.geoms if poly.geom_type == "Polygon")
    return valid


# A teleport target's z is the player's *feet*. A collider blocks the spot when its
# vertical extent overlaps a thin slack band around the feet, ``[z - Z_BAND_DOWN,
# z + Z_BAND_UP]`` — not the player's full visual height. Walls in collision.bcd run
# from ~ground level upward, so this catches them (including ones whose modeled base
# floats a little above the navmesh, e.g. WC Triton's central cylinder sits ~4u high),
# while overhead structures the player walks *under* (domes, arches, upper-floor walls
# — bases 75–270u up) are correctly ignored. A full body-height band over-blocks those
# and throws teleports wildly past them; a foot-only point slice misses the floating-
# base walls and clips. ~50u of upward slack threads that needle.
#
# A real wall always rises *above* the feet (high zmax), so it's caught regardless of
# how far down the band reaches; the only thing Z_BAND_DOWN includes is colliders whose
# TOP is below the feet — sub-floor foundation/water volumes (e.g. GH MainHub's dock
# cylinders, r~447 at z ending ~13u under the surface). Too much downward slack lets one
# of those wipe out the walkable dock around it and throw a teleport hundreds of units
# off. Keep it small — just enough for a wall whose base is modeled a hair below the
# navmesh — so genuinely-underfoot geometry is ignored.
Z_BAND_UP = 50.0
Z_BAND_DOWN = 8.0

# When a collider's base is at or *below* the feet, the feet are inside the volume. That
# alone can't mean "blocked": every solid in collision.bcd is flagged identically
# (`CT_Object`), and coarse *terrain* volumes — e.g. GH HFjord's rocky floor or Ravenwood's
# ground, modelled as r~500 OBJECT cylinders the walkable navmesh sits *inside* — carry the
# same flag as real walls. Blocking on flag/size is impossible; the only separator is how far
# the solid rises ABOVE the feet, i.e. whether the player's body capsule fits. This is a
# physical height check, but the player ("PlayerObject", tid 1) has NO collision file, so the
# capsule height isn't readable from game data — it's a calibrated constant bounded by in-game
# behaviour:
#   walkable (terrain you stand inside): GH dock +22/+34u, Ravenwood ground +55u
#   blocks (real wall/chamber/trunk):    WC Drains chamber +94u, Celestia +288u, Bartleby +250u,
#                                        Drains building box +730u
# The navmesh only ever sits inside a collider for these big terrain/building volumes (a normal
# wall has navmesh *beside* it, caught by the horizontal footprint), so the gap between terrain
# (<=55u) and structures (>=94u) is wide and stable. 75u sits between: it frees GH + Ravenwood
# while every genuine wall still blocks (Celestia 208u/z=-350, GH 87u, AZ 223u unchanged; Drains
# lands 340u out, still well outside its building box — vs the old, more conservative 510u).
#
# BUT rise alone can't separate every case: Khrysalis KR_Z00_Hub's flat UniverseTeleport pad is a
# BOX rising only +52u above the floor (navmesh at the box's base) that genuinely bounces, while
# Ravenwood's walkable terrain CYLINDER rises +55u — nearly identical rise, opposite verdict. The
# tie-breaker is the proxy shape: across every zone examined the must-NOT-block volumes are
# CYLINDERS/SPHERES (coarse terrain the navmesh threads through) and BOXES are always structural
# (pads/walls/buildings). So a BOX the navmesh is *embedded* in walls off at a much smaller rise
# (`Z_BOX_TOL`) — only a box the navmesh sits on *top* of, rise ~0, is walkable.
Z_EMBED_TOL = 75.0   # cylinder/sphere: terrain rises <=55u, structures >=94u
Z_BOX_TOL = 20.0     # box: structural even when shallow (Khrysalis pad +52u); only rise~0 (a
                     # platform the navmesh sits on top of) is walkable


def _collider_blocks_foot(z: float, zlo: float, zhi: float, is_box: bool = False) -> bool:
    """Whether a bcd collider with vertical extent ``[zlo, zhi]`` walls off a foot level ``z``.

    Two regimes:
    - base *above* the feet (overhead): blocks only when it hangs within ``Z_BAND_UP`` of the
      feet — a ceiling too low to stand under — and is ignored once it clears the head
      (domes/arches/upper floors, bases 75-270u up).
    - base *at or below* the feet (embedded): blocks when the solid rises far enough above the
      feet that the body can't fit. The threshold is shape-dependent — ``Z_BOX_TOL`` for a
      structural BOX (a low flat pad still bounces), ``Z_EMBED_TOL`` for a CYLINDER/SPHERE
      (a coarse terrain volume the surface merely sits inside pokes up less and stays
      walkable). A collider whose top is below the feet is ground underfoot and never blocks.
    """
    if z > zhi + Z_BAND_DOWN:
        return False                    # collider top below the feet -> underfoot, ignore
    if zlo <= z:
        return (zhi - z) >= (Z_BOX_TOL if is_box else Z_EMBED_TOL)  # embedded
    return (zlo - z) <= Z_BAND_UP        # overhead: a low base within reach blocks


def _z_overlaps(obj_zmin: float, obj_zmax: float, band_lo: float, band_hi: float) -> bool:
    """Whether an object's vertical extent overlaps the foot-level slack band."""
    return obj_zmin <= band_hi and obj_zmax >= band_lo


def build_collision_shapes_typed(world: CollisionWorld, z_slice: float):
    """``(box_polys, round_polys)`` of solid collision objects at the player's foot level.

    An object is included when its vertical extent overlaps the slack band
    ``[z_slice - Z_BAND_DOWN, z_slice + Z_BAND_UP]``, so a ground wall (even one whose
    modeled base floats slightly above the feet) blocks while overhead geometry the
    player walks under does not.

    The two lists are kept separate because they mean different things in KI's collision
    authoring and are treated differently when carving walkable space (see ``_compose_walls``):
      - **boxes** are specific wall segments — a real wall you can't pass;
      - **rounds** (cylinders/spheres) are usually the *coarse bounding volume* of a whole
        structure (Celestia's Floating Land chamber is a single r~834 cylinder whose interior
        is walkable floor with a doorway; WC zones bound buildings the same way). Treating
        those as solid discs wipes out the walkable floor inside them.
    """
    band_lo = z_slice - Z_BAND_DOWN
    band_hi = z_slice + Z_BAND_UP
    boxes, rounds = [], []
    for obj in world.objects:
        try:
            scale_val = obj.scale if isinstance(obj.scale, (float, int)) else obj.scale[0]
            if obj.proxy == ProxyType.BOX:
                # Box dimensions are intentionally left unscaled (the stored transform
                # may already encode scale); only the slice test changed to a band.
                l, w, h = obj.params.length, obj.params.width, obj.params.depth
                if _z_overlaps(obj.location[2] - h / 2, obj.location[2] + h / 2, band_lo, band_hi):
                    world_pts = transformCube(toCubeVertices((l, w, h)), obj.location, obj.rotation)
                    pts2d = [(p[0], p[1]) for p in world_pts]
                    if len(pts2d) >= 3:
                        boxes.append(Polygon(pts2d).convex_hull)

            elif obj.proxy == ProxyType.SPHERE:
                r = obj.params.radius * scale_val
                if r > 0 and _z_overlaps(obj.location[2] - r, obj.location[2] + r, band_lo, band_hi):
                    rounds.append(Point(obj.location[0], obj.location[1]).buffer(r))

            elif obj.proxy == ProxyType.CYLINDER:
                # Collision cylinders store a true world-space radius (median ~500 in
                # WC — these are building-sized volumes). A previous ``* 0.125`` fudge
                # shrank them to ~1/8, so teleports could land *inside* a building.
                r = obj.params.radius * scale_val
                half_len = (obj.params.length / 2) * scale_val
                if r > 0 and _z_overlaps(obj.location[2] - half_len, obj.location[2] + half_len, band_lo, band_hi):
                    rounds.append(Point(obj.location[0], obj.location[1]).buffer(r))
        except Exception:
            continue
    return boxes, rounds


def build_collision_shapes(world: CollisionWorld, z_slice: float) -> List[Polygon]:
    """All solid-collision footprints (boxes + round volumes) at the foot level.
    Thin wrapper over ``build_collision_shapes_typed`` for callers that don't need the
    box/round split."""
    boxes, rounds = build_collision_shapes_typed(world, z_slice)
    return boxes + rounds


# bcd collision flags that do NOT obstruct player movement (mirror of entity_collision's
# `_NON_MOVEMENT_CATEGORIES` for the baked-in zone geometry). The compiled collision.bcd carries
# the same client-object/trigger/etc. volumes as the entity collision files — e.g. Darkmoor's
# AscensionChapel bcd has 4 CLIENT_OBJECT boxes/cylinders — and a teleport may land where they
# overlap. Real walls are flagged OBJECT (or unflagged); WALKABLE is the navmesh itself.
_NON_MOVEMENT_FLAGS = (CollisionFlag.CLIENT_OBJECT | CollisionFlag.TRIGGER
                       | CollisionFlag.HITSCAN | CollisionFlag.FOG)


def _all_collider_solids(world: CollisionWorld):
    """``[(footprint_polygon, z_min, z_max, is_box), ...]`` for every movement-blocking bcd
    box/cylinder/sphere, with its full vertical extent and NOT z-filtered. ``is_box`` distinguishes
    structural BOX colliders (pads/walls/buildings — always solid where the navmesh enters them)
    from CYLINDER/SPHERE volumes (which may be coarse terrain the navmesh sits inside); see
    ``_collider_blocks_foot``. Non-movement categories (``_NON_MOVEMENT_FLAGS``) are skipped — they
    don't block the player. Used by the height-aware wall builder + the teleport grid."""
    solids = []
    for obj in world.objects:
        try:
            fl = obj.category_flags
            if (fl & _NON_MOVEMENT_FLAGS) and CollisionFlag.OBJECT not in fl:
                continue  # client-object / trigger / hitscan / fog volume -> not a movement wall
            scale_val = obj.scale if isinstance(obj.scale, (float, int)) else obj.scale[0]
            is_box = False
            if obj.proxy == ProxyType.BOX:
                l, w, h = obj.params.length, obj.params.width, obj.params.depth
                pts = transformCube(toCubeVertices((l, w, h)), obj.location, obj.rotation)
                poly = Polygon([(p[0], p[1]) for p in pts]).convex_hull
                zlo, zhi = obj.location[2] - h / 2, obj.location[2] + h / 2
                is_box = True
            elif obj.proxy == ProxyType.SPHERE:
                r = obj.params.radius * scale_val
                if r <= 0:
                    continue
                poly = Point(obj.location[0], obj.location[1]).buffer(r)
                zlo, zhi = obj.location[2] - r, obj.location[2] + r
            elif obj.proxy == ProxyType.CYLINDER:
                r = obj.params.radius * scale_val
                hl = (obj.params.length / 2) * scale_val
                if r <= 0:
                    continue
                poly = Point(obj.location[0], obj.location[1]).buffer(r)
                zlo, zhi = obj.location[2] - hl, obj.location[2] + hl
            else:
                continue
            if poly.is_valid and not poly.is_empty:
                solids.append((poly, zlo, zhi, is_box))
        except Exception:
            continue
    return solids


# Per-zone walkable triangles with their surface z, and the height-aware bcd-wall region.
# Both are zone-static (independent of the teleport target), so they're memoized per zone.
_walkable_tris_cache: dict[str, tuple] = {}
_bcd_walls_cache: dict[str, object] = {}
_collider_solids_cache: dict[str, list] = {}
_mesh_cache: dict[str, tuple] = {}  # zone -> numpy (verts2d, surface_z, bbox)


def _zone_collider_solids(world: CollisionWorld, zone_name: str | None):
    """``_all_collider_solids`` memoized per zone."""
    if zone_name is not None and zone_name in _collider_solids_cache:
        return _collider_solids_cache[zone_name]
    solids = _all_collider_solids(world)
    if zone_name is not None:
        _collider_solids_cache[zone_name] = solids
    return solids


def _walkable_mesh(world: CollisionWorld, zone_name: str | None):
    """The walkable navmesh as plain numpy arrays for fast point queries: ``(verts, z, bbox)``
    where ``verts`` is ``(N, 3, 2)`` triangle XY corners, ``z`` is ``(N,)`` surface heights, and
    ``bbox`` is ``(N, 4)`` ``[minx, miny, maxx, maxy]``. Memoized per zone.

    This replaces building ~thousands of individual shapely ``Polygon`` objects (the dominant
    per-zone setup cost). The whole mesh is transformed and assembled with vectorized numpy —
    no per-triangle Python object — and point-in-triangle tests run vectorized in
    ``_mesh_levels_at``. (The shapely-polygon form, ``_walkable_tris``, is kept only for
    ``zone_bcd_walls``, which needs geometric intersection/union.)"""
    if zone_name is not None and zone_name in _mesh_cache:
        return _mesh_cache[zone_name]
    chunks_v, chunks_z = [], []
    for obj in world.objects:
        if (obj.proxy == ProxyType.MESH and CollisionFlag.WALKABLE in obj.category_flags
                and obj.faces and obj.vertices):
            try:
                V = np.asarray(obj.vertices, dtype=float)               # (Vn, 3) model space
                M = np.asarray(toMultidim(obj.rotation), dtype=float)   # (3, 3)
                Wv = V @ M + np.asarray(obj.location, dtype=float)      # (Vn, 3) world space
                F = np.asarray(obj.faces, dtype=np.intp)                # (Fn, 3)
                tv = Wv[F]                                              # (Fn, 3, 3)
            except Exception:
                continue
            chunks_v.append(tv[:, :, :2])                              # (Fn, 3, 2)
            chunks_z.append(tv[:, :, 2].mean(axis=1))                  # (Fn,)
    if not chunks_v:
        result = (np.empty((0, 3, 2)), np.empty((0,)), np.empty((0, 4)))
    else:
        verts = np.concatenate(chunks_v, axis=0)
        z = np.concatenate(chunks_z, axis=0)
        ax, ay = verts[:, 0, 0], verts[:, 0, 1]
        bx, by = verts[:, 1, 0], verts[:, 1, 1]
        cx, cy = verts[:, 2, 0], verts[:, 2, 1]
        area2 = np.abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))  # drop degenerate tris
        keep = area2 > 1e-6
        verts, z = verts[keep], z[keep]
        bbox = np.column_stack([verts[:, :, 0].min(1), verts[:, :, 1].min(1),
                                verts[:, :, 0].max(1), verts[:, :, 1].max(1)])
        result = (verts, z, bbox)
    if zone_name is not None:
        _mesh_cache[zone_name] = result
    return result


def _mesh_levels_at(x: float, y: float, mesh):
    """Sorted distinct surface heights of the walkable navmesh at ``(x, y)``, vectorized.

    Bounding-box prefilter (one numpy mask over all triangles) then a barycentric/sign
    point-in-triangle test on the survivors. For the handful of nodes a teleport probes this
    is microseconds; even A* over hundreds of nodes stays in single-digit ms."""
    verts, z, bbox = mesh
    if verts.shape[0] == 0:
        return []
    cand = np.nonzero((bbox[:, 0] <= x) & (x <= bbox[:, 2])
                      & (bbox[:, 1] <= y) & (y <= bbox[:, 3]))[0]
    if cand.size == 0:
        return []
    tv = verts[cand]
    ax, ay = tv[:, 0, 0], tv[:, 0, 1]
    bx, by = tv[:, 1, 0], tv[:, 1, 1]
    cx, cy = tv[:, 2, 0], tv[:, 2, 1]
    d1 = (x - bx) * (ay - by) - (ax - bx) * (y - by)
    d2 = (x - cx) * (by - cy) - (bx - cx) * (y - cy)
    d3 = (x - ax) * (cy - ay) - (cx - ax) * (y - ay)
    has_neg = (d1 < 0) | (d2 < 0) | (d3 < 0)
    has_pos = (d1 > 0) | (d2 > 0) | (d3 > 0)
    inside = ~(has_neg & has_pos)  # all same sign (boundary inclusive) -> point in triangle
    if not inside.any():
        return []
    return sorted(set(np.round(z[cand][inside], 3).tolist()))


def _ground_z_at(world: CollisionWorld, zone_name: str | None, x: float, y: float):
    """The teleport-valid ground height of the walkable navmesh at ``(x, y)``, or None.

    A floating-island / ramp zone can stack several walkable surfaces at one XY. We want the
    one a teleport will actually land on: the lowest surface that is NOT inside any collider's
    vertical reach (so the body isn't dropped into a wall/cylinder). Falls back to the lowest
    surface, then None. Cheap — vectorized point-in-triangle against the cached numpy mesh."""
    levels = _mesh_levels_at(x, y, _walkable_mesh(world, zone_name))
    if not levels:
        return None
    pt = Point(x, y)
    covering = [(zlo, zhi, box) for fp, zlo, zhi, box in _zone_collider_solids(world, zone_name)
                if fp.contains(pt)]
    for z in levels:  # lowest-first: prefer the ground level under any obstacle
        if not any(_collider_blocks_foot(z, zlo, zhi, box) for zlo, zhi, box in covering):
            return z
    return levels[0]


def _walkable_tris(world: CollisionWorld, zone_name: str | None):
    """``(STRtree, [triangle], [surface_z])`` over the walkable navmesh faces."""
    if zone_name is not None and zone_name in _walkable_tris_cache:
        return _walkable_tris_cache[zone_name]
    tris, zs = [], []
    for obj in world.objects:
        if obj.proxy == ProxyType.MESH and CollisionFlag.WALKABLE in obj.category_flags:
            pts = transformCube(obj.vertices, obj.location, obj.rotation)
            for a, b, c in obj.faces:
                try:
                    tri = Polygon([
                        (pts[a][0], pts[a][1]), (pts[b][0], pts[b][1]), (pts[c][0], pts[c][1]),
                    ])
                    if tri.is_valid and tri.area > 0:
                        tris.append(tri)
                        zs.append((pts[a][2] + pts[b][2] + pts[c][2]) / 3.0)
                except Exception:
                    continue
    tree = STRtree(tris) if tris else None
    result = (tree, tris, zs)
    if zone_name is not None:
        _walkable_tris_cache[zone_name] = result
    return result


def zone_bcd_walls(world: CollisionWorld, zone_name: str | None):
    """Height-aware bcd collision walls, memoized per zone.

    A collider only walls off a spot where the *walkable surface there* is actually within
    the collider's vertical extent — you can't be blocked by collision that's entirely above
    or below your feet at that XY. So instead of slicing every collider at one global z (which
    makes a tall cylinder a flat disc that wrongly blocks a ramp passing under it), each
    collider footprint is intersected with only the walkable triangles whose surface z falls in
    its band ``[z_min - Z_BAND_UP, z_max + Z_BAND_DOWN]``. This is what lets a teleport land on
    the low/outer part of Celestia's ramp (which dips below the chamber cylinder's base) while
    still avoiding the inner ramp that genuinely rises into it, and it subsumes the old
    sub-floor ``Z_BAND_DOWN`` special-case (a cylinder whose top is below the floor matches no
    triangles). Zone-static, so cached. Pure CPU; first call ~0.4–2.5s, then free.
    """
    if zone_name is not None and zone_name in _bcd_walls_cache:
        return _bcd_walls_cache[zone_name]
    tree, tris, zs = _walkable_tris(world, zone_name)
    walls = Polygon()
    if tree is not None:
        blocked = []
        for fp, zlo, zhi, _is_box in _all_collider_solids(world):
            band_lo, band_hi = zlo - Z_BAND_UP, zhi + Z_BAND_DOWN
            matching = [
                tris[i] for i in tree.query(fp)
                if band_lo <= zs[i] <= band_hi and tris[i].intersects(fp)
            ]
            if matching:
                region = fp.intersection(unary_union(matching))
                if not region.is_empty:
                    blocked.append(region)
        if blocked:
            walls = unary_union(blocked)
    if zone_name is not None:
        _bcd_walls_cache[zone_name] = walls
    return walls


# ---------------------------------------------------------------------------
# Lazy hexagonal walkability grid. A node is teleport-valid when it sits on walkable
# navmesh, that ground surface is NOT inside any bcd collider's vertical reach
# (height-aware — you can walk a ramp *under* a tall cylinder), and it clears every static
# entity collider (teleporter pads, boats). Hex layout gives 6 equidistant neighbours (the
# right substrate for A* nav). Crucially we DON'T rasterize the whole zone: a teleport only
# needs the nearest walkable node to the target, so we evaluate nodes on demand in expanding
# rings and memoize each verdict. The same lazy node cache backs A* nav. First teleport pays
# only the per-zone index build (navmesh/collider STRtrees) + a few dozen node probes, not a
# full-zone sweep.
# ---------------------------------------------------------------------------

GRID_SPACING = 100.0  # hex node centre-to-centre distance, world units

# When the target's own XY isn't walkable, relocate to the nearest walkable node ranked by
# ``dxy + Z_RANK_WEIGHT * |Δz|`` so a node on the target's own floor beats a closer one on the
# wrong floor (see ``closest_walkable``). Modest — same-floor Δz is tiny, so it only bites
# across floors (Δz in the hundreds).
Z_RANK_WEIGHT = 2.0

# A surface directly at the target's XY is only accepted as the exact landing when it's within
# this of the target's own height. Beyond it the target's floor isn't represented at that XY
# (it sits under an overhang / in a mesh gap), so we ring-search for a node on the right floor
# instead of teleporting a whole floor away. Floors in these zones are ~900-2500u apart while a
# floor's own z-spread (ramps/stairs) stays well under this, so the gap is unambiguous.
FLOOR_MATCH_TOL = 300.0

_SQRT3 = math.sqrt(3.0)
# Axial hex directions (q, r). Six equidistant neighbours.
_HEX_DIRS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))

# zone -> _ZoneWalkGrid
_walk_grid_cache: dict[str, object] = {}


def _hex_round(qf, rf):
    """Round fractional axial coords to the nearest hex (via cube rounding)."""
    xf, zf = qf, rf
    yf = -xf - zf
    rx, ry, rz = round(xf), round(yf), round(zf)
    dx, dy, dz = abs(rx - xf), abs(ry - yf), abs(rz - zf)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return int(rx), int(rz)


def _hex_ring(q0, r0, k):
    """Yield the axial coords of the ring at hex-distance ``k`` around ``(q0, r0)``."""
    if k == 0:
        yield (q0, r0)
        return
    q = q0 + _HEX_DIRS[4][0] * k
    r = r0 + _HEX_DIRS[4][1] * k
    for i in range(6):
        for _ in range(k):
            yield (q, r)
            q += _HEX_DIRS[i][0]
            r += _HEX_DIRS[i][1]


class _ZoneWalkGrid:
    """Lazy, cached hex walkability grid for one zone. Pointy-top axial layout with
    centre spacing ``GRID_SPACING``. ``node_z`` evaluates+memoizes a node; ``neighbours``
    and ``node_z`` are everything A* nav needs."""

    def __init__(self, world, zone_name, extra_shapes, player_radius, spacing=GRID_SPACING):
        self.spacing = spacing
        self.mesh = _walkable_mesh(world, zone_name)  # numpy (verts, z, bbox)
        raw_solids = _all_collider_solids(world)
        self.bcd_buf = [(fp.buffer(player_radius), zlo, zhi, box)
                        for fp, zlo, zhi, box in raw_solids]
        self.bcd_tree = STRtree([fp for fp, _, _, _ in self.bcd_buf]) if self.bcd_buf else None
        ev = filter_valid_polygons(extra_shapes) if extra_shapes else []
        self.static_prep = prep(unary_union(ev).buffer(player_radius)) if ev else None
        self._cache: dict = {}       # (q, r) -> teleport-valid ground_z or None
        self._walk_cache: dict = {}  # (q, r) -> walk-valid ground_z or None

    @property
    def has_mesh(self):
        return self.mesh[0].shape[0] > 0

    def to_world(self, q, r):
        return self.spacing * (q + r / 2.0), self.spacing * (_SQRT3 / 2.0) * r

    def to_hex(self, x, y):
        r = (2.0 * y) / (self.spacing * _SQRT3)
        q = x / self.spacing - r / 2.0
        return _hex_round(q, r)

    def ground_z_at(self, x, y, prefer_z=None, strict=False):
        """Teleport-valid ground height at world ``(x, y)``, or None. On walkable navmesh,
        not inside a bcd collider's vertical band (height-aware), and clear of static
        entity colliders.

        ``strict`` drops the ``prefer_z`` shell exemption described below, so every covering
        volume is honoured as a wall. That is *too* strict for general use — the exemption is
        load-bearing for a large share of walkable ground (a scan of nine zones found ~5400
        sampled surfaces that are only teleport-valid because of it, including whole zone
        floors that sit inside a giant bounding BOX) — so it is not a stricter-is-better
        toggle. It exists for one purpose: re-solving after the *game* has rejected a landing,
        where we know something solid is there that the exemption excused. See
        ``teleport_math.collision_tp``.

        With ``prefer_z`` (the goal's own feet height) the surface returned is the clear
        walkable level *closest to the goal's height* — i.e. the floor the goal is actually
        standing on. This is what disambiguates stacked multi-level XYs: an upper-floor target
        (high ``prefer_z``) keeps the upper surface even when ground-floor navmesh sits at the
        same XY hundreds of units below, and vice-versa. (The earlier directional min/max pick
        collapsed to the wrong floor whenever the target's own surface rounded a hair onto the
        wrong side of ``prefer_z`` — a 1u boundary error that dropped teleports a whole floor.)

        A collider whose vertical band *contains* ``prefer_z`` is treated as NOT walling off
        this floor: the target is a real, reachable game position sitting inside that volume, so
        it's a coarse structural/terrain shell the body occupies (a tower's bounding BOX, a
        terrain cylinder), not a wall — otherwise the whole floor inside it reads as blocked.

        Without ``prefer_z`` the legacy lowest-first surface is returned, so callers that don't
        pass it (e.g. the walk-nav node cache) are unchanged."""
        if self.static_prep is not None and self.static_prep.contains(Point(x, y)):
            return None  # on/next to a teleporter pad, boat, etc.
        levels = _mesh_levels_at(x, y, self.mesh)
        if not levels:
            return None
        pt = Point(x, y)
        covering = [self.bcd_buf[i] for i in self.bcd_tree.query(pt)] if self.bcd_tree is not None else []
        covering = [(zlo, zhi, box) for fp, zlo, zhi, box in covering if fp.contains(pt)]
        if prefer_z is not None and not strict:
            # A volume the target itself stands inside is a shell, not a wall for this floor.
            covering = [(zlo, zhi, box) for (zlo, zhi, box) in covering
                        if not (zlo <= prefer_z <= zhi)]
        clear = [z for z in levels  # surfaces a teleport can land on (body not in a collider)
                 if not any(_collider_blocks_foot(z, zlo, zhi, box) for zlo, zhi, box in covering)]
        if not clear:
            return None
        if prefer_z is None:
            return clear[0]  # lowest-first (legacy: ground under any overhead collider)
        return min(clear, key=lambda z: abs(z - prefer_z))  # the goal's own floor

    def node_z(self, q, r):
        """Ground z at node ``(q, r)`` if walkable, else None. Evaluated once, memoized."""
        v = self._cache.get((q, r), 0)  # 0 sentinel = unevaluated (z can be 0.0)
        if v != 0:
            return v if v is not None else None
        x, y = self.to_world(q, r)
        z = self.ground_z_at(x, y)
        self._cache[(q, r)] = z
        return z

    def neighbours(self, q, r):
        return [(q + dq, r + dr) for dq, dr in _HEX_DIRS]

    def closest_walkable(self, target, max_rings=300, strict=False):
        """Nearest walkable node to ``target`` as ``(x, y, z)``, by expanding-ring search
        (evaluate on demand, stop once no farther ring could beat the best). None if the
        whole searched area is blocked.

        Nodes are ranked by ``dxy + Z_RANK_WEIGHT * |surface_z - target.z|``, not XY distance
        alone: when the target's own XY is unwalkable (e.g. under an overhang) the nearest node
        in the plane can be on the *wrong floor* directly below/above the target, so a small
        cross-floor Z penalty steers the pick to the node on the target's actual floor even if
        it's a bit farther in XY. Same-floor nodes have ~zero Z term, so within a floor this is
        still nearest-XY. The ring prune stays valid because cost >= dxy.

        Each node is evaluated *only* through the ``prefer_z``-aware ``ground_z_at`` — NOT
        pre-gated on ``node_z`` (which is ``prefer_z``-less). A node on the target's own raised
        floor sits inside that floor's shell volume (a tower's bounding cylinder), which the
        ``prefer_z``-less check reads as a wall and rejects — so pre-gating on ``node_z`` threw
        away the correct-floor candidate and forced a landing a whole floor away (Ravenwood's Ice
        tower: target off-mesh at z=116, correct platform node 40u out at z=102 skipped, landing
        355u out on the z=21 ground). Ranking directly on ``ground_z_at(prefer_z)`` keeps it."""
        q0, r0 = self.to_hex(target.x, target.y)
        best, best_cost = None, None
        for k in range(max_rings + 1):
            if best_cost is not None and (k - 1) * self.spacing > best_cost:
                break  # no node this far out can beat the best cost (cost >= dxy)
            for (q, r) in _hex_ring(q0, r0, k):
                x, y = self.to_world(q, r)
                z = self.ground_z_at(x, y, prefer_z=target.z, strict=strict)  # goal's surface
                if z is not None:
                    cost = math.hypot(x - target.x, y - target.y) + Z_RANK_WEIGHT * abs(z - target.z)
                    if best_cost is None or cost < best_cost:
                        best, best_cost = (x, y, z), cost
        return best

    # --- walking (more permissive than teleport-valid) + A* nav ---

    def walk_z(self, q, r):
        """Ground z at ``(q, r)`` if you can WALK there, else None. More permissive than
        ``node_z``: on raw navmesh and clear of static entity colliders (teleporter pads/
        boats), but it does NOT exclude bcd-collider interiors — a chamber cylinder's ramp
        is walkable even though a teleport landing inside it bounces. Memoized."""
        v = self._walk_cache.get((q, r), 0)
        if v != 0:
            return v if v is not None else None
        x, y = self.to_world(q, r)
        if self.static_prep is not None and self.static_prep.contains(Point(x, y)):
            z = None
        else:
            levels = _mesh_levels_at(x, y, self.mesh)
            z = levels[0] if levels else None
        self._walk_cache[(q, r)] = z
        return z

    def _nearest_walk_node(self, q0, r0, max_rings=40):
        for k in range(max_rings + 1):
            for (q, r) in _hex_ring(q0, r0, k):
                if self.walk_z(q, r) is not None:
                    return (q, r)
        return None

    def find_walk_path(self, start_xyz, goal_xyz, max_nodes=20000):
        """A* over WALK-valid hex nodes from ``start`` to ``goal``. Returns ``[(x, y, z), …]``
        waypoints (start node first, goal node last), or None if unreachable on foot.
        Endpoints are snapped to the nearest walk-valid node. Evaluated lazily — only the
        nodes A* touches are probed (and memoized for the zone)."""
        sq = self.to_hex(start_xyz.x, start_xyz.y)
        if self.walk_z(*sq) is None:
            sq = self._nearest_walk_node(*sq)
        gq = self.to_hex(goal_xyz.x, goal_xyz.y)
        if self.walk_z(*gq) is None:
            gq = self._nearest_walk_node(*gq)
        if sq is None or gq is None:
            return None
        if sq == gq:
            x, y = self.to_world(*sq)
            return [(x, y, self.walk_z(*sq))]
        gxw, gyw = self.to_world(*gq)

        def _h(node):
            x, y = self.to_world(*node)
            return math.hypot(x - gxw, y - gyw)

        open_heap = [(_h(sq), 0.0, sq)]
        came = {sq: None}
        gscore = {sq: 0.0}
        seen = set()
        n_expanded = 0
        while open_heap and n_expanded < max_nodes:
            _, gc, cur = heapq.heappop(open_heap)
            if cur in seen:
                continue
            seen.add(cur)
            n_expanded += 1
            if cur == gq:
                path = []
                node = cur
                while node is not None:
                    x, y = self.to_world(*node)
                    path.append((x, y, self.walk_z(*node)))
                    node = came[node]
                path.reverse()
                return path
            for nb in self.neighbours(*cur):
                if nb in seen or self.walk_z(*nb) is None:
                    continue
                ng = gc + self.spacing
                if nb not in gscore or ng < gscore[nb]:
                    gscore[nb] = ng
                    came[nb] = cur
                    heapq.heappush(open_heap, (ng + _h(nb), ng, nb))
        return None


def get_walk_grid(world: CollisionWorld, zone_name: str | None, extra_shapes=None,
                  player_radius: float = 45.0) -> "_ZoneWalkGrid":
    """The zone's lazy hex walkability grid, memoized. Pass ``extra_shapes`` = the zone's full
    static footprints (``build_zone_static_shapes(zone, None)``)."""
    g = _walk_grid_cache.get(zone_name) if zone_name is not None else None
    if g is None:
        g = _ZoneWalkGrid(world, zone_name, extra_shapes, player_radius)
        if zone_name is not None:
            _walk_grid_cache[zone_name] = g
    return g


def blocking_volumes_at(world: CollisionWorld, zone_name: str | None, target: XYZ,
                        player_radius: float = 45.0, extra_shapes=None) -> list:
    """Footprints of the bcd volumes that wall off ``target``'s own surface but are excused
    by the ``prefer_z`` shell rule — i.e. exactly what a rejected teleport ran into.

    Used to keep the post-teleport walk from pathing *through* the thing that just bounced
    us. Empty when nothing covers the target, which is the usual case."""
    grid = get_walk_grid(world, zone_name, extra_shapes, player_radius)
    if grid.bcd_tree is None:
        return []
    pt = Point(target.x, target.y)
    out = []
    for i in grid.bcd_tree.query(pt):
        fp, zlo, zhi, box = grid.bcd_buf[i]
        if not fp.contains(pt):
            continue
        if zlo <= target.z <= zhi and _collider_blocks_foot(target.z, zlo, zhi, box):
            out.append(fp)
    return out


def find_walkable_teleport_point(world: CollisionWorld, zone_name: str | None, target: XYZ,
                                 extra_shapes=None, player_radius: float = 45.0,
                                 spacing: float = GRID_SPACING, strict: bool = False):
    """Closest teleport-valid point to ``target``: the target itself when it's walkable (at its
    true ground height), else the nearest walkable hex node found by lazy expanding-ring search.
    Returns ``(XYZ, reason)`` or ``(None, reason)``.

    The exact target is tested first so a clear target lands precisely on it; a *blocked* target
    — or one whose only walkable surface at that XY is a whole floor off (the target sits under
    an overhang / in a mesh gap, so the surface there belongs to a different level) — falls to
    the hex grid, where the ring search finds a node on the target's own floor and the
    post-teleport walk closes the remaining gap. Only the nodes near the target are evaluated
    (and cached for the zone) — no full-zone sweep."""
    grid = get_walk_grid(world, zone_name, extra_shapes, player_radius)
    if not grid.has_mesh:
        return None, "no_mesh"
    suffix = "_strict" if strict else ""

    tz = grid.ground_z_at(target.x, target.y, prefer_z=target.z, strict=strict)
    if tz is not None and abs(tz - target.z) <= FLOOR_MATCH_TOL:
        return XYZ(target.x, target.y, tz), "target_clear" + suffix

    best = grid.closest_walkable(target, strict=strict)
    if best is None:
        return None, "no_walkable" + suffix
    return XYZ(best[0], best[1], best[2]), "grid_node" + suffix


# Unioned walkable navmesh per zone. Building it from the raw triangles (~15k in a
# big zone) costs ~1.5s, and it never changes within a session, so we memoize it.
_navmesh_cache: dict[str, object] = {}


def build_mesh_shapes(world: CollisionWorld, z_slice: float | None = None) -> List[Polygon]:
    """Build the *real* walkable navmesh footprints (actual triangle faces).

    This used to take the convex hull of each mesh proxy, which over-stated the
    walkable area ~2.3x — filling in building interiors, fountains and courtyards
    that aren't walkable. The solver then happily placed teleports in that fake
    area (and the inflated mesh, eroded by the player radius, threw points far from
    the target). We now union the actual WALKABLE triangle faces, i.e. the game's
    true walkable surface. ``z_slice`` is unused (the mesh is taken whole) but kept
    for signature compatibility.
    """
    shapes = []
    for obj in world.objects:
        if obj.proxy == ProxyType.MESH and CollisionFlag.WALKABLE in obj.category_flags:
            pts3d = transformCube(obj.vertices, obj.location, obj.rotation)
            tris = []
            for face in obj.faces:
                a, b, c = face
                try:
                    tri = Polygon([
                        (pts3d[a][0], pts3d[a][1]),
                        (pts3d[b][0], pts3d[b][1]),
                        (pts3d[c][0], pts3d[c][1]),
                    ])
                    if tri.is_valid and tri.area > 0:
                        tris.append(tri)
                except Exception:
                    continue
            if tris:
                # Merge each proxy's own faces once; far cheaper than a single
                # global union of every triangle in the zone.
                shapes.append(unary_union(tris))
    return shapes


def _walkable_union(world: CollisionWorld, zone_name: str | None):
    """The unioned walkable navmesh polygon, memoized per zone."""
    if zone_name is not None:
        cached = _navmesh_cache.get(zone_name)
        if cached is not None:
            return cached
    shapes = filter_valid_polygons(build_mesh_shapes(world))
    union = unary_union(shapes) if shapes else Polygon()
    if zone_name is not None:
        _navmesh_cache[zone_name] = union
    return union


def _walkable_minus_walls(union_mesh, walls, player_radius: float):
    """Navmesh with ``walls`` (dilated by the player's clearance) carved out.

    Dilating the *walls* and subtracting them — rather than eroding the whole free
    area — keeps the navmesh's own outer edges intact (you can still stand at the
    lip of a platform) while guaranteeing the body clears every wall. ``walls`` is the
    height-aware bcd wall region (``zone_bcd_walls``) unioned with the static entity
    colliders. If full clearance leaves nothing reachable, the clearance is relaxed
    step-wise rather than failing outright: a snug landing beats none.
    """
    if walls.is_empty:
        return union_mesh
    for clearance in (player_radius, player_radius * 0.5, 0.0):
        carved = walls.buffer(clearance) if clearance > 0 else walls
        region = union_mesh.difference(carved)
        if not region.is_empty:
            return region
    return None


def straight_path_walkable(world, zone_name, start_xyz, target_xyz,
                           static_shapes=None, player_radius: float = 0.0, step: float = 50.0):
    """Whether the straight XY segment ``start -> target`` stays on walkable ground —
    i.e. whether ``client.goto`` (a dumb straight-line walk) can cover it.

    Uses the *raw* walkable navmesh (NOT minus ``collision.bcd`` walls): walking is
    navmesh-validated and passes straight through teleport-blocking-but-walkable volumes
    like the WC Drains chamber cylinders, so those must not count against the walk. Static
    *entity* colliders (``static_shapes`` — teleporter pads, boats), however, DO block: we
    must never walk onto a pad we deliberately teleported clear of (it would bounce/warp),
    so they're subtracted (buffered by ``player_radius``). Returns True only if every
    sampled point, endpoint included, is on that region. Pure CPU — run off the loop.
    """
    mesh = _walkable_union(world, zone_name)
    if mesh.is_empty:
        return False
    region = mesh
    if static_shapes:
        sv = filter_valid_polygons(static_shapes)
        if sv:
            blockers = unary_union(sv)
            if player_radius > 0:
                blockers = blockers.buffer(player_radius)
            region = mesh.difference(blockers)
    if region.is_empty:
        return False
    in_region = prep(region)
    dx, dy = target_xyz.x - start_xyz.x, target_xyz.y - start_xyz.y
    total = math.hypot(dx, dy)
    if total < 1e-6:
        return True
    ux, uy = dx / total, dy / total
    d = 0.0
    while d <= total:
        if not in_region.contains(Point(start_xyz.x + ux * d, start_xyz.y + uy * d)):
            return False
        d += step
    return in_region.contains(Point(target_xyz.x, target_xyz.y))


def find_safe_collision_point(world: CollisionWorld, target: XYZ, player_radius: float,
                              extra_shapes=None, zone_name: str | None = None):
    """The point *closest* to ``target`` that is walkable and clear of walls.

    Returns ``(xyz, reason)``:
      - ``(target, "target_clear")``    target is already walkable & wall-clear,
      - ``(safe_point, "safe_point")``  nearest walkable point with wall clearance,
      - ``(None, reason)``              no navmesh / nothing walkable to land on.

    Walls (zone collision footprints + ``extra_shapes`` static colliders) are dilated
    by ``player_radius`` and subtracted from the real walkable navmesh, so the result
    is on walkable ground, keeps the body off every wall, and is as close to ``target``
    as the geometry allows. ``zone_name`` enables the per-zone navmesh cache. Pure CPU
    work — run off the event loop.
    """
    union_mesh = _walkable_union(world, zone_name)
    if union_mesh.is_empty:
        return None, "no_mesh"

    bcd_walls = zone_bcd_walls(world, zone_name)
    extra_valid = filter_valid_polygons(extra_shapes) if extra_shapes else []
    extra_coll = unary_union(extra_valid) if extra_valid else Polygon()
    walls = unary_union([w for w in (bcd_walls, extra_coll) if not w.is_empty]) if (
        not bcd_walls.is_empty or not extra_coll.is_empty) else Polygon()

    walkable = _walkable_minus_walls(union_mesh, walls, player_radius)
    if walkable is None or walkable.is_empty:
        return None, "no_walkable"

    tp = Point(target.x, target.y)
    if walkable.contains(tp):
        return XYZ(target.x, target.y, target.z), "target_clear"

    _, candidate = nearest_points(tp, walkable)
    # The relocated landing can be at a very different height than the target — e.g. on the
    # lower part of a ramp that passes *under* a chamber cylinder. Teleporting there at the
    # target's z would put us back inside that cylinder (bounce), so use the actual ground
    # height at the landing (the teleport-valid level below the obstacle), falling back to
    # target.z only if the navmesh can't be sampled.
    gz = _ground_z_at(world, zone_name, candidate.x, candidate.y)
    return XYZ(candidate.x, candidate.y, gz if gz is not None else target.z), "safe_point"
