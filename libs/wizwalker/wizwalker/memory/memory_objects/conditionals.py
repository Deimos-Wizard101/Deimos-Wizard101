from wizwalker.memory.memory_objects.enums import SpellEffects, Operator, RequirementTarget, HangingDisposition, MinionType, StatusEffect
from wizwalker.memory.memory_object import Primitive, PropertyClass, DynamicMemoryObject
from typing import Any
from enum import Enum


charm_effect_types = [
    SpellEffects.modify_outgoing_damage,
    SpellEffects.modify_outgoing_damage_flat,
    SpellEffects.modify_outgoing_heal,
    SpellEffects.modify_outgoing_heal_flat,
    SpellEffects.modify_outgoing_damage_type,
    SpellEffects.modify_outgoing_armor_piercing,
    SpellEffects.push_charm,
    SpellEffects.steal_charm,
    SpellEffects.remove_charm,
    SpellEffects.swap_charm,
    SpellEffects.cloaked_charm,
    SpellEffects.modify_card_charm,
    SpellEffects.push_converted_charm,
    SpellEffects.steal_converted_charm,
    SpellEffects.remove_converted_charm,
]

over_time_effect_types = [
    SpellEffects.reduce_over_time,
    SpellEffects.detonate_over_time,
    SpellEffects.steal_over_time,
    SpellEffects.remove_over_time,
    SpellEffects.swap_over_time,
    SpellEffects.push_converted_over_time,
    SpellEffects.steal_converted_over_time,
    SpellEffects.remove_converted_over_time,
    SpellEffects.damage_over_time,
    SpellEffects.modify_over_time_duration,
    SpellEffects.heal_over_time,
]

ward_effect_types = [
    SpellEffects.push_ward,
    SpellEffects.steal_ward,
    SpellEffects.remove_ward,
    SpellEffects.swap_ward,
    SpellEffects.cloaked_ward,
    SpellEffects.cloaked_ward_no_remove,
    SpellEffects.heal_by_ward,
    SpellEffects.push_converted_ward,
    SpellEffects.steal_converted_ward,
    SpellEffects.remove_converted_ward,
    SpellEffects.modify_incoming_damage,
    SpellEffects.modify_incoming_damage_flat,
    SpellEffects.maximum_incoming_damage,
    SpellEffects.modify_incoming_heal,
    SpellEffects.modify_incoming_heal_flat,
    SpellEffects.modify_incoming_damage_type,
    SpellEffects.modify_incoming_armor_piercing,
    SpellEffects.modify_card_incoming_damage,
    SpellEffects.modify_incoming_damage_over_time,
    SpellEffects.modify_incoming_heal_over_time,
]

# SpellEffects values that ReqHangingAura.m_effectType can name. Sourced from
# the 1.600 type dump (class ReqHangingAura → m_effectType.enum_options). Auras
# share these effect-type values with charms/wards — what makes a hanging
# effect an aura is its structural metadata, not the effect_type alone. So
# this list is "what an aura *can be*", not "any hanging effect with one of
# these types is an aura". Use it for filter membership when reading
# ReqHangingAura.effect_type(), not for classifying live participant.hanging_effects().
aura_effect_types = [
    SpellEffects.absorb_damage,
    SpellEffects.absorb_heal,
    SpellEffects.add_combat_trigger_list,
    SpellEffects.bounce_all,
    SpellEffects.bounce_back,
    SpellEffects.bounce_next,
    SpellEffects.bounce_previous,
    SpellEffects.cloaked_charm,
    SpellEffects.cloaked_ward,
    SpellEffects.cloaked_ward_no_remove,
    SpellEffects.confusion_block,
    SpellEffects.crit_block,
    SpellEffects.crit_boost,
    SpellEffects.crit_boost_school_specific,
    SpellEffects.dampen,
    SpellEffects.dispel,
    SpellEffects.dispel_block,
    SpellEffects.maximum_incoming_damage,
    SpellEffects.modify_accuracy,
    SpellEffects.modify_incoming_armor_piercing,
    SpellEffects.modify_incoming_damage,
    SpellEffects.modify_incoming_damage_flat,
    SpellEffects.modify_incoming_damage_over_time,
    SpellEffects.modify_incoming_damage_type,
    SpellEffects.modify_incoming_heal,
    SpellEffects.modify_incoming_heal_flat,
    SpellEffects.modify_incoming_heal_over_time,
    SpellEffects.modify_incoming_steal_health,
    SpellEffects.modify_outgoing_armor_piercing,
    SpellEffects.modify_outgoing_damage,
    SpellEffects.modify_outgoing_damage_flat,
    SpellEffects.modify_outgoing_damage_type,
    SpellEffects.modify_outgoing_heal,
    SpellEffects.modify_outgoing_heal_flat,
    SpellEffects.modify_pip_round_rate,
    SpellEffects.modify_power_pip_chance,
    SpellEffects.pip_conversion,
    SpellEffects.power_pip_conversion,
    SpellEffects.protect_beneficial,
    SpellEffects.protect_harmful,
    SpellEffects.push_charm,
    SpellEffects.remove_combat_trigger_list,
    SpellEffects.stun_block,
    SpellEffects.stun_resist,
]


class HangingSpellEffect(Enum):
    invalid_spell_effect = 0,
    absorb_damage = 35,
    absorb_heal = 36,
    add_combat_trigger_list = 85,
    afterlife = 80,
    backlash_damage = 87,
    bounce_all = 34,
    bounce_back = 33,
    bounce_next = 31,
    bounce_previous = 32,
    cloaked_charm = 40,
    cloaked_ward = 41,
    cloaked_ward_no_remove = 84,
    confusion = 39,
    confusion_block = 107,
    crit_block = 45,
    crit_boost = 44,
    crit_boost_school_specific = 95,
    damage = 1,
    damage_no_crit = 2,
    damage_over_time = 73,
    damage_per_total_pip_power = 82,
    dampen = 66,
    deferred_damage = 81,
    delay_cast = 47,
    detonate_over_time = 7,
    dispel = 38,
    divide_damage = 103,
    heal = 3,
    heal_over_time = 74,
    instant_kill = 79,
    intercept = 89,
    max_health_damage = 110,
    maximum_incoming_damage = 23,
    mind_control = 68,
    modify_accuracy = 37,
    modify_backlash = 88,
    modify_card_accuracy = 51,
    modify_card_armor_piercing = 54,
    modify_card_cloak = 48,
    modify_card_damage = 49,
    modify_card_mutation = 52,
    modify_card_rank = 53,
    modify_hate = 72,
    modify_incoming_armor_piercing = 26,
    modify_incoming_damage = 22,
    modify_incoming_damage_flat = 117,
    modify_incoming_damage_type = 25,
    modify_incoming_heal = 24,
    modify_incoming_heal_flat = 116,
    modify_incoming_heal_over_time = 136,
    modify_outgoing_armor_piercing = 30,
    modify_outgoing_damage = 27,
    modify_outgoing_damage_flat = 119,
    modify_outgoing_damage_type = 29,
    modify_outgoing_heal = 28,
    modify_outgoing_heal_flat = 118,
    modify_pip_round_rate = 108,
    modify_pips = 69,
    modify_power_pip_chance = 75,
    modify_power_pips = 70,
    modify_rank = 76,
    modify_shadow_creature_level = 92,
    modify_shadow_pips = 71,
    pip_conversion = 43,
    polymorph = 46,
    power_pip_conversion = 98,
    protect_beneficial = 101,
    protect_card_beneficial = 99,
    protect_card_harmful = 100,
    protect_harmful = 102,
    push_charm = 8,
    push_over_time = 12,
    push_ward = 10,
    reduce_over_time = 6,
    remove_aura = 17,
    remove_charm = 14,
    remove_combat_trigger_list = 86,
    remove_over_time = 16,
    remove_ward = 15,
    reshuffle = 67,
    reveal_cloak = 78,
    select_shadow_creature_attack_target = 93,
    shadow_creature = 91,
    shadow_decrement_turn = 94,
    shadow_self = 90,
    spawn_creature = 96,
    steal_charm = 9,
    steal_health = 5,
    steal_over_time = 13,
    steal_ward = 11,
    stun = 65,
    stun_block = 77,
    stun_resist = 42,
    summon_creature = 63,
    swap_charm = 19,
    swap_over_time = 21,
    swap_ward = 20,
    teleport_player = 64,
    un_polymorph = 97,
    max_health_heal = 127,
    heal_by_ward = 128,
    taunt = 129,
    pacify = 130


class Requirement(DynamicMemoryObject, PropertyClass):
    async def apply_not(self) -> bool:
        return await self.read_value_from_offset(72, Primitive.bool)

    async def operator(self) -> Operator:
        return await self.read_enum(76, Operator)

    async def _evaluate(self, data: dict[str, Any]) -> bool:
        # data can contain:
        # - combat: CombatHandler instance
        # - target_idx: combat member index
        raise NotImplementedError()

    async def _do_ops(self, original_state: bool, new_state: bool) -> bool:
        state = new_state ^ (await self.apply_not())
        match await self.operator():
            case Operator.AND:
                return original_state and state
            case Operator.OR:
                return original_state or state

    async def apply(self, original_state: bool, data: dict[str, Any]) -> bool:
        return await self._do_ops(original_state, await self._evaluate(data))


class RequirementList(Requirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        state = True
        for req in await self.requirements():
            preq = await promote_requirement(req)
            state = await preq.apply(state, data)
        return state

    async def requirements(self) -> list[Requirement]:
        results = []
        for addr in await self.read_shared_linked_list(80):
            requirement = await promote_requirement(Requirement(self.hook_handler, addr))
            results.append(requirement)
        return results


class ConditionalSpellEffectRequirement(Requirement):
    async def target_type(self) -> RequirementTarget:
        return await self.read_enum(80, RequirementTarget)

    async def get_target(self, data: dict[str, Any]):
        combat = data["combat"]
        if await self.target_type() == RequirementTarget.caster:
            member = await combat.get_client_member()
        else:
            member = (await combat.get_members())[data["target_idx"]]

        return member


# "name": "class ReqHangingCharm


class ReqHangingCharm(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        participant = await member.get_participant()

        hanging_effects = await participant.hanging_effects()
        valid_effects = []
        for effect in hanging_effects:
            if await effect.effect_type() in charm_effect_types:
                if (
                    await effect.disposition() == HangingDisposition.both
                    or await self.disposition() == HangingDisposition.both
                    or await effect.disposition() == await self.disposition()
                ):
                    valid_effects.append(effect)

        return await self.min_count() <= len(valid_effects) <= await self.max_count()

    async def disposition(self) -> HangingDisposition:
        return await self.read_enum(88, HangingDisposition)

    async def min_count(self) -> int:
        return await self.read_value_from_offset(92, Primitive.int32)

    async def max_count(self) -> int:
        return await self.read_value_from_offset(96, Primitive.int32)


class ReqCombatHealth(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        member_health_percentage = await member.health() / await member.max_health()
        return (
            await self.min_percent()
            <= member_health_percentage
            <= await self.max_percent()
        )

    async def min_percent(self) -> float:
        return await self.read_value_from_offset(88, Primitive.float32)

    async def max_percent(self) -> float:
        return await self.read_value_from_offset(92, Primitive.float32)


class ReqHangingOverTime(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        participant = await member.get_participant()
        hanging_effects = await participant.hanging_effects()
        valid_effects = []
        for effect in hanging_effects:
            if await effect.effect_type() in over_time_effect_types:
                if (
                    await effect.disposition() == HangingDisposition.both
                    or await self.disposition() == HangingDisposition.both
                    or await effect.disposition() == await self.disposition()
                ):
                    valid_effects.append(effect)
        return await self.min_count() <= len(valid_effects) <= await self.max_count()

    async def disposition(self) -> HangingDisposition:
        return await self.read_enum(88, HangingDisposition)

    async def min_count(self) -> int:
        return await self.read_value_from_offset(92, Primitive.int32)

    async def max_count(self) -> int:
        return await self.read_value_from_offset(96, Primitive.int32)


school_id_to_names = {
    "Fire": 2343174,
    "Ice": 72777,
    "Storm": 83375795,
    "Myth": 2448141,
    "Life": 2330892,
    "Death": 78318724,
    "Balance": 1027491821,
    "Star": 2625203,
    "Sun": 78483,
    "Moon": 2504141,
    "Gardening": 663550619,
    "Shadow": 1429009101,
    "Fishing": 1488274711,
    "Cantrips": 1760873841,
    "CastleMagic": 806477568,
    "WhirlyBurly": 931528087,
}
school_to_str = {index: i for i, index in school_id_to_names.items()}


class ReqIsSchool(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        participant = await member.get_participant()
        school_id = await participant.primary_magic_school_id()
        return await self.magic_school_name() == school_to_str[school_id]

    async def magic_school_name(self) -> str:
        return await self.read_string_from_offset(88)


class ReqHangingAura(ConditionalSpellEffectRequirement):
    """ReqHangingAura — checks for an aura on caster/target. Unlike the
    charm/ward/over_time family this requirement gates on presence (not a
    [min,max] count window) and selects either a specific aura SpellEffect or
    "any aura" via the m_anyType flag. Field offsets verified against the
    1.600 type dump (class ReqHangingAura).

    _evaluate scans participant.aura_effects() for at least one entry whose
    disposition matches (with both-permissive on either side) and whose
    effect_type matches if any_type is False. The 1-aura-per-side cap is
    enforced by the engine, not by this query — aura_effects may still expose
    multiple sub-effect entries from a single aura cast, which is fine since
    this is a presence check (any match returns True).
    """
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        participant = await member.get_participant()
        auras = await participant.aura_effects()
        want_disp = await self.disposition()
        any_type = await self.any_type()
        want_type = await self.effect_type()
        for aura in auras:
            if not any_type:
                if (await aura.effect_type()) != want_type:
                    continue
            adisp = await aura.disposition()
            if adisp != HangingDisposition.both and want_disp != HangingDisposition.both and adisp != want_disp:
                continue
            return True
        return False

    async def effect_type(self) -> SpellEffects:
        return await self.read_enum(88, SpellEffects)

    async def disposition(self) -> HangingDisposition:
        return await self.read_enum(92, HangingDisposition)

    async def any_type(self) -> bool:
        return await self.read_value_from_offset(96, Primitive.bool)

    async def global_effect(self) -> bool:
        return await self.read_value_from_offset(97, Primitive.bool)


class ReqHangingWard(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        participant = await member.get_participant()
        hanging_effects = await participant.hanging_effects()
        valid_effects = []
        for effect in hanging_effects:
            if await effect.effect_type() in ward_effect_types:
                if (
                    await effect.disposition() == HangingDisposition.both
                    or await self.disposition() == HangingDisposition.both
                    or await effect.disposition() == await self.disposition()
                ):
                    valid_effects.append(effect)
        return await self.min_count() <= len(valid_effects) <= await self.max_count()

    async def disposition(self) -> HangingDisposition:
        return await self.read_enum(88, HangingDisposition)

    async def min_count(self) -> int:
        return await self.read_value_from_offset(92, Primitive.int32)

    async def max_count(self) -> int:
        return await self.read_value_from_offset(96, Primitive.int32)


class ReqHangingEffectType(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        participant = await member.get_participant()
        hanging_effects = await participant.hanging_effects()
        # TODO finsh this

    async def effect_type(self) -> SpellEffects:
        # Type-dump (1.600) names this enum SpellEffect::kSpellEffects, not the
        # narrower HangingSpellEffect that wizwalker historically used. Reading
        # as HangingSpellEffect would silently drop values not in that subset.
        return await self.read_enum(88, SpellEffects)

    async def param_low(self) -> int:
        return await self.read_value_from_offset(92, Primitive.int32)

    async def param_high(self) -> int:
        return await self.read_value_from_offset(96, Primitive.int32)

    async def min_count(self) -> int:
        return await self.read_value_from_offset(100, Primitive.int32)

    async def max_count(self) -> int:
        return await self.read_value_from_offset(104, Primitive.int32)


class ReqPvPCombat(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        participant = await member.get_participant()
        return await participant.pvp()


class ReqShadowPipCount(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        participant = await member.get_participant()
        num_shadow_pip = await participant.num_shadow_pips()
        return await self.min_pips() <= num_shadow_pip <= await self.max_pips()

    async def min_pips(self) -> int:
        return await self.read_value_from_offset(88, Primitive.int32)

    async def max_pips(self) -> int:
        return await self.read_value_from_offset(92, Primitive.int32)


class ReqPipCount(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        participant = await member.get_participant()
        num_power_pip = await participant.num_power_pips()
        return await self.min_pips() <= num_power_pip <= await self.max_pips()

    async def min_pips(self) -> int:
        return await self.read_value_from_offset(88, Primitive.int32)

    async def max_pips(self) -> int:
        return await self.read_value_from_offset(92, Primitive.int32)


class ReqMinion(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        combat = data["combat"]

        member = await self.get_target(data)
        participant = await member.get_participant()
        match await self.minion_type():
            case MinionType.is_minion:
                return await participant.is_minion()
            case MinionType.has_minion:
                # TODO find out what in the world this means
                raise NotImplementedError()
            case MinionType.on_team:
                for combatmember in await combat.get_members():
                    if combatmember in await combat.get_members():
                        part = await combatmember.get_participant()
                        if (
                            combatmember.is_minion()
                            and await part.team_id() == await participant.team_id()
                        ):
                            return True
            case MinionType.on_other_team:
                for combatmember in await combat.get_members():
                    if combatmember in await combat.get_members():
                        part = await combatmember.get_participant()
                        if (
                            combatmember.is_minion()
                            and not await part.team_id() == await participant.team_id()
                        ):
                            return True
            case MinionType.on_any_team:
                for combatmember in await combat.get_members():
                    if await combatmember.is_minion():
                        return True

        return False

    async def minion_type(self) -> MinionType:
        return await self.read_enum(88, MinionType)


class ReqCombatStatus(ConditionalSpellEffectRequirement):
    async def _evaluate(self, data: dict[str, Any]) -> bool:
        member = await self.get_target(data)
        participant = await member.get_participant()
        match await self.status():
            case StatusEffect.stunned:
                return await participant.stunned() != 0
            case StatusEffect.confused:
                return await participant.confused() != 0

    async def status(self) -> StatusEffect:
        return await self.read_enum(88, StatusEffect)


async def promote_requirement(req: Requirement):
    match await req.read_type_name():
        case "ReqCombatHealth":
            prom_type = ReqCombatHealth
        case "RequirementList":
            prom_type = RequirementList
        case "ReqHangingCharm":
            prom_type = ReqHangingCharm
        case "ReqHangingOverTime":
            prom_type = ReqHangingOverTime
        case "ReqHangingWard":
            prom_type = ReqHangingWard
        case "ReqHangingAura":
            prom_type = ReqHangingAura
        case "ReqIsSchool":
            prom_type = ReqIsSchool
        # case 'ReqHangingEffectType':
        #     prom_type = ReqHangingEffectType
        case "ReqPvPCombat":
            prom_type = ReqPvPCombat
        case "ReqShadowPipCount":
            prom_type = ReqShadowPipCount
        case "ReqPipCount":
            prom_type = ReqPipCount
        case "ReqMinion":
            prom_type = ReqMinion
        case "ReqCombatStatus":
            prom_type = ReqCombatStatus
        case _:
            raise RuntimeError(
                f"Unknown requirement type: {await req.read_type_name()}"
            )

    return prom_type(req.hook_handler, await req.read_base_address())
