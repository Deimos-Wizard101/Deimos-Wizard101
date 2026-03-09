from typing import List, Optional

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass

from .enums import PipAquiredByEnum
from .game_stats import DynamicGameStats
from .pip_count import DynamicPipCount
from .play_deck import DynamicPlayDeck
from .spell import DynamicHand
from .spell_effect import DynamicSpellEffect
from .behavior_template import NPCBehaviorTemplate, NpcBehaviorTemplateTitleType
from .client_object import DynamicClientObject


class CombatParticipant(PropertyClass):
    """
    Base class for CombatParticipants
    """

    def read_base_address(self) -> int:
        raise NotImplementedError()

    async def fetch_entity(self) -> DynamicClientObject | None:
        client = self.hook_handler.client
        for ent in await client.get_base_entity_list():
            if await ent.global_id_full() == await self.owner_id_full():
                return ent
        return None

    async def fetch_npc_behavior_template(self) -> NPCBehaviorTemplate | None:
        ent = await self.fetch_entity()
        if ent is None:
            return None
        return await ent.fetch_npc_behavior_template()


    async def owner_id_full(self) -> int:
        """
        This combat participant's owner id
        """
        return await self.read_value_from_offset(112, Primitive.uint64)

    async def write_owner_id_full(self, owner_id_full: int):
        """
        Write this combat participant's owner id

        Args:
            owner_id_full: The owner id to write
        """
        await self.write_value_to_offset(112, owner_id_full, Primitive.uint64)

    async def template_id_full(self) -> int:
        """
        This combat participant's template id
        """
        return await self.read_value_from_offset(120, Primitive.uint64)

    async def write_template_id_full(self, template_id_full: int):
        """
        Write this combat participant's template id

        Args:
            template_id_full: The template id to write
        """
        await self.write_value_to_offset(120, template_id_full, Primitive.uint64)

    async def is_player(self) -> bool:
        """
        If this combat participant is a player
        """
        return await self.read_value_from_offset(128, Primitive.bool)

    async def write_is_player(self, is_player: bool):
        """
        Write if this combat participant is a player

        Args:
            is_player: The bool to write
        """
        await self.write_value_to_offset(128, is_player, Primitive.bool)

    async def zone_id_full(self) -> int:
        """
        This combat participant's zone id
        """
        return await self.read_value_from_offset(136, Primitive.uint64)

    async def write_zone_id_full(self, zone_id_full: int):
        """
        Write this combat participant's zone id

        Args:
            zone_id_full: The zone id to write
        """
        await self.write_value_to_offset(136, zone_id_full, Primitive.uint64)

    # TODO: look into what a team id is; i.e is it always the two ids
    async def team_id(self) -> int:
        """
        This combat participant's team id
        """
        return await self.read_value_from_offset(144, Primitive.int32)

    async def write_team_id(self, team_id: int):
        """
        Write this combat participant's team id

        Args:
            team_id: The team id to write
        """
        await self.write_value_to_offset(144, team_id, Primitive.int32)

    # TODO: turn this into an enum?
    async def primary_magic_school_id(self) -> int:
        """
        This combat participant's primary school id

        Notes:
            This is a template id
        """
        return await self.read_value_from_offset(148, Primitive.int32)

    async def write_primary_magic_school_id(self, primary_magic_school_id: int):
        """
        Write this combat participant's primate school id

        Args:
            primary_magic_school_id: The school id to write

        Notes:
            this is a template id
        """
        await self.write_value_to_offset(148, primary_magic_school_id, Primitive.int32)

    async def pip_count(self) -> Optional[DynamicPipCount]:
        addr = await self.read_value_from_offset(152, Primitive.int64)

        if addr == 0:
            return None

        return DynamicPipCount(self.hook_handler, addr)

    async def num_pips(self) -> int:
        """
        The number of pips this combat participant has
        """
        pipcount = await self.pip_count()
        return await pipcount.generic_pips()

    async def write_num_pips(self, num_pips: int):
        """
        Write this participant's pip number

        Args:
            num_pips: The pip number to write
        """
        pipcount = await self.pip_count()
        return await pipcount.write_generic_pips(num_pips)

    async def num_power_pips(self) -> int:
        """
        The number of power pips this combat participant has
        """
        pipcount = await self.pip_count()
        return await pipcount.power_pips()

    async def write_num_power_pips(self, num_power_pips: int):
        """
        Write the number of power pips this combat participant has

        Args:
            num_power_pips: The power pip number to write
        """
        pipcount = await self.pip_count()
        return await pipcount.write_power_pips(num_power_pips)

    async def num_shadow_pips(self) -> int:
        """
        The number of shadow pips this combat participant has
        """
        pipcount = await self.pip_count()
        return await pipcount.shadow_pips()

    async def write_num_shadow_pips(self, num_shadow_pips: int):
        """
        Write the number of shadow pips this combat participant has

        Args:
            num_shadow_pips: The power pip number to write
        """
        pipcount = await self.pip_count()
        return await pipcount.write_shadow_pips(num_shadow_pips)

    async def pips_suspended(self) -> bool:
        """
        If this participant's pips are suspended
        """
        return await self.read_value_from_offset(184, Primitive.bool)

    async def write_pips_suspended(self, pips_suspended: bool):
        """
        Write if this participant's pips are suspended

        Args:
            pips_suspended: bool if pips are suspended
        """
        await self.write_value_to_offset(184, pips_suspended, Primitive.bool)

    # TODO: finish docs
    async def stunned(self) -> int:
        return await self.read_value_from_offset(188, Primitive.int32)

    async def write_stunned(self, stunned: int):
        await self.write_value_to_offset(188, stunned, Primitive.int32)

    async def mindcontrolled(self) -> int:
        return await self.read_value_from_offset(216, Primitive.int32)

    async def write_mindcontrolled(self, mindcontrolled: int):
        await self.write_value_to_offset(216, mindcontrolled, Primitive.int32)

    async def original_team(self) -> int:
        return await self.read_value_from_offset(224, Primitive.int32)

    async def write_original_team(self, original_team: int):
        await self.write_value_to_offset(224, original_team, Primitive.int32)

    async def aura_turn_length(self) -> int:
        return await self.read_value_from_offset(236, Primitive.int32)

    async def write_aura_turn_length(self, n_aura_turn_length: int):
        await self.write_value_to_offset(236, n_aura_turn_length, Primitive.int32)

    async def clue(self) -> int:
        return await self.read_value_from_offset(228, Primitive.int32)

    async def write_clue(self, clue: int):
        await self.write_value_to_offset(228, clue, Primitive.int32)

    async def rounds_dead(self) -> int:
        return await self.read_value_from_offset(232, Primitive.int32)

    async def write_rounds_dead(self, rounds_dead: int):
        await self.write_value_to_offset(232, rounds_dead, Primitive.int32)

    async def polymorph_turn_length(self) -> int:
        return await self.read_value_from_offset(240, Primitive.int32)

    async def write_polymorph_turn_length(self, n_polymorph_turn_length: int):
        await self.write_value_to_offset(240, n_polymorph_turn_length, Primitive.int32)

    async def player_health(self) -> int:
        return await self.read_value_from_offset(244, Primitive.int32)

    async def write_player_health(self, player_health: int):
        await self.write_value_to_offset(244, player_health, Primitive.int32)

    async def max_player_health(self) -> int:
        return await self.read_value_from_offset(248, Primitive.int32)

    async def write_max_player_health(self, max_player_health: int):
        await self.write_value_to_offset(248, max_player_health, Primitive.int32)

    async def hide_current_hp(self) -> bool:
        return await self.read_value_from_offset(252, Primitive.bool)

    async def write_hide_current_hp(self, _hide_current_h_p: bool):
        await self.write_value_to_offset(252, _hide_current_h_p, Primitive.bool)

    async def max_hand_size(self) -> int:
        return await self.read_value_from_offset(256, Primitive.int32)

    async def write_max_hand_size(self, max_hand_size: int):
        await self.write_value_to_offset(256, max_hand_size, Primitive.int32)

    async def hand(self) -> Optional[DynamicHand]:
        addr = await self.read_value_from_offset(264, Primitive.int64)

        if addr == 0:
            return None

        return DynamicHand(self.hook_handler, addr)

    async def saved_hand(self) -> Optional[DynamicHand]:
        addr = await self.read_value_from_offset(272, Primitive.int64)

        if addr == 0:
            return None

        return DynamicHand(self.hook_handler, addr)

    async def play_deck(self) -> Optional[DynamicPlayDeck]:
        addr = await self.read_value_from_offset(280, Primitive.int64)

        if addr == 0:
            return None

        return DynamicPlayDeck(self.hook_handler, addr)

    async def saved_play_deck(self) -> Optional[DynamicPlayDeck]:
        addr = await self.read_value_from_offset(288, Primitive.int64)

        if addr == 0:
            return None

        return DynamicPlayDeck(self.hook_handler, addr)

    async def saved_game_stats(self) -> Optional[DynamicGameStats]:
        addr = await self.read_value_from_offset(296, Primitive.int64)

        if addr == 0:
            return None

        return DynamicGameStats(self.hook_handler, addr)

    async def saved_primary_magic_school_id(self) -> int:
        return await self.read_value_from_offset(312, Primitive.int32)

    async def write_saved_primary_magic_school_id(self, saved_primary_magic_school_id: int):
        await self.write_value_to_offset(312, saved_primary_magic_school_id, Primitive.int32)

    async def game_stats(self) -> Optional[DynamicGameStats]:
        addr = await self.read_value_from_offset(320, Primitive.int64)

        if addr == 0:
            return None

        return DynamicGameStats(self.hook_handler, addr)

    # TODO: figure out what color is
    # async def color(self) -> class Color:
    #     return await self.read_value_from_offset(336, "class Color")
    #
    # async def write_color(self, color: class Color):
    #     await self.write_value_to_offset(328, 336, "class Color")

    async def rotation(self) -> float:
        return await self.read_value_from_offset(340, Primitive.float32)

    async def write_rotation(self, rotation: float):
        await self.write_value_to_offset(340, rotation, Primitive.float32)

    async def radius(self) -> float:
        return await self.read_value_from_offset(344, Primitive.float32)

    async def write_radius(self, radius: float):
        await self.write_value_to_offset(344, radius, Primitive.float32)

    async def subcircle(self) -> int:
        return await self.read_value_from_offset(348, Primitive.int32)

    async def write_subcircle(self, subcircle: int):
        await self.write_value_to_offset(348, subcircle, Primitive.int32)

    async def pvp(self) -> bool:
        return await self.read_value_from_offset(352, Primitive.bool)

    async def write_pvp(self, pvp: bool):
        await self.write_value_to_offset(352, pvp, Primitive.bool)

    async def raid(self) -> bool:
        return await self.read_value_from_offset(353, Primitive.bool)

    async def write_raid(self, raid: int):
        await self.write_value_to_offset(353, raid, Primitive.bool)

    # TODO: add class for this
    # async def dynamic_symbol(self):
    #   return await self.read_value_from_offset(356, "enum DynamicSigilSymbol"")

    async def accuracy_bonus(self) -> float:
        return await self.read_value_from_offset(400, Primitive.float32)

    async def write_accuracy_bonus(self, accuracy_bonus: float):
        await self.write_value_to_offset(400, accuracy_bonus, Primitive.float32)

    async def minion_sub_circle(self) -> int:
        return await self.read_value_from_offset(404, Primitive.int32)

    async def write_minion_sub_circle(self, minion_sub_circle: int):
        await self.write_value_to_offset(404, minion_sub_circle, Primitive.int32)

    async def is_minion(self) -> bool:
        return await self.read_value_from_offset(408, Primitive.bool)

    async def write_is_minion(self, is_minion: bool):
        await self.write_value_to_offset(408, is_minion, Primitive.bool)

    async def is_accompany_npc(self) -> bool:
        return await self.read_value_from_offset(416, Primitive.bool)

    async def write_is_accompany_npc(self, is_accompany_npc:bool) -> bool:
        await self.write_value_to_offset(416, is_accompany_npc, Primitive.bool)

    async def hanging_effects(self) -> List[DynamicSpellEffect]:
        hanging_effects = []
        for addr in await self.read_linked_list(424):
            hanging_effects.append(DynamicSpellEffect(self.hook_handler, addr))

        return hanging_effects

    async def public_hanging_effects(self) -> List[DynamicSpellEffect]:
        hanging_effects = []
        for addr in await self.read_linked_list(440):
            hanging_effects.append(DynamicSpellEffect(self.hook_handler, addr))

        return hanging_effects

    async def aura_effects(self) -> List[DynamicSpellEffect]:
        aura_effects = []
        for addr in await self.read_linked_list(456):
            aura_effects.append(DynamicSpellEffect(self.hook_handler, addr))

        return aura_effects

    # TODO: add this class
    # async def shadow_effects(self) -> class SharedPointer<class ShadowSpellTrackingData>:
    #     return await self.read_value_from_offset(472, "class SharedPointer<class ShadowSpellTrackingData>")

    async def shadow_spell_effects(self) -> List[DynamicSpellEffect]:
        shadow_spell_effects = []
        for addr in await self.read_linked_list(488):
            shadow_spell_effects.append(DynamicSpellEffect(self.hook_handler, addr))

        return shadow_spell_effects

    async def death_activated_effects(self) -> List[DynamicSpellEffect]:
        death_activated_effects = []
        for addr in await self.read_shared_linked_list(520):
            death_activated_effects.append(DynamicSpellEffect(self.hook_handler, addr))

        return death_activated_effects

    # note: these are actually DelaySpellEffects
    async def delay_cast_effects(self) -> List[DynamicSpellEffect]:
        delay_cast_effects = []
        for addr in await self.read_linked_list(536):
            delay_cast_effects.append(DynamicSpellEffect(self.hook_handler, addr))

        return delay_cast_effects

    async def polymorph_spell_template_id(self) -> int:
        return await self.read_value_from_offset(584, Primitive.uint32)

    async def write_polymorph_spell_template_id(self, polymorph_spell_template_id: int):
        await self.write_value_to_offset(584, polymorph_spell_template_id, Primitive.uint32)

    async def side(self) -> str:
        return await self.read_string_from_offset(608)

    async def write_side(self, side: str):
        await self.write_string_to_offset(608, side)

    async def shadow_spells_disabled(self) -> bool:
        return await self.read_value_from_offset(680, Primitive.bool)

    async def write_shadow_spells_disabled(self, shadow_spells_disabled: bool):
        await self.write_value_to_offset(680, shadow_spells_disabled, Primitive.bool)

    async def ignore_spells_pvp_only_flag(self) -> bool:
        return await self.read_value_from_offset(681, Primitive.bool)

    async def write_ignore_spells_pvp_only_flag(self, ignore_spells_pvp_only_flag: bool):
        await self.write_value_to_offset(681, ignore_spells_pvp_only_flag, Primitive.bool)

    async def ignore_spells_pve_only_flag(self) -> bool:
        return await self.read_value_from_offset(682, Primitive.bool)

    async def write_ignore_spells_pve_only_flag(self, ignore_spells_pvp_only_flag: bool):
        await self.write_value_to_offset(682, ignore_spells_pvp_only_flag, Primitive.bool)

    async def boss_mob(self) -> bool:
        # we use the npc template instead if possible
        templ = await self.fetch_npc_behavior_template()
        if templ is None:
            # The offset isn't accurate enough for our purposes, but we can fall back to it
            return await self.read_value_from_offset(683, Primitive.bool)
        return await templ.mob_title() == NpcBehaviorTemplateTitleType.boss

    async def hide_pvp_enemy_chat(self) -> bool:
        return await self.read_value_from_offset(684, Primitive.bool)

    async def write_hide_pvp_enemy_chat(self, hide_pvp_enemy_chat: bool):
        await self.write_value_to_offset(684, hide_pvp_enemy_chat, Primitive.bool)

    async def combat_trigger_ids(self) -> int:
        return await self.read_value_from_offset(704, Primitive.int32)

    async def write_combat_trigger_ids(self, combat_trigger_ids: int):
        await self.write_value_to_offset(704, combat_trigger_ids, Primitive.int32)

    async def backlash(self) -> int:
        return await self.read_value_from_offset(732, Primitive.int32)

    async def write_backlash(self, backlash: int):
        await self.write_value_to_offset(732, backlash, Primitive.int32)

    async def past_backlash(self) -> int:
        return await self.read_value_from_offset(736, Primitive.int32)

    async def write_past_backlash(self, past_backlash: int):
        await self.write_value_to_offset(736, past_backlash, Primitive.int32)

    async def shadow_creature_level(self) -> int:
        return await self.read_value_from_offset(740, Primitive.int32)

    async def write_shadow_creature_level(self, shadow_creature_level: int):
        await self.write_value_to_offset(740, shadow_creature_level, Primitive.int32)

    async def past_shadow_creature_level(self) -> int:
        return await self.read_value_from_offset(744, Primitive.int32)

    async def write_past_shadow_creature_level(self, past_shadow_creature_level: int):
        await self.write_value_to_offset(744, past_shadow_creature_level, Primitive.int32)

    async def shadow_creature_level_count(self) -> int:
        return await self.read_value_from_offset(752, Primitive.int32)

    async def write_shadow_creature_level_count(self, shadow_creature_level_count: int):
        await self.write_value_to_offset(752, shadow_creature_level_count, Primitive.int32)

    async def intercept_effect(self) -> Optional[DynamicSpellEffect]:
        addr = await self.read_value_from_offset(776, Primitive.int64)

        if addr == 0:
            return None

        return DynamicSpellEffect(self.hook_handler, addr)

    async def rounds_since_shadow_pip(self) -> int:
        return await self.read_value_from_offset(808, Primitive.int32)

    async def write_rounds_since_shadow_pip(self, rounds_since_shadow_pip: int):
        await self.write_value_to_offset(808, rounds_since_shadow_pip, Primitive.int32)

    async def polymorph_effect(self) -> Optional[DynamicSpellEffect]:
        addr = await self.read_value_from_offset(832, Primitive.int64)

        if addr == 0:
            return None

        return DynamicSpellEffect(self.hook_handler, addr)

    async def confused(self) -> int:
        return await self.read_value_from_offset(196, Primitive.int32)

    async def write_confused(self, confused: int):
        await self.write_value_to_offset(196, confused, Primitive.int32)

    async def confusion_trigger(self) -> int:
        return await self.read_value_from_offset(200, Primitive.int32)

    async def write_confusion_trigger(self, confusion_trigger: int):
        await self.write_value_to_offset(200, confusion_trigger, Primitive.int32)

    async def confusion_display(self) -> bool:
        return await self.read_value_from_offset(204, Primitive.bool)

    async def write_confusion_display(self, confusion_display: bool):
        await self.write_value_to_offset(204, confusion_display, Primitive.bool)

    async def confused_target(self) -> bool:
        return await self.read_value_from_offset(205, Primitive.bool)

    async def write_confused_target(self, confused_target: bool):
        await self.write_value_to_offset(205, confused_target, Primitive.bool)

    async def untargetable(self) -> bool:
        return await self.read_value_from_offset(206, Primitive.bool)

    async def write_untargetable(self, untargetable: bool):
        await self.write_value_to_offset(206, untargetable, Primitive.bool)

    async def untargetable_rounds(self) -> int:
        return await self.read_value_from_offset(208, Primitive.int32)

    async def write_untargetable_rounds(self, untargetable_rounds: int):
        await self.write_value_to_offset(208, untargetable_rounds, Primitive.int32)

    async def restricted_target(self) -> bool:
        return await self.read_value_from_offset(212, Primitive.bool)

    async def write_restricted_target(self, restricted_target: bool):
        await self.write_value_to_offset(212, restricted_target, Primitive.bool)

    async def exit_combat(self) -> bool:
        return await self.read_value_from_offset(213, Primitive.bool)

    async def write_exit_combat(self, exit_combat: bool):
        await self.write_value_to_offset(213, exit_combat, Primitive.bool)

    async def stunned_display(self) -> bool:
        return await self.read_value_from_offset(192, Primitive.bool)

    async def write_stunned_display(self, stunned_display: bool):
        await self.write_value_to_offset(192, stunned_display, Primitive.bool)

    async def mindcontrolled_display(self) -> bool:
        return await self.read_value_from_offset(220, Primitive.bool)

    async def write_mindcontrolled_display(self, mindcontrolled_display: bool):
        await self.write_value_to_offset(220, mindcontrolled_display, Primitive.bool)

    async def auto_pass(self) -> bool:
        return await self.read_value_from_offset(728, Primitive.bool)

    async def write_auto_pass(self, auto_pass: bool):
        await self.write_value_to_offset(728, auto_pass, Primitive.bool)

    async def vanish(self) -> bool:
        return await self.read_value_from_offset(729, Primitive.bool)

    async def write_vanish(self, vanish: bool):
        await self.write_value_to_offset(729, vanish, Primitive.bool)

    async def my_team_turn(self) -> bool:
        return await self.read_value_from_offset(730, Primitive.bool)

    async def write_my_team_turn(self, my_team_turn: bool):
        await self.write_value_to_offset(730, my_team_turn, Primitive.bool)

    async def planning_phase_pip_aquired_type(self) -> PipAquiredByEnum:
        return await self.read_enum(824, PipAquiredByEnum)

    async def write_planning_phase_pip_aquired_type(self, planning_phase_pip_aquired_type: PipAquiredByEnum):
        await self.write_enum(824, planning_phase_pip_aquired_type)

    # async def cheat_settings(self) -> class SharedPointer<class CombatCheatSettings>:
    #     return await self.read_value_from_offset(96, "class SharedPointer<class CombatCheatSettings>")

    async def is_monster(self) -> int:
        return await self.read_value_from_offset(412, Primitive.uint32)

    async def write_is_monster(self, is_monster: int):
        await self.write_value_to_offset(412, is_monster, Primitive.uint32)

    # async def weapon_nif_sound_list(self) -> class SharedPointer<class SpellNifSoundOverride>:
    #     return await self.read_value_from_offset(80, "class SharedPointer<class SpellNifSoundOverride>")

    async def pet_combat_trigger(self) -> int:
        return await self.read_value_from_offset(720, Primitive.int32)

    async def write_pet_combat_trigger(self, pet_combat_trigger: int):
        await self.write_value_to_offset(720, pet_combat_trigger, Primitive.int32)

    async def pet_combat_trigger_target(self) -> int:
        return await self.read_value_from_offset(724, Primitive.int32)

    async def write_pet_combat_trigger_target(self, pet_combat_trigger_target: int):
        await self.write_value_to_offset(724, pet_combat_trigger_target, Primitive.int32)

    async def shadow_pip_rate_threshold(self) -> float:
        return await self.read_value_from_offset(848, Primitive.float32)

    async def write_shadow_pip_rate_threshold(self, shadow_pip_rate_threshold: float):
        await self.write_value_to_offset(848, shadow_pip_rate_threshold, Primitive.float32)

    async def base_spell_damage(self) -> int:
        return await self.read_value_from_offset(852, Primitive.int32)

    async def write_base_spell_damage(self, base_spell_damage: int):
        await self.write_value_to_offset(852, base_spell_damage, Primitive.int32)

    async def stat_damage(self) -> float:
        return await self.read_value_from_offset(856, Primitive.float32)

    async def write_stat_damage(self, stat_damage: float):
        await self.write_value_to_offset(856, stat_damage, Primitive.float32)

    async def stat_resist(self) -> float:
        return await self.read_value_from_offset(860, Primitive.float32)

    async def write_stat_resist(self, stat_resist: float):
        await self.write_value_to_offset(860, stat_resist, Primitive.float32)

    async def stat_pierce(self) -> float:
        return await self.read_value_from_offset(864, Primitive.float32)

    async def write_stat_pierce(self, stat_pierce: float):
        await self.write_value_to_offset(864, stat_pierce, Primitive.float32)

    async def mob_level(self) -> int:
        return await self.read_value_from_offset(868, Primitive.int32)

    async def write_mob_level(self, mob_level: int):
        await self.write_value_to_offset(868, mob_level, Primitive.int32)

    async def player_time_updated(self) -> bool:
        return await self.read_value_from_offset(872, Primitive.bool)

    async def write_player_time_updated(self, player_time_updated: bool):
        await self.write_value_to_offset(872, player_time_updated, Primitive.bool)

    async def player_time_eliminated(self) -> bool:
        return await self.read_value_from_offset(873, Primitive.bool)

    async def write_player_time_eliminated(self, player_time_eliminated: bool):
        await self.write_value_to_offset(873, player_time_eliminated, Primitive.bool)

    async def player_time_warning(self) -> bool:
        return await self.read_value_from_offset(874, Primitive.bool)

    async def write_player_time_warning(self, player_time_warning: bool):
        await self.write_value_to_offset(874, player_time_warning, Primitive.bool)

    async def deck_fullness(self) -> float:
        return await self.read_value_from_offset(876, Primitive.float32)

    async def write_deck_fullness(self, deck_fullness: float):
        await self.write_value_to_offset(876, deck_fullness, Primitive.float32)

    async def archmastery_points(self) -> float:
        return await self.read_value_from_offset(880, Primitive.float32)

    async def write_archmastery_points(self, archmastery_points: float):
        await self.write_value_to_offset(880, archmastery_points, Primitive.float32)

    async def max_archmastery_points(self) -> float:
        return await self.read_value_from_offset(884, Primitive.float32)

    async def write_max_archmastery_points(self, max_archmastery_points: float):
        await self.write_value_to_offset(884, max_archmastery_points, Primitive.float32)

    async def archmastery_school(self) -> int:
        return await self.read_value_from_offset(888, Primitive.uint32)

    async def write_archmastery_school(self, archmastery_school: int):
        await self.write_value_to_offset(888, archmastery_school, Primitive.uint32)

    async def archmastery_flags(self) -> int:
        return await self.read_value_from_offset(892, Primitive.uint32)

    async def write_archmastery_flags(self, archmastery_flags: int):
        await self.write_value_to_offset(892, archmastery_flags, Primitive.uint32)
        
    async def shadow_pact_target(self) -> int:
        return await self.read_value_from_offset(392, Primitive.int32)
    
    async def write_shadow_pact_target(self, shadow_pact_target: int):
        await self.write_value_to_offset(392, shadow_pact_target, Primitive.int32)

class DynamicCombatParticipant(DynamicMemoryObject, CombatParticipant):
    pass