# reads the client's quest data (quest manager in memory and poi.dat in Root.wad) so auto quest
# can find the targets of collect/use/go to goals when the quest arrow doesn't show. read only.
#
# offsets (Wizard_1_610):
# poi.dat - per goal, key is (goal name id << 32) | quest name id, gives the target spots and adjectives
# quest manager is at game client +0x22AC0, quest map at +0x80 (+0x340 if the byte at +0x360 is set)
# WizQuestData - +0x48 name, +0x68 name id, +0xB0 goal map, +0xE8 gid
# WizGoalData - +0x50 title, +0x70 name id, +0x74 status (0 = not done), +0x78 location,
# +0x98 zone, +0xB8 type, +0x110 tag list, +0x140 quest helper on
# active quest gid is at +0x130 and the active goal id at +0x150 of a global found by pattern
# if something can't be read we return nothing and auto quest falls back to the old search

import asyncio
import os
import struct
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger
from wizwalker import XYZ, Keycode

GOAL_TYPES = {1: "defeat", 2: "defeat & collect", 3: "collect", 4: "talk", 5: "go to", 6: "collect",
              7: "rank", 8: "use", 9: "complete quest", 15: "collect after defeat", 16: "encounter"}
COLLECT_TYPES = frozenset({3, 6, 8})  # collect and use goals

# patterns for the quest manager and the active quest global
_MANAGER_PATTERN = rb"\x48\x8B\x53\x28\x48\x8B\x92\xE8\x00\x00\x00\x48\x8B\x8E"  # offset from the game client to the manager is at +14
_ACTIVE_PATTERN = rb"\x48\x8B\x05....\x0F\xB6\x80\x54\x01\x00\x00\xC3"  # rip relative address at +3
_MODULE = "WizardGraphicalClient.exe"

QUEST_MAP, QUEST_MAP_ALT, QUEST_MAP_ALT_FLAG = 0x80, 0x340, 0x360
QUEST_NAME, QUEST_NAME_ID, QUEST_GOALS, QUEST_GID = 0x48, 0x68, 0xB0, 0xE8
GOAL_TITLE, GOAL_NAME_ID, GOAL_STATUS, GOAL_LOCATION = 0x50, 0x70, 0x74, 0x78
GOAL_ZONE, GOAL_TYPE, GOAL_TAGS, GOAL_HELPER = 0x98, 0xB8, 0x110, 0x140
TAG_LIST = 0x48
ACTIVE_QUEST, ACTIVE_GOAL = 0x130, 0x150
MAX_NODES = 4000
SAME_SPOT = 80.0  # targets closer than this count as the same one


# poi.dat


@dataclass(frozen=True)
class PoiRecord:
    flag: int
    zone: str
    template_id: int
    position: XYZ
    a: int
    b: int


@dataclass
class PoiDb:
    zones: list = field(default_factory=list)
    records: dict = field(default_factory=dict)  # goal key -> [PoiRecord]
    adjectives: dict = field(default_factory=dict)  # goal key -> set of adjective hashes
    doors: dict = field(default_factory=dict)  # zone -> [(neighbouring zone, door position)]
    rides: set = field(default_factory=set)  # (zone, next zone) pairs that are rides


def parse_poi(data: bytes) -> PoiDb:
    # poi.dat layout: zone names, 33 byte records, zone -> ids, zone graph with the door spots,
    # goal -> adjectives, zone -> models
    from wizwalker.utils import make_string_id

    pos = 0

    def take(fmt):
        nonlocal pos
        values = struct.unpack_from(fmt, data, pos)
        pos += struct.calcsize(fmt)
        return values

    def text():
        nonlocal pos
        (n,) = take("<i")
        value = data[pos:pos + n].decode("latin1")
        pos += n
        return value

    db = PoiDb()
    (count,) = take("<i")
    db.zones = [text() for _ in range(count)]
    (count,) = take("<i")
    for _ in range(count):
        key, flag, zone, oid, x, y, z, a, b = take("<QBHQfffBB")
        record = PoiRecord(flag, db.zones[zone] if zone < len(db.zones) else "", oid & 0xFFFFFFFF, XYZ(x, y, z), a, b)
        db.records.setdefault(key, []).append(record)
    (count,) = take("<i")
    for _ in range(count):  # zone -> ids
        _zone, n = take("<Ii")
        pos += 8 * n
    by_hash = {make_string_id(name): name for name in db.zones}
    (count,) = take("<i")
    for _ in range(count):  # zone -> doors
        zone_hash, n = take("<Ii")
        zone = by_hash.get(zone_hash)
        for _ in range(n):
            neighbour = text()
            xy, z = take("<QI")
            x, y = struct.unpack("<ff", struct.pack("<Q", xy))
            if zone is not None:
                db.doors.setdefault(zone, []).append((neighbour, XYZ(x, y, struct.unpack("<f", struct.pack("<I", z))[0])))
    if pos < len(data):
        (count,) = take("<i")
        for _ in range(count):
            key, n = take("<Qi")
            db.adjectives[key] = set(take(f"<{n}I")) if n else set()
    return db


GATE_KINDS = ("standard", "dungeon", "dungeonExitConfirm", "xNoWait")  # gate kinds we can go through like a normal door
RIDE_MARK = "SkipRide"  # gate kinds with this in the name are rides


def merge_gate_list(db: PoiDb, path=None) -> int:
    # adds the doors from wizsprinter's gates_list.txt that poi.dat is missing, rides also go in db.rides
    if path is None:
        try:
            import wizwalker.extensions.wizsprinter as wizsprinter

            path = Path(list(wizsprinter.__path__)[0]) / "traversalData" / "gates_list.txt"
        except Exception:
            return 0
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    have = {(zone, n) for zone, doors in db.doors.items() for n, _ in doors}
    added = 0
    for line in lines:
        parts = line.strip().split(";")
        if len(parts) != 6 or (parts[0] not in GATE_KINDS and RIDE_MARK not in parts[0]):
            continue
        kind, x, y, z, src, dst = parts
        if (src, dst) in have:
            continue
        try:
            door = XYZ(float(x), float(y), float(z))
        except ValueError:
            continue
        db.doors.setdefault(src, []).append((dst, door))
        have.add((src, dst))
        if RIDE_MARK in kind:
            db.rides.add((src, dst))
        added += 1
    return added


_POI: dict = {}
_POI_LOCK = threading.Lock()


def poi_db() -> PoiDb:
    # loads poi.dat once, empty db if it can't be read
    with _POI_LOCK:
        if "db" not in _POI:
            try:
                from katsuba.wad import Archive
                from wizwalker.utils import get_wiz_install

                root = Archive.mmap(str(Path(get_wiz_install()) / "Data" / "GameData" / "Root.wad"))
                _POI["db"] = parse_poi(bytes(root["poi.dat"]))
                added = merge_gate_list(_POI["db"])
                if added:
                    logger.debug(f"[quest] {added} door(s) from wizsprinter's gate list that poi.dat lacks")
                logger.debug(f"[quest] poi.dat: {sum(len(v) for v in _POI['db'].records.values())} placements, "
                             f"{len(_POI['db'].adjectives)} goals with target adjectives")
            except Exception as e:
                logger.warning(f"[quest] poi.dat unreadable ({e}); collect quests use the old search")
                _POI["db"] = PoiDb()
        return _POI["db"]


# quest manager


@dataclass
class Goal:
    quest_gid: int
    quest_name: str
    quest_name_id: int
    name_id: int
    title: str
    status: int
    goal_type: int
    location: str
    destination_zone: str
    helper: bool
    tags: list
    active: bool = False  # goal is part of the active quest
    selected: bool = False  # goal is the one selected in game

    @property
    def key(self) -> int:
        return (self.name_id << 32) | self.quest_name_id

    @property
    def kind(self) -> str:
        return GOAL_TYPES.get(self.goal_type, f"type {self.goal_type}")


class QuestReader:
    # reads the quests and goals of one client

    def __init__(self, client):
        self.client = client
        self.manager_offset: Optional[int] = None
        self.active_global: Optional[int] = None

    async def _read(self, address: int, size: int) -> bytes:
        return await self.client.hook_handler.read_bytes(address, size)

    async def _u64(self, address: int) -> int:
        return struct.unpack("<Q", await self._read(address, 8))[0]

    async def _u32(self, address: int) -> int:
        return struct.unpack("<I", await self._read(address, 4))[0]

    async def _string(self, address: int) -> str:
        # MSVC std::string, short ones are inline, size at +0x10 and capacity at +0x18
        raw = await self._read(address, 32)
        size, capacity = struct.unpack_from("<QQ", raw, 0x10)
        if size == 0 or size > 4096:
            return ""
        if capacity < 16:
            data = raw[:size]
        else:
            data = await self._read(struct.unpack_from("<Q", raw, 0)[0], size)
        return data.decode("utf-8", "replace")

    async def _map_values(self, map_address: int) -> list[int]:
        # values of an MSVC std::map in order (shared ptr at node +0x28)
        head = await self._u64(map_address)
        if not head:
            return []
        out, stack = [], []
        node = await self._u64(head + 8)  # root
        while (stack or node) and len(out) < MAX_NODES:
            while node and node != head:
                raw = await self._read(node, 0x30)
                if raw[0x19]:  # isnil
                    break
                stack.append((node, raw))
                node = struct.unpack_from("<Q", raw, 0)[0]
            if not stack:
                break
            node, raw = stack.pop()
            value = struct.unpack_from("<Q", raw, 0x28)[0]
            if value:
                out.append(value)
            node = struct.unpack_from("<Q", raw, 0x10)[0]
        return out

    async def _list_strings(self, list_address: int) -> list[str]:
        # MSVC std::list<std::string>, next at +0, string at +0x10
        head = await self._u64(list_address)
        out = []
        node = await self._u64(head) if head else 0
        while node and node != head and len(out) < 64:
            out.append(await self._string(node + 0x10))
            node = await self._u64(node)
        return out

    async def _resolve(self) -> bool:
        if self.manager_offset is not None and self.active_global is not None:
            return True
        handler = self.client.hook_handler
        try:
            found = await handler.pattern_scan(_MANAGER_PATTERN, module=_MODULE)
            self.manager_offset = struct.unpack("<i", await self._read(found + 14, 4))[0]
            found = await handler.pattern_scan(_ACTIVE_PATTERN, module=_MODULE)
            rel = struct.unpack("<i", await self._read(found + 3, 4))[0]
            self.active_global = found + 7 + rel
            logger.debug(f"[quest] quest manager at game client +{self.manager_offset:#x}, "
                         f"active quest global {self.active_global:#x}")
            return True
        except Exception as e:
            logger.warning(f"[quest] couldn't find the quest manager ({e})")
            self.manager_offset = self.active_global = None
            return False

    async def goals(self) -> list[Goal]:
        # every goal of every quest, marks the active one
        if not await self._resolve():
            return []
        game_client = await self.client.game_client.read_base_address()
        manager = await self._u64(game_client + self.manager_offset)
        if not manager:
            return []
        alt = (await self._read(manager + QUEST_MAP_ALT_FLAG, 1))[0]
        quests = await self._map_values(manager + (QUEST_MAP_ALT if alt else QUEST_MAP))
        active_quest = active_goal = 0
        try:
            registry = await self._u64(self.active_global)
            if registry:
                active_quest = await self._u64(registry + ACTIVE_QUEST)
                active_goal = await self._u32(registry + ACTIVE_GOAL)
        except Exception:
            pass
        out = []
        for quest in quests:
            try:
                quest_gid = await self._u64(quest + QUEST_GID)
                quest_name = await self._string(quest + QUEST_NAME)
                quest_name_id = await self._u32(quest + QUEST_NAME_ID)
                for goal in await self._map_values(quest + QUEST_GOALS):
                    raw = await self._read(goal, GOAL_HELPER + 1)
                    name_id, status = struct.unpack_from("<Ii", raw, GOAL_NAME_ID)
                    goal_type = struct.unpack_from("<i", raw, GOAL_TYPE)[0]
                    tag_list = struct.unpack_from("<Q", raw, GOAL_TAGS)[0]
                    out.append(Goal(
                        quest_gid=quest_gid, quest_name=quest_name, quest_name_id=quest_name_id,
                        name_id=name_id, title=await self._string(goal + GOAL_TITLE), status=status,
                        goal_type=goal_type, location=await self._string(goal + GOAL_LOCATION),
                        destination_zone=await self._string(goal + GOAL_ZONE), helper=bool(raw[GOAL_HELPER]),
                        tags=await self._list_strings(tag_list + TAG_LIST) if tag_list else [],
                        active=quest_gid == active_quest and (not active_goal or name_id == active_goal),
                        selected=quest_gid == active_quest and bool(active_goal) and name_id == active_goal,
                    ))
                    out[-1].in_active_quest = quest_gid == active_quest
            except Exception as e:
                logger.debug(f"[quest] skipped an unreadable quest ({e})")
        return out

    async def active_goals(self, kinds=None) -> list[Goal]:
        # open goals of the active quest, selected one first. some quests have a bunch open at once
        # (like the 8 dirt mounds)
        goals = [g for g in await self.goals() if g.status == 0 and getattr(g, "in_active_quest", g.active)
                 and (kinds is None or g.goal_type in kinds)]
        return sorted(goals, key=lambda g: not g.selected)

    async def active_goal(self, kinds=None) -> Optional[Goal]:
        # the selected goal, or the first open one
        goals = await self.active_goals(kinds)
        return goals[0] if goals else None

    async def is_open(self, goal: Goal) -> bool:
        # true if the goal is still open
        return any(g.key == goal.key for g in await self.active_goals())


_READERS: dict = {}  # one reader per client process


def quest_reader(client) -> QuestReader:
    reader = _READERS.get(client.process_id)
    if reader is None or reader.client is not client:
        reader = _READERS[client.process_id] = QuestReader(client)
    return reader


async def describe_active_goal(client) -> str:
    # one line about the active goal for the log
    try:
        goal = await quest_reader(client).active_goal()
    except Exception as e:
        return f"quest data unreadable ({e})"
    if goal is None:
        return ""
    return (f"active goal '{label(goal.title)}' ({goal.kind}) of '{label(goal.quest_name)}'"
            + (f" at {label(goal.location)}" if goal.location else "")
            + (f", zone {goal.destination_zone}" if goal.destination_zone else ""))


# zone routing


WORLD_GATE_MIN = 3  # a door spot with this many destinations is the spiral door
GATE_COST = 20  # makes the spiral door the last choice
WORLD_DOOR_COST = 2 * GATE_COST  # other doors into another world are quest portals, only if nothing else works


def zone_doors(db: PoiDb, zone: str) -> list[tuple[str, XYZ, bool]]:
    # doors out of a zone and if each one is the spiral door. rides don't count toward that
    # (the crown of fire elevator spot has 3)
    doors = db.doors.get(zone, [])
    shared: dict = {}
    for n, pos in doors:
        if (zone, n) not in db.rides:
            key = (round(pos.x), round(pos.y))
            shared[key] = shared.get(key, 0) + 1
    return [(n, pos, (zone, n) not in db.rides and shared.get((round(pos.x), round(pos.y)), 0) >= WORLD_GATE_MIN)
            for n, pos in doors]


def zone_route(db: PoiDb, start: str, goal: str) -> list[tuple[str, XYZ, bool]]:
    # fewest doors from start to goal, the spiral door only to change worlds
    import heapq

    if start == goal:
        return []
    best = {start: 0}
    previous: dict = {}
    heap = [(0, start)]
    while heap:
        cost, zone = heapq.heappop(heap)
        if zone == goal:
            route, step = [], goal
            while step != start:
                came_from, door, gate = previous[step]
                route.append((step, door, gate))
                step = came_from
            return route[::-1]
        if cost > best.get(zone, 1 << 30):
            continue
        for neighbour, pos, gate in zone_doors(db, zone):
            if gate and neighbour.split("/")[0] == zone.split("/")[0]:
                continue  # the spiral door only for other worlds
            other_world = neighbour.split("/")[0] != zone.split("/")[0]
            nxt = cost + (GATE_COST if gate else WORLD_DOOR_COST if other_world else 1)
            if nxt < best.get(neighbour, 1 << 30):
                best[neighbour] = nxt
                previous[neighbour] = (zone, pos, gate)
                heapq.heappush(heap, (nxt, neighbour))
    return []


def label(text: str) -> str:
    # turns a lang key into the text the game shows
    if text and "_" in text and " " not in text:
        try:
            from src import game_templates as templates

            return templates.lang_text(text) or text
        except Exception:
            return text
    return text


async def _through_loading(client, start_within: float = 3.0):
    # wait for the loading screen after a door (it can show up a bit late), then for it to finish
    from src.teleport_math import wait_for_load

    for _ in range(int(start_within / 0.1)):
        try:
            if await client.is_loading():
                break
        except Exception:
            break
        await asyncio.sleep(0.1)
    if not await wait_for_load(client):
        await asyncio.sleep(0.5)


async def _wait_in_range(client, spot: XYZ, ticks: int = 30) -> bool:
    # wait for the X prompt, walk to the spot if it doesn't show
    for tick in range(ticks):
        try:
            if await client.is_in_npc_range():
                return True
        except Exception:
            pass
        if tick == ticks // 3:
            try:
                await client.goto(spot.x, spot.y)
            except Exception:
                pass
        await asyncio.sleep(0.1)
    return False


# spiral door menu: optionWindow has pageCount ("1/5"), opt0-opt3 (one world each) and
# leftButton/rightButton, teleportButton and cancelButton are next to it
WORLD_NAMES = {"WizardCity": "Wizard City", "DragonSpire": "Dragonspyre"}  # zone prefix -> menu label


def _plain(text: str) -> str:
    import re

    return re.sub(r"<[^>]*>", "", text or "").strip()


def _same_world(label: str, world: str) -> bool:
    def norm(x: str) -> str:
        return "".join(ch for ch in x.lower() if ch.isalnum())

    return norm(label) in (norm(world), norm(WORLD_NAMES.get(world, world)))


async def _visible_named(parent, name: str):
    for w in await parent.get_windows_with_name(name):
        try:
            if await w.is_visible():
                return w
        except Exception:
            continue
    return None


async def _spiral_page(menu) -> tuple[int, int]:
    import re

    count = await _visible_named(menu, "pageCount")
    numbers = re.findall(r"\d+", _plain(await count.maybe_text())) if count is not None else []
    return (int(numbers[0]), int(numbers[1])) if len(numbers) >= 2 else (1, 1)


async def pick_world(client, world: str) -> bool:
    # pages through the spiral door menu to the world and teleports. world names are the check box
    # labels at +736 (wizsprinter's goToNewWorld reads +616 which doesn't work anymore)
    root = client.root_window
    menu = await _visible_named(root, "optionWindow")
    if menu is None:
        return False
    here = await client.zone_name()
    async with client.mouse_handler:
        page, pages = await _spiral_page(menu)
        for _ in range(pages + 2):  # back to the first page
            if page <= 1:
                break
            left = await _visible_named(menu, "leftButton")
            if left is None:
                break
            await client.mouse_handler.click_window(left)
            await asyncio.sleep(0.3)
            page, pages = await _spiral_page(menu)
        seen = []
        for _ in range(max(pages, 1) + 1):
            for name in ("opt0", "opt1", "opt2", "opt3"):
                option = await _visible_named(menu, name)
                if option is None:
                    continue
                label = _plain(await option.maybe_text())
                seen.append(label)
                if _same_world(label, world):
                    await client.mouse_handler.click_window(option)
                    await asyncio.sleep(0.5)
                    teleport = await _visible_named(root, "teleportButton")
                    if teleport is None:
                        return False
                    await client.mouse_handler.click_window(teleport)
                    for _ in range(300):
                        if await client.is_loading() or await client.zone_name() != here:
                            return True
                        await asyncio.sleep(0.1)
                    return False
            right = await _visible_named(menu, "rightButton")
            if right is None or page >= pages:
                break
            await client.mouse_handler.click_window(right)
            await asyncio.sleep(0.3)
            page, pages = await _spiral_page(menu)
        logger.info(f"[quest] {client.title}: {world} isn't on the spiral door (it lists {', '.join(dict.fromkeys(seen))})")
        cancel = await _visible_named(root, "cancelButton")
        if cancel is not None:
            await client.mouse_handler.click_window(cancel)
    return False


async def _through_world_gate(client, gate: XYZ, world: str) -> bool:
    # go to the spiral door, open it and pick the world
    from src.teleport_math import collision_tp

    await collision_tp(client, gate, door=True)
    if not await _wait_in_range(client, gate, ticks=50):
        logger.info(f"[quest] {client.title}: couldn't get to the spiral door")
        return False
    here = await client.zone_name()
    for _ in range(30):  # open the menu
        if await _visible_named(client.root_window, "optionWindow") is not None:
            break
        await client.send_key(Keycode.X, 0.1)
        await asyncio.sleep(0.3)
    else:
        logger.info(f"[quest] {client.title}: the spiral door's menu didn't open")
        return False
    try:
        if not await pick_world(client, world):
            return False
    except Exception as e:
        logger.info(f"[quest] {client.title}: the spiral door to {world} failed ({e!r})")
        return False
    await _through_loading(client)
    return await client.zone_name() != here


async def _prompt_text(client) -> str:
    # text of the X prompt, empty if there isn't one
    from src.paths import npc_range_path, popup_msgtext_path
    from src.utils import get_window_from_path, is_visible_by_path

    try:
        if not await is_visible_by_path(client, npc_range_path):
            return ""
        window = await get_window_from_path(client.root_window, popup_msgtext_path)
        return (await window.maybe_text()) or "" if window else ""
    except Exception:
        return ""


async def approach(client, spot: XYZ, max_seconds: float = 4.0) -> bool:
    # walk toward the spot in small steps until the X prompt shows or we stop getting closer.
    # for targets inside something where the teleport can only land next to it
    import math

    from wizwalker.utils import calculate_perfect_yaw

    last, stalls, walked = None, 0, 0.0
    while walked < max_seconds:
        if await _prompt_text(client):
            return True
        try:
            pos = await client.body.position()
        except Exception:
            break
        distance = math.hypot(spot.x - pos.x, spot.y - pos.y)
        if distance < 40:
            break
        if last is not None and last - distance < 10:
            stalls += 1
            if stalls >= 2:
                break  # up against it
        last = distance
        try:
            await client.body.write_yaw(calculate_perfect_yaw(pos, spot))
            await client.send_key(Keycode.W, 0.25)
        except Exception:
            break
        walked += 0.25
    return bool(await _prompt_text(client))


async def answer_dungeon_box(client) -> bool:
    # clicks yes on the dungeon box (leave dungeon yes/no, or the one button enter warning).
    # only boxes that mention a dungeon
    try:
        for box in await client.root_window.get_windows_with_name("MessageBoxModalWindow"):
            if not await box.is_visible():
                continue
            texts = []

            async def any_window(_w):
                return True

            for w in await box.get_windows_with_predicate(any_window):
                try:
                    text = await w.maybe_text()
                except Exception:
                    text = ""
                if text:
                    texts.append(text)
            if "dungeon" not in " ".join(texts).lower():
                continue
            for name in ("leftButton", "centerButton"):  # Yes, or the only button
                for button in await box.get_windows_with_name(name):
                    if await button.is_visible():
                        logger.info(f"[quest] {client.title}: answering the dungeon box with {name}")
                        async with client.mouse_handler:
                            await client.mouse_handler.click_window(button)
                        await asyncio.sleep(0.3)
                        return True
    except Exception as e:
        logger.debug(f"[quest] {client.title}: couldn't read the dungeon box ({e!r})")
    return False


async def _zone_changes(client, here: str, seconds: float, confirm_dungeon: bool = False) -> bool:
    # wait for a loading screen or zone change, clicks through the dungeon warning if confirm_dungeon
    from src.paths import dungeon_warning_path
    from src.utils import is_visible_by_path

    for tick in range(int(seconds / 0.1)):
        try:
            if await client.is_loading() or await client.zone_name() != here:
                return True
            if confirm_dungeon and await is_visible_by_path(client, dungeon_warning_path):
                await client.send_key(Keycode.ENTER, 0.1)
            if tick % 5 == 4:  # check for the leave dungeon box every half second
                await answer_dungeon_box(client)
        except Exception:
            pass
        await asyncio.sleep(0.1)
    return False


RIDE_SECONDS = 90.0  # how long a ride gets to finish


async def _ride(client, start: XYZ, zone: str) -> bool:
    # takes a ride to the zone, presses X at every prompt on the way until we get there
    import time

    from src.teleport_math import collision_tp

    logger.info(f"[quest] {client.title}: riding to {zone}")
    # teleport right on the ride spot like wizsprinter does, collision tp thinks the roost
    # platform is solid and lands too far away
    try:
        await client.teleport(start)
        await asyncio.sleep(0.5)
        await _settle(client)
        await asyncio.sleep(0.5)
    except Exception:
        pass
    if not await _prompt_text(client):
        logger.debug(f"[quest] {client.title}: no prompt on the ride's spot; landing by collision")
        await collision_tp(client, start, door=True)
        if not await _prompt_text(client):
            await approach(client, start, max_seconds=5.0)
    deadline, pressed = time.time() + RIDE_SECONDS, 0.0
    while time.time() < deadline:
        try:
            if await client.zone_name() == zone and not await client.is_loading():
                return True
            if not await client.is_loading() and time.time() - pressed > 1.0:
                if await _prompt_text(client):
                    await client.send_key(Keycode.X, 0.1)
                    pressed = time.time()
                elif await answer_dungeon_box(client):  # Marleybone's Ironworks asks first
                    pressed = time.time()
        except Exception as e:
            logger.debug(f"[quest] {client.title}: ride step failed ({e!r})")
        await asyncio.sleep(0.4)
    return await client.zone_name() == zone


async def travel_toward(client, zone: str, hops: int = 1) -> bool:
    # go through up to hops doors toward the zone, true once we're there
    from src.teleport_math import collision_tp

    for _ in range(hops):
        here = await client.zone_name()
        if here == zone:
            return True
        db = poi_db()
        route = zone_route(db, here, zone)
        if not route:
            logger.info(f"[quest] {client.title}: no known way from {here} to {zone}")
            return False
        next_zone, door, gate = route[0]
        logger.info(f"[quest] {client.title}: {here} -> {next_zone}{' by the spiral door' if gate else ''} "
                    f"({len(route)} door(s) to {zone})")
        if gate:
            if not await _through_world_gate(client, door, next_zone.split("/")[0]):
                return False
            await asyncio.sleep(0.5)
            continue
        if (here, next_zone) in db.rides:
            if not await _ride(client, door, next_zone):
                logger.info(f"[quest] {client.title}: the ride to {next_zone} didn't take us")
                return False
            await _through_loading(client)
            continue
        await collision_tp(client, door, door=True)
        changed = await _zone_changes(client, here, 2.5)  # most doors take us as we land
        if not changed:
            prompt = (await _prompt_text(client)).lower()
            logger.debug(f"[quest] {client.title}: at the door to {next_zone}: "
                         + (f"prompt {prompt!r}" if prompt else "no prompt"))
            if "to enter" in prompt:
                # dungeon entrance, some queue first. press X once and wait here, pressing X again
                # or walking away leaves the queue
                logger.info(f"[quest] {client.title}: entering the dungeon at the door to {next_zone}")
                await client.send_key(Keycode.X, 0.1)
                changed = await _zone_changes(client, here, 90.0, confirm_dungeon=True)
            elif prompt:
                await client.send_key(Keycode.X, 0.1)  # a door you open
                changed = await _zone_changes(client, here, 10.0, confirm_dungeon=True)
            else:  # landed short of the door, walk up to it
                prompted = await approach(client, door, max_seconds=5.0)
                logger.debug(f"[quest] {client.title}: walked up to the door to {next_zone}: "
                             + (f"prompt {(await _prompt_text(client))!r}" if prompted else "no prompt"))
                changed = await _zone_changes(client, here, 1.0)
                if not changed and prompted:
                    entering = "to enter" in (await _prompt_text(client)).lower()
                    await client.send_key(Keycode.X, 0.1)
                    changed = await _zone_changes(client, here, 90.0 if entering else 10.0, confirm_dungeon=True)
                elif not changed:
                    # no prompt and no zone change, the trigger can be just behind the door so walk through
                    try:
                        pos = await client.body.position()
                        dx, dy = door.x - pos.x, door.y - pos.y
                        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
                        await client.goto(door.x + dx / length * 80, door.y + dy / length * 80)
                    except Exception:
                        pass
                    changed = await _zone_changes(client, here, 5.0)
        if not changed:
            logger.info(f"[quest] {client.title}: the door to {next_zone} didn't take us")
            return False
        await _through_loading(client)
    return await client.zone_name() == zone


DROP_HEIGHT = 350.0  # height to drop from when nothing else works
RING_RADII = (90.0, 150.0, 300.0, 500.0)  # ring sizes to try around a spot the game won't keep us at
RING_WALKS = 8  # max ring spots to walk in from
RING_DIRECTIONS = 8


SAME_FLOOR = 150.0  # landing within this height counts as the same floor (for stuff on tables)
_UNREACHABLE: dict = {}  # (zone, rounded spot) -> failed tries


def spot_key(zone: str, spot: XYZ) -> tuple:
    return zone, round(spot.x / 25), round(spot.y / 25), round(spot.z / 25)


async def _settle(client):
    # after a teleport you float until you move, tapping W/S makes gravity kick in
    try:
        await client.send_key(Keycode.W, 0.1)
        await client.send_key(Keycode.S, 0.1)
    except Exception:
        pass


async def _use_prompt(client) -> bool:
    # press X on the prompt and wait for whatever it starts to finish
    from src.utils import is_free

    if not await _prompt_text(client):
        return False
    await client.send_key(Keycode.X, 0.1)
    await asyncio.sleep(0.6)
    for _ in range(300):
        try:
            if await is_free(client):
                break
        except Exception:
            break
        await asyncio.sleep(0.1)
    return True


async def land_at(client, spot: XYZ, done=None) -> bool:
    # teleport to a quest spot and make sure we stay there. some spots send us back, put us on
    # another floor or are inside something. then we try the exact spot, rings around it and walk in,
    # and last drop onto it from above
    import math

    from src.teleport_math import collision_tp

    def far(a: XYZ, b: XYZ) -> float:
        return math.hypot(a.x - b.x, a.y - b.y)

    async def finished() -> bool:
        if done is None:
            return False
        try:
            return bool(await done())
        except Exception:
            return False

    fell_below = [0]
    sent_back = [0]
    why = [""]

    async def kept_at(point: XYZ) -> bool:
        # teleport to the point, let gravity act and check we're still there on the same floor
        why[0] = ""
        try:
            await client.teleport(point)
        except Exception:
            why[0] = "teleport failed"
            return False
        await asyncio.sleep(0.3)
        await _settle(client)
        await asyncio.sleep(0.6)
        try:
            pos = await client.body.position()
        except Exception:
            why[0] = "position unreadable"
            return False
        if await client.is_loading():
            why[0] = "zone changed"
            return False
        if far(pos, point) <= 80:
            if abs(pos.z - spot.z) <= SAME_FLOOR:
                return True
            if pos.z < spot.z - SAME_FLOOR:
                fell_below[0] += 1  # fell, nothing to stand on at that height
                why[0] = f"fell to z {pos.z:.0f}"
            else:
                why[0] = f"stuck up at z {pos.z:.0f}"
        elif far(pos, start) <= 150:
            sent_back[0] += 1  # sent back to where we started
            why[0] = "sent back"
        else:
            why[0] = f"pushed off to ({pos.x:.0f}, {pos.y:.0f})"
        return False

    from src.teleport_math import wait_for_load

    await wait_for_load(client)
    zone = await client.zone_name()
    key = spot_key(zone, spot)
    start = await client.body.position()
    if _UNREACHABLE.get(key, 0) < 2:
        await collision_tp(client, spot)
        await asyncio.sleep(1.0)
        if far(spot, start) < 300 or await finished():
            return True
        try:
            pos = await client.body.position()
        except Exception:
            return True
        if far(pos, start) > 150 or await client.is_loading():
            return True
        logger.info(f"[quest] {client.title}: the game sent us back from {spot}; trying it without collision snapping")
    else:
        logger.info(f"[quest] {client.title}: {spot} failed before; going straight to the ways around it")

    # try the exact spot, collision tp may have picked another floor
    if not await kept_at(XYZ(spot.x, spot.y, spot.z + 5)):
        logger.debug(f"[quest] {client.title}: not kept at the exact spot ({why[0]})")
    else:
        if await finished():
            return True
        if await approach(client, spot, max_seconds=2.0):
            await _use_prompt(client)
        if done is None or await finished():
            return True

    exact_sent_back = why[0] == "sent back"
    walks = 0

    async def walk_in_from(point: XYZ, where: str) -> bool:
        # land at the point and walk in, true if that got us there
        nonlocal walks
        if not await kept_at(point):
            logger.debug(f"[quest] {client.title}: not kept at {where} ({why[0]})")
            return await finished()
        if await finished():
            logger.info(f"[quest] {client.title}: reached it from {where}")
            return True
        walks += 1
        logger.debug(f"[quest] {client.title}: kept at {where}; walking in")
        if await approach(client, spot, max_seconds=3.0):
            logger.debug(f"[quest] {client.title}: in reach of it; pressing X")
            await _use_prompt(client)
        if await finished():
            logger.info(f"[quest] {client.title}: reached it walking in from {where}")
            return True
        return done is None  # no done check, this is as close as we can get

    if exact_sent_back:
        # the game sends us back from the spot itself, sometimes a second or more after landing which
        # is too late for collision_tp to notice. land where the strict solve says and walk in
        from src.teleport_math import strict_landing

        clear = await strict_landing(client, spot)
        if clear is not None and far(clear, spot) > 5:
            if await walk_in_from(XYZ(clear.x, clear.y, clear.z + 5),
                                  f"the strict collision landing {far(clear, spot):.0f}u out"):
                return True

    # if the spot itself got refused 90u out almost always is too, start at 150
    radii = RING_RADII[1:] if exact_sent_back else RING_RADII
    for radius in radii:
        if radius > radii[0] and fell_below[0] >= RING_DIRECTIONS:
            # every point around it made us fall, it's up on something so drop onto it
            logger.info(f"[quest] {client.title}: {spot} is up on something; dropping onto it")
            break
        for k in range(RING_DIRECTIONS):
            if walks >= RING_WALKS:
                break
            angle = 2 * math.pi * k / RING_DIRECTIONS
            point = XYZ(spot.x + radius * math.cos(angle), spot.y + radius * math.sin(angle), spot.z + 5)
            if await walk_in_from(point, f"{radius:.0f}u, {math.degrees(angle):.0f} deg"):
                return True

    logger.info(f"[quest] {client.title}: no way in on foot; dropping onto {spot} from above")
    try:
        await client.teleport(XYZ(spot.x, spot.y, spot.z + DROP_HEIGHT))
        await asyncio.sleep(0.3)
        await _settle(client)
    except Exception:
        return False
    await asyncio.sleep(1.5)
    if await finished():
        return True
    try:
        pos = await client.body.position()
    except Exception:
        return True
    if far(pos, start) > 150 and done is None:
        return True
    _UNREACHABLE[key] = _UNREACHABLE.get(key, 0) + 1
    logger.info(f"[quest] {client.title}: couldn't reach {spot} ({_UNREACHABLE[key]} time(s))"
                + ("; the game sent us back from everywhere near it, so that area may not be open "
                   "to us yet" if far(pos, start) <= 150 and sent_back[0] >= RING_DIRECTIONS else ""))
    return False


async def teleport_to_goal(client) -> bool:
    # quest tp when there's no arrow: one door toward the goal's zone, or the closest target once we're there
    from src.teleport_math import collision_tp

    goal = await quest_reader(client).active_goal()
    if goal is None:
        return False
    here = await client.zone_name()
    if goal.destination_zone and goal.destination_zone != here:
        return await travel_toward(client, goal.destination_zone, hops=1) or True
    targets = await goal_targets(client, goal)
    if not targets:
        return False
    target = nearest_first(targets, await client.body.position())[0]
    logger.info(f"[quest] {client.title}: to a {target.source} target of '{label(goal.title)}' at {target.position}")
    reader = quest_reader(client)

    async def moved_on() -> bool:
        return not await reader.is_open(goal)

    await land_at(client, target.position, done=moved_on)
    try:  # landed next to it, walk up to it
        pos = await client.body.position()
        if ((pos.x - target.position.x) ** 2 + (pos.y - target.position.y) ** 2) ** 0.5 > 100 \
                and not await moved_on():
            await approach(client, target.position, max_seconds=5.0)
    except Exception:
        pass
    return True


_TEMPLATE_ADJ: dict[int, frozenset] = {}
_ZONE_OBJECTS: dict[str, list] = {}
_ZONE_LOCK = threading.Lock()


def template_adjective_ids(template_id: int) -> frozenset:
    # adjective ids of a template from Root.wad
    if template_id in _TEMPLATE_ADJ:
        return _TEMPLATE_ADJ[template_id]
    found = frozenset()
    try:
        from wizwalker.utils import make_string_id

        from src import game_templates as templates

        if templates._load():
            others = templates._STATE["others"]
            path = others.get(template_id) or others.get(template_id & 0xFFFFFFFF)
            if path is not None:
                obj = templates._deserialize(path)
                found = frozenset(make_string_id(templates._text(a)) for a in obj["m_adjectiveList"])
    except Exception:
        found = frozenset()
    _TEMPLATE_ADJ[template_id] = found
    return found


def zone_objects(zone: str) -> list[tuple[int, XYZ]]:
    # (template id, position) of every object placed in the zone's gamedata.bin
    with _ZONE_LOCK:
        if zone in _ZONE_OBJECTS:
            return _ZONE_OBJECTS[zone]
        out = []
        try:
            from katsuba.op import Serializer, SerializerOptions
            from katsuba.wad import Archive
            from wizwalker.utils import get_wiz_install

            from src import game_templates as templates

            if templates._load():
                options = SerializerOptions()
                options.shallow = False
                options.skip_unknown_types = True
                serializer = Serializer(options, templates._STATE["type_list"])
                path = Path(get_wiz_install()) / "Data" / "GameData" / (zone.replace("/", "-") + ".wad")
                if path.exists():
                    data = Archive.mmap(str(path)).deserialize("gamedata.bin", serializer)
                    for inst in data["m_objectList"]:
                        if inst is None:
                            continue
                        try:
                            loc = inst["m_location"]
                            out.append((int(inst["m_templateID.m_full"]) & 0xFFFFFFFF, XYZ(loc.x, loc.y, loc.z)))
                        except Exception:
                            continue
        except Exception as e:
            logger.debug(f"[quest] couldn't read {zone}'s placed objects ({e})")
        _ZONE_OBJECTS[zone] = out
        return out


@dataclass
class Target:
    position: XYZ
    source: str  # live / placed / poi
    template_id: int = 0
    entity: object = None


def _merge(targets: list[Target]) -> list[Target]:
    # one target per spot, live ones first
    order = {"live": 0, "placed": 1, "poi": 2}
    out: list[Target] = []
    for t in sorted(targets, key=lambda t: order.get(t.source, 9)):
        if all(((t.position.x - o.position.x) ** 2 + (t.position.y - o.position.y) ** 2) ** 0.5 > SAME_SPOT for o in out):
            out.append(t)
    return out


def nearest_first(targets: list[Target], start: XYZ) -> list[Target]:
    # closest unvisited target next
    left, tour, here = list(targets), [], start
    while left:
        nxt = min(left, key=lambda t: (t.position.x - here.x) ** 2 + (t.position.y - here.y) ** 2
                  + (t.position.z - here.z) ** 2)
        left.remove(nxt)
        tour.append(nxt)
        here = nxt.position
    return tour


async def goal_adjectives(goal: Goal) -> set:
    # adjective hashes of the goal's targets from poi.dat
    db = await asyncio.get_running_loop().run_in_executor(None, poi_db)
    return db.adjectives.get(goal.key, set())


def goal_template_ids(goal: Goal) -> set:
    # template ids of the goal's spots in poi.dat, used when it has no adjectives
    return {r.template_id for r in poi_db().records.get(goal.key, []) if r.template_id}


async def live_targets(client, wanted: set, template_ids: set = frozenset()) -> list[Target]:
    # loaded objects with one of the adjectives or template ids
    out: list[Target] = []
    if not wanted and not template_ids:
        return out
    try:
        entities = await client.get_base_entity_list()
    except Exception as e:
        logger.debug(f"[quest] entity list unreadable ({e})")
        return out
    for entity in entities:
        try:
            template = await entity.object_template()
            if template is None:
                continue
            tid = await template.template_id()
            if (template_ids and (tid & 0xFFFFFFFF) in template_ids) or (
                    wanted and wanted & set(await template.object_property_hashset())):
                out.append(Target(await entity.location(), "live", tid, entity))
        except Exception:
            continue
    return _merge(out)


async def goal_targets(client, goal: Goal) -> list[Target]:
    # where the goal's targets are in this zone: loaded objects, placed spawn spots and poi.dat spots.
    # items spawn at runtime so the spots are also where to look when nothing is loaded
    loop = asyncio.get_running_loop()
    db = await loop.run_in_executor(None, poi_db)
    wanted = db.adjectives.get(goal.key, set())
    template_ids = goal_template_ids(goal)
    zone = await client.zone_name()
    targets = await live_targets(client, wanted, template_ids)

    def placed():
        return [Target(pos, "placed", tid) for tid, pos in zone_objects(zone)
                if tid in template_ids or (wanted and wanted & template_adjective_ids(tid))]

    if wanted or template_ids:
        targets += await loop.run_in_executor(None, placed)
    for record in db.records.get(goal.key, []):
        if record.zone == zone and (record.position.x or record.position.y or record.position.z):
            targets.append(Target(record.position, "poi", record.template_id))
    merged = _merge(targets)
    counts = {s: sum(1 for t in merged if t.source == s) for s in ("live", "placed", "poi")}
    logger.info(f"[quest] {client.title}: '{label(goal.title or goal.quest_name)}' ({goal.kind}) in {zone}: "
                f"{counts['live']} loaded target(s), {counts['placed']} placed and {counts['poi']} quest-data "
                f"spot(s) to look at; {len(wanted)} target adjective(s), {len(template_ids)} target template(s)")
    return merged


def goal_zones(goal: Goal) -> list[str]:
    # zones poi.dat puts the goal's targets in
    return sorted({r.zone for r in poi_db().records.get(goal.key, []) if r.zone})


HIDDEN_NEAR = 300.0  # object this close to a goal spot counts as its marker
_HIDDEN: dict = {}  # quest name id -> markers no goal spot claims


def unclaimed_markers(db: PoiDb, quest_name_id: int, world: str, objects=None) -> list[tuple[str, XYZ]]:
    # hidden object quests (like the stone roses) put the same object at every goal but poi.dat can
    # miss one (the grand chasm rose is in grand chasm past). finds the object next to the other goals'
    # spots and returns the placements of it that no goal claims
    import math
    from collections import Counter

    objects = objects or zone_objects
    claimed = [r for k, rs in db.records.items() if k & 0xFFFFFFFF == quest_name_id for r in rs if r.zone]
    if len(claimed) < 2:
        return []

    def near(zone: str, pos: XYZ, template_id: int = None) -> list:
        return [t for t, p in objects(zone) if (template_id is None or t == template_id)
                and math.hypot(p.x - pos.x, p.y - pos.y) <= HIDDEN_NEAR]

    counts = Counter()
    for r in claimed:
        counts.update(set(near(r.zone, r.position)))
    if not counts:
        return []
    marker, seen = counts.most_common(1)[0]
    if seen < max(2, len(claimed) // 2):
        return []  # nothing the spots have in common
    out = []
    for zone in db.zones:
        if not zone.startswith(world + "/"):
            continue
        for t, pos in objects(zone):
            if t == marker and not any(r.zone == zone and math.hypot(r.position.x - pos.x, r.position.y - pos.y)
                                       <= HIDDEN_NEAR for r in claimed):
                out.append((zone, pos))
    return out


def hidden_goal_spot(goal: Goal) -> Optional[tuple[str, XYZ]]:
    # spot for a goal poi.dat doesn't have: the unclaimed marker in the goal's zone, or in a zone with
    # the same name (grand chasm -> grand chasm past), or the only one. reads every zone of the world
    # once per quest so run it in an executor
    if not goal.destination_zone:
        return None
    if goal.quest_name_id not in _HIDDEN:
        world = goal.destination_zone.split("/")[0]
        _HIDDEN[goal.quest_name_id] = unclaimed_markers(poi_db(), goal.quest_name_id, world)
        logger.debug(f"[quest] {len(_HIDDEN[goal.quest_name_id])} unclaimed marker(s) for quest "
                     f"{goal.quest_name_id:#x}: {_HIDDEN[goal.quest_name_id]}")
    spots = _HIDDEN[goal.quest_name_id]
    return pick_hidden(spots, goal.destination_zone)


def pick_hidden(spots: list, zone: str) -> Optional[tuple[str, XYZ]]:
    import re

    same = [s for s in spots if s[0] == zone]
    if same:
        return same[0]
    stem = re.sub(r"^[A-Za-z]{2}_[A-Za-z0-9]+_", "", zone.split("/")[-1]).lower()
    alike = [s for s in spots if stem and stem in s[0].split("/")[-1].lower()]
    if alike:
        return alike[0]
    return spots[0] if len(spots) == 1 else None
