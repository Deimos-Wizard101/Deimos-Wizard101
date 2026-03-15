from typing import List, Optional

from wizwalker.errors import MemoryReadError
from wizwalker.utils import XYZ
from wizwalker.memory import HookHandler
from wizwalker.memory.memory_object import Primitive, PropertyClass, DynamicMemoryObject
from .combat_participant import DynamicCombatParticipant
from .enums import DuelExecutionOrder, DuelPhase, SigilInitiativeSwitchMode
from .combat_resolver import DynamicCombatResolver


# TODO: add m_gameEffectInfo and friends, and fix offsets
class Duel(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def participant_list(self,) -> List[DynamicCombatParticipant]:
        pointers = await self.read_shared_vector(80)

        participants = []
        for addr in pointers:
            participants.append(DynamicCombatParticipant(self.hook_handler, addr))

        return participants

    # TODO: need to add new type
    # async def dynamicTeams offset=104
        #"class SharedPointer<class DynamicSigilInstance>"
    async def dynamic_turn(self) -> int:
        return await self.read_value_from_offset(120, Primitive.uint32)

    async def write_dynamic_turn(self, dynamic_turn: int):
        await self.write_value_to_offset(120, dynamic_turn, Primitive.uint32)

    async def dynamic_turn_subcircles(self) -> int:
        return await self.read_value_from_offset(124, Primitive.uint32)

    async def write_dynamic_turn_subcircle(self, dynamic_turn_subcircle: int):
        await self.write_value_to_offset(124, dynamic_turn_subcircle, Primitive.uint32)

    async def dynamic_turn_counter(self) -> int:
        return await self.read_value_from_offset(128, Primitive.int32)

    async def write_dynamic_turn_counter(self, dynamic_turn_counter: int):
        await self.write_value_to_offset(128, dynamic_turn_counter, Primitive.int32)

    async def duel_id_full(self) -> int:
        return await self.read_value_from_offset(72, Primitive.uint64)

    async def write_duel_id_full(self, duel_id_full: int):
        await self.write_value_to_offset(72, duel_id_full, Primitive.uint64)

    async def planning_timer(self) -> float:
        return await self.read_value_from_offset(144, Primitive.float32)

    async def write_planning_timer(self, planning_timer: float):
        await self.write_value_to_offset(144, planning_timer, Primitive.float32)

    async def position(self) -> XYZ:
        return await self.read_xyz(148)

    async def write_position(self, position: XYZ):
        await self.write_xyz(148, position)

    async def yaw(self) -> float:
        return await self.read_value_from_offset(160, Primitive.float32)

    async def write_yaw(self, yaw: float):
        await self.write_value_to_offset(160, yaw, Primitive.float32)

    async def disable_timer(self) -> bool:
        return await self.read_value_from_offset(179, Primitive.bool)

    async def write_disable_timer(self, disable_timer: bool):
        await self.write_value_to_offset(179, disable_timer, Primitive.bool)

    async def tutorial_mode(self) -> bool:
        return await self.read_value_from_offset(180, Primitive.bool)

    async def write_tutorial_mode(self, tutorial_mode: bool):
        await self.write_value_to_offset(180, tutorial_mode, Primitive.bool)

    async def first_team_to_act(self) -> int:
        return await self.read_value_from_offset(184, Primitive.int32)

    async def write_first_team_to_act(self, first_team_to_act: int):
        await self.write_value_to_offset(184, first_team_to_act, Primitive.int32)

    async def combat_resolver(self) -> Optional[DynamicCombatResolver]:
        addr = await self.read_value_from_offset(136, Primitive.int64)

        if addr == 0:
            return None

        return DynamicCombatResolver(self.hook_handler, addr)

    async def pvp(self) -> bool:
        return await self.read_value_from_offset(176, Primitive.bool)

    async def write_pvp(self, pvp: bool):
        await self.write_value_to_offset(176, pvp, Primitive.bool)

    async def battleground(self) -> bool:
        return await self.read_value_from_offset(177, Primitive.bool)

    async def write_battleground(self, b_battleground: bool):
        await self.write_value_to_offset(177, b_battleground, Primitive.bool)

    async def raid(self) -> bool:
        return await self.read_value_from_offset(178, Primitive.bool)

    async def write_raid(self, raid: bool):
        await self.write_value_to_offset(178, raid, Primitive.bool)

    async def round_num(self) -> int:
        return await self.read_value_from_offset(192, Primitive.int32)

    async def write_round_num(self, round_num: int):
        await self.write_value_to_offset(192, round_num, Primitive.int32)

    async def execution_phase_timer(self) -> float:
        return await self.read_value_from_offset(200, Primitive.float32)

    async def write_execution_phase_timer(self, execution_phase_timer: float):
        await self.write_value_to_offset(200, execution_phase_timer, Primitive.float32)

    # note: this seems to be unused
    # async def execution_phase_combat_actions(self) -> class CombatAction:
    #     return await self.read_value_from_offset(208, "class CombatAction")

    # note: this also seems to be unused
    # async def sigil_actions(self) -> class CombatAction:
    #     return await self.read_value_from_offset(224, "class CombatAction")

    # async def shadow_pip_rule(self) -> class SharedPointer<class ShadowPipRule>:
    #     return await self.read_value_from_offset(280, "class SharedPointer<class ShadowPipRule>")

    # async def game_object_anim_state_tracker(self) -> class GameObjectAnimStateTracker:
    #     return await self.read_value_from_offset(296, "class GameObjectAnimStateTracker")

    async def duel_phase(self) -> DuelPhase:
        return await self.read_enum(196, DuelPhase)

    async def write_duel_phase(self, duel_phase: DuelPhase):
        await self.write_enum(196, duel_phase)

    # async def duel_modifier(self) -> class SharedPointer<class DuelModifier>:
    #     return await self.read_value_from_offset(264, "class SharedPointer<class DuelModifier>")

    async def initiative_switch_mode(self) -> SigilInitiativeSwitchMode:
        return await self.read_enum(384, SigilInitiativeSwitchMode)

    async def write_initiative_switch_mode(self, initiative_switch_mode: SigilInitiativeSwitchMode):
        await self.write_enum(384, initiative_switch_mode)

    async def initiative_switch_rounds(self) -> int:
        return await self.read_value_from_offset(388, Primitive.int32)

    async def write_initiative_switch_rounds(self, initiative_switch_rounds: int):
        await self.write_value_to_offset(388, initiative_switch_rounds, Primitive.int32)

    # async def combat_rules(self) -> class SharedPointer<class CombatRule>:
    #     return await self.read_value_from_offset(464, "class SharedPointer<class CombatRule>")

    # async def game_effect_info(self) -> class SharedPointer<class GameEffectInfo>:
    #     return await self.read_value_from_offset(496, "class SharedPointer<class GameEffectInfo>")

    # async def stat_effects(self) -> class SharedPointer<class GameEffectContainer>:
    #     return await self.read_value_from_offset(512, "class SharedPointer<class GameEffectContainer>")

    # async def alternate_turn_combat_rule(self) -> class SharedPointer<class AlternateTurnsCombatRule>:
    #     return await self.read_value_from_offset(480, "class SharedPointer<class AlternateTurnsCombatRule>")

    async def alt_turn_counter(self) -> int:
        return await self.read_value_from_offset(456, Primitive.int32)

    async def write_alt_turn_counter(self, alt_turn_counter: int):
        await self.write_value_to_offset(456, alt_turn_counter, Primitive.int32)

    async def original_first_team_to_act(self) -> int:
        return await self.read_value_from_offset(188, Primitive.int32)

    async def write_original_first_team_to_act(self, original_first_team_to_act: int):
        await self.write_value_to_offset(188, original_first_team_to_act, Primitive.int32)

    async def execution_order(self) -> DuelExecutionOrder:
        return await self.read_enum(528, DuelExecutionOrder)

    async def write_execution_order(self, execution_order: DuelExecutionOrder):
        await self.write_enum(528, execution_order)

    async def no_henchmen(self) -> bool:
        return await self.read_value_from_offset(532, Primitive.bool)

    async def write_no_henchmen(self, no_henchmen: bool):
        await self.write_value_to_offset(532, no_henchmen, Primitive.bool)

    async def spell_truncation(self) -> bool:
        return await self.read_value_from_offset(540, Primitive.bool)

    async def write_spell_truncation(self, spell_truncation: bool):
        await self.write_value_to_offset(540, spell_truncation, Primitive.bool)

    async def shadow_threshold_factor(self) -> float:
        return await self.read_value_from_offset(548, Primitive.float32)

    async def write_shadow_threshold_factor(self, shadow_threshold_factor: float):
        await self.write_value_to_offset(548, shadow_threshold_factor, Primitive.float32)

    async def shadow_pip_rating_factor(self) -> float:
        return await self.read_value_from_offset(552, Primitive.float32)

    async def write_shadow_pip_rating_factor(self, shadow_pip_rating_factor: float):
        await self.write_value_to_offset(552, shadow_pip_rating_factor, Primitive.float32)

    async def default_shadow_pip_rating(self) -> float:
        return await self.read_value_from_offset(556, Primitive.float32)

    async def write_default_shadow_pip_rating(self, default_shadow_pip_rating: float):
        await self.write_value_to_offset(556, default_shadow_pip_rating, Primitive.float32)

    async def shadow_pip_threshold_team0(self) -> float:
        return await self.read_value_from_offset(560, Primitive.float32)

    async def write_shadow_pip_threshold_team0(self, shadow_pip_threshold_team0: float):
        await self.write_value_to_offset(560, shadow_pip_threshold_team0, Primitive.float32)

    async def shadow_pip_threshold_team1(self) -> float:
        return await self.read_value_from_offset(564, Primitive.float32)

    async def write_shadow_pip_threshold_team1(self, shadow_pip_threshold_team1: float):
        await self.write_value_to_offset(564, shadow_pip_threshold_team1, Primitive.float32)

    async def duel(self) -> bool:
        return await self.read_value_from_offset(568, Primitive.bool)

    async def write_duel(self, duel: bool):
        await self.write_value_to_offset(568, duel, Primitive.bool)

    #async def max_archmastery(self) -> float:
    #   return await self.read_value_from_offset(572, Primitive.float32)

    async def scalar_damage(self) -> float:
        return await self.read_value_from_offset(600, Primitive.float32)

    async def write_scalar_damage(self, scalar_damage: float):
        await self.write_value_to_offset(600, scalar_damage, Primitive.float32)

    async def scalar_resist(self) -> float:
        return await self.read_value_from_offset(604, Primitive.float32)

    async def write_scalar_resist(self, scalar_resist: float):
        await self.write_value_to_offset(604, scalar_resist, Primitive.float32)

    async def scalar_pierce(self) -> float:
        return await self.read_value_from_offset(608, Primitive.float32)

    async def write_scalar_pierce(self, scalar_pierce: float):
        await self.write_value_to_offset(608, scalar_pierce, Primitive.float32)

    async def damage_limit(self) -> float:
        return await self.read_value_from_offset(612, Primitive.float32)

    async def write_damage_limit(self, damage_limit: float):
        await self.write_value_to_offset(612, damage_limit, Primitive.float32)

    # TODO 2.0: this d_ shouldn't be here
    async def d_k0(self) -> float:
        return await self.read_value_from_offset(616, Primitive.float32)

    async def write_d_k0(self, d_k0: float):
        await self.write_value_to_offset(616, d_k0, Primitive.float32)

    async def d_n0(self) -> float:
        return await self.read_value_from_offset(620, Primitive.float32)

    async def write_d_n0(self, d_n0: float):
        await self.write_value_to_offset(620, d_n0, Primitive.float32)

    async def resist_limit(self) -> float:
        return await self.read_value_from_offset(624, Primitive.float32)

    async def write_resist_limit(self, resist_limit: float):
        await self.write_value_to_offset(624, resist_limit, Primitive.float32)

    async def r_k0(self) -> float:
        return await self.read_value_from_offset(628, Primitive.float32)

    async def write_r_k0(self, r_k0: float):
        await self.write_value_to_offset(628, r_k0, Primitive.float32)

    async def r_n0(self) -> float:
        return await self.read_value_from_offset(632, Primitive.float32)

    async def write_r_n0(self, r_n0: float):
        await self.write_value_to_offset(632, r_n0, Primitive.float32)

    async def full_party_group(self) -> bool:
        return await self.read_value_from_offset(636, Primitive.bool)

    async def write_full_party_group(self, full_party_group: bool):
        await self.write_value_to_offset(636, full_party_group, Primitive.bool)

    async def match_timer(self) -> float:
        return await self.read_value_from_offset(656, Primitive.float32)

    async def write_match_timer(self, match_timer: float):
        await self.write_value_to_offset(656, match_timer, Primitive.float32)

    async def bonus_time(self) -> int:
        return await self.read_value_from_offset(660, Primitive.int32)

    async def write_bonus_time(self, bonus_time: int):
        await self.write_value_to_offset(660, bonus_time, Primitive.int32)

    async def pass_penalty(self) -> int:
        return await self.read_value_from_offset(664, Primitive.int32)

    async def write_pass_penalty(self, pass_penalty: int):
        await self.write_value_to_offset(664, pass_penalty, Primitive.int32)

    async def yellow_time(self) -> int:
        return await self.read_value_from_offset(668, Primitive.int32)

    async def write_yellow_time(self, yellow_time: int):
        await self.write_value_to_offset(668, yellow_time, Primitive.int32)

    async def red_time(self) -> int:
        return await self.read_value_from_offset(672, Primitive.int32)

    async def write_red_time(self, red_time: int):
        await self.write_value_to_offset(672, red_time, Primitive.int32)

    async def min_turn_time(self) -> int:
        return await self.read_value_from_offset(676, Primitive.int32)

    async def write_min_turn_time(self, min_turn_time: int):
        await self.write_value_to_offset(676, min_turn_time, Primitive.int32)

    async def is_player_timed_duel(self) -> bool:
        return await self.read_value_from_offset(637, Primitive.bool)

    async def write_is_player_timed_duel(self, is_player_timed_duel: bool):
        await self.write_value_to_offset(637, is_player_timed_duel, Primitive.bool)

    async def hide_noncombatant_distance(self) -> float:
        return await self.read_value_from_offset(536, Primitive.float32)

    async def write_hide_noncombatant_distance(self, hide_noncombatant_distance: float):
        await self.write_value_to_offset(536, hide_noncombatant_distance, Primitive.float32)


class DynamicDuel(DynamicMemoryObject, Duel):
    pass


class CurrentDuel(Duel):
    def __init__(self, hook_handler: HookHandler):
        super().__init__(hook_handler)
        self._duel_manager_addr = None

    async def read_base_address(self) -> int:
        if not self._duel_manager_addr:
            mov_instruction_addr = await self.hook_handler.pattern_scan(
                rb".......\xE8....\x90.......\x48\x85\xC9\x74.\x0F\x28\x45",
                module="WizardGraphicalClient.exe"
            )
            rip_offset = await self.hook_handler.read_typed(
                mov_instruction_addr + 3, Primitive.int32
            )
            self._duel_manager_addr = mov_instruction_addr + 7 + rip_offset
        # avoid circular import
        from .client_duel_manager import DynamicClientDuelManager
        while True: # sometimes this can go wrong thanks to bad timing
            duel_manager = DynamicClientDuelManager(self.hook_handler, await self.read_typed(self._duel_manager_addr, Primitive.int64))
            try:
                for duel in (await duel_manager.duelmap()).values():
                    for part in await duel.participant_list():
                        if await part.owner_id_full() == await self.hook_handler.client.client_object.global_id_full():
                            return await duel.read_base_address()
                return 0 # we succeeded but aren't in a duel
            except (ValueError, MemoryReadError):
                pass # if something else happens we want it to fail

    async def duel_phase(self) -> DuelPhase:
        try:
            return await super().duel_phase()
        except MemoryReadError:
            return DuelPhase.ended
