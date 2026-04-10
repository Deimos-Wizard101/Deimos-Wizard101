import asyncio
from typing import Dict, List, Tuple

from wizwalker import Client
from wizwalker.combat import CombatHandler
from wizwalker.errors import MemoryInvalidated

from src.combat_math import base_damage_calculation_from_id
from src.combat_objects import school_to_str
from src.combat_utils import add_universal_stat, enemy_type_str, get_str_masteries, to_percent, to_seperated_str_stats

# UNFINISHED - slack

# STATS FORMAT
# NAME: example - SCHOOL: example
# POWER PIPS: X - PIPS: X
# SHADOW PIPS: X
# Boosts: Ice - 35%, Myth - 40%
# Resists: Fire - 70%, Storm - 80%
# Damages: Fire - 80%, Storm - 65%
# Criticals: Fire - 121, Storm - 272
# Blocks: Ice - 60, Myth - 50
# Masteries: Fire, Storm
# Max Possible Damage: 14000 (this won't come for a while)

damage_per_pip = {2343174: 100, 72777: 83, 83375795: 125, 78318724: 85, 2330892: 83, 2448141: 90, 1027491821: 85}

shadow_damage_per_pip = {
    2343174: 120,
    72777: 100,
    83375795: 130,
    78318724: 105,
    2330892: 100,
    2448141: 115,
    1027491821: 105,
}

# Track combat members across calls to preserve dead member positions
_tracked_allies: list[tuple[int, str]] = []  # [(owner_id, name), ...] in position order
_tracked_enemies: list[tuple[int, str]] = []  # [(owner_id, name), ...] in position order


def _update_tracking(tracked, alive_map, alive_order):
    """
    Update tracked list with alive members, placing replacements in dead slots.

    tracked: list of (owner_id, name) in duel circle position order
    alive_map: {owner_id: (member, name)} for currently alive members
    alive_order: [owner_id, ...] in duel circle order from get_members()
    """
    tracked_ids = {oid for oid, _ in tracked}
    alive_ids = set(alive_order)

    if not tracked_ids or not (alive_ids & tracked_ids):
        # New combat — no overlap with previous tracking
        tracked.clear()

        for oid in alive_order:
            tracked.append((oid, alive_map[oid][1]))

        return

    new_ids = alive_ids - tracked_ids
    if not new_ids:
        return

    # Map known alive members to their tracked indices
    tracked_id_to_idx = {oid: i for i, (oid, _) in enumerate(tracked)}
    # Dead positions available for replacement
    dead_positions = sorted(i for i, (oid, _) in enumerate(tracked) if oid not in alive_ids)

    for ai, oid in enumerate(alive_order):
        if oid not in new_ids:
            continue

        name = alive_map[oid][1]

        # Find the tracked indices of the nearest known neighbours
        # in the alive order to bracket where this new member belongs
        prev_ti = -1
        next_ti = len(tracked)

        for j, other_oid in enumerate(alive_order):
            if other_oid in tracked_id_to_idx:
                ti = tracked_id_to_idx[other_oid]

                if j < ai:
                    prev_ti = max(prev_ti, ti)
                elif j > ai:
                    next_ti = min(next_ti, ti)

        # Replace the dead slot between the brackets
        candidates = [dp for dp in dead_positions if prev_ti < dp < next_ti]
        if candidates:
            tracked[candidates[0]] = (oid, name)
            dead_positions.remove(candidates[0])

        else:
            tracked.append((oid, name))


def _find_alive_index(tracked, alive_map, preferred_idx):
    """Get alive member at preferred tracked index (0-based), or nearest alive."""
    if preferred_idx < len(tracked):
        oid = tracked[preferred_idx][0]

        if oid in alive_map:
            return alive_map[oid][0], preferred_idx

    # Fall back to first alive member in tracked order
    for i, (oid, _) in enumerate(tracked):
        if oid in alive_map:
            return alive_map[oid][0], i

    return None, preferred_idx


async def total_stats(
    client: Client,
    ally_index: int,
    enemy_index: int,
    base_damage: int = None,
    school_id: int = None,
    force_crit: bool = None,
    force_school: bool = False,
    swapped: bool = False,
    view_target: bool = False,
):
    global _tracked_allies, _tracked_enemies
    # Gets the readable relevant stats, splitting members by team
    combat = CombatHandler(client)

    try:
        members = await combat.get_members()

        # Split members by team using team_id
        client_member = await combat.get_client_member()

        if client_member is None:
            return None

        client_participant = await client_member.get_participant()
        client_original_team = await client_participant.original_team()
        client_current_team = await client_participant.team_id()

        allies = []
        enemies = []

        for m in members:
            p = await m.get_participant()

            if await p.original_team() == client_original_team:
                allies.append(m)
            else:
                enemies.append(m)

        if not allies or not enemies:
            return None

        # Build owner_id -> (member, name) maps for alive members (preserving order)
        alive_ally_map = {}
        alive_ally_order = []

        for m in allies:
            oid = await m.owner_id()
            alive_ally_map[oid] = (m, await m.name())
            alive_ally_order.append(oid)

        alive_enemy_map = {}
        alive_enemy_order = []

        for m in enemies:
            oid = await m.owner_id()
            alive_enemy_map[oid] = (m, await m.name())
            alive_enemy_order.append(oid)

        # Update tracking (preserves dead member positions, replaces dead slots)
        _update_tracking(_tracked_allies, alive_ally_map, alive_ally_order)
        _update_tracking(_tracked_enemies, alive_enemy_map, alive_enemy_order)

        # Clamp indices (1-based from GUI) to tracked range
        if len(_tracked_allies) < ally_index:
            ally_index = len(_tracked_allies)

        if len(_tracked_enemies) < enemy_index:
            enemy_index = len(_tracked_enemies)

        ally_index -= 1  # 0-based
        enemy_index -= 1  # 0-based

        # Resolve alive members for the selected indices (fall back if dead)
        if not swapped:
            member, ally_index = _find_alive_index(_tracked_allies, alive_ally_map, ally_index)
            target, enemy_index = _find_alive_index(_tracked_enemies, alive_enemy_map, enemy_index)

        else:
            member, enemy_index = _find_alive_index(_tracked_enemies, alive_enemy_map, enemy_index)
            target, ally_index = _find_alive_index(_tracked_allies, alive_ally_map, ally_index)

        if not member or not target:
            return None

        if view_target:
            member, target = target, member

        member_id = await member.owner_id()
        target_id = await target.owner_id()
        participant = await member.get_participant()
        stats = await member.get_stats()

        # Full name lists preserving dead positions
        ally_names = [name for _, name in _tracked_allies]
        enemy_names = [name for _, name in _tracked_enemies]

        # Safety clamp — indices can drift if members die between tracking and resolution
        if ally_names:
            ally_index = min(ally_index, len(ally_names) - 1)

        if enemy_names:
            enemy_index = min(enemy_index, len(enemy_names) - 1)

        member_name = await member.name()
        member_type = await enemy_type_str(member)
        template_id = await participant.template_id_full()
        npc_template = await participant.fetch_npc_behavior_template()
        template_name = await npc_template.behavior_name() if npc_template else "N/A"
        user_base_damage = base_damage
        user_school_id = school_id

        if school_id == "target":
            target_participant = await target.get_participant()
            school_id = await target_participant.primary_magic_school_id()

        elif not school_id or not force_school:
            school_id = await participant.primary_magic_school_id()

        real_school_id = await participant.primary_magic_school_id()

        school_name = school_to_str[real_school_id]
        temp_school_name = school_to_str[school_id]

        power_pips = await member.power_pips()
        pips = await member.normal_pips()
        shadow_pips = await member.shadow_pips()

        health = await member.health()
        max_health = await member.max_health()

        raw_resistances = await stats.dmg_reduce_percent()
        uni_resist = await stats.dmg_reduce_percent_all()
        real_resistances = to_percent(add_universal_stat(raw_resistances, uni_resist))

        raw_damages = await stats.dmg_bonus_percent()
        uni_damage = await stats.dmg_bonus_percent_all()
        real_damages = to_percent(add_universal_stat(raw_damages, uni_damage))

        raw_pierces = await stats.ap_bonus_percent()
        uni_pierce = await stats.ap_bonus_percent_all()
        real_pierces = to_percent(add_universal_stat(raw_pierces, uni_pierce))

        raw_crits = await stats.critical_hit_rating_by_school()
        uni_crit = await stats.critical_hit_rating_all()
        real_crits = add_universal_stat(raw_crits, uni_crit)

        raw_blocks = await stats.block_rating_by_school()
        uni_block = await stats.block_rating_all()
        real_blocks = add_universal_stat(raw_blocks, uni_block)

        masteries = await get_str_masteries(member)
        masteries_str = ", ".join(masteries)

        total_pips = (power_pips * 2) + (shadow_pips * 3.6) + pips

        if school_id in damage_per_pip:
            dpp = shadow_damage_per_pip[school_id]

        else:
            dpp = 100

        if not base_damage:
            base_damage = dpp * total_pips

        global_effect = None
        combat_resolver = await client.duel.combat_resolver()

        if combat_resolver:
            global_effect = await combat_resolver.global_effect()

        estimated_damage = await base_damage_calculation_from_id(
            client, members, member_id, target_id, base_damage, school_id, global_effect, force_crit=force_crit
        )

        resistances, raw_boosts = to_seperated_str_stats(real_resistances)

        damages, _ = to_seperated_str_stats(real_damages)
        pierces, _ = to_seperated_str_stats(real_pierces)
        crits, _ = to_seperated_str_stats(real_crits)
        blocks, _ = to_seperated_str_stats(real_blocks)

        if await member.is_player() and await target.is_player():
            stat_lines = [{"key": "pvp", "label": "Notice", "value": "The stat viewer is not supported in PvP."}]

        else:
            stat_lines = [
                {
                    "key": "est_dmg",
                    "label": "Est. Max Dmg",
                    "value": f"{int(estimated_damage)} vs {await target.name()}",
                },
                {"key": "name", "label": "Name", "value": f"{member_name} - {member_type} - {school_name}"},
                {"key": "template_id", "label": "Template ID", "value": str(template_id)},
                {"key": "template_name", "label": "Template Name", "value": template_name},
                {"key": "power_pips", "label": "Power Pips", "value": str(power_pips)},
                {"key": "pips", "label": "Pips", "value": str(pips)},
                {"key": "shadow_pips", "label": "Shadow Pips", "value": str(shadow_pips)},
                {
                    "key": "health",
                    "label": "Health",
                    "value": f"{health}/{max_health} ({int(health / max_health * 100)}%)",
                },
                {"key": "boosts", "label": "Boosts", "value": dict_to_str(raw_boosts, take_abs=True)},
                {"key": "resists", "label": "Resists", "value": dict_to_str(resistances)},
                {"key": "damages", "label": "Damages", "value": dict_to_str(damages)},
                {"key": "pierces", "label": "Pierces", "value": dict_to_str(pierces)},
                {"key": "crits", "label": "Crits", "value": dict_to_str(crits)},
                {"key": "blocks", "label": "Blocks", "value": dict_to_str(blocks)},
                {"key": "masteries", "label": "Masteries", "value": masteries_str},
            ]

        # Per-slot damage estimates using tracked positions (preserves dead members)
        slot_info = {}
        ally_target_id = target_id if not swapped else member_id
        enemy_target_id = member_id if not swapped else target_id

        for side, tracked, alive_map, tid in [
            ("ally", _tracked_allies, alive_ally_map, ally_target_id),
            ("enemy", _tracked_enemies, alive_enemy_map, enemy_target_id),
        ]:
            for i, (oid, tracked_name) in enumerate(tracked):
                entry = alive_map.get(oid)

                if entry is None:
                    # Dead member — preserve position
                    slot_info[(side, i + 1)] = {
                        "name": tracked_name,
                        "max_dmg": 0,
                        "sim_dmg": 0,
                        "is_friendly": (side == "ally"),
                        "is_dead": True,
                        "is_stunned": False,
                    }
                    continue

                m = entry[0]
                try:
                    p = await m.get_participant()
                    sid = await p.primary_magic_school_id()
                    pp = await m.power_pips()
                    np = await m.normal_pips()
                    sp = await m.shadow_pips()
                    base = shadow_damage_per_pip.get(sid, 100) * ((pp * 2) + (sp * 3.6) + np)
                    mid = await m.owner_id()
                    name = await m.name()
                    current_tid = await p.team_id()
                    is_friendly = current_tid == client_current_team
                    max_dmg = await base_damage_calculation_from_id(
                        client, members, mid, tid, base, sid, global_effect, force_crit=True
                    )

                    if user_base_damage and user_school_id:
                        sim_dmg = await base_damage_calculation_from_id(
                            client,
                            members,
                            mid,
                            tid,
                            user_base_damage,
                            user_school_id,
                            global_effect,
                            force_crit=force_crit,
                        )

                    else:
                        sim_dmg = max_dmg

                    stunned = await m.is_stunned()
                    slot_info[(side, i + 1)] = {
                        "name": name,
                        "max_dmg": int(max_dmg),
                        "sim_dmg": int(sim_dmg),
                        "is_friendly": is_friendly,
                        "is_dead": False,
                        "is_stunned": stunned,
                    }

                except Exception:
                    slot_info[(side, i + 1)] = {
                        "name": tracked_name,
                        "max_dmg": 0,
                        "sim_dmg": 0,
                        "is_friendly": (side == "ally"),
                        "is_dead": False,
                        "is_stunned": False,
                    }

        return (stat_lines, ally_names, enemy_names, ally_index, enemy_index, temp_school_name, slot_info)

    except (MemoryInvalidated, ValueError):
        await asyncio.sleep(0.5)
        return await total_stats(
            client, ally_index + 1, enemy_index + 1, base_damage, swapped=swapped, view_target=view_target
        )


def dict_to_str(
    input_dict: Dict[str, float],
    seperator_1: str = ": ",
    seperator_2: str = ", ",
    take_abs: bool = False,
    key_blacklist: List[str] = ["WhirlyBurly", "Gardening", "CastleMagic", "Cantrips", "Fishing"],
) -> str:
    # Converts a str stats dict to a GUI readable list of stats
    output_str = ""

    for key in list(input_dict.keys()):
        if key not in key_blacklist:
            if not take_abs:
                output_str += f"{key}{seperator_1}{int(input_dict[key])}{seperator_2}"

            else:
                output_str += f"{key}{seperator_1}{abs(int(input_dict[key]))}{seperator_2}"

    return output_str


def to_gui_str(stats, seperator: str = "\n") -> str:
    # Converts the total stats into GUI readable strings
    str_stats_list = []

    for stat in stats:
        if type(stat) == Dict[str, float]:
            str_stats_list.append(dict_to_str(stat))

        else:
            str_stats_list.append(str(stat))

    str_stats = seperator.join(str_stats_list)
    return str_stats
