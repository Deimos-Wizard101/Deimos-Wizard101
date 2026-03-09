from typing import List

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass


class GameStats(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def max_hitpoints(self) -> int:
        """
        Client's max hitpoints; base + bonus
        """
        base = await self.base_hitpoints()
        bonus = await self.bonus_hitpoints()
        return base + bonus

    async def max_mana(self) -> int:
        """
        Clients's max mana; base + bonus
        """
        base = await self.base_mana()
        bonus = await self.bonus_mana()
        return base + bonus

    async def base_hitpoints(self) -> int:
        return await self.read_value_from_offset(80, Primitive.int32)

    async def write_base_hitpoints(self, base_hitpoints: int):
        await self.write_value_to_offset(80, base_hitpoints, Primitive.int32)

    async def base_mana(self) -> int:
        return await self.read_value_from_offset(84, Primitive.int32)

    async def write_base_mana(self, base_mana: int):
        await self.write_value_to_offset(84, base_mana, Primitive.int32)

    async def base_gold_pouch(self) -> int:
        return await self.read_value_from_offset(88, Primitive.int32)

    async def write_base_gold_pouch(self, base_gold_pouch: int):
        await self.write_value_to_offset(88, base_gold_pouch, Primitive.int32)

    async def base_event_currency1_pouch(self) -> int:
        return await self.read_value_from_offset(92, Primitive.int32)

    async def write_base_event_currency1_pouch(self, base_event_currency1_pouch: int):
        await self.write_value_to_offset(92, base_event_currency1_pouch, Primitive.int32)

    async def base_event_currency2_pouch(self) -> int:
        return await self.read_value_from_offset(96, Primitive.int32)

    async def write_base_event_currency2_pouch(self, base_event_currency2_pouch: int):
        await self.write_value_to_offset(96, base_event_currency2_pouch, Primitive.int32)

    async def base_pvp_currency_pouch(self) -> int:
        return await self.read_value_from_offset(100, Primitive.int32)

    async def write_base_pvp_currency_pouch(self, base_pvp_currency_pouch: int):
        await self.write_value_to_offset(100, base_pvp_currency_pouch, Primitive.int32)

    async def base_pvp_tourney_currency_pouch(self) -> int:
        return await self.read_value_from_offset(104, Primitive.int32)

    async def write_base_pvp_tourney_currency_pouch(self, base_pvp_tourney_currency_pouch: int):
        await self.write_value_to_offset(104, base_pvp_tourney_currency_pouch, Primitive.int32)
    
    async def energy_max(self) -> int:
        return await self.read_value_from_offset(108, Primitive.int32)

    async def write_energy_max(self, energy_max: int):
        await self.write_value_to_offset(108, energy_max, Primitive.int32)

    async def current_hitpoints(self) -> int:
        return await self.read_value_from_offset(112, Primitive.int32)

    async def write_current_hitpoints(self, current_hitpoints: int):
        await self.write_value_to_offset(112, current_hitpoints, Primitive.int32)

    async def current_gold(self) -> int:
        return await self.read_value_from_offset(116, Primitive.int32)

    async def write_current_gold(self, current_gold: int):
        await self.write_value_to_offset(116, current_gold, Primitive.int32)

    async def current_event_currency1(self) -> int:
        return await self.read_value_from_offset(120, Primitive.int32)

    async def write_current_event_currency1(self, current_event_currency1: int):
        await self.write_value_to_offset(120, current_event_currency1, Primitive.int32)

    async def current_event_currency2(self) -> int:
        return await self.read_value_from_offset(124, Primitive.int32)

    async def write_current_event_currency2(self, current_event_currency2: int):
        await self.write_value_to_offset(124, current_event_currency2, Primitive.int32)

    async def current_pvp_currency(self) -> int:
        return await self.read_value_from_offset(128, Primitive.int32)

    async def write_current_pvp_currency(self, current_pvp_currency: int):
        await self.write_value_to_offset(128, current_pvp_currency, Primitive.int32)

    async def current_pvp_tourney_currency(self) -> int:
        return await self.read_value_from_offset(132, Primitive.int32)

    async def write_current_pvp_tourney_currency(self, current_pvp_currency: int):
        await self.write_value_to_offset(132, current_pvp_currency, Primitive.int32)
    
    async def current_mana(self) -> int:
        return await self.read_value_from_offset(136, Primitive.int32)

    async def write_current_mana(self, current_mana: int):
        await self.write_value_to_offset(136, current_mana, Primitive.int32)

    async def current_arena_points(self) -> int:
        return await self.read_value_from_offset(140, Primitive.int32)

    async def write_current_arena_points(self, current_arena_points: int):
        await self.write_value_to_offset(140, current_arena_points, Primitive.int32)

    async def spell_charge_base(self) -> List[int]:
        return await self.read_dynamic_vector(144, Primitive.int32)

    # TODO: add write_dynamic_vector
    # async def write_spell_charge_base(self, spell_charge_base: int):
    #     await self.write_value_to_offset(144, spell_charge_base, Primitive.int32)

    async def potion_max(self) -> float:
        return await self.read_value_from_offset(168, Primitive.float32)

    async def write_potion_max(self, potion_max: float):
        await self.write_value_to_offset(168, potion_max, Primitive.float32)

    async def potion_charge(self) -> float:
        return await self.read_value_from_offset(172, Primitive.float32)

    async def write_potion_charge(self, potion_charge: float):
        await self.write_value_to_offset(172, potion_charge, Primitive.float32)

    # async def arena_ladder(self) -> class SharedPointer<class Ladder>:
    #     return await self.read_value_from_offset(176, "class SharedPointer<class Ladder>")

    # async def derby_ladder(self) -> class SharedPointer<class Ladder>:
    #     return await self.read_value_from_offset(192, "class SharedPointer<class Ladder>")

    # async def bracket_lader(self) -> class SharedPointer<class Ladder>:
    #     return await self.read_value_from_offset(208, "class SharedPointer<class Ladder>")

    async def bonus_hitpoints(self) -> int:
        return await self.read_value_from_offset(224, Primitive.int32)

    async def write_bonus_hitpoints(self, bonus_hitpoints: int):
        await self.write_value_to_offset(224, bonus_hitpoints, Primitive.int32)

    async def bonus_mana(self) -> int:
        return await self.read_value_from_offset(228, Primitive.int32)

    async def write_bonus_mana(self, bonus_mana: int):
        await self.write_value_to_offset(228, bonus_mana, Primitive.int32)

    async def bonus_energy(self) -> int:
        return await self.read_value_from_offset(244, Primitive.int32)

    async def write_bonus_energy(self, bonus_energy: int):
        await self.write_value_to_offset(244, bonus_energy, Primitive.int32)

    async def critical_hit_percent_all(self) -> float:
        return await self.read_value_from_offset(248, Primitive.float32)

    async def write_critical_hit_percent_all(self, critical_hit_percent_all: float):
        await self.write_value_to_offset(248, critical_hit_percent_all, Primitive.float32)

    async def block_percent_all(self) -> float:
        return await self.read_value_from_offset(252, Primitive.float32)

    async def write_block_percent_all(self, block_percent_all: float):
        await self.write_value_to_offset(252, block_percent_all, Primitive.float32)

    async def critical_hit_rating_all(self) -> float:
        return await self.read_value_from_offset(256, Primitive.float32)

    async def write_critical_hit_rating_all(self, critical_hit_rating_all: float):
        await self.write_value_to_offset(256, critical_hit_rating_all, Primitive.float32)

    async def block_rating_all(self) -> float:
        return await self.read_value_from_offset(260, Primitive.float32)

    async def write_block_rating_all(self, block_rating_all: float):
        await self.write_value_to_offset(260, block_rating_all, Primitive.float32)

    async def reference_level(self) -> int:
        return await self.read_value_from_offset(324, Primitive.int32)

    async def write_reference_level(self, reference_level: int):
        await self.write_value_to_offset(324, reference_level, Primitive.int32)

    async def highest_character_level_on_account(self) -> int:
        return await self.read_value_from_offset(336, Primitive.int32)

    async def write_highest_character_level_on_account(self, highest_character_level_on_account: int):
        await self.write_value_to_offset(336, highest_character_level_on_account, Primitive.int32)

    async def pet_act_chance(self) -> int:
        return await self.read_value_from_offset(344, Primitive.int32)

    async def write_pet_act_chance(self, pet_act_chance: int):
        await self.write_value_to_offset(344, pet_act_chance, Primitive.int32)

    async def dmg_bonus_percent(self) -> List[float]:
        return await self.read_dynamic_vector(352, Primitive.float32)

    async def write_dmg_bonus_percent(self, dmg_bonus_percent: float):
        await self.write_value_to_offset(352, dmg_bonus_percent, Primitive.float32)

    async def dmg_bonus_flat(self) -> List[float]:
        return await self.read_dynamic_vector(376, Primitive.float32)

    async def write_dmg_bonus_flat(self, dmg_bonus_flat: float):
        await self.write_value_to_offset(376, dmg_bonus_flat, Primitive.float32)

    async def acc_bonus_percent(self) -> List[float]:
        return await self.read_dynamic_vector(400, Primitive.float32)

    async def write_acc_bonus_percent(self, acc_bonus_percent: float):
        await self.write_value_to_offset(400, acc_bonus_percent, Primitive.float32)

    async def ap_bonus_percent(self) -> List[float]:
        return await self.read_dynamic_vector(424, Primitive.float32)

    async def write_ap_bonus_percent(self, ap_bonus_percent: float):
        await self.write_value_to_offset(424, ap_bonus_percent, Primitive.float32)

    async def dmg_reduce_percent(self) -> List[float]:
        return await self.read_dynamic_vector(448, Primitive.float32)

    async def write_dmg_reduce_percent(self, dmg_reduce_percent: float):
        await self.write_value_to_offset(448, dmg_reduce_percent, Primitive.float32)

    async def dmg_reduce_flat(self) -> List[float]:
        return await self.read_dynamic_vector(472, Primitive.float32)

    async def write_dmg_reduce_flat(self, dmg_reduce_flat: float):
        await self.write_value_to_offset(472, dmg_reduce_flat, Primitive.float32)

    async def acc_reduce_percent(self) -> List[float]:
        return await self.read_dynamic_vector(496, Primitive.float32)

    async def write_acc_reduce_percent(self, acc_reduce_percent: float):
        await self.write_value_to_offset(496, acc_reduce_percent, Primitive.float32)

    async def heal_bonus_percent(self) -> List[float]:
        return await self.read_dynamic_vector(520, Primitive.float32)

    async def write_heal_bonus_percent(self, heal_bonus_percent: float):
        await self.write_value_to_offset(520, heal_bonus_percent, Primitive.float32)

    async def heal_inc_bonus_percent(self) -> List[float]:
        return await self.read_dynamic_vector(544, Primitive.float32)

    async def write_heal_inc_bonus_percent(self, heal_inc_bonus_percent: float):
        await self.write_value_to_offset(544, heal_inc_bonus_percent, Primitive.float32)

    async def spell_charge_bonus(self) -> List[int]:
        return await self.read_dynamic_vector(592, Primitive.int32)

    async def write_spell_charge_bonus(self, spell_charge_bonus: int):
        await self.write_value_to_offset(592, spell_charge_bonus, Primitive.int32)

    async def dmg_bonus_percent_all(self) -> float:
        return await self.read_value_from_offset(712, Primitive.float32)

    async def write_dmg_bonus_percent_all(self, dmg_bonus_percent_all: float):
        await self.write_value_to_offset(712, dmg_bonus_percent_all, Primitive.float32)

    async def dmg_bonus_flat_all(self) -> float:
        return await self.read_value_from_offset(716, Primitive.float32)

    async def write_dmg_bonus_flat_all(self, dmg_bonus_flat_all: float):
        await self.write_value_to_offset(716, dmg_bonus_flat_all, Primitive.float32)

    async def acc_bonus_percent_all(self) -> float:
        return await self.read_value_from_offset(720, Primitive.float32)

    async def write_acc_bonus_percent_all(self, acc_bonus_percent_all: float):
        await self.write_value_to_offset(720, acc_bonus_percent_all, Primitive.float32)

    async def ap_bonus_percent_all(self) -> float:
        return await self.read_value_from_offset(724, Primitive.float32)

    async def write_ap_bonus_percent_all(self, ap_bonus_percent_all: float):
        await self.write_value_to_offset(724, ap_bonus_percent_all, Primitive.float32)

    async def dmg_reduce_percent_all(self) -> float:
        return await self.read_value_from_offset(728, Primitive.float32)

    async def write_dmg_reduce_percent_all(self, dmg_reduce_percent_all: float):
        await self.write_value_to_offset(728, dmg_reduce_percent_all, Primitive.float32)

    async def dmg_reduce_flat_all(self) -> float:
        return await self.read_value_from_offset(732, Primitive.float32)

    async def write_dmg_reduce_flat_all(self, dmg_reduce_flat_all: float):
        await self.write_value_to_offset(732, dmg_reduce_flat_all, Primitive.float32)

    async def acc_reduce_percent_all(self) -> float:
        return await self.read_value_from_offset(736, Primitive.float32)

    async def write_acc_reduce_percent_all(self, acc_reduce_percent_all: float):
        await self.write_value_to_offset(736, acc_reduce_percent_all, Primitive.float32)

    async def heal_bonus_percent_all(self) -> float:
        return await self.read_value_from_offset(740, Primitive.float32)

    async def write_heal_bonus_percent_all(self, heal_bonus_percent_all: float):
        await self.write_value_to_offset(740, heal_bonus_percent_all, Primitive.float32)

    async def heal_inc_bonus_percent_all(self) -> float:
        return await self.read_value_from_offset(744, Primitive.float32)

    async def write_heal_inc_bonus_percent_all(self, heal_inc_bonus_percent_all: float):
        await self.write_value_to_offset(744, heal_inc_bonus_percent_all, Primitive.float32)

    async def spell_charge_bonus_all(self) -> int:
        return await self.read_value_from_offset(752, Primitive.int32)

    async def write_spell_charge_bonus_all(self, spell_charge_bonus_all: int):
        await self.write_value_to_offset(752, spell_charge_bonus_all, Primitive.int32)

    async def power_pip_base(self) -> float:
        return await self.read_value_from_offset(756, Primitive.float32)

    async def write_power_pip_base(self, power_pip_base: float):
        await self.write_value_to_offset(756, power_pip_base, Primitive.float32)

    async def power_pip_bonus_percent_all(self) -> float:
        return await self.read_value_from_offset(792, Primitive.float32)

    async def write_power_pip_bonus_percent_all(self, power_pip_bonus_percent_all: float):
        await self.write_value_to_offset(792, power_pip_bonus_percent_all, Primitive.float32)

    async def xp_percent_increase(self) -> float:
        return await self.read_value_from_offset(800, Primitive.float32)

    async def write_xp_percent_increase(self, xp_percent_increase: float):
        await self.write_value_to_offset(800, xp_percent_increase, Primitive.float32)

    async def critical_hit_percent_by_school(self) -> List[float]:
        return await self.read_dynamic_vector(616, Primitive.float32)

    async def write_critical_hit_percent_by_school(self, critical_hit_percent_by_school: float):
        await self.write_value_to_offset(616, critical_hit_percent_by_school, Primitive.float32)

    async def block_percent_by_school(self) -> List[float]:
        return await self.read_dynamic_vector(640, Primitive.float32)

    async def write_block_percent_by_school(self, block_percent_by_school: float):
        await self.write_value_to_offset(640, block_percent_by_school, Primitive.float32)

    async def critical_hit_rating_by_school(self) -> List[float]:
        return await self.read_dynamic_vector(664, Primitive.float32)

    async def write_critical_hit_rating_by_school(self, critical_hit_rating_by_school: float):
        await self.write_value_to_offset(664, critical_hit_rating_by_school, Primitive.float32)

    async def block_rating_by_school(self) -> List[float]:
        return await self.read_dynamic_vector(688, Primitive.float32)

    async def write_block_rating_by_school(self, block_rating_by_school: float):
        await self.write_value_to_offset(688, block_rating_by_school, Primitive.float32)

    async def balance_mastery(self) -> int:
        return await self.read_value_from_offset(832, Primitive.int32)

    async def write_balance_mastery(self, balance_mastery: int):
        await self.write_value_to_offset(832, balance_mastery, Primitive.int32)

    async def death_mastery(self) -> int:
        return await self.read_value_from_offset(836, Primitive.int32)

    async def write_death_mastery(self, death_mastery: int):
        await self.write_value_to_offset(836, death_mastery, Primitive.int32)

    async def fire_mastery(self) -> int:
        return await self.read_value_from_offset(840, Primitive.int32)

    async def write_fire_mastery(self, fire_mastery: int):
        await self.write_value_to_offset(840, fire_mastery, Primitive.int32)

    async def ice_mastery(self) -> int:
        return await self.read_value_from_offset(844, Primitive.int32)

    async def write_ice_mastery(self, ice_mastery: int):
        await self.write_value_to_offset(844, ice_mastery, Primitive.int32)

    async def life_mastery(self) -> int:
        return await self.read_value_from_offset(848, Primitive.int32)

    async def write_life_mastery(self, life_mastery: int):
        await self.write_value_to_offset(848, life_mastery, Primitive.int32)

    async def myth_mastery(self) -> int:
        return await self.read_value_from_offset(852, Primitive.int32)

    async def write_myth_mastery(self, myth_mastery: int):
        await self.write_value_to_offset(852, myth_mastery, Primitive.int32)

    async def storm_mastery(self) -> int:
        return await self.read_value_from_offset(856, Primitive.int32)

    async def write_storm_mastery(self, storm_mastery: int):
        await self.write_value_to_offset(856, storm_mastery, Primitive.int32)

    async def maximum_number_of_islands(self) -> int:
        return await self.read_value_from_offset(860, Primitive.int32)

    async def write_maximum_number_of_islands(self, maximum_number_of_islands: int):
        await self.write_value_to_offset(860, maximum_number_of_islands, Primitive.int32)

    async def gardening_level(self) -> int:
        return await self.read_value_from_offset(864, Primitive.uint8)

    async def write_gardening_level(self, gardening_level: int):
        await self.write_value_to_offset(864, gardening_level, Primitive.uint8)

    async def gardening_xp(self) -> int:
        return await self.read_value_from_offset(868, Primitive.int32)

    async def write_gardening_xp(self, gardening_xp: int):
        await self.write_value_to_offset(868, gardening_xp, Primitive.int32)

    async def invisible_to_friends(self) -> bool:
        return await self.read_value_from_offset(872, Primitive.bool)

    async def write_invisible_to_friends(self, invisible_to_friends: bool):
        await self.write_value_to_offset(872, invisible_to_friends, Primitive.bool)

    async def show_item_lock(self) -> bool:
        return await self.read_value_from_offset(873, Primitive.bool)

    async def write_show_item_lock(self, show_item_lock: bool):
        await self.write_value_to_offset(873, show_item_lock, Primitive.bool)

    async def quest_finder_enabled(self) -> bool:
        return await self.read_value_from_offset(874, Primitive.bool)

    async def write_quest_finder_enabled(self, quest_finder_enabled: bool):
        await self.write_value_to_offset(874, quest_finder_enabled, Primitive.bool)

    async def buddy_list_limit(self) -> int:
        return await self.read_value_from_offset(876, Primitive.int32)

    async def write_buddy_list_limit(self, buddy_list_limit: int):
        await self.write_value_to_offset(876, buddy_list_limit, Primitive.int32)

    async def dont_allow_friend_finder_codes(self) -> bool:
        return await self.read_value_from_offset(884, Primitive.bool)

    async def write_dont_allow_friend_finder_codes(self, dont_allow_friend_finder_codes: bool):
        await self.write_value_to_offset(884, dont_allow_friend_finder_codes, Primitive.bool)

    async def stun_resistance_percent(self) -> float:
        return await self.read_value_from_offset(880, Primitive.float32)

    async def write_stun_resistance_percent(self, stun_resistance_percent: float):
        await self.write_value_to_offset(880, stun_resistance_percent, Primitive.float32)

    async def shadow_magic_unlocked(self) -> bool:
        return await self.read_value_from_offset(892, Primitive.bool)

    async def write_shadow_magic_unlocked(self, shadow_magic_unlocked: bool):
        await self.write_value_to_offset(892, shadow_magic_unlocked, Primitive.bool)

    async def shadow_pip_max(self) -> int:
        return await self.read_value_from_offset(888, Primitive.int32)

    async def write_shadow_pip_max(self, shadow_pip_max: int):
        await self.write_value_to_offset(888, shadow_pip_max, Primitive.int32)

    async def fishing_level(self) -> int:
        return await self.read_value_from_offset(893, Primitive.uint8)

    async def write_fishing_level(self, fishing_level: int):
        await self.write_value_to_offset(893, fishing_level, Primitive.uint8)

    async def fishing_xp(self) -> int:
        return await self.read_value_from_offset(896, Primitive.int32)

    async def write_fishing_xp(self, fishing_xp: int):
        await self.write_value_to_offset(896, fishing_xp, Primitive.int32)

    async def fishing_luck_bonus_percent(self) -> List[float]:
        return await self.read_dynamic_vector(568, Primitive.float32)

    async def write_fishing_luck_bonus_percent(self, fishing_luck_bonus_percent: float):
        await self.write_value_to_offset(568, fishing_luck_bonus_percent, Primitive.float32)

    async def fishing_luck_bonus_percent_all(self) -> float:
        return await self.read_value_from_offset(748, Primitive.float32)

    async def write_fishing_luck_bonus_percent_all(self, fishing_luck_bonus_percent_all: float):
        await self.write_value_to_offset(748, fishing_luck_bonus_percent_all, Primitive.float32)

    async def subscriber_benefit_flags(self) -> int:
        return await self.read_value_from_offset(900, Primitive.uint32)

    async def write_subscriber_benefit_flags(self, subscriber_benefit_flags: int):
        await self.write_value_to_offset(900, subscriber_benefit_flags, Primitive.uint32)

    async def elixir_benefit_flags(self) -> int:
        return await self.read_value_from_offset(904, Primitive.uint32)

    async def write_elixir_benefit_flags(self, elixir_benefit_flags: int):
        await self.write_value_to_offset(904, elixir_benefit_flags, Primitive.uint32)

    async def shadow_pip_bonus_percent(self) -> float:
        return await self.read_value_from_offset(796, Primitive.float32)

    async def write_shadow_pip_bonus_percent(self, shadow_pip_bonus_percent: float):
        await self.write_value_to_offset(796, shadow_pip_bonus_percent, Primitive.float32)

    async def wisp_bonus_percent(self) -> float:
        return await self.read_value_from_offset(824, Primitive.float32)

    async def write_wisp_bonus_percent(self, wisp_bonus_percent: float):
        await self.write_value_to_offset(824, wisp_bonus_percent, Primitive.float32)

    async def pip_conversion_rating_all(self) -> float:
        return await self.read_value_from_offset(288, Primitive.float32)

    async def write_pip_conversion_rating_all(self, pip_conversion_rating_all: float):
        await self.write_value_to_offset(288, pip_conversion_rating_all, Primitive.float32)

    async def pip_conversion_rating_per_school(self) -> List[float]:
        return await self.read_dynamic_vector(264, Primitive.float32)

    async def write_pip_conversion_rating_per_school(self, pip_conversion_rating_per_school: float):
        await self.write_value_to_offset(264, pip_conversion_rating_per_school, Primitive.float32)

    async def pip_conversion_percent_all(self) -> float:
        return await self.read_value_from_offset(320, Primitive.float32)

    async def write_pip_conversion_percent_all(self, pip_conversion_percent_all: float):
        await self.write_value_to_offset(320, pip_conversion_percent_all, Primitive.float32)

    async def pip_conversion_percent_per_school(self) -> List[float]:
        return await self.read_dynamic_vector(296, Primitive.float32)

    async def write_pip_conversion_percent_per_school(self, pip_conversion_percent_per_school: float):
        await self.write_value_to_offset(296, pip_conversion_percent_per_school, Primitive.float32)

    async def monster_magic_level(self) -> int:
        return await self.read_value_from_offset(908, Primitive.uint8)

    async def write_monster_magic_level(self, monster_magic_level: int):
        await self.write_value_to_offset(908, monster_magic_level, Primitive.uint8)

    async def monster_magic_xp(self) -> int:
        return await self.read_value_from_offset(912, Primitive.int32)

    async def write_monster_magic_xp(self, monster_magic_xp: int):
        await self.write_value_to_offset(912, monster_magic_xp, Primitive.int32)

    async def player_chat_channel_is_public(self) -> bool:
        return await self.read_value_from_offset(916, Primitive.bool)

    async def write_player_chat_channel_is_public(self, player_chat_channel_is_public: bool):
        await self.write_value_to_offset(916, player_chat_channel_is_public, Primitive.bool)

    async def extra_inventory_space(self) -> int:
        return await self.read_value_from_offset(920, Primitive.int32)

    async def write_extra_inventory_space(self, extra_inventory_space: int):
        await self.write_value_to_offset(920, extra_inventory_space, Primitive.int32)

    async def remember_last_realm(self) -> bool:
        return await self.read_value_from_offset(924, Primitive.bool)

    async def write_remember_last_realm(self, remember_last_realm: bool):
        await self.write_value_to_offset(924, remember_last_realm, Primitive.bool)

    async def new_spellbook_layout_warning(self) -> bool:
        return await self.read_value_from_offset(925, Primitive.bool)

    async def write_new_spellbook_layout_warning(self, new_spellbook_layout_warning: bool):
        await self.write_value_to_offset(925, new_spellbook_layout_warning, Primitive.bool)

    async def pip_conversion_base_all_schools(self) -> int:
        return await self.read_value_from_offset(760, Primitive.int32)

    async def write_pip_conversion_base_all_schools(self, pip_conversion_base_all_schools: int):
        await self.write_value_to_offset(760, pip_conversion_base_all_schools, Primitive.int32)

    async def pip_conversion_base_per_school(self) -> List[int]:
        return await self.read_dynamic_vector(768, Primitive.int32)

    async def write_pip_conversion_base_per_school(self, pip_conversion_base_per_school: int):
        await self.write_value_to_offset(768, pip_conversion_base_per_school, Primitive.int32)

    async def purchased_custom_emotes1(self) -> int:
        return await self.read_value_from_offset(928, Primitive.uint32)

    async def write_purchased_custom_emotes1(self, purchased_custom_emotes1: int):
        await self.write_value_to_offset(928, purchased_custom_emotes1, Primitive.uint32)

    async def purchased_custom_teleport_effects1(self) -> int:
        return await self.read_value_from_offset(932, Primitive.uint32)

    async def write_purchased_custom_teleport_effects1(self, purchased_custom_teleport_effects1: int):
        await self.write_value_to_offset(932, purchased_custom_teleport_effects1, Primitive.uint32)

    async def equipped_teleport_effect(self) -> int:
        return await self.read_value_from_offset(936, Primitive.uint32)

    async def write_equipped_teleport_effect(self, equipped_teleport_effect: int):
        await self.write_value_to_offset(936, equipped_teleport_effect, Primitive.uint32)

    async def highest_world1_id(self) -> int:
        return await self.read_value_from_offset(956, Primitive.uint32)

    async def write_highest_world1_id(self, highest_world1_id: int):
        await self.write_value_to_offset(956, highest_world1_id, Primitive.uint32)

    async def highest_world2_id(self) -> int:
        return await self.read_value_from_offset(960, Primitive.uint32)

    async def write_highest_world2_id(self, highest_world2_i_d: int):
        await self.write_value_to_offset(960, highest_world2_i_d, Primitive.uint32)

    async def active_class_projects_list(self) -> int:
        return await self.read_value_from_offset(968, Primitive.uint32)

    async def write_active_class_projects_list(self, active_class_projects_list: int):
        await self.write_value_to_offset(968, active_class_projects_list, Primitive.uint32)

    async def disabled_item_slot_ids(self) -> int:
        return await self.read_value_from_offset(984, Primitive.uint32)

    async def write_disabled_item_slot_ids(self, disabled_item_slot_ids: int):
        await self.write_value_to_offset(984, disabled_item_slot_ids, Primitive.uint32)

    async def adventure_power_cooldown_time(self) -> int:
        return await self.read_value_from_offset(1000, Primitive.uint32)

    async def write_adventure_power_cooldown_time(self, adventure_power_cooldown_time: int):
        await self.write_value_to_offset(1000, adventure_power_cooldown_time, Primitive.uint32)

    async def purchased_custom_emotes2(self) -> int:
        return await self.read_value_from_offset(940, Primitive.uint32)

    async def write_purchased_custom_emotes2(self, purchased_custom_emotes2: int):
        await self.write_value_to_offset(940, purchased_custom_emotes2, Primitive.uint32)

    async def purchased_custom_teleport_effects2(self) -> int:
        return await self.read_value_from_offset(944, Primitive.uint32)

    async def write_purchased_custom_teleport_effects2(self, purchased_custom_teleport_effects2: int):
        await self.write_value_to_offset(944, purchased_custom_teleport_effects2, Primitive.uint32)

    async def purchased_custom_emotes3(self) -> int:
        return await self.read_value_from_offset(948, Primitive.uint32)

    async def write_purchased_custom_emotes3(self, purchased_custom_emotes3: int):
        await self.write_value_to_offset(948, purchased_custom_emotes3, Primitive.uint32)

    async def purchased_custom_teleport_effects3(self) -> int:
        return await self.read_value_from_offset(952, Primitive.uint32)

    async def write_purchased_custom_teleport_effects3(self, purchased_custom_teleport_effects3: int):
        await self.write_value_to_offset(952, purchased_custom_teleport_effects3, Primitive.uint32)

    async def shadow_pip_rating(self) -> float:
        return await self.read_value_from_offset(1004, Primitive.float32)

    async def write_shadow_pip_rating(self, shadow_pip_rating: float):
        await self.write_value_to_offset(1004, shadow_pip_rating, Primitive.float32)

    async def bonus_shadow_pip_rating(self) -> float:
        return await self.read_value_from_offset(1008, Primitive.float32)

    async def write_bonus_shadow_pip_rating(self, bonus_shadow_pip_rating: float):
        await self.write_value_to_offset(1008, bonus_shadow_pip_rating, Primitive.float32)

    async def shadow_pip_rate_accumulated(self) -> float:
        return await self.read_value_from_offset(1012, Primitive.float32)

    async def write_shadow_pip_rate_accumulated(self, shadow_pip_rate_accumulated: float):
        await self.write_value_to_offset(1012, shadow_pip_rate_accumulated, Primitive.float32)

    async def shadow_pip_rate_threshold(self) -> float:
        return await self.read_value_from_offset(1016, Primitive.float32)

    async def write_shadow_pip_rate_threshold(self, shadow_pip_rate_threshold: float):
        await self.write_value_to_offset(1016, shadow_pip_rate_threshold, Primitive.float32)

    async def shadow_pip_rate_percentage(self) -> int:
        return await self.read_value_from_offset(1020, Primitive.int32)

    async def write_shadow_pip_rate_percentage(self, shadow_pip_rate_percentage: int):
        await self.write_value_to_offset(1020, shadow_pip_rate_percentage, Primitive.int32)

    async def friendly_player(self) -> bool:
        return await self.read_value_from_offset(1024, Primitive.bool)

    async def write_friendly_player(self, friendly_player: bool):
        await self.write_value_to_offset(1024, friendly_player, Primitive.bool)

    async def emoji_skin_tone(self) -> int:
        return await self.read_value_from_offset(1028, Primitive.int32)

    async def write_emoji_skin_tone(self, emoji_skin_tone: int):
        await self.write_value_to_offset(1028, emoji_skin_tone, Primitive.int32)

    async def show_pvp_option(self) -> int:
        return await self.read_value_from_offset(1032, Primitive.uint32)

    async def write_show_pvp_option(self, show_pvp_option: int):
        await self.write_value_to_offset(1032, show_pvp_option, Primitive.uint32)

    async def favorite_slot(self) -> int:
        return await self.read_value_from_offset(1036, Primitive.int32)

    async def write_favorite_slot(self, favorite_slot: int):
        await self.write_value_to_offset(1036, favorite_slot, Primitive.int32)

    async def cantrip_level(self) -> int:
        return await self.read_value_from_offset(1040, Primitive.uint8)

    async def write_cantrip_level(self, cantrip_level: int):
        await self.write_value_to_offset(1040, cantrip_level, Primitive.uint8)

    async def cantrip_xp(self) -> int:
        return await self.read_value_from_offset(1044, Primitive.int32)

    async def write_cantrip_xp(self, cantrip_xp: int):
        await self.write_value_to_offset(1044, cantrip_xp, Primitive.int32)

    async def archmastery_base(self) -> float:
        return await self.read_value_from_offset(1048, Primitive.float32)

    async def write_archmastery_base(self, archmastery_base: float):
        return await self.write_value_to_offset(1048, archmastery_base, Primitive.float32)

    async def archmastery_bonus_flat(self) -> float:
        return await self.read_value_from_offset(1052, Primitive.float32)

    async def write_archmastery_bonus_flat(self, archmastery_bonus_flat: float):
        return await self.write_value_to_offset(1052, archmastery_bonus_flat, Primitive.float32)

    async def archmastery_bonus_percentage(self) -> float:
        return await self.read_value_from_offset(1056, Primitive.float32)

    async def write_archmastery_bonus_percentage(self, archmastery_bonus_percentage: float):
        return await self.write_value_to_offset(1056, archmastery_bonus_percentage, Primitive.float32)

    async def highest_character_world_on_account(self) -> int:
        return await self.read_value_from_offset(340, Primitive.int32)

    async def write_highest_character_world_on_account(self, highest_character_world_on_account: int):
        return await self.write_value_to_offset(340, highest_character_world_on_account, Primitive.int32)

    async def school_id(self) -> int:
        return await self.read_value_from_offset(328, Primitive.uint32)

    async def write_school_id(self, school_id: int):
        return await self.write_value_to_offset(328, school_id, Primitive.uint32)

    async def level_scaled(self) -> int:
        return await self.read_value_from_offset(332, Primitive.int32)

    async def write_level_scaled(self, level_scaled: int):
        return await self.write_value_to_offset(332, level_scaled, Primitive.int32)

    async def current_zone_name(self) -> str:
        return await self.read_string_from_offset(1064)

    async def write_current_zone_name(self, current_zone_name: str):
        await self.write_string_to_offset(1064, current_zone_name)

    async def mail_sent_today(self) -> int:
        return await self.read_value_from_offset(1096, Primitive.uint8)

    async def write_mail_sent_today(self, mail_sent_today: int):
        await self.write_value_to_offset(1096, mail_sent_today, Primitive.uint8)

    async def secondary_school(self) -> int:
        return await self.read_value_from_offset(1100, Primitive.int32)

    async def write_secondary_school(self, secondary_school: int):
        await self.write_value_to_offset(1100, secondary_school, Primitive.int32)

    async def disable_cross_play(self) -> bool:
        return await self.read_value_from_offset(1104, Primitive.bool)

    async def write_disable_cross_play(self, disable_cross_play: bool):
        await self.write_value_to_offset(1104, disable_cross_play, Primitive.bool)

    async def photo_filters(self) -> int:
        return await self.read_value_from_offset(1108, Primitive.uint32)

    async def write_photo_filters(self, photo_filters: int):
        await self.write_value_to_offset(1108, photo_filters, Primitive.uint32)

class CurrentGameStats(GameStats):
    async def read_base_address(self) -> int:
        return await self.hook_handler.read_current_player_stat_base()


class DynamicGameStats(DynamicMemoryObject, GameStats):
    pass
