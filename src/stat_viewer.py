import asyncio
from typing import Dict, List, Tuple
from wizwalker import Client
from wizwalker.errors import MemoryInvalidated
from wizwalker.combat import CombatHandler
from src.combat_objects import school_to_str
from src.combat_utils import get_str_masteries, enemy_type_str, add_universal_stat, to_seperated_str_stats, to_percent
from src.combat_math import base_damage_calculation_from_id

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

damage_per_pip = {
	2343174: 100,
	72777: 83,
	83375795: 125,
	78318724: 85,
	2330892: 83,
	2448141: 90,
	1027491821: 85
}

shadow_damage_per_pip = {
	2343174: 120,
	72777: 100,
	83375795: 130,
	78318724: 105,
	2330892: 100,
	2448141: 115,
	1027491821: 105
}


async def total_stats(client: Client, ally_index: int, enemy_index: int, base_damage: int = None, school_id: int = None, force_crit: bool = None, force_school: bool = False, swapped: bool = False):
	# Gets the readable relevant stats, splitting members by team
	combat = CombatHandler(client)
	try:
		members = await combat.get_members()

		# Split members by team using team_id
		client_member = await combat.get_client_member()
		if client_member is None:
			return None
		client_participant = await client_member.get_participant()
		client_team_id = await client_participant.team_id()

		allies = []
		enemies = []
		for m in members:
			p = await m.get_participant()
			if await p.team_id() == client_team_id:
				allies.append(m)
			else:
				enemies.append(m)

		if not allies or not enemies:
			return None

		# Clamp indices (1-based from GUI) to valid range
		if len(allies) < ally_index:
			ally_index = len(allies)
		if len(enemies) < enemy_index:
			enemy_index = len(enemies)
		ally_index -= 1  # 0-based
		enemy_index -= 1  # 0-based

		# Default: caster=ally (show your stats), target=enemy (damage against them)
		# Swapped: caster=enemy (show their stats), target=ally (their damage against you)
		if not swapped:
			member = allies[ally_index]
			target = enemies[enemy_index]
		else:
			member = enemies[enemy_index]
			target = allies[ally_index]

		member_id = await member.owner_id()
		target_id = await target.owner_id()
		participant = await member.get_participant()
		stats = await member.get_stats()

	except MemoryInvalidated:
		await asyncio.sleep(0.5)
		return await total_stats(client, ally_index + 1, enemy_index + 1, base_damage, swapped=swapped)

	else:
		ally_names = [f'{i + 1} - {await m.name()}' for i, m in enumerate(allies)]
		enemy_names = [f'{i + 1} - {await m.name()}' for i, m in enumerate(enemies)]
		member_name = await member.name()
		member_type = await enemy_type_str(member)
		user_base_damage = base_damage
		user_school_id = school_id
		if not school_id or not force_school:
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
		masteries_str = ', '.join(masteries)

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

		estimated_damage = await base_damage_calculation_from_id(client, members, member_id, target_id, base_damage, school_id, global_effect, force_crit=force_crit)

		resistances, raw_boosts = to_seperated_str_stats(real_resistances)

		damages, _ = to_seperated_str_stats(real_damages)
		pierces, _ = to_seperated_str_stats(real_pierces)
		crits, _ = to_seperated_str_stats(real_crits)
		blocks, _ = to_seperated_str_stats(real_blocks)

		if await member.is_player() and await target.is_player():
			total_stats = ['The stat viewer is not supported in PvP.']

		else:
			total_stats = [
				f'Estimated Max Dmg Against {await target.name()}: {int(estimated_damage)}',
				f'Name: {member_name} - {member_type} - {school_name}',
				f'Power Pips: {power_pips} - Pips: {pips}',
				f'Shadow Pips: {shadow_pips}',
				f'Health: {health}/{max_health} ({(health // max_health) * 100}%)',
				f'Boosts: {dict_to_str(raw_boosts, take_abs=True)}',
				f'Resists: {dict_to_str(resistances)}',
				f'Damages: {dict_to_str(damages)}',
				f'Pierces: {dict_to_str(pierces)}',
				f'Crits: {dict_to_str(crits)}',
				f'Blocks: {dict_to_str(blocks)}',
				f'Masteries: {masteries_str}',
			]

		# Per-slot damage estimates (each member vs selected target on the other side)
		slot_info = {}
		ally_target_id = await enemies[enemy_index].owner_id()
		enemy_target_id = await allies[ally_index].owner_id()

		for side, team, tid in [('ally', allies, ally_target_id), ('enemy', enemies, enemy_target_id)]:
			for i, m in enumerate(team):
				try:
					p = await m.get_participant()
					sid = await p.primary_magic_school_id()
					pp = await m.power_pips()
					np = await m.normal_pips()
					sp = await m.shadow_pips()
					base = shadow_damage_per_pip.get(sid, 100) * ((pp * 2) + (sp * 3.6) + np)
					mid = await m.owner_id()
					name = await m.name()
					max_dmg = await base_damage_calculation_from_id(client, members, mid, tid, base, sid, global_effect, force_crit=True)
					if user_base_damage and user_school_id:
						sim_dmg = await base_damage_calculation_from_id(client, members, mid, tid, user_base_damage, user_school_id, global_effect, force_crit=force_crit)
					else:
						sim_dmg = max_dmg
					slot_info[(side, i + 1)] = {'name': name, 'max_dmg': int(max_dmg), 'sim_dmg': int(sim_dmg)}
				except Exception:
					slot_info[(side, i + 1)] = {'name': '???', 'max_dmg': 0, 'sim_dmg': 0}

		return (total_stats, ally_names, enemy_names, ally_index, enemy_index, temp_school_name, slot_info)


def dict_to_str(input_dict: Dict[str, float], seperator_1: str = ': ', seperator_2: str = ', ', take_abs: bool = False, key_blacklist: List[str] = ['WhirlyBurly', 'Gardening', 'CastleMagic', 'Cantrips', 'Fishing']) -> str:
    # Converts a str stats dict to a GUI readable list of stats
    output_str = ''
    for key in list(input_dict.keys()):
        if key not in key_blacklist:
            if not take_abs:
                output_str += f'{key}{seperator_1}{int(input_dict[key])}{seperator_2}'

            else:
                output_str += f'{key}{seperator_1}{abs(int(input_dict[key]))}{seperator_2}'

    return output_str


def to_gui_str(stats, seperator: str = '\n') -> str:
    # Converts the total stats into GUI readable strings
    str_stats_list = []
    for stat in stats:
        if type(stat) == Dict[str, float]:
            str_stats_list.append(dict_to_str(stat))

        else:
            str_stats_list.append(str(stat))

    str_stats = seperator.join(str_stats_list)

    return str_stats