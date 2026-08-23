import json
import math
import os
import re
import threading
from pathlib import Path
from xml.etree import ElementTree as etree

from loguru import logger
from shapely.affinity import affine_transform, rotate, scale, translate
from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import unary_union
from wizwalker.utils import get_wiz_install

# katsuba + kinif + wiztype are best-effort: if any is missing we degrade to
# bounding-box entity collision rather than breaking collision TP entirely.
try:
    import kinif
    import wiztype
    from katsuba.op import (
        STATEFUL_FLAGS,
        LazyList,
        LazyObject,
        Serializer,
        SerializerOptions,
        TypeList,
    )
    from katsuba.wad import Archive

    _PRECISE_AVAILABLE = True
except Exception:  # pragma: no cover - import-time capability probe
    _PRECISE_AVAILABLE = False

# WADs to search for a model whose asset path has no |Source| prefix.
_FALLBACK_WADS = [
    "Mob-WorldData.wad",
    "Mob2-WorldData.wad",
    "_Shared-WorldData.wad",
    "Root.wad",
]

# Bounding-circle radius for a static object whose model can't be resolved to a
# footprint (e.g. the Universe teleport, which only references a blank-character
# placeholder NIF). Big enough to keep a teleport off the object, small enough not to
# wall off the area around it.
_DEFAULT_STATIC_RADIUS = 150.0

# A placed object whose footprint spans more than this (world units, widest side) is a
# zone-scale environment mesh — a barrier shell, the foliage/tree layer, a skybox — placed
# at the origin as one sprawling model. Its convex hull is the whole zone, so treating it as
# a solid collider walls off the entire floor (Khrysalis KR_Z00_Hub: KR_Z00_Barrier r~11025,
# the dead/live tree meshes r~6600–7700). These aren't discrete obstacles and the walkable
# navmesh already bounds movement, so they're dropped from the static-collider set.
_MAX_STATIC_SPAN = 4000.0

# Teleporter / dock-warp pads (templates named ``<WORLD>-TELEPORT-<PLACE>``) are
# solid in-game — landing a teleport on one rubber-bands you — but their template
# carries an *empty* render asset and an empty ``m_solidCollisionFilename``, so
# nothing links them to a model and the solver treats the spot as walkable. Their
# model lives at a predictable StateObject path keyed off the world prefix, e.g.
# ``AZ-TELEPORT-ZULTUNDOCK`` -> ``StateObjects/AZ_Teleporter/AZ_Teleporter.nif``
# (hull radius ~230u, matching the observed bounce). We resolve that and mark the
# object collidable. If the model can't be read we fall back to a disc this big.
_TELEPORT_FALLBACK_RADIUS = 220.0


def _parse_collision_xml(data: bytes) -> tuple[list | None, int, int]:
    """Parse a KI collision file (``<world><primitive>…``, the same schema
    ``CollisionWorld.save_xml`` emits) into a model-local 2D movement footprint.

    Returns ``(points, n_total, n_click)``:
      - ``points``  convex-hull outline ``[(x, y), …]`` of the *movement* primitives
        (boxes/spheres/cylinders projected to the horizontal plane, each placed by its
        own local transform), or None if there are none. Same shape ``footprint_points``
        yields from a render NIF, so the placement pipeline is unchanged.
      - ``n_total`` primitives seen, ``n_click`` of them interaction click-boxes.

    Click-boxes (primitives whose name contains "click", e.g. ``PlayerClickBox_collision``)
    are *interaction triggers you approach to activate* — boat/dock travel points, NPC
    hit-boxes — not walls. They're excluded from the footprint so we don't shove a teleport
    away from something the bot needs to be next to; the counts let the caller decide a
    click-only object isn't a movement obstacle at all.
    """
    try:
        from .collision_math import transformCube, toCubeVertices
    except Exception:
        return None, 0, 0
    try:
        root = etree.fromstring(data)
    except Exception:
        return None, 0, 0
    polys = []
    n_total = n_click = 0
    for prim in root.findall("primitive"):
        n_total += 1
        if "click" in (prim.get("name") or "").lower():
            n_click += 1
            continue
        ptype = (prim.get("type") or "").lower()
        loc_el = prim.find("location")
        lx = float(loc_el.get("x", 0)) if loc_el is not None else 0.0
        ly = float(loc_el.get("y", 0)) if loc_el is not None else 0.0
        lz = float(loc_el.get("z", 0)) if loc_el is not None else 0.0
        rot_el = prim.find("rotation")
        if rot_el is not None and rot_el.get("matrix"):
            try:
                rot = tuple(float(x) for x in rot_el.get("matrix").split())
            except Exception:
                rot = (1, 0, 0, 0, 1, 0, 0, 0, 1)
        else:
            rot = (1, 0, 0, 0, 1, 0, 0, 0, 1)
        try:
            if ptype == "box":
                dim = prim.find("dimensions")
                l, w, d = float(dim.get("l")), float(dim.get("w")), float(dim.get("d"))
                world_pts = transformCube(toCubeVertices((l, w, d)), (lx, ly, lz), rot)
                poly = Polygon([(p[0], p[1]) for p in world_pts]).convex_hull
            elif ptype == "sphere":
                r = float(prim.find("radius").get("value"))
                poly = Point(lx, ly).buffer(r)
            elif ptype in ("cylinder", "tube"):
                el = prim.find(ptype)
                r = float(el.get("radius"))
                poly = Point(lx, ly).buffer(r)
            else:
                continue  # plane/ray/mesh: not used as a horizontal footprint here
        except Exception:
            continue
        if poly is not None and not poly.is_empty:
            polys.append(poly)
    if not polys:
        return None, n_total, n_click
    hull = unary_union(polys).convex_hull
    if hull.geom_type != "Polygon" or hull.is_empty:
        return None, n_total, n_click
    return list(hull.exterior.coords), n_total, n_click


# Collision-file primitive categories that do NOT obstruct player *movement* (a teleport may
# land where they overlap). The game flags solid, player-blocking geometry as ``CT_Object`` or
# ``CT_None`` (the default for walls/props — barriers, trees, boats, teleporter pads all use it).
# ``CT_ClientObject`` is client-side-only collision — e.g. the ``BigGenericBlocker`` volumes
# (1360x2117x500 boxes) that blanket Arcanum interiors over walkable floor; the player walks
# straight through them. Trigger/hitscan/fog are non-physical. Excluding these is the category
# generalisation of the click-box name test (an interaction click-box is just a named trigger).
_NON_MOVEMENT_CATEGORIES = {"CT_ClientObject", "CT_Trigger", "CT_Hitscan", "CT_Fog"}


def _collision_primitives(data: bytes) -> tuple:
    """Parse a collision file ONCE into ``(prims, n_total, n_nonblock, n_category)`` where ``prims`` is
    ``[(local_2d_polygon, z_min, z_max, is_mesh), ...]`` — one entry PER movement-blocking primitive,
    NOT a single convex hull. ``is_mesh`` marks a convex-hulled MESH primitive so the placer can
    span-guard it (a concave environment mesh hulls into a floor-spanning blob).

    This is the authoritative collision geometry (``m_solidCollisionFilename``). Keeping each
    box/cylinder/sphere separate is the whole point: a forest's collision is 30-odd trunk
    cylinders scattered across the zone, and a barrier's is one small box — convex-hulling them
    (as the render-mesh path does) collapses them into a zone-spanning blob that walls off the
    floor. Non-movement primitives — interaction click-boxes AND ``_NON_MOVEMENT_CATEGORIES``
    (e.g. ``CT_ClientObject`` blockers) — are counted in ``n_nonblock`` but excluded from
    ``prims``, so one parse answers both "what blocks?" and "is this purely non-blocking?" (an
    object whose every primitive is non-blocking isn't a movement obstacle). Each entry carries
    the primitive's world-vertical extent for height-aware code. Local units."""
    try:
        from .collision_math import transformCube, toCubeVertices
    except Exception:
        return [], 0, 0, 0
    try:
        root = etree.fromstring(data)
    except Exception:
        return [], 0, 0, 0
    out = []
    n_total = n_nonblock = n_category = 0
    for prim in root.findall("primitive"):
        n_total += 1
        is_click = "click" in (prim.get("name") or "").lower()
        is_noncat = (prim.get("category") or "") in _NON_MOVEMENT_CATEGORIES
        if is_click or is_noncat:
            n_nonblock += 1
            if is_noncat:
                n_category += 1  # CT_ClientObject etc.: authoritatively non-player-movement
            continue
        ptype = (prim.get("type") or "").lower()
        loc_el = prim.find("location")
        lx = float(loc_el.get("x", 0)) if loc_el is not None else 0.0
        ly = float(loc_el.get("y", 0)) if loc_el is not None else 0.0
        lz = float(loc_el.get("z", 0)) if loc_el is not None else 0.0
        rot_el = prim.find("rotation")
        if rot_el is not None and rot_el.get("matrix"):
            try:
                rot = tuple(float(x) for x in rot_el.get("matrix").split())
            except Exception:
                rot = (1, 0, 0, 0, 1, 0, 0, 0, 1)
        else:
            rot = (1, 0, 0, 0, 1, 0, 0, 0, 1)
        try:
            if ptype == "box":
                dim = prim.find("dimensions")
                l, w, d = float(dim.get("l")), float(dim.get("w")), float(dim.get("d"))
                world_pts = transformCube(toCubeVertices((l, w, d)), (lx, ly, lz), rot)
                poly = Polygon([(p[0], p[1]) for p in world_pts]).convex_hull
                zmin, zmax = lz - d / 2, lz + d / 2
            elif ptype == "sphere":
                r = float(prim.find("radius").get("value"))
                poly = Point(lx, ly).buffer(r, quad_segs=4)  # 16-gon: ample for a collider
                zmin, zmax = lz - r, lz + r
            elif ptype in ("cylinder", "tube"):
                el = prim.find(ptype)
                r = float(el.get("radius"))
                hl = float(el.get("length", 0)) / 2
                poly = Point(lx, ly).buffer(r, quad_segs=4)
                zmin, zmax = lz - hl, lz + hl
            elif ptype == "mesh":
                # A collision MESH (gate/portcullis/door slab, irregular prop). Project its
                # transformed vertices to the plane and convex-hull them: a slab -> a thin
                # blocking rectangle, exactly what the doorway needs. A large *concave*
                # environment mesh would hull into a floor-spanning blob, but its placed span
                # is caught by the ``_MAX_STATIC_SPAN`` guard in ``zone_static_objects`` (it
                # then falls back to the render hull, which is itself span-capped). Verts are in
                # this primitive's own local frame, so apply its location/rotation like a box.
                mesh_el = prim.find("mesh")
                vlist = mesh_el.find("vertexlist") if mesh_el is not None else None
                if vlist is None:
                    continue
                mv = [(float(v.get("x", 0)), float(v.get("y", 0)), float(v.get("z", 0)))
                      for v in vlist.findall("vert")]
                if len(mv) < 3:
                    continue
                wp = transformCube(mv, (lx, ly, lz), rot)
                poly = Polygon([(p[0], p[1]) for p in wp]).convex_hull
                if poly.geom_type != "Polygon":
                    continue  # collinear projection (zero-thickness vertical sheet): nothing to block
                mz = [p[2] for p in wp]
                zmin, zmax = min(mz), max(mz)
            else:
                continue  # plane/ray
        except Exception:
            continue
        if poly is not None and poly.is_valid and not poly.is_empty:
            out.append((poly, zmin, zmax, ptype == "mesh"))
    return out, n_total, n_nonblock, n_category


def _is_teleporter_name(name: str) -> bool:
    """Whether a template name marks a solid teleporter/dock-warp pad."""
    return bool(name) and "TELEPORT" in name.upper().split("-")


def _teleporter_model_asset(name: str) -> str | None:
    """Predictable StateObject model path for a ``<WORLD>-TELEPORT-…`` pad.

    The shared per-world teleporter model: ``AZ-TELEPORT-ZULTUNDOCK`` ->
    ``StateObjects/AZ_Teleporter/AZ_Teleporter.nif``. Returns None if ``name``
    has no world prefix.
    """
    prefix = name.split("-", 1)[0] if name else ""
    if not prefix:
        return None
    return f"StateObjects/{prefix}_Teleporter/{prefix}_Teleporter.nif"


def _footprint_cache_path(revision: str) -> Path:
    """Writable, per-revision footprint cache location (alongside Deimos settings)."""
    appdata = os.environ.get("APPDATA", "")
    base = Path(appdata) / "Deimos" if appdata else Path(os.getcwd())
    return base / "footprint_cache" / (revision.replace(".", "_") + ".json")


def _client_version(revision: str) -> str:
    """The client-version component of a revision string, e.g.
    ``r803238.Wizard_1_610`` -> ``Wizard_1_610``.

    The property/type tree is compiled into the client executable and only changes on a
    client-version bump — every ``r80xxxx.Wizard_1_610`` *build* (a content patch) shares one
    tree. So this, not the build number, is the correct key for the type-list cache: it lets one
    dump serve every build of a version instead of forcing a fresh (and, when wiztype's signature
    is stale for the new build, hanging) re-pull on each content patch. Falls back to the whole
    string if there's no ``build.version`` split."""
    return revision.split(".", 1)[1] if "." in revision else revision


def _typelist_cache_path(key: str) -> Path:
    """Writable katsuba TypeList location (alongside Deimos settings), keyed by ``key`` (the
    client version, e.g. ``Wizard_1_610`` — see ``_client_version``)."""
    appdata = os.environ.get("APPDATA", "")
    base = Path(appdata) / "Deimos" if appdata else Path(os.getcwd())
    return base / "types" / (key.replace(".", "_") + ".json")


def _typelist_is_loadable(path: Path) -> bool:
    """Cheap validity probe: the cached dump exists, is non-empty, and katsuba can
    open it. Catches a corrupt/half-written cache so we re-dump instead of choking."""
    try:
        return path.exists() and path.stat().st_size > 0 and bool(TypeList.open(str(path)))
    except Exception:
        return False


def _dump_type_list(revision: str, path: Path) -> None:
    """Pull a fresh type dump from the running client and write it to ``path`` (atomic).

    Requires a live WizardGraphicalClient. Raises with an actionable message when
    wiztype can't read the client's type tree — that means the client was patched
    and wiztype's memory signature is stale, which a re-dump cannot fix.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        f"[entity_collision] pulling a fresh type dump for revision {revision} "
        f"from the running client via wiztype (one-time, ~10-30s)"
    )
    try:
        tree = wiztype.get_type_tree()
    except Exception as e:
        raise RuntimeError(
            f"wiztype could not read the client's type tree "
            f"({type(e).__name__}: {e}); the client was likely patched and wiztype's "
            f"memory signature is stale — upgrade wiztype "
            f"(`uv lock --upgrade-package wiztype && uv sync`)"
        ) from e
    tmp = path.with_suffix(".tmp")
    wiztype.JsonTypeDumperV1(tree).dump(tmp, indent=None)
    tmp.replace(path)
    logger.info(
        f"[entity_collision] type list cached at {path} "
        f"({path.stat().st_size // (1024 * 1024)} MB)"
    )


def _extract_nif_asset(template) -> str | None:
    """Find the first `.nif` m_assetName in a deserialized template's behaviors."""
    try:
        behaviors = template["m_behaviors"]
    except Exception:
        return None
    if not isinstance(behaviors, LazyList):
        return None
    for behavior in behaviors:
        if not isinstance(behavior, LazyObject):
            continue
        try:
            asset = behavior["m_assetName"]
        except Exception:
            continue
        if isinstance(asset, (bytes, bytearray)):
            asset = asset.decode("latin-1", "replace")
        if isinstance(asset, str) and asset.lower().endswith(".nif"):
            return asset
    return None


def _solid_collision_filename(template) -> str | None:
    """The template's active ``m_solidCollisionFilename`` (a separate collision-geometry
    file), or None. Many placed objects — boats, doors, dock pads — carry an empty render
    asset but reference their real collision shape here (often a shared proxy like
    ``MB_FactoryDoor_Collision.xml``), so this is the authoritative footprint source."""
    try:
        behaviors = template["m_behaviors"]
    except Exception:
        return None
    if not isinstance(behaviors, LazyList):
        return None
    for behavior in behaviors:
        if not isinstance(behavior, LazyObject):
            continue
        try:
            solid = behavior["m_solidCollisionFilename"]
        except Exception:
            continue
        if isinstance(solid, (bytes, bytearray)):
            solid = solid.decode("latin-1", "replace")
        if solid:  # non-empty -> has solid collision geometry
            try:
                disabled = bool(behavior["m_bDisableCollision"])
            except Exception:
                disabled = False
            if not disabled:
                return solid
    return None


def _has_solid_collision(template) -> bool:
    """Whether a template is a solid obstacle the player can't walk through."""
    return _solid_collision_filename(template) is not None


class _Resolver:
    """Process-wide, lazily-initialized model-footprint resolver."""

    def __init__(self):
        # Reentrant: zone_static_objects() holds the lock while calling footprint_points().
        self._lock = threading.RLock()
        self._state = None  # None=untried, True=ready, False=unavailable
        self._serializer = None  # STATEFUL: ObjectData templates + spawnData
        self._world_serializer = None  # plain flags: gamedata.bin + TemplateManifest
        self._root = None
        self._gamedata = None
        self._template_paths: dict[str, str] = {}  # entity name -> ObjectData path
        self._asset_cache: dict[str, str | None] = {}  # entity name -> nif asset
        self._collidable_cache: dict[str, bool] = {}  # entity name -> is solid obstacle
        self._hull_cache: dict[str, list | None] = {}  # asset -> local render-mesh hull points
        # Collision-file dedupe: one filename deserialize, one file read, one parse per object.
        self._solid_fn_cache: dict[str, str | None] = {}  # entity name -> m_solidCollisionFilename
        self._coll_bytes_cache: dict[str, bytes | None] = {}  # filename -> raw collision-file bytes
        self._coll_data_cache: dict[str, tuple] = {}  # entity name -> (prims, n_total, n_nonblock, n_category)
        self._wads: dict[str, object] = {}
        self._id2name: dict[int, str] | None = None  # templateID -> template basename
        self._zone_static_cache: dict[str, list] = {}  # zone -> [(z, footprint), ...]
        # Model footprints are deterministic per NIF and only change on a game update,
        # so the asset/hull caches persist to disk (keyed by revision) — parsing the
        # NIFs is the warm-up cost, and this makes it a one-time-ever cost.
        self._cache_file: Path | None = None
        self._cache_dirty = False
        self._lang_cache: dict[
            tuple[str, str], dict[str, str]
        ] = {}  # (locale, file) -> table
        self._zone_name_cache: dict[
            tuple[str, str], str
        ] = {}  # (zone, locale) -> display

    def _initialize(self) -> bool:
        if self._state is not None:
            return self._state
        # Serialize first-time init across threads: generating the type list (wiztype)
        # is expensive and writes a file, so two callers must not race into it.
        with self._lock:
            if self._state is not None:
                return self._state
            self._state = self._do_initialize()
        return self._state

    def _do_initialize(self) -> bool:
        try:
            if not _PRECISE_AVAILABLE:
                raise RuntimeError("katsuba/kinif/wiztype not available")
            install = Path(get_wiz_install())
            self._gamedata = install / "Data" / "GameData"
            revision = (install / "Bin" / "revision.dat").read_text().strip()

            # Set up the serializers from a type list matching the running client, keyed by
            # CLIENT VERSION (not build) so a content patch reuses an existing dump instead of
            # re-pulling one — see _resolve_type_list.
            self._resolve_type_list(revision)

            self._cache_file = _footprint_cache_path(revision)
            self._load_footprint_cache()

            logger.info(
                f"[entity_collision] precise resolver ready (revision {revision}, "
                f"{len(self._template_paths)} templates, "
                f"{len(self._hull_cache)} cached hulls)"
            )
            return True
        except Exception as e:
            logger.warning(
                f"[entity_collision] precise resolver unavailable ({e}); "
                f"entities will use bounding boxes"
            )
            return False

    def _cached_type_lists(self, version: str | None) -> list[Path]:
        """Existing cached type-list dumps, newest first (by mtime).

        With ``version`` given, only dumps for that client version — the version-keyed name
        (``Wizard_1_610.json``) or legacy build-keyed dumps (``r802307_Wizard_1_610.json``); every
        build of a version shares one type tree, so any is a valid source. With ``version=None``,
        every cached dump regardless of version (the cross-version resilience fallback). Corrupt or
        half-written files are dropped by the cheap loadable probe."""
        d = _typelist_cache_path(version or "_").parent
        try:
            files = [p for p in d.glob("*.json")
                     if (version is None
                         or p.stem == version or p.stem.endswith("_" + version))
                     and _typelist_is_loadable(p)]
        except Exception:
            return []
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def _try_type_list(self, path: Path) -> bool:
        """Build the serializers from ``path`` and confirm they match the client. False on error."""
        try:
            self._setup_serializers(path)
            return self._probe_serializer()
        except Exception:
            return False

    def _resolve_type_list(self, revision: str) -> None:
        """Set up the serializers from a type list matching the running client, or raise.

        Every user's install self-serves this from its OWN client — no maintainer-hosted dump, no
        authoring per patch. The list is keyed by CLIENT VERSION (``Wizard_1_610``), not build
        (``r803238``): wiztype locates the type tree by a pattern scan of the client, so one dump
        serves every ``r80xxxx`` build of a version. Resolution, in order:

        1. Reuse a probe-valid cached dump for THIS client version (fast, offline — the usual
           case, and what makes a content patch a no-op instead of a re-pull that would stall
           ~30s and die on a partial ``ReadProcessMemory`` when wiztype's scan doesn't fit the
           new build).
        2. No same-version dump -> pull a fresh one from the running client (self-serve). Works
           whenever wiztype's pattern scan matches the client — the normal path on a version bump.
        3. Couldn't pull (a client recompile shifted the layout wiztype scans for). Most updates
           don't change the collision types, and any that do change get a NEW property hash we
           simply skip — so the newest dump from a PRIOR version still deserializes what collision
           needs. Reuse it rather than dropping to bounding boxes: teleportation keeps working
           across the update with zero maintainer or user action.

        Only if nothing at all validates do entities fall back to bounding boxes (the caller
        treats the raised error as "resolver unavailable")."""
        version = _client_version(revision)
        # 1) same-version cache.
        for path in self._cached_type_lists(version):
            if self._try_type_list(path):
                logger.info(
                    f"[entity_collision] reusing cached type list '{path.name}' for revision "
                    f"{revision} (client version {version}); no re-pull needed"
                )
                return
        # 2) fresh self-serve pull from the running client.
        fresh = _typelist_cache_path(version)
        try:
            _dump_type_list(revision, fresh)
        except Exception as e:
            logger.warning(f"[entity_collision] live type-list dump failed ({e})")
        else:
            if self._try_type_list(fresh):
                logger.info(
                    f"[entity_collision] dumped a fresh type list for {version} from the client"
                )
                return
            logger.warning("[entity_collision] freshly dumped type list did not validate")
        # 3) cross-version resilience: newest prior dump that still deserializes.
        for path in self._cached_type_lists(None):
            if self._try_type_list(path):
                logger.warning(
                    f"[entity_collision] no type list for {version}; reusing prior dump "
                    f"'{path.name}' (this game update likely didn't change collision types)"
                )
                return
        raise RuntimeError(
            "no usable type list: no cached dump validated and a live wiztype dump was "
            "unavailable (update wiztype if this persists)"
        )

    def _setup_serializers(self, types_path: Path) -> None:
        """(Re)build the serializers, Root archive, and template index from a type list."""
        type_list = TypeList.open(str(types_path))
        opts = SerializerOptions()
        opts.flags |= STATEFUL_FLAGS
        opts.shallow = False
        opts.skip_unknown_types = True
        self._serializer = Serializer(opts, type_list)

        # gamedata.bin and TemplateManifest.xml are serialized without the stateful
        # property-hash flags the templates use; they need their own serializer.
        wopts = SerializerOptions()
        wopts.shallow = False
        wopts.skip_unknown_types = True
        self._world_serializer = Serializer(wopts, type_list)

        self._root = Archive.mmap(str(self._gamedata / "Root.wad"))
        self._template_paths.clear()
        for fp in self._root.iter_glob("ObjectData/**/*.xml"):
            self._template_paths[fp.rsplit("/", 1)[-1][:-4]] = fp
        self._id2name = None  # manifest must be re-read against the new serializer

    def _probe_serializer(self) -> bool:
        """Cheaply confirm the type list matches the client by deserializing a single
        template with the stateful serializer the resolver actually uses. A dump that
        opened fine but doesn't match the client throws or yields None here."""
        try:
            path = next(iter(self._template_paths.values()))
        except StopIteration:
            return False
        try:
            return self._root.deserialize(path, self._serializer) is not None
        except Exception:
            return False

    def _load_footprint_cache(self) -> None:
        """Seed the asset/hull caches from the on-disk footprint cache (best-effort)."""
        try:
            if self._cache_file and self._cache_file.exists():
                data = json.loads(self._cache_file.read_text(encoding="utf-8"))
                self._asset_cache.update(data.get("assets", {}))
                self._collidable_cache.update(data.get("collidable", {}))
                for asset, hull in data.get("hulls", {}).items():
                    self._hull_cache[asset] = [tuple(p) for p in hull] if hull else None
        except Exception as e:
            logger.warning(f"[entity_collision] footprint cache load failed ({e})")

    def _save_footprint_cache(self) -> None:
        """Persist the asset/hull caches to disk if they grew (atomic, best-effort)."""
        if not self._cache_dirty or not self._cache_file:
            return
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "assets": self._asset_cache,
                "collidable": self._collidable_cache,
                "hulls": self._hull_cache,
            }
            tmp = self._cache_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self._cache_file)
            self._cache_dirty = False
        except Exception as e:
            logger.warning(f"[entity_collision] footprint cache save failed ({e})")

    def _open_wad(self, name: str):
        archive = self._wads.get(name)
        if archive is None:
            path = self._gamedata / name
            if not path.exists():
                return None
            archive = Archive.mmap(str(path))
            self._wads[name] = archive
        return archive

    def _read_nif(self, asset: str, zone_name: str | None) -> bytes | None:
        """Resolve a KI asset path to NIF bytes from the appropriate WAD."""
        if asset.startswith("|"):
            parts = asset.strip("|").split("|", 2)
            if len(parts) != 3:
                return None
            source, category, internal = parts
            candidates = [f"{source}-{category}.wad"]
        else:
            internal = asset
            zone_wad = zone_name.replace("/", "-") + ".wad" if zone_name else None
            # Many placed-object models (teleporters, StateObjects) live in the
            # world-level WorldData wad, e.g. "Azteca/AZ_Z00_Zocalo" -> Azteca-WorldData.wad.
            world_wad = (
                (zone_name.split("/")[0] + "-WorldData.wad")
                if zone_name and "/" in zone_name
                else None
            )
            candidates = (
                ([zone_wad] if zone_wad else [])
                + ([world_wad] if world_wad else [])
                + _FALLBACK_WADS
            )

        basename = internal.rsplit("/", 1)[-1]
        for wad_name in candidates:
            archive = self._open_wad(wad_name)
            if archive is None:
                continue
            try:
                return bytes(archive[internal])
            except Exception:
                for fp in archive.iter_glob(f"**/{basename}"):
                    try:
                        return bytes(archive[fp])
                    except Exception:
                        continue
        return None

    def _resolve_template(self, name: str) -> None:
        """Deserialize a template once, caching both its NIF asset and collidability."""
        if name not in self._asset_cache or name not in self._collidable_cache:
            asset = None
            collidable = False
            path = self._template_paths.get(name)
            if path:
                try:
                    template = self._root.deserialize(path, self._serializer)
                    asset = _extract_nif_asset(template)
                    collidable = _has_solid_collision(template)
                except Exception:
                    pass
            self._asset_cache[name] = asset
            self._collidable_cache[name] = collidable
            self._cache_dirty = True
        # Teleporter/dock-warp pads declare no render asset and no solid-collision
        # file, yet they physically bounce you. Point them at the shared per-world
        # teleporter StateObject model and force collidable so the solver routes a
        # teleport clear of the pad in one shot (the empirical retreat is the backstop
        # if even this model is missing — then the wider default disc applies). Applied
        # here (not just on a fresh resolve) so it also corrects entries seeded from an
        # older on-disk footprint cache that recorded them as non-collidable.
        if _is_teleporter_name(name):
            if not self._collidable_cache.get(name):
                self._collidable_cache[name] = True
                self._cache_dirty = True
            if not self._asset_cache.get(name):
                self._asset_cache[name] = _teleporter_model_asset(name)
                self._cache_dirty = True

    def _asset_for(self, name: str) -> str | None:
        # Always route through _resolve_template: it skips the costly deserialize on a
        # cache hit but still applies the teleporter fix-up, which must run even for
        # entries seeded from an older on-disk footprint cache.
        self._resolve_template(name)
        return self._asset_cache[name]

    def is_collidable(self, name: str) -> bool:
        """Whether a placed object named ``name`` is a solid obstacle. Thread-only."""
        self._resolve_template(name)
        return self._collidable_cache[name]

    def _hull_for(self, asset: str, zone_name: str | None) -> list | None:
        if asset not in self._hull_cache:
            hull = None
            data = self._read_nif(asset, zone_name)
            if data:
                try:
                    verts = kinif.geometry_vertices(data)
                except Exception:
                    verts = None
                if verts:
                    poly = MultiPoint([(v[0], v[1]) for v in verts]).convex_hull
                    if poly.geom_type == "Polygon" and not poly.is_empty:
                        hull = list(poly.exterior.coords)
            self._hull_cache[asset] = hull
            self._cache_dirty = True
        return self._hull_cache[asset]

    def _solid_collision_filename_for(self, name: str) -> str | None:
        """The object's ``m_solidCollisionFilename``, deserializing the template once and caching.
        Shared by every collision-file consumer so the template isn't re-deserialized per use."""
        if name not in self._solid_fn_cache:
            fn = None
            path = self._template_paths.get(name)
            if path:
                try:
                    template = self._root.deserialize(path, self._serializer)
                    fn = _solid_collision_filename(template)
                except Exception:
                    fn = None
            self._solid_fn_cache[name] = fn
        return self._solid_fn_cache[name]

    def _collision_data_for(self, name: str, zone_name: str | None) -> tuple:
        """``(prims, n_total, n_nonblock, n_category)`` for an object — ONE deserialize (filename),
        ONE file read, ONE parse, cached per entity name. The single source for every collision-file
        consumer (movement_collidable, the static-placement primitives, the footprint fallback),
        which previously each re-deserialized + re-read + re-parsed the same file. ``n_nonblock`` =
        primitives excluded from ``prims`` (click-box or non-movement category); ``n_category`` =
        the subset excluded for a non-movement CATEGORY (``CT_ClientObject`` etc.)."""
        if name not in self._coll_data_cache:
            data_tuple = ([], 0, 0, 0)
            fn = self._solid_collision_filename_for(name)
            if fn:
                if fn not in self._coll_bytes_cache:
                    self._coll_bytes_cache[fn] = self._read_nif(fn, zone_name)
                raw = self._coll_bytes_cache[fn]
                if raw:
                    data_tuple = _collision_primitives(raw)
            self._coll_data_cache[name] = data_tuple
        return self._coll_data_cache[name]

    def collision_primitives_for(self, name: str, zone_name: str | None) -> list:
        """The object's authoritative collision geometry as ``[(local_2d_polygon, zmin, zmax, is_mesh), …]``
        — one entry per primitive (box/sphere/cylinder/mesh). Empty if no collision file /
        unparseable (read error), in which case the caller falls back to the render-mesh hull."""
        return self._collision_data_for(name, zone_name)[0]

    def movement_collidable(self, name: str, zone_name: str | None) -> bool:
        """Whether a placed object is a *movement* obstacle (a teleport must clear it).

        Stricter than ``is_collidable``: an object whose only collision is an interaction
        click-box (boat/dock travel points, NPC hit-boxes) or a non-movement category
        (``CT_ClientObject`` blockers) is something the bot walks through or approaches to
        activate, not a wall — so it's *not* a movement obstacle and we let teleports land
        where it overlaps.

        A non-movement CATEGORY (``CT_ClientObject`` etc.) is authoritative: an object whose every
        primitive is one of those does NOT obstruct movement even with a render model — it's the
        engine declaring "not player collision". This matters for sprawling blockers like
        ``DM_HowlingLands_Blocker`` (one ``CT_ClientObject`` box + a zone-spanning NIF; trusting the
        render model there blankets the whole zone with that NIF's convex hull). A click-box, by
        contrast, is an interaction trigger that may sit on a genuinely physical object (a
        teleporter pad), so a click-box-only object with a render model still counts — that render
        model / the teleporter override is what blocks it."""
        self._resolve_template(name)
        if not self._collidable_cache.get(name):
            return False
        _prims, n_total, n_nonblock, n_category = self._collision_data_for(name, zone_name)
        if n_total > 0 and n_category >= n_total:
            return False  # every primitive is a non-movement category -> never a wall
        if self._asset_cache.get(name):
            return True  # render/teleporter model -> solid (pads, physical click-box objects)
        if n_total > 0 and n_nonblock >= n_total:
            return False  # click-box-only interaction trigger with no render model
        return True

    def footprint_points(self, name: str, zone_name: str | None) -> list | None:
        """Local-space 2D hull points for an entity's model, or None. Thread-only.

        Prefers the render-NIF hull; when an object has no render asset (boats, dock pads,
        doors that reference only a separate collision file) it falls back to the convex hull of
        that object's collision-file primitives — the real, often much smaller collider —
        instead of an oversized default disc."""
        if not self._initialize():
            return None
        with self._lock:
            asset = self._asset_for(name)
            if asset:
                hull = self._hull_for(asset, zone_name)
                if hull:
                    return hull
            prims = self._collision_data_for(name, zone_name)[0]
            if prims:
                hull = unary_union([p for p, _, _, _ in prims]).convex_hull
                if hull.geom_type == "Polygon" and not hull.is_empty:
                    return list(hull.exterior.coords)
            return None

    def collider_radius(self, template_id: int, zone_name: str | None) -> float | None:
        """Horizontal collider radius of an object's model footprint, or None.

        Resolves ``template_id`` -> template basename (via the manifest) -> the
        model footprint hull (the same path used for static-object collision), then
        returns the radius of the smallest circle enclosing that hull, measured from
        its centroid. This is the object's true *horizontal* extent — for the
        "Player Object" template it's the wizard's footprint radius, not a
        vertical-height proxy. In local model units; scale by the object's scale to
        get world units. Thread-only (acquires the resolver lock, which is reentrant).
        """
        if not self._initialize():
            return None
        with self._lock:
            self._load_manifest()
            name = self._id2name.get(template_id) if self._id2name else None
        if not name:
            return None
        points = self.footprint_points(name, zone_name)
        if not points:
            return None
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        radius = max(math.hypot(p[0] - cx, p[1] - cy) for p in points)
        return radius if radius > 0 else None

    def _load_manifest(self) -> None:
        """Build the templateID -> template basename map from Root.wad's manifest (once)."""
        if self._id2name is not None:
            return
        id2name: dict[int, str] = {}
        try:
            manifest = self._root.deserialize(
                "TemplateManifest.xml", self._world_serializer
            )
            for entry in manifest["m_serializedTemplates"]:
                if entry is None:
                    continue
                tid = entry["m_id"]
                fn = entry["m_filename"]
                if isinstance(fn, (bytes, bytearray)):
                    fn = fn.decode("latin-1", "replace")
                base = fn.rsplit("/", 1)[-1]
                if base.endswith(".xml"):
                    base = base[:-4]
                id2name[tid] = base
        except Exception as e:
            logger.warning(
                f"[entity_collision] could not load TemplateManifest ({e}); "
                f"static objects will use bounding boxes"
            )
        self._id2name = id2name

    def zone_static_objects(self, zone_name: str) -> list:
        """All static placed-object footprints in a zone, as ``[(z, polygon), ...]``.

        Reads the zone's ``gamedata.bin`` object table (whole zone, from files — no
        render dependency), resolves each object's model footprint and places it at the
        object's world transform. Cached per zone. Thread-only.
        """
        if not self._initialize():
            return []
        with self._lock:
            cached = self._zone_static_cache.get(zone_name)
            if cached is not None:
                return cached

            placed: list = []
            precise = 0
            oversized = 0
            try:
                self._load_manifest()
                archive = self._open_wad(zone_name.replace("/", "-") + ".wad")
                if archive is None:
                    self._zone_static_cache[zone_name] = placed
                    return placed

                zone_data = archive.deserialize("gamedata.bin", self._world_serializer)
                for inst in zone_data["m_objectList"]:
                    if inst is None:  # a CoreObjectInfo subtype not in the TypeList
                        continue
                    try:
                        tid = inst["m_templateID.m_full"]
                        loc = inst["m_location"]
                        ori = inst["m_orientation"]
                        obj_scale = inst["m_fScale"] or 1.0
                    except Exception:
                        continue

                    name = self._id2name.get(tid) if self._id2name else None
                    # Only solid *movement* obstacles block the player. Skip everything
                    # else — decorative meshes (archways), walk-on triggers, NPCs (soft
                    # capsule), interaction click-boxes (boat/dock travel points you must
                    # stand next to), and templates we can't resolve — so we don't shove
                    # teleports around things you can walk through or need to reach.
                    if not name or not self.movement_collidable(name, zone_name):
                        continue

                    # Fold scale -> rotate(yaw) -> translate into ONE affine matrix
                    # [a, b, d, e, xoff, yoff] applied per primitive (1 GEOS call instead of 3).
                    _c, _s = math.cos(ori.z), math.sin(ori.z)
                    _mat = (obj_scale * _c, -obj_scale * _s,
                            obj_scale * _s, obj_scale * _c, loc.x, loc.y)

                    def _place_local(local_poly, base_z, _m=_mat):
                        p = affine_transform(local_poly, _m)
                        if p.is_valid and not p.is_empty:
                            placed.append((base_z, p))

                    # PRIMARY: the object's authoritative collision geometry — one shape per
                    # primitive, so a forest stays 30 scattered trunk-discs and a barrier stays
                    # one small box, instead of a single zone-spanning convex hull.
                    prims = self.collision_primitives_for(name, zone_name)
                    if prims:
                        placed_any = False
                        for local_poly, zmin, zmax, is_mesh in prims:
                            if is_mesh:
                                # A convex-hulled MESH: fine for a gate/prop slab, but a large
                                # concave environment mesh hulls into a floor-spanning blob. If the
                                # PLACED hull is that big, skip just it; if that leaves the object
                                # with nothing, fall through to the span-capped render-hull fallback.
                                pm = affine_transform(local_poly, _mat)
                                bx = pm.bounds
                                if max(bx[2] - bx[0], bx[3] - bx[1]) > _MAX_STATIC_SPAN:
                                    continue
                            _place_local(local_poly, loc.z + (zmin + zmax) / 2 * obj_scale)
                            placed_any = True
                        if placed_any:
                            precise += 1
                            continue

                    # FALLBACK: no collision file / read error, or its only primitives were
                    # oversized-mesh hulls we dropped above. Use the render-mesh hull, then a
                    # default disc. The render hull can be a bogus zone-spanning blob for sprawling
                    # models, so the size cap still guards it here.
                    shape = None
                    points = self.footprint_points(name, zone_name)
                    if points:
                        poly = Polygon(points)
                        if poly.is_valid and not poly.is_empty:
                            poly = scale(poly, xfact=obj_scale, yfact=obj_scale, origin=(0, 0))
                            poly = rotate(poly, ori.z, origin=(0, 0), use_radians=True)
                            shape = translate(poly, xoff=loc.x, yoff=loc.y)
                    if shape is None:
                        default_r = (
                            _TELEPORT_FALLBACK_RADIUS
                            if _is_teleporter_name(name)
                            else _DEFAULT_STATIC_RADIUS
                        )
                        shape = Point(loc.x, loc.y).buffer(default_r * obj_scale)

                    if shape is not None and not shape.is_empty:
                        sminx, sminy, smaxx, smaxy = shape.bounds
                        if max(smaxx - sminx, smaxy - sminy) > _MAX_STATIC_SPAN:
                            oversized += 1
                            continue
                        placed.append((loc.z, shape))

                logger.debug(
                    f"[entity_collision] {zone_name}: {len(placed)} static collision shapes "
                    f"from {precise} objects' collision files (+fallbacks), "
                    f"{oversized} oversized hull fallbacks dropped"
                )
            except Exception as e:
                logger.warning(
                    f"[entity_collision] static objects unavailable for {zone_name} ({e})"
                )

            self._save_footprint_cache()  # persist any newly-parsed model footprints
            self._zone_static_cache[zone_name] = placed
            return placed

    def _lang_table(self, langfile: str, locale: str) -> dict[str, str]:
        """Parse and cache a W101 ``.lang`` file from Root.wad.

        Format (UTF-16-LE): a ``1:<File>`` header, then entries of
        ``<key>\\r\\n\\r\\n<value>`` back-to-back — so after the header it's
        ``[key, "", value]`` repeating.
        """
        ck = (locale, langfile)
        table = self._lang_cache.get(ck)
        if table is None:
            table = {}
            try:
                raw = bytes(self._root[f"Locale/{locale}/{langfile}.lang"]).decode(
                    "utf-16-le"
                )
                lines = raw.split("\r\n")
                i = 1  # skip the "1:<File>" header
                while i + 2 < len(lines):
                    key = lines[i].strip()
                    if key:
                        table[key] = lines[i + 2]
                    i += 3
            except Exception:
                pass  # missing/locale-less lang file -> empty table, resolves to None
            self._lang_cache[ck] = table
        return table

    def _resolve_lang(self, token: str, locale: str) -> str | None:
        """Resolve a ``<LangFile>_<key>`` token (e.g. ``WizardZone_00000987``)."""
        if not token or "_" not in token:
            return None
        langfile, key = token.split("_", 1)
        return self._lang_table(langfile, locale).get(key)

    def _resolve_one_zone(self, path: str, locale: str) -> str | None:
        """Display name for exactly this zone path (no parent fallback), or None."""
        try:
            archive = self._open_wad(path.replace("/", "-") + ".wad")
            if archive is None:
                return None
            zone_data = archive.deserialize("gamedata.bin", self._world_serializer)
            token = zone_data["m_zoneDisplayName"]
            if isinstance(token, (bytes, bytearray)):
                token = token.decode("latin-1", "replace")
            return self._resolve_lang(token, locale)
        except Exception as e:
            logger.debug(f"[entity_collision] no display name for {path} ({e})")
            return None

    def zone_display_name(self, zone_name: str, locale: str = "en-US") -> str | None:
        """Canonical display name for a zone path, or None. Thread-safe, cached.

        ``Azteca/AZ_Z00_Zocalo`` -> ``The Zocalo`` via the zone's gamedata.bin
        ``m_zoneDisplayName`` lang token resolved against the Root.wad lang files.

        Zone paths are hierarchical, so if the full path has no display name (e.g. a
        sub-area that ships no gamedata of its own) we walk up to the parent zone; we're
        still physically inside it, so its name is the accurate answer:
        ``Azteca/AZ_Z00_Zocalo/SomeSubArea`` -> ``The Zocalo``.
        """
        if not self._initialize():
            return None
        with self._lock:
            return self._zone_display_walk(zone_name, locale)

    def _zone_display_walk(self, path: str, locale: str) -> str | None:
        ck = (path, locale)
        if ck in self._zone_name_cache:
            return self._zone_name_cache[ck] or None
        name = self._resolve_one_zone(path, locale)
        if not name and "/" in path:
            name = self._zone_display_walk(
                path.rsplit("/", 1)[0], locale
            )  # parent zone
        self._zone_name_cache[ck] = name or ""
        return name

    def world_display_name(
        self, world_segment: str, locale: str = "en-US"
    ) -> str | None:
        """Canonical world name for a path's first segment via WorldNames.lang.

        ``WizardCity`` -> ``Wizard City``, ``DragonSpire`` -> ``Dragonspyre``. Returns
        None for segments not in the table (event/PvP namespaces); the caller decides
        the fallback. Thread-safe, cached (the lang table is parsed once).
        """
        if not self._initialize():
            return None
        with self._lock:
            return self._lang_table("WorldNames", locale).get(world_segment)


_resolver = _Resolver()


def build_zone_static_shapes(
    zone_name: str | None, target_z: float | None = None, z_threshold: float = 700.0
) -> list[Polygon]:
    """In a worker thread: the zone's static-object collision footprints.

    Reads every placed object from the zone's ``gamedata.bin`` (whole zone, from files,
    so colliders outside render range are known before teleporting), resolving each to
    a precise model footprint or a bounding circle. When ``target_z`` is given, objects
    clearly on another floor (``|z - target_z|`` beyond the threshold) are dropped so
    geometry above/below the player doesn't block the solve. Results are cached per zone.
    """
    if not zone_name:
        return []
    placed = _resolver.zone_static_objects(zone_name)
    if target_z is None:
        return [shape for _z, shape in placed]
    return [shape for z, shape in placed if abs(z - target_z) <= z_threshold]


def get_object_collider_radius(template_id: int, zone_name: str | None) -> float | None:
    """In a worker thread: the horizontal collider radius of an object's model.

    Pulls the actual footprint of the object identified by ``template_id`` (e.g. the
    player's "Player Object") and returns its bounding-circle radius in local model
    units, or ``None`` when the model can't be resolved (caller should fall back).
    Multiply by the object's scale for world units. Thread-safe, cached.
    """
    if not template_id:
        return None
    return _resolver.collider_radius(template_id, zone_name)


def get_zone_display_name(zone_name: str, locale: str = "en-US") -> str | None:
    """Canonical, human-readable name for a zone path (any zone, not just the current one).

    Reads the zone's ``gamedata.bin`` display token and resolves it against the game's
    lang files, e.g. ``Azteca/AZ_Z00_Zocalo`` -> ``The Zocalo``. Returns None if it can't
    be resolved (no TypeList, zone wad missing, locale without that lang file). Cached.
    """
    if not zone_name:
        return None
    return _resolver.zone_display_name(zone_name, locale)


def get_world_display_name(world_segment: str, locale: str = "en-US") -> str | None:
    """Canonical name for a world (a zone path's first segment), e.g. ``WizardCity`` ->
    ``Wizard City``, ``DragonSpire`` -> ``Dragonspyre``.

    Resolves via the game's ``WorldNames.lang``; for segments not in that table (event,
    PvP, test namespaces) it falls back to splitting CamelCase into words so the result
    is still presentable. Cached.
    """
    if not world_segment:
        return world_segment
    name = _resolver.world_display_name(world_segment, locale)
    if name:
        return name
    return " ".join(re.findall("[A-Z][^A-Z]*", world_segment)) or world_segment
