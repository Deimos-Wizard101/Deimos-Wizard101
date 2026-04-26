import asyncio
from typing import *

import wizwalker
from wizwalker.combat import CombatHandler
from wizwalker.combat import CombatMember
from wizwalker.combat.card import CombatCard
from wizwalker.memory import EffectTarget, SpellEffects, DynamicSpellEffect
from wizwalker.memory.memory_objects.spell_effect import CompoundSpellEffect, ConditionalSpellEffect, HangingConversionSpellEffect
from wizwalker.memory.memory_objects.enums import WindowFlags, HangingDisposition, HangingEffectType, EffectTarget
from wizwalker.memory.memory_objects.conditionals import charm_effect_types, ward_effect_types, over_time_effect_types, aura_effect_types

from .combat_backends.combat_config_parser import TargetType, TargetData, MoveConfig, TemplateSpell \
    , NamedSpell, SpellType, Spell, DrawSpell, Condition, AllCondition, ConditionTarget, ComparisonOp, AggregationMode \
    , GambitSpec, ClearSpec, EchoSpec, SwapSpec, HangingType, HANGING_CATEGORIES, hanging_type_info
from wizwalker.memory.memory_objects.conditionals import ReqHangingAura
from .combat_backends.backend_base import BaseCombatBackend

from enum import Enum, auto
from collections import Counter


# Toggle to enable [INSPECT]/[REQ-DBG]/[COND-DBG]/[MT-DBG] tracing in this file.
# Off by default; flip to True (or set the env var DEIMOS_COMBAT_DEBUG=1) to
# resurface the verbose verb/predicate/dispatch traces used during development.
import os as _os
_DEBUG = _os.environ.get("DEIMOS_COMBAT_DEBUG", "").lower() in ("1", "true", "yes")


def _dbg(msg: str) -> None:
    if _DEBUG:
        print(msg)


async def _flatten_effect(effect, out: List, depth: int = 0):
    """Recursively unwrap container effects (Compound/EffectList, Conditional,
    HangingConversion) so callers see leaf SpellEffects regardless of nesting.
    Without recursion, branch effects wrapped in EffectListSpellEffect surface
    as `invalid_spell_effect` (the wrapper's type) rather than the actual
    damage/hang-applying inner effect."""
    if depth > 8:  # Cycle / pathological-nesting guard.
        return
    cls = type(effect)
    if issubclass(cls, CompoundSpellEffect):  # EffectListSpellEffect inherits this.
        for sub in await effect.effects_list():
            await _flatten_effect(sub, out, depth + 1)
        return
    if issubclass(cls, ConditionalSpellEffect):
        for elem in await effect.elements():
            await _flatten_effect(await elem.effect(), out, depth + 1)
        return
    if issubclass(cls, HangingConversionSpellEffect):
        for sub in await effect.output_effect():
            await _flatten_effect(sub, out, depth + 1)
        return
    out.append(effect)


async def get_inner_card_effects(card: CombatCard) -> List[DynamicSpellEffect]:
    output_effects: List[DynamicSpellEffect] = []
    for effect in await card.get_spell_effects():
        await _flatten_effect(effect, output_effects)
    return output_effects


async def is_enchantable(card: CombatCard) -> bool:
    return not any((
        await card.is_enchanted(),
        await card.is_enchanted_from_item_card(),
        await card.is_treasure_card(),
        await card.is_item_card(),
        await card.is_cloaked(),
    ))


damage_effects = {
    SpellEffects.damage,
    SpellEffects.damage_no_crit,
    SpellEffects.damage_over_time,
    SpellEffects.damage_per_total_pip_power,
    SpellEffects.deferred_damage,
    SpellEffects.instant_kill,
    SpellEffects.divide_damage,
    SpellEffects.steal_health,
    SpellEffects.max_health_damage
}

buff_damage_effects = {
    SpellEffects.modify_incoming_damage,
    SpellEffects.modify_incoming_damage_flat,
    SpellEffects.modify_incoming_damage_over_time,
    SpellEffects.modify_outgoing_damage,
    SpellEffects.modify_outgoing_damage_flat
}

buff_heal_effects = {
    SpellEffects.modify_outgoing_heal,
    SpellEffects.modify_outgoing_heal_flat,
    SpellEffects.modify_incoming_heal,
    SpellEffects.modify_incoming_heal_flat,
    SpellEffects.modify_incoming_heal_over_time
}

heal_effects = {
    SpellEffects.heal,
    SpellEffects.heal_by_ward,
    SpellEffects.heal_over_time,
    SpellEffects.heal_percent,
    SpellEffects.max_health_heal
}
charm_effects = {
    SpellEffects.modify_outgoing_armor_piercing,
    SpellEffects.modify_outgoing_damage,
    SpellEffects.modify_outgoing_damage_flat,
    SpellEffects.modify_outgoing_heal,
    SpellEffects.modify_outgoing_heal_flat,
    SpellEffects.cloaked_charm,
    SpellEffects.modify_accuracy
}
ward_effects = {
    SpellEffects.modify_incoming_armor_piercing,
    SpellEffects.modify_incoming_damage,
    SpellEffects.modify_incoming_damage_flat,
    SpellEffects.modify_incoming_damage_over_time,
    SpellEffects.modify_incoming_heal,
    SpellEffects.modify_incoming_heal_flat,
    SpellEffects.modify_incoming_heal_over_time
}

ally_targets = {
    EffectTarget.friendly_minion,
    EffectTarget.friendly_single,
    EffectTarget.friendly_single_not_me,
    EffectTarget.friendly_team,
    EffectTarget.friendly_team_all_at_once,
    EffectTarget.multi_target_friendly,
    EffectTarget.self
}

enemy_targets = {
    EffectTarget.at_least_one_enemy,
    EffectTarget.enemy_single,
    EffectTarget.enemy_team,
    EffectTarget.enemy_team_all_at_once,
    EffectTarget.multi_target_enemy,
    EffectTarget.preselected_enemy_single
}

aoe_targets = {
    EffectTarget.enemy_team,
    EffectTarget.enemy_team_all_at_once,
    EffectTarget.friendly_team,
    EffectTarget.friendly_team_all_at_once
}

class ReqSatisfaction(Enum):
    true = auto()
    false = auto()
    reject_card = auto()


def get_req_status(req_statement: bool) -> ReqSatisfaction:
    if req_statement:
        return ReqSatisfaction.true
    
    return ReqSatisfaction.false


async def is_req_satisfied(effect: DynamicSpellEffect, req: SpellType, template: TemplateSpell, allow_aoe: bool = False) -> bool:
    eff_type = await effect.effect_type()
    target = await effect.effect_target()
    param = await effect.effect_param()
    rounds = await effect.num_rounds()

    _aoe_targets = aoe_targets
    if not allow_aoe:
        _aoe_targets = {}


    def is_blade() -> bool:
        return all((
            eff_type in charm_effects,
            target in ally_targets.difference(_aoe_targets),
            param > 0,
            rounds == 0,
        ))

    def is_charm() -> bool:
        return all((
            eff_type in charm_effects,
            target in enemy_targets.difference(_aoe_targets),
            param < 0,
            rounds == 0,
        ))

    def is_ward() -> bool:
        return all((
            eff_type in ward_effects,
            target in ally_targets.difference(_aoe_targets),
            param < 0,
            rounds == 0,
        ))

    def is_trap() -> bool:
        return all((
            eff_type in ward_effects,
            target in enemy_targets.difference(_aoe_targets),
            param > 0,
            rounds == 0,
        ))
    
    def is_aura() -> bool:
        return all((
            eff_type in charm_effects.union(ward_effects),
            target is EffectTarget.self,
            rounds > 0,
        ))
    
    def is_global() -> bool:
        return all((
            eff_type in charm_effects.union(ward_effects),
            target is EffectTarget.target_global,
        ))
    
    def hits_enemy() -> bool:
        return target in enemy_targets
    
    def hits_ally() -> bool:
        return target in ally_targets
    
    def is_effect_beneficial(neg_is_good: bool = False) -> bool:
        if is_global():
            return True

        if neg_is_good:
            return (hits_ally() and param < 0) or (hits_enemy() and param > 0)
        
        return (hits_ally() and param > 0) or (hits_enemy() and param < 0)
    

    def is_damage() -> bool:
        return eff_type in damage_effects and hits_enemy() and is_effect_beneficial(True)
    
    def is_heal() -> bool:
        return eff_type in heal_effects and hits_ally() and is_effect_beneficial()

    #if is_damage() and SpellType.type_damage not in template.requirements:
    #    return ReqSatisfaction.reject_card
    
    #if is_heal() and SpellType.type_heal not in template.requirements:
    #    return ReqSatisfaction.reject_card

    is_satisfied = True
    match req:
        case SpellType.type_damage:
            is_satisfied = is_damage()
        
        case SpellType.type_inc_damage:
            is_satisfied = eff_type in (SpellEffects.modify_incoming_damage, SpellEffects.modify_incoming_damage_flat, SpellEffects.modify_incoming_damage_over_time) and is_effect_beneficial(True)

        case SpellType.type_out_damage:
            is_satisfied = eff_type in (SpellEffects.modify_outgoing_damage, SpellEffects.modify_outgoing_damage_flat) and is_effect_beneficial()

        case SpellType.type_aoe:
            is_satisfied = target in aoe_targets
        
        case SpellType.type_inc_heal:
            is_satisfied = eff_type in (SpellEffects.modify_incoming_heal, SpellEffects.modify_incoming_heal_flat, SpellEffects.modify_incoming_heal_over_time) and is_effect_beneficial()

        case SpellType.type_out_heal:
            is_satisfied = eff_type in (SpellEffects.modify_outgoing_heal, SpellEffects.modify_outgoing_heal_flat) and is_effect_beneficial()
        
        case SpellType.type_heal:
            is_satisfied = is_heal()
        
        case SpellType.type_heal_self:
            is_satisfied = eff_type in heal_effects and target in (EffectTarget.self, EffectTarget.friendly_team) and is_effect_beneficial()
        
        case SpellType.type_heal_other: #TODO: Figure out why this even exists - slack
            is_satisfied = eff_type in heal_effects and target in (EffectTarget.friendly_single, EffectTarget.friendly_single_not_me) and is_effect_beneficial()
        
        case SpellType.type_blade:
            is_satisfied = is_blade() and hits_ally()
        
        case SpellType.type_charm:
            is_satisfied = is_charm() and hits_enemy()

        case SpellType.type_ward:
            is_satisfied = is_ward() and hits_ally()
        
        case SpellType.type_trap:
            is_satisfied = is_trap() and hits_enemy()
        
        case SpellType.type_enchant:
            is_satisfied = target is EffectTarget.spell
        
        case SpellType.type_aura:
            is_satisfied = is_aura()

        case SpellType.type_global:
            is_satisfied = is_global()
        
        case SpellType.type_polymorph:
            is_satisfied = eff_type is SpellEffects.polymorph
        
        case SpellType.type_shadow:
            is_satisfied = eff_type is SpellEffects.shadow_self
        
        case SpellType.type_shadow_creature:
            is_satisfied = eff_type in (SpellEffects.shadow_creature, SpellEffects.select_shadow_creature_attack_target)
        
        case SpellType.type_pierce:
            is_satisfied = eff_type in (SpellEffects.modify_outgoing_armor_piercing, SpellEffects.modify_incoming_armor_piercing) and is_effect_beneficial()
        
        case SpellType.type_prism:
            is_satisfied = eff_type in (SpellEffects.modify_outgoing_damage_type, SpellEffects.modify_incoming_damage_type)
        
        case SpellType.type_dispel:
            is_satisfied = eff_type is SpellEffects.dispel

        case SpellType.type_mod_damage:
            is_satisfied = eff_type is SpellEffects.modify_card_damage and target is EffectTarget.spell

        case SpellType.type_mod_heal:
            is_satisfied = eff_type is SpellEffects.modify_card_outgoing_heal and target is EffectTarget.spell

        case SpellType.type_mod_pierce:
            is_satisfied = eff_type is SpellEffects.modify_card_outgoing_armor_piercing and target is EffectTarget.spell
        
        case _:
            # This should never happen
            is_satisfied = False

    return get_req_status(is_satisfied)
        

async def does_card_contain_reqs(card: CombatCard, template: TemplateSpell) -> bool:
    effects = await get_inner_card_effects(card)
    is_aoe_req = SpellType.type_aoe in template.requirements
    # req_met / gambit() / clear() / echo() / swap() are meta-filters checked
    # post-selection, not per-effect.
    reqs_to_check = [
        r for r in template.requirements
        if r is not SpellType.type_req_met
        and not isinstance(r, (GambitSpec, ClearSpec, EchoSpec, SwapSpec))
    ]
    matched_reqs = 0
    needed_matches = len(reqs_to_check)

    if SpellType.type_damage in template.requirements:
        card_name = await card.name()
        eff_info = []
        for e in effects:
            eff_info.append(f"{await e.effect_type()}@{await e.effect_target()}")
        _dbg(f"[MT-DBG] does_card_contain_reqs: card={card_name}, reqs={template.requirements}, effects=[{', '.join(eff_info)}]")

    for req in reqs_to_check:
        for e in effects:
            req_status = await is_req_satisfied(e, req, template, is_aoe_req)
            match req_status:
                case ReqSatisfaction.true:
                    matched_reqs += 1
                    break

                case ReqSatisfaction.reject_card:
                    break

                case _:
                    pass


    # Multi-target spells use an effect type not in wizwalker's enum (shows as
    # invalid_spell_effect). Infer spell category from the multi-target effect target.
    if matched_reqs < needed_matches:
        for e in effects:
            eff_target = await e.effect_target()
            if eff_target == EffectTarget.multi_target_enemy and SpellType.type_damage in template.requirements:
                matched_reqs += 1
                break
            elif eff_target == EffectTarget.multi_target_friendly and SpellType.type_heal in template.requirements:
                matched_reqs += 1
                break

    if matched_reqs == needed_matches and is_aoe_req:
        # Reject cards that have single-target damage effects — they require
        # target selection and are not true AOEs (e.g. Storm Beetle: single-target
        # damage + team blade falsely matches type_aoe via the blade's target).
        for e in effects:
            eff_type = await e.effect_type()
            target = await e.effect_target()
            if eff_type in damage_effects and target in enemy_targets and target not in aoe_targets:
                return False

    return matched_reqs == needed_matches


async def card_requires_target_selection(card: CombatCard) -> bool:
    """Check if a card requires the player to select a target (i.e. not a true AOE).
    Returns True if any damage/steal effect targets a single enemy rather than a team,
    or if the card is a multi-target enemy spell."""
    effects = await get_inner_card_effects(card)
    for e in effects:
        eff_type = await e.effect_type()
        eff_target = await e.effect_target()
        if eff_type in damage_effects and eff_target in enemy_targets and eff_target not in aoe_targets:
            return True
        # Multi-target enemy spells also require target selection
        if eff_target == EffectTarget.multi_target_enemy:
            return True
    return False


async def card_is_multi_target(card: CombatCard) -> bool:
    """Check if a card uses multi-target selection (select enemies/allies individually).
    Uses top-level effects because multi_target_enemy/friendly is on the outer
    CompoundSpellEffect, not on the unwrapped sub-effects."""
    effects = await card.get_spell_effects()
    for e in effects:
        eff_target = await e.effect_target()
        if eff_target in (EffectTarget.multi_target_enemy, EffectTarget.multi_target_friendly):
            return True
    return False


class SprintyCombat(CombatHandler):
    def __init__(self, client: wizwalker.client.Client, config_provider: BaseCombatBackend, handle_mouseless: bool = False):
        super().__init__(client)
        self.client: wizwalker.client.Client = client # to restore autocomplete
        self.config = config_provider
        self.turn_adjust = 0
        self.cur_card_count = 0
        self.prev_card_count = 0
        self.was_pass = False
        self.had_first_round = False
        self.rel_round_offset = 0
        self.handle_mouseless = handle_mouseless

    async def handle_combat(self):
        self.turn_adjust = 0
        self.cur_card_count = 0
        self.prev_card_count = 0
        self.rel_round_offset = 0
        self.was_pass = False
        self.had_first_round = False
        self._did_deck_inspect = False  # one-shot deck dump per fight
        await super().handle_combat()

    async def get_member_named(self, name: str) -> Optional[CombatMember]:
        # Issue: #4
        async def _inner():
            members: List[CombatMember] = await self.get_members()

            for member in members:
                if name == await member.name():
                    return member
            return None
        try:
            return await wizwalker.utils.maybe_wait_for_any_value_with_timeout(
                _inner,
                timeout=2.0
            )
        except wizwalker.errors.ExceptionalTimeout:
            return None

    async def get_member_vaguely_named(self, name: str) -> Optional[CombatMember]:
        # Issue #4
        async def _inner():
            members = await self.get_members()

            for member in members:
                if name.lower() in (await member.name()).lower():
                    return member
            return None
        try:
            return await wizwalker.utils.maybe_wait_for_any_value_with_timeout(
                _inner,
                timeout=2.0
            )
        except wizwalker.errors.ExceptionalTimeout:
            return None

    async def pass_button(self):
        self.was_pass = True
        await super().pass_button()

    async def get_cards(self) -> List[CombatCard]:  # extended to sort by enchanted
        async def _inner() -> List[CombatCard]:
            cards = await super(SprintyCombat, self).get_cards()
            rese, res = [], []
            for card in cards:
                if await card.is_enchanted():
                    rese.append(card)
                else:
                    res.append(card)
            return rese + res
        try:
            return await wizwalker.utils.maybe_wait_for_any_value_with_timeout(_inner, sleep_time=0.2, timeout=2.0)
        except wizwalker.errors.ExceptionalTimeout:
            return []

    async def get_num_card_windows(self) -> int:
        hand = (await self.client.root_window.get_windows_with_name("Hand"))[0]
        num = 0
        for i in range(7):
            card = await hand.get_child_by_name(f"Card{i+1}")
            if await card.is_visible():
                num += 1

        return num

    async def get_card_named(self, name: str) -> Optional[CombatCard]:
        try:
            return await super().get_card_named(name)
        except ValueError:
            return None

    async def get_card_with_predicate(self, pred: Callable) -> Optional[CombatCard]:
        cards = await self.get_cards_with_predicate(pred)
        if len(cards) > 0:
            return cards[0]
        return None

    async def get_card_vaguely_named(self, name: str) -> Optional[CombatCard]:
        async def _pred(card: CombatCard):
            return name.lower() in (await card.name()).lower()

        return await self.get_card_with_predicate(_pred)

    async def get_card_counts(self) -> Tuple[int, int]:
        # Issue: #6. Very rare error
        async def _inner():
            window = None
            while window is None:
                window, *_ = await self.client.root_window.get_windows_with_name("CountText")
            text: str = await window.maybe_text()
            _, count_text = text.splitlines()
            count_text = count_text[8:-9]
            count_text = count_text.replace("of", "").strip()  # I know this sucks
            res1, res2 = count_text.split()
            return int(res1), int(res2)
        try:
            return await wizwalker.utils.maybe_wait_for_any_value_with_timeout(_inner, sleep_time=0.2, timeout=2.0)
        except wizwalker.errors.ExceptionalTimeout:
            return (0, 0) # TODO: Maybe propagate, but good enough for now

    async def get_castable_cards(self) -> List[CombatCard]:  # extension for castable cards only
        async def _pred(card: CombatCard):
            return await card.is_castable()

        return await self.get_cards_with_predicate(_pred)

    async def get_castable_cards_named(self, name: str) -> List[CombatCard]:
        cards = await self.get_castable_cards()
        res = []

        for card in cards:
            if name == await card.name():
                res.append(card)

        return res

    async def get_castable_cards_vaguely_named(self, name: str) -> List[CombatCard]:
        cards = await self.get_castable_cards()
        res = []
        for card in cards:
            if name.lower() in (await card.name()).lower():
                res.append(card)

        return res

    async def get_castable_card_named(self, name: str, only_enchants=False) -> Optional[CombatCard]:  # extension to get only castable card
        cards = await self.get_castable_cards()

        for card in cards:
            if name == await card.name():
                if only_enchants:
                    for e in await card.get_spell_effects():
                        if await e.effect_target() is EffectTarget.spell:
                            return card
                    else:
                        continue
                return card

        return None

    async def get_castable_card_vaguely_named(self, name: str, only_enchants=False) -> Optional[CombatCard]:
        cards = await self.get_castable_cards()

        for card in cards:
            if name.lower() in (await card.name()).lower():
                if only_enchants:
                    for e in await card.get_spell_effects():
                        if await e.effect_target() is EffectTarget.spell:
                            return card
                    else:
                        continue
                return card

        return None

    async def get_castable_enchanted_card_named(self, name: str) -> Optional[CombatCard]:
        for s in await self.get_castable_cards_named(name):
            if await s.is_enchanted():
                return s
        return None

    async def get_castable_enchanted_card_vaguely_named(self, name: str) -> Optional[CombatCard]:
        for s in await self.get_castable_cards_vaguely_named(name):
            if await s.is_enchanted():
                return s
        return None

    async def get_castable_cards_by_template(self, template: TemplateSpell) -> List[CombatCard]:
        cards = await self.get_castable_cards()
        res = []
        for c in cards:
            if await does_card_contain_reqs(c, template):
                res.append(c)

        return res

    async def get_cards_by_template(self, template: TemplateSpell) -> List[CombatCard]:
        cards = await self.get_cards()
        res = []
        for c in cards:
            if await does_card_contain_reqs(c, template):
                res.append(c)

        return res


    async def get_boss_or_none(self) -> Optional[CombatMember]:
        for m in await self.get_members():
            if await m.is_boss():
                return m
        return None

    async def get_allies(self) -> List[CombatMember]:
        members = []
        my_client = await self.get_client_member()
        my_participant = await my_client.get_participant()
        my_team_id = await my_participant.team_id()
        my_id = await my_participant.owner_id_full()
        for mem in await self.get_members():
            participant = await mem.get_participant()
            if await participant.team_id() == my_team_id \
                    and await participant.owner_id_full() != my_id:
                members.append(mem)
        return members

    async def get_enemies(self) -> List[CombatMember]:
        members = []
        my_client = await self.get_client_member()
        my_participant = await my_client.get_participant()
        my_team_id = await my_participant.team_id()
        for mem in await self.get_members():
            participant = await mem.get_participant()
            if await participant.team_id() != my_team_id:
                members.append(mem)
        return members

    async def get_nth_ally_or_none(self, n: int) -> Optional[CombatMember]:
        allies = await self.get_allies()
        if len(allies) <= n:
            return None
        return allies[n]

    async def get_nth_enemy_or_none(self, n: int) -> Optional[CombatMember]:
        enemies = await self.get_enemies()
        if len(enemies) <= n:
            return None
        return enemies[n]

    async def try_get_spell(self, spell: Spell, only_enchants=False, only_enchantable: bool = False, castable: bool = True, multi: bool = False) -> Union[CombatCard, str, None, List]:
        if isinstance(spell, NamedSpell):
            spell: NamedSpell
            if spell.name in ("pass", "none", "willcast", "discard"):
                return spell.name

            res = []
            if castable:
                if spell.is_literal:
                    cards = await self.get_castable_cards_named(spell.name)
                else:
                    cards = await self.get_castable_cards_vaguely_named(spell.name)
            else:
                all_cards = await self.get_cards()
                if spell.is_literal:
                    cards = [c for c in all_cards if await c.name() == spell.name]
                else:
                    cards = [c for c in all_cards if spell.name.lower() in (await c.name()).lower()]

            for c in cards:
                if only_enchants:
                    effects = await c.get_spell_effects()
                    if not any(await e.effect_target() is EffectTarget.spell for e in effects):
                        continue
                if only_enchantable and not await is_enchantable(c):
                    continue
                res.append(c)

            if len(res) > 0:
                if multi:
                    return res
                return res[0]
            return None

        elif isinstance(spell, TemplateSpell):
            spell: TemplateSpell
            res = None
            if castable:
                res = await self.get_castable_cards_by_template(spell)
            else:
                res = await self.get_cards_by_template(spell)

            if only_enchantable:
                res = [c for c in res if await is_enchantable(c)]

            if len(res) > 0:
                if multi:
                    return res
                return res[0]
            return None
        else:
            raise NotImplementedError("Unknown spell config type")

    async def disc_on_target(self, targ: CombatCard):
        pre_discard_count = await self.get_num_card_windows()
        await targ.discard()
        while await self.get_num_card_windows() == pre_discard_count:
            await asyncio.sleep(0.1)
        self.cur_card_count -= 1

    async def try_get_config_target(self, target: TargetData) -> Union[bool, Optional[CombatMember]]:
        ttype = None
        data = None
        if target is not None:
            ttype = target.target_type
            data = target.extra_data
        else:
            return None

        if ttype is TargetType.type_boss:
            if boss := await self.get_boss_or_none():
                return boss
        elif ttype is TargetType.type_self:
            return await self.get_client_member()
        elif ttype is TargetType.type_aoe:
            return None
        elif ttype is TargetType.type_enemy:
            if data is None:
                if enemy := await self.get_nth_enemy_or_none(0):
                    return enemy
            else:
                if enemy := await self.get_nth_enemy_or_none(data):
                    return enemy
        elif ttype is TargetType.type_ally:
            if data is None:
                if ally := await self.get_nth_ally_or_none(0):
                    return ally
            else:
                if ally := await self.get_nth_ally_or_none(data):
                    return ally
        elif ttype is TargetType.type_enemies:
            enemies = await self.get_enemies()
            return enemies if enemies else False
        elif ttype is TargetType.type_allies:
            allies = [await self.get_client_member()] + await self.get_allies()
            return allies if allies else False
        elif ttype is TargetType.type_named:
            if target.is_literal:
                if res := await self.get_member_named(data):
                    return res
            if res := await self.get_member_vaguely_named(data):
                return res
        elif ttype is TargetType.type_spell:
            #if type(data) is list:
            #    res = []
            #    for item in data:
            #        #if card := await self.try_get_spell(spell=item, castable=False):
            #        res.append(item)
            #    return res
            #else:
            return data
                #if res := await self.try_get_spell(spell=data, castable=False):
                #    return res
                #else:
                #    return None
        elif ttype is TargetType.type_select:
            members = []
            if isinstance(data, list):
                for sub in data:
                    res = await self.try_get_config_target(sub)
                    #if isinstance(sub, tuple):
                    #    sub_type, sub_extra = sub
                    #    print(sub_type)
                    #    print(sub_extra)
                    #    res = await self.try_get_config_target(TargetData(sub_type, sub_extra))
                    #else:
                    #    res = await self.try_get_config_target(TargetData(sub))
                    if res:
                        #if isinstance(res, list):
                        #    members.extend(res)
                        #else:
                        members.append(res)
            return members if members else False

        return False

    async def resolve_condition_target(self, cond_target: ConditionTarget) -> Union[Optional[CombatMember], List[CombatMember]]:
        ttype = cond_target.target_type
        index = cond_target.index
        if ttype is TargetType.type_self:
            return await self.get_client_member()
        elif ttype is TargetType.type_boss:
            return await self.get_boss_or_none()
        elif ttype is TargetType.type_enemy:
            return await self.get_nth_enemy_or_none(index if index is not None else 0)
        elif ttype is TargetType.type_ally:
            return await self.get_nth_ally_or_none(index if index is not None else 0)
        elif ttype is TargetType.type_enemies:
            return await self.get_enemies()
        elif ttype is TargetType.type_allies:
            return [await self.get_client_member()] + await self.get_allies()
        return None

    # Map predicate-attribute aliases to (category, disposition) pairs. Built
    # from HANGING_CATEGORIES so adding a category there auto-extends predicates.
    # Each category emits 3 entries: <canonical>, beneficial_<canonical>,
    # harmful_<canonical>, plus the same triplet for every alias (e.g. "charm",
    # "ward", "ot", "aura"). e.g. charms → "charms", "beneficial_charms",
    # "harmful_charms", "charm", "beneficial_charm", "harmful_charm".
    _HANGING_ATTRS = {}
    for _canon, (_, _, _, _aliases, _) in HANGING_CATEGORIES.items():
        for _name in [_canon] + list(_aliases):
            _HANGING_ATTRS[_name] = (_canon, None)
            _HANGING_ATTRS[f"beneficial_{_name}"] = (_canon, HangingDisposition.beneficial)
            _HANGING_ATTRS[f"harmful_{_name}"] = (_canon, HangingDisposition.harmful)

    _HANGING_CATEGORY_MAP = {k: v[0] for k, v in HANGING_CATEGORIES.items()}

    async def _count_hanging_effects(self, member: CombatMember, category: str, disposition: Optional[HangingDisposition]) -> int:
        participant = await member.get_participant()
        # Auras: engine enforces 1-per-side, but aura_effects() exposes one
        # entry per sub-effect of a multi-effect aura spell (e.g. Punishment
        # has 5 modify-effects → 5 entries). Treat the answer as boolean
        # (0 or 1) so predicates like `self.beneficial_auras < 1` mean what
        # users expect: "no aura active" vs "an aura is active".
        if category == "auras":
            effects = list(await participant.aura_effects())
        else:
            effects = list(await participant.hanging_effects())
        type_list = self._HANGING_CATEGORY_MAP[category]
        count = 0
        for effect in effects:
            etype = await effect.effect_type()
            if etype not in type_list:
                continue
            if disposition is not None:
                edisp = await effect.disposition()
                if edisp != HangingDisposition.both and edisp != disposition:
                    continue
            count += 1
        if category == "auras":
            count = 1 if count > 0 else 0
        _dbg(f"[COND-DBG] _count_hanging_effects: category={category}, disposition={disposition}, total_effects={len(effects)}, matched={count}")
        return count

    def _compare(self, actual: float, op: ComparisonOp, val: float) -> bool:
        if op is ComparisonOp.lt:
            return actual < val
        elif op is ComparisonOp.le:
            return actual <= val
        elif op is ComparisonOp.gt:
            return actual > val
        elif op is ComparisonOp.ge:
            return actual >= val
        elif op is ComparisonOp.eq:
            return actual == val
        elif op is ComparisonOp.ne:
            return actual != val
        return False

    async def _read_member_attr(self, member: CombatMember, condition: Condition) -> Optional[float]:
        # Check for hanging effect pseudo-attributes first
        if condition.attribute in self._HANGING_ATTRS:
            category, disposition = self._HANGING_ATTRS[condition.attribute]
            return float(await self._count_hanging_effects(member, category, disposition))

        attr_fn = getattr(member, condition.attribute, None)
        if attr_fn is None or not callable(attr_fn):
            return None
        actual = await attr_fn()
        if condition.is_percent:
            max_fn = getattr(member, f"max_{condition.attribute}", None)
            if max_fn is None or not callable(max_fn):
                return None
            max_val = await max_fn()
            if max_val == 0:
                return None
            actual = (actual / max_val) * 100
        return float(actual)

    async def evaluate_condition(self, condition) -> bool:
        # AllCondition: short-circuit AND over its clauses.
        if isinstance(condition, AllCondition):
            for clause in condition.clauses:
                if not await self.evaluate_condition(clause):
                    return False
            return True
        try:
            target = await self.resolve_condition_target(condition.target)
            if target is None:
                _dbg(f"[COND-DBG] evaluate_condition: target is None for {condition}")
                return False

            agg = condition.target.aggregation

            # Single member (no aggregation)
            if agg is None:
                if isinstance(target, list):
                    return False
                val = await self._read_member_attr(target, condition)
                if val is None:
                    _dbg(f"[COND-DBG] evaluate_condition: attr read returned None for {condition}")
                    return False
                result = self._compare(val, condition.op, condition.value)
                _dbg(f"[COND-DBG] evaluate_condition: {condition.attribute}={val} {condition.op.value} {condition.value} -> {result}")
                return result

            # Group aggregation
            members = target if isinstance(target, list) else [target]
            if not members:
                return False

            if agg is AggregationMode.agg_any:
                for m in members:
                    val = await self._read_member_attr(m, condition)
                    if val is not None and self._compare(val, condition.op, condition.value):
                        return True
                return False

            elif agg is AggregationMode.agg_all:
                for m in members:
                    val = await self._read_member_attr(m, condition)
                    if val is None or not self._compare(val, condition.op, condition.value):
                        return False
                return True

            elif agg is AggregationMode.agg_avg:
                total = 0.0
                count = 0
                for m in members:
                    val = await self._read_member_attr(m, condition)
                    if val is not None:
                        total += val
                        count += 1
                if count == 0:
                    return False
                return self._compare(total / count, condition.op, condition.value)

            return False
        except Exception as e:
            _dbg(f"[COND-DBG] evaluate_condition EXCEPTION: {type(e).__name__}: {e}")
            return False

    async def _get_member_index(self, member: CombatMember) -> Optional[int]:
        members = await self.get_members()
        for i, m in enumerate(members):
            if await m.owner_id() == await member.owner_id():
                return i
        return None

    _HANGING_TYPE_LISTS = {
        HangingEffectType.charm:     charm_effect_types,
        HangingEffectType.ward:      ward_effect_types,
        HangingEffectType.over_time: over_time_effect_types,
    }

    async def _hanging_conversion_satisfied(self, conv: HangingConversionSpellEffect) -> bool:
        """Check whether a HangingConversionSpellEffect's requirements are met
        against the caster's hanging effects (the conversion source)."""
        try:
            eff_type = await conv.hanging_effect_type()
            min_n = await conv.min_effect_count()
            max_n = await conv.max_effect_count()

            caster = await self.get_client_member()
            participant = await caster.get_participant()
            hanging = await participant.hanging_effects()

            if eff_type is HangingEffectType.any:
                count = len(hanging)
            elif eff_type is HangingEffectType.specific:
                specific = await conv.specific_effect_types()
                count = 0
                for h in hanging:
                    if (await h.effect_type()) in specific:
                        count += 1
            else:
                type_list = self._HANGING_TYPE_LISTS.get(eff_type, [])
                count = 0
                for h in hanging:
                    if (await h.effect_type()) in type_list:
                        count += 1

            satisfied = min_n <= count <= max_n
            _dbg(f"[REQ-DBG] hanging_conversion: type={eff_type}, count={count}, range=[{min_n},{max_n}] -> {satisfied}")
            return satisfied
        except Exception as e:
            _dbg(f"[REQ-DBG] hanging_conversion EXCEPTION: {type(e).__name__}: {e}")
            return False

    async def _inspect_deck_once(self):
        """One-shot dump of every card's full effect tree to verify field semantics
        (especially HangingConversionSpellEffect.apply_to_effect_source). Runs once
        per SprintyCombat instance so it appears at the first round of each fight."""
        if not _DEBUG:
            return
        if getattr(self, "_did_deck_inspect", False):
            return
        self._did_deck_inspect = True
        try:
            cards = await self.get_cards()
            _dbg(f"[INSPECT] === DECK DUMP ({len(cards)} cards) ===")
            for ci, card in enumerate(cards):
                name = await card.name()
                effects = await card.get_spell_effects()
                _dbg(f"[INSPECT] [{ci}] {name} (top-level effects: {len(effects)})")
                for ei, eff in enumerate(effects):
                    await self._dump_effect(eff, depth=1, idx=ei)
            _dbg(f"[INSPECT] === END DECK DUMP ===")
        except Exception as e:
            _dbg(f"[INSPECT] EXCEPTION: {type(e).__name__}: {e}")

    async def _dump_effect(self, eff, depth: int, idx: int):
        pad = "  " * depth
        klass = type(eff).__name__
        try:
            etype = await eff.effect_type()
        except Exception:
            etype = "?"
        try:
            etarget = await eff.effect_target()
        except Exception:
            etarget = "?"
        try:
            edisp = await eff.disposition()
        except Exception:
            edisp = "?"
        header = f"{pad}[{idx}] {klass} type={etype} target={etarget} disposition={edisp}"

        if isinstance(eff, HangingConversionSpellEffect):
            try:
                het = await eff.hanging_effect_type()
                min_n = await eff.min_effect_count()
                max_n = await eff.max_effect_count()
                from_src = await eff.apply_to_effect_source()
                not_dmg = await eff.not_damage_type()
                spec = await eff.specific_effect_types()
                outputs = await eff.output_effect()
                print(header)
                print(f"{pad}  HangingConversion: hanging_type={het} count_range=[{min_n},{max_n}] apply_to_effect_source={from_src} not_damage_type={not_dmg} specific={spec} outputs={len(outputs)}")
                for oi, o in enumerate(outputs):
                    await self._dump_effect(o, depth + 2, oi)
            except Exception as e:
                print(f"{header}  <conversion read error: {type(e).__name__}: {e}>")
            return

        if isinstance(eff, ConditionalSpellEffect):
            try:
                elements = await eff.elements()
                print(f"{header}  Conditional: {len(elements)} branches")
                for bi, elem in enumerate(elements):
                    reqs = await elem.reqs()
                    req_items = await reqs.requirements()
                    elem_eff = await elem.effect()
                    print(f"{pad}    Branch[{bi}]: {len(req_items)} reqs")
                    for ri, r in enumerate(req_items):
                        await self._dump_requirement(r, ri, pad + "      ")
                    print(f"{pad}      output:")
                    await self._dump_effect(elem_eff, depth + 4, 0)
            except Exception as e:
                print(f"{header}  <conditional read error: {type(e).__name__}: {e}>")
            return

        if isinstance(eff, CompoundSpellEffect):
            try:
                sub = await eff.effects_list()
                print(f"{header}  Compound: {len(sub)} sub-effects")
                for si, s in enumerate(sub):
                    await self._dump_effect(s, depth + 2, si)
            except Exception as e:
                print(f"{header}  <compound read error: {type(e).__name__}: {e}>")
            return

        print(header)

    async def _dump_requirement(self, req, idx: int, pad: str):
        klass = type(req).__name__
        fields = []
        for fname in ("apply_not", "operator", "disposition", "target_type",
                      "min_count", "max_count", "min_pips", "max_pips",
                      "min_percent", "max_percent", "magic_school_name"):
            if hasattr(req, fname):
                try:
                    v = await getattr(req, fname)()
                    fields.append(f"{fname}={v}")
                except Exception:
                    pass
        print(f"{pad}Req[{idx}]: {klass} {' '.join(fields)}")

    # Recognized as "hanging-driven" branches for the strict-branch check in
    # card_requirements_met. ReqHangingAura._evaluate always returns False for
    # now, so aura branches are recognized as hanging conditionals but never
    # satisfy req_met until evaluation lands.
    _HANGING_REQ_CLASSES = tuple(
        v[1] for v in HANGING_CATEGORIES.values() if v[1] is not None
    )

    @staticmethod
    async def _branch_has_positive_hanging_req(req_items: list) -> bool:
        """A branch counts as a 'bonus' branch only if it has at least one
        non-negated hanging requirement. Negated reqs (apply_not=True) describe
        the absence-of-bonus fallback path, not the bonus itself."""
        for r in req_items:
            if not isinstance(r, SprintyCombat._HANGING_REQ_CLASSES):
                continue
            try:
                if not await r.apply_not():
                    return True
            except Exception:
                continue
        return False

    async def card_requirements_met(self, card: CombatCard, target_member: Optional[CombatMember]) -> bool:
        """Plain `req_met` predicate (strict): card must have at least one
        currently-active hanging-driven bonus to pass. Cards with no
        hanging-driven effects (e.g. plain damage spells like Supernova) FAIL
        req_met — they fall through to a plain `any<damage>` line. Default /
        non-hanging conditional branches (school checks, pip checks, etc.) don't
        count; only branches with a non-negated hanging requirement do."""
        try:
            card_name = await card.name()
            effects = await card.get_spell_effects()
            saw_relevant = False
            for effect in effects:
                if isinstance(effect, HangingConversionSpellEffect):
                    saw_relevant = True
                    if await self._hanging_conversion_satisfied(effect):
                        _dbg(f"[REQ-DBG] card_requirements_met: card={card_name} -> True (hanging conversion satisfied)")
                        return True
                    continue

                if not isinstance(effect, ConditionalSpellEffect):
                    continue

                target_idx = 0
                if target_member is not None:
                    idx = await self._get_member_index(target_member)
                    if idx is not None:
                        target_idx = idx
                data = {"combat": self, "target_idx": target_idx}

                for element in await effect.elements():
                    req_list = await element.reqs()
                    try:
                        req_items = await req_list.requirements()
                    except Exception as e:
                        # Wizwalker can't promote some requirement classes yet
                        # (e.g. ReqHangingAura). Skip this branch — it neither
                        # satisfies nor disqualifies the card.
                        _dbg(f"[REQ-DBG] card_requirements_met: card={card_name} branch skipped ({type(e).__name__}: {e})")
                        continue
                    if not await self._branch_has_positive_hanging_req(req_items):
                        continue  # ignore fallback branches and non-hanging conditionals
                    saw_relevant = True
                    try:
                        is_met = await req_list._evaluate(data)
                    except Exception as e:
                        _dbg(f"[REQ-DBG] card_requirements_met: card={card_name} branch eval skipped ({type(e).__name__}: {e})")
                        continue
                    if is_met:
                        _dbg(f"[REQ-DBG] card_requirements_met: card={card_name} -> True (hanging-conditional branch met)")
                        return True

            if not saw_relevant:
                _dbg(f"[REQ-DBG] card_requirements_met: card={card_name} -> False (no hanging-driven effects, strict mode)")
                return False
            _dbg(f"[REQ-DBG] card_requirements_met: card={card_name} -> False (no hanging bonus active)")
            return False
        except Exception as e:
            _dbg(f"[REQ-DBG] card_requirements_met EXCEPTION: {type(e).__name__}: {e}")
            return False

    # Category lookup tables derived from the registry — adding a category in
    # combat_api.HANGING_CATEGORIES auto-extends these. None values are kept so
    # callers can distinguish "category unsupported on this path" from
    # "category not present at all" via .get().
    # Union of every category's hanging-applying SpellEffects, used by the echo
    # matcher to decide whether a branch's output effect is "applies a hanging".
    # Includes auras explicitly since they're not in HANGING_CATEGORIES yet.
    _ALL_HANGING_EFFECTS = (
        set(charm_effect_types) | set(ward_effect_types)
        | set(over_time_effect_types) | set(aura_effect_types)
    )

    _CATEGORY_TO_LIST      = {k: v[0] for k, v in HANGING_CATEGORIES.items()}
    _CATEGORY_TO_REQ_CLASS = {k: v[1] for k, v in HANGING_CATEGORIES.items()}
    _CATEGORY_TO_HET       = {k: v[2] for k, v in HANGING_CATEGORIES.items()}
    _CATEGORY_TO_SWAP      = {k: v[4] for k, v in HANGING_CATEGORIES.items()}

    @classmethod
    def _resolve_verb_sides(cls, spec: Union["GambitSpec", "ClearSpec", "EchoSpec"]) -> List[Tuple[str, HangingDisposition]]:
        """Return the list of (side, required_disposition) tuples that satisfy
        the verb. side is 'caster' or 'target'. The disposition baked into the
        hanging type pins which half of the verb's two-sided definition matches;
        an unspecified disposition covers both halves.

        Verb tables (source side the spell reads to fire its bonus):
          gambit: caster-beneficial OR target-harmful   (consume good or strip bad)
          clear:  caster-harmful   OR target-beneficial (cleanse self or strip buff)
          echo:   target-beneficial OR target-harmful   (mirror enemy effect to self)
        """
        _, disp = hanging_type_info(spec.hanging_type)
        if isinstance(spec, EchoSpec):
            if disp is None:
                return [("target", HangingDisposition.beneficial),
                        ("target", HangingDisposition.harmful)]
            return [("target", disp)]
        is_gambit = isinstance(spec, GambitSpec)
        if disp is None:
            if is_gambit:
                return [("caster", HangingDisposition.beneficial),
                        ("target", HangingDisposition.harmful)]
            return [("caster", HangingDisposition.harmful),
                    ("target", HangingDisposition.beneficial)]
        if is_gambit:
            if disp == HangingDisposition.beneficial:
                return [("caster", HangingDisposition.beneficial)]
            return [("target", HangingDisposition.harmful)]
        # Clear
        if disp == HangingDisposition.beneficial:
            return [("target", HangingDisposition.beneficial)]
        return [("caster", HangingDisposition.harmful)]

    async def _count_member_hanging(self, member: CombatMember, category: str, disposition: HangingDisposition) -> int:
        """Count hanging effects on a member matching category ('charm'/'ward'/
        'over_time'/'auras') + disposition. Effects with disposition=both count
        for either beneficial or harmful queries. Auras live on a separate
        participant collection (aura_effects) and must be combined with the
        main hanging_effects list."""
        type_list = self._CATEGORY_TO_LIST[category]
        participant = await member.get_participant()
        # Auras: see _count_hanging_effects — engine caps at 1 per side, but
        # aura_effects exposes one entry per sub-effect of a multi-effect
        # spell. Clamp to boolean so gambit/clear `min_count` behave sanely
        # (only 0 or 1 ever holds for auras).
        if category == "auras":
            hanging = list(await participant.aura_effects())
        else:
            hanging = list(await participant.hanging_effects())
        count = 0
        for h in hanging:
            if (await h.effect_type()) not in type_list:
                continue
            d = await h.disposition()
            if d != HangingDisposition.both and d != disposition:
                continue
            count += 1
        if category == "auras":
            count = 1 if count > 0 else 0
        return count

    async def _conversion_matches_verb(
        self,
        conv: HangingConversionSpellEffect,
        target_member: Optional[CombatMember],
        spec: Union[GambitSpec, ClearSpec, EchoSpec],
    ) -> bool:
        """A HangingConversionSpellEffect matches Gambit/Clear if:
        - its category aligns with spec's category, AND
        - at least one of the verb's resolved (side, disposition) pairs has
          >= max(spec.min_count, spell_min) matching hanging effects.
        We scan resolved sides directly because `apply_to_effect_source` doesn't
        reliably identify the consumed-from side (verified empirically — Novus
        Storm has apply_to_effect_source=False but consumes caster's charms)."""
        category, _ = hanging_type_info(spec.hanging_type)
        het = await conv.hanging_effect_type()
        target_het = self._CATEGORY_TO_HET.get(category)  # may be None for new categories
        category_list = self._CATEGORY_TO_LIST[category]

        if het is HangingEffectType.any:
            pass
        elif het is HangingEffectType.specific:
            specific = await conv.specific_effect_types()
            if not any(t in category_list for t in specific):
                return False
        elif target_het is None or het is not target_het:
            # No HET shorthand for this category (or it doesn't match) — only the
            # specific/any paths above can satisfy. Fall through as no-match.
            return False

        threshold = max(spec.min_count, await conv.min_effect_count())
        caster = await self.get_client_member()
        for side, disp in self._resolve_verb_sides(spec):
            member = caster if side == "caster" else target_member
            if member is None:
                continue
            if await self._count_member_hanging(member, category, disp) >= threshold:
                return True
        return False

    async def _conditional_branch_matches_verb(
        self,
        req_items: list,
        spec: Union[GambitSpec, ClearSpec, EchoSpec],
    ) -> bool:
        """A ConditionalSpellEffect branch matches Gambit/Clear if it contains a
        hanging requirement of the matching category whose (target_type,
        disposition) aligns with one of the verb's resolved sides."""
        from wizwalker.memory.memory_objects.enums import RequirementTarget
        category, _ = hanging_type_info(spec.hanging_type)
        req_class = self._CATEGORY_TO_REQ_CLASS.get(category)
        if req_class is None:
            return False  # No wizwalker requirement class for this category yet.
        sides = self._resolve_verb_sides(spec)

        for r in req_items:
            if not isinstance(r, req_class):
                continue
            try:
                if await r.apply_not():
                    continue
                disp = await r.disposition()
                tgt = await r.target_type()
            except Exception:
                continue
            req_side = "caster" if tgt == RequirementTarget.caster else "target"
            for side, want_disp in sides:
                if side != req_side:
                    continue
                if disp == HangingDisposition.both or disp == want_disp:
                    return True
        return False

    async def _branch_output_applies_hanging_to_self(self, branch_effect, depth: int = 0) -> bool:
        """Walk a ConditionalSpellEffect branch's output effect (recursing
        Compound/EffectList wrappers) and return True if any leaf has
        effect_type in a hanging category and effect_target == self. This is
        the echo signature: read enemy hang -> apply hang to caster."""
        if depth > 8:
            return False
        cls = type(branch_effect)
        if issubclass(cls, CompoundSpellEffect):
            for sub in await branch_effect.effects_list():
                if await self._branch_output_applies_hanging_to_self(sub, depth + 1):
                    return True
            return False
        if issubclass(cls, ConditionalSpellEffect):
            for elem in await branch_effect.elements():
                if await self._branch_output_applies_hanging_to_self(await elem.effect(), depth + 1):
                    return True
            return False
        try:
            etype = await branch_effect.effect_type()
            etarget = await branch_effect.effect_target()
        except Exception:
            return False
        return etype in self._ALL_HANGING_EFFECTS and etarget == EffectTarget.self

    async def card_matches_gambit_or_clear(
        self,
        card: CombatCard,
        target_member: Optional[CombatMember],
        spec: Union[GambitSpec, ClearSpec, EchoSpec],
    ) -> bool:
        """Returns True iff the card has at least one currently-active bonus
        matching the Gambit/Clear verb + hanging type + minimum count."""
        verb = "gambit" if isinstance(spec, GambitSpec) else ("clear" if isinstance(spec, ClearSpec) else "echo")
        try:
            card_name = await card.name()
            effects = await card.get_spell_effects()
            for effect in effects:
                if isinstance(effect, HangingConversionSpellEffect):
                    if await self._conversion_matches_verb(effect, target_member, spec):
                        _dbg(f"[REQ-DBG] {verb}({spec.hanging_type.value},{spec.min_count}): card={card_name} -> True (hanging conversion)")
                        return True
                    continue
                if not isinstance(effect, ConditionalSpellEffect):
                    continue

                target_idx = 0
                if target_member is not None:
                    idx = await self._get_member_index(target_member)
                    if idx is not None:
                        target_idx = idx
                data = {"combat": self, "target_idx": target_idx}

                for element in await effect.elements():
                    req_list = await element.reqs()
                    try:
                        req_items = await req_list.requirements()
                    except Exception as e:
                        # Unknown requirement class (e.g. ReqHangingAura before
                        # wizwalker grows it). Skip the branch — neither match
                        # nor disqualify.
                        _dbg(f"[REQ-DBG] {verb}: card={card_name} branch skipped ({type(e).__name__}: {e})")
                        continue
                    if not await self._conditional_branch_matches_verb(req_items, spec):
                        continue
                    try:
                        is_met = await req_list._evaluate(data)
                    except Exception as e:
                        _dbg(f"[REQ-DBG] {verb}: card={card_name} branch eval skipped ({type(e).__name__}: {e})")
                        continue
                    if not is_met:
                        continue
                    if not await self._verb_count_satisfied(req_items, target_member, spec):
                        continue
                    # Echo additionally requires the branch's output to apply a
                    # hanging-category effect to caster (read-target/apply-self).
                    if isinstance(spec, EchoSpec):
                        try:
                            branch_eff = await element.effect()
                        except Exception as e:
                            _dbg(f"[REQ-DBG] echo: card={card_name} branch effect read failed ({type(e).__name__}: {e})")
                            continue
                        if not await self._branch_output_applies_hanging_to_self(branch_eff):
                            _dbg(f"[REQ-DBG] echo({spec.hanging_type.value}): card={card_name} branch req matched but output does not apply hanging to self")
                            continue
                    _dbg(f"[REQ-DBG] {verb}({spec.hanging_type.value},{spec.min_count}): card={card_name} -> True (conditional)")
                    return True
            _dbg(f"[REQ-DBG] {verb}({spec.hanging_type.value},{spec.min_count}): card={card_name} -> False")
            return False
        except Exception as e:
            _dbg(f"[REQ-DBG] {verb} EXCEPTION: {type(e).__name__}: {e}")
            return False

    async def _verb_count_satisfied(
        self,
        req_items: list,
        target_member: Optional[CombatMember],
        spec: Union[GambitSpec, ClearSpec, EchoSpec],
    ) -> bool:
        """For a branch already known to match the verb, verify the actual count
        on the appropriate member meets spec.min_count."""
        from wizwalker.memory.memory_objects.enums import RequirementTarget
        category, _ = hanging_type_info(spec.hanging_type)
        req_class = self._CATEGORY_TO_REQ_CLASS.get(category)
        if req_class is None:
            return False
        sides = self._resolve_verb_sides(spec)
        caster = await self.get_client_member()

        for r in req_items:
            if not isinstance(r, req_class):
                continue
            try:
                if await r.apply_not():
                    continue
                disp = await r.disposition()
                tgt = await r.target_type()
            except Exception:
                continue
            req_side = "caster" if tgt == RequirementTarget.caster else "target"
            for side, want_disp in sides:
                if side != req_side:
                    continue
                if disp != HangingDisposition.both and disp != want_disp:
                    continue
                member = caster if side == "caster" else target_member
                if member is None:
                    continue
                if await self._count_member_hanging(member, category, want_disp) >= spec.min_count:
                    return True
        return False

    async def card_matches_swap(self, card: CombatCard, spec: SwapSpec) -> bool:
        """Match cards whose top-level effect is a swap of the requested
        category+disposition. Swap effects are plain SpellEffects values
        (swap_charm/swap_ward/swap_over_time) carrying a HangingDisposition;
        unlike gambit/clear, they aren't wrapped in conditionals."""
        category, want_disp = hanging_type_info(spec.hanging_type)
        target_eff = self._CATEGORY_TO_SWAP.get(category)
        if target_eff is None:
            return False
        try:
            card_name = await card.name()
            for effect in await card.get_spell_effects():
                try:
                    etype = await effect.effect_type()
                except Exception:
                    continue
                if etype is not target_eff:
                    continue
                try:
                    disp = await effect.disposition()
                except Exception:
                    continue
                if want_disp is not None and disp != HangingDisposition.both and disp != want_disp:
                    continue
                _dbg(f"[REQ-DBG] swap({spec.hanging_type.value},{spec.min_count}): card={card_name} -> True (effect_type={etype}, disposition={disp})")
                return True
            _dbg(f"[REQ-DBG] swap({spec.hanging_type.value},{spec.min_count}): card={card_name} -> False")
            return False
        except Exception as e:
            _dbg(f"[REQ-DBG] swap EXCEPTION: {type(e).__name__}: {e}")
            return False

    async def try_execute_config(self, move_config: MoveConfig, willcasted: bool = False) -> bool | Tuple[bool, bool]:
        _dbg(f"[COND-DBG] try_execute_config: condition={move_config.condition}, move={move_config.move}")
        if move_config.condition is not None:
            if not await self.evaluate_condition(move_config.condition):
                return False

        if type(move_config.move) is list and type(move_config.target) is list:
            success = False
            willcasted = False
            for m, t in zip(move_config.move, move_config.target):
                resp = await self.try_execute_config(MoveConfig(m, t), willcasted=willcasted)
                if type(resp) is tuple:
                    success, willcasted = resp
                else:
                    success = resp
            return success
        if type(move_config.move.card) is DrawSpell:
            for i in range(move_config.move.card.draw_amount):
                card_count = await self.get_num_card_windows()
                if card_count == 7:
                    break
                if draw_windows := await self.client.root_window.get_windows_with_name("Draw"):
                    draw_window = draw_windows[0]
                    if await draw_window.is_control_grayed():
                        break
                    await self.draw_button()
                    while await self.get_num_card_windows() == card_count:
                        await asyncio.sleep(0.1)
                    self.cur_card_count += 1
                    await asyncio.sleep(self.config.cast_time*2)

            return True
        only_enchantable = move_config.move.enchant is not None
        is_template = isinstance(move_config.move.card, TemplateSpell)
        needs_req_met = is_template and SpellType.type_req_met in move_config.move.card.requirements
        gambit_clear_specs = (
            [r for r in move_config.move.card.requirements if isinstance(r, (GambitSpec, ClearSpec, EchoSpec))]
            if is_template else []
        )
        swap_specs = (
            [r for r in move_config.move.card.requirements if isinstance(r, SwapSpec)]
            if is_template else []
        )
        needs_post_filter = needs_req_met or bool(gambit_clear_specs) or bool(swap_specs)

        # When any post-selection filter is active we must iterate candidates
        # so a card whose filter-check fails can be skipped in favor of another
        # castable match (rather than failing the whole clause).
        if needs_post_filter:
            candidates = await self.try_get_spell(
                move_config.move.card, only_enchantable=only_enchantable, multi=True
            )
            if not candidates:
                _dbg(f"[MT-DBG] no candidates for {move_config.move.card}")
                return False
        else:
            single = await self.try_get_spell(move_config.move.card, only_enchantable=only_enchantable)
            if single is None:
                _dbg(f"[MT-DBG] cur_card is None for {move_config.move.card}")
                return False
            if single == "pass":
                await self.pass_button()
                return True
            candidates = [single]

        target = await self.try_get_config_target(move_config.target)

        if target == False:  # Wouldn't want a None to mess it up
            _dbg(f"[MT-DBG] target is False for {move_config.target}")
            return False

        ttype = move_config.target.target_type if move_config.target else None
        req_t = target[0] if isinstance(target, list) else target
        req_member = req_t if isinstance(req_t, CombatMember) else None

        cur_card = None
        for cand in candidates:
            # Card has single-target damage — only compatible with enemy/boss targeting
            if await card_requires_target_selection(cand):
                if ttype in (TargetType.type_aoe, TargetType.type_self, TargetType.type_ally):
                    _dbg(f"[MT-DBG] target_selection rejected: ttype={ttype}, card={await cand.name()}")
                    continue
            if needs_req_met and not await self.card_requirements_met(cand, req_member):
                continue
            # All declared gambit/clear specs must hold simultaneously.
            failed_spec = False
            for spec in gambit_clear_specs:
                if not await self.card_matches_gambit_or_clear(cand, req_member, spec):
                    failed_spec = True
                    break
            if failed_spec:
                continue
            for spec in swap_specs:
                if not await self.card_matches_swap(cand, spec):
                    failed_spec = True
                    break
            if failed_spec:
                continue
            cur_card = cand
            break

        if cur_card is None:
            if needs_post_filter:
                _dbg(f"[REQ-DBG] no candidate passed post-filters for {move_config.move.card}")
            return False

        # Multi-target spell — wrap single target in list for confirm button flow.
        # Use "enemies" / "allies" targets to select all, or select(...) for specific targets.
        is_mt = await card_is_multi_target(cur_card)
        _dbg(f"[MT-DBG] card={await cur_card.name()}, is_multi_target={is_mt}, target={target}, target_type={type(target).__name__}")
        if is_mt:
            if target is None:
                _dbg(f"[MT-DBG] multi-target but target is None")
                return False  # Multi-target needs explicit targets
            if isinstance(target, CombatMember):
                target = [target]  # Wrap so cast() uses list branch (clicks confirm)
                _dbg(f"[MT-DBG] wrapped single target in list")

        if cur_card == "willcast":
            if willcasted:
                return True
            spell_checkbox_windows = await self.client.root_window.get_windows_with_type("SpellCheckBox")

            wnd = ([x for x in spell_checkbox_windows if await x.name() == "PetCard"])[0]

            if await wnd.flags() - WindowFlags.disabled >= 0:
                return True

            card = CombatCard(self, wnd)
            if await card.is_castable():
                await card.cast(target)
                await asyncio.sleep(self.config.cast_time*2)
                return (True, True)
            return True

        if cur_card == "discard":
            if type(target) is list:
                for card in target:
                    combat_card = await self.try_get_spell(card, castable=False)
                    if combat_card is not None:
                        await self.disc_on_target(combat_card)
                        await asyncio.sleep(self.config.cast_time*2)
            else:
                combat_card = await self.try_get_spell(target, castable=False)
                if combat_card is not None:
                    await self.disc_on_target(combat_card)
                    await asyncio.sleep(self.config.cast_time*2)
            #discard_card = await self.try_get_spell(target, castable=False)
            return True

        fused = ""
        if only_enchantable and not await cur_card.is_enchanted():
            enchant_card = await self.try_get_spell(move_config.move.enchant, only_enchants=False, castable=False)
            if enchant_card != "none":
                if enchant_card is not None:
                    # Issue: 5. Casting wasn't that reliable
                    enchant_is_grayed = not await enchant_card.is_castable()
                    if enchant_is_grayed:
                        return False
                    previous_cards = await self.get_cards()
                    previous_card_names = Counter([await card.name() for card in previous_cards])
                    pre_enchant_count = len(await self.get_cards())
                    while len(await self.get_cards()) == pre_enchant_count:
                        await enchant_card.cast(cur_card, sleep_time=self.config.cast_time*2)
                        await asyncio.sleep(self.config.cast_time*2) # give it some time for card list to update

                    self.cur_card_count -= 1
                    new_cards = await self.get_cards()
                    new_card_names = Counter([await card.name() for card in new_cards])
                    diff = list(new_card_names - previous_card_names)
                    if diff:
                        cur_card = await self.try_get_spell(NamedSpell(name=diff[0], is_literal=True), only_enchantable=only_enchantable)
                        if move_config.move.second_enchant:
                            second_enchant_card = await self.try_get_spell(move_config.move.second_enchant, only_enchants=False)
                            if second_enchant_card != "none":
                                if second_enchant_card is not None:
                                    pre_enchant_count = len(await self.get_cards())
                                    while len(await self.get_cards()) == pre_enchant_count:
                                        await second_enchant_card.cast(cur_card, sleep_time=self.config.cast_time*2)
                                        await asyncio.sleep(self.config.cast_time*2) # give it some time for card list to update
                                    self.cur_card_count -= 1
                                
                                elif second_enchant_card is None and (isinstance(move_config.move.second_enchant, TemplateSpell) and not move_config.move.second_enchant.optional):
                                    return False

                        fused = diff[0]

                elif enchant_card is None and (isinstance(move_config.move.enchant, TemplateSpell) and not move_config.move.enchant.optional):
                    return False
                
                #elif enchant_card is None and enchant_is_grayed:
                #    return False

        to_cast = None
        if fused:
            to_cast = await self.try_get_spell(NamedSpell(name=fused, is_literal=True))
        elif needs_post_filter:
            # Use the cur_card we picked above — try_get_spell would return the
            # first template match, which may not be the one that passed our filters.
            to_cast = cur_card
        else:
            to_cast = await self.try_get_spell(move_config.move.card)
        if to_cast is None:
            return False  # this should not happen
        
        # Issue: 5. Casting wasn't that reliable
        try:
            while to_cast != None:
                try:
                    if isinstance(target, Spell):
                        card_count = await self.get_num_card_windows()
                        target = await self.try_get_spell(target, castable=False, multi=True, only_enchantable=True)
                        if target:
                            if type(target) is list:
                                for targ in target:
                                    if await targ.is_enchanted():
                                        is_enchant = False
                                        for e in await to_cast.get_spell_effects():
                                            if await e.effect_target() is EffectTarget.spell:
                                                is_enchant = True
                                                break
                                        if not is_enchant:
                                            target = targ
                                            break
                                    else:
                                        target = targ
                                        break
                                else:
                                    break
                            else:
                                if await target.is_enchanted():
                                    is_enchant = False
                                    for e in await to_cast.get_spell_effects():
                                        if await e.effect_target() is EffectTarget.spell:
                                            is_enchant = True
                                            break
                                    if is_enchant:
                                        break
                            await to_cast.cast(target, sleep_time=self.config.cast_time*2)
                            while await self.get_num_card_windows() == card_count:
                                await asyncio.sleep(0.1)
                            self.cur_card_count -= 1
                            await asyncio.sleep(self.config.cast_time) # give it some time for card list to update
                        break
                    await to_cast.cast(target, sleep_time=self.config.cast_time*2)
                    await asyncio.sleep(self.config.cast_time) # give it some time for card list to update
                    if fused:
                        to_cast = await self.try_get_spell(NamedSpell(name=fused, is_literal=True))
                    elif needs_post_filter:
                        # Don't loop another cast — the next template match may not
                        # satisfy our filters, and we've consumed the one that did.
                        to_cast = None
                    else:
                        to_cast = await self.try_get_spell(move_config.move.card)
                except ValueError:
                    break # Issue: 8
        except wizwalker.errors.WizWalkerMemoryError or ValueError:
            pass # Let it happen if it happens
        return True

    async def fail_turn(self):
        self.turn_adjust -= 1
        await self.pass_button()

    async def on_fizzle(self):
        self.turn_adjust -= 1

    async def handle_round(self):
        # try:
        #     await self.client.mouse_handler.activate_mouseless()
        # except wizwalker.errors.HookAlreadyActivated:
        #     pass
        async with self.client.mouse_handler:
            self.config.attach_combat(self) # For safety. Could probably also do this in handle_comba

            real_round = await self.round_number()
            _dbg_castable = await self.get_castable_cards()
            _dbg_names = [await c.name() for c in _dbg_castable]
            _dbg(f"[MT-DBG] castable cards: {_dbg_names}")
            await self._inspect_deck_once()
            self.cur_card_count = len(await self.get_cards()) + (await self.get_card_counts())[0]
                
            if not self.had_first_round:
                current_round = real_round - 1
                if current_round > 0:
                    self.turn_adjust -= current_round
            else:
                if self.cur_card_count >= self.prev_card_count and not self.was_pass:
                    await self.on_fizzle()
            self.was_pass = False
            current_round = (real_round - 1 + self.turn_adjust + self.rel_round_offset)
                        
            # Issue: #3. Need to make sure it's valid
            member: CombatMember = None
            try:
                member = await wizwalker.utils.maybe_wait_for_any_value_with_timeout(
                    self.get_client_member,
                    timeout=2.0
                )
            except wizwalker.errors.ExceptionalTimeout:
                # TODO: Maybe make this more dramatic
                await self.fail_turn() # This is quite catastrophic. Use default fail for now
            
            if member is not None:
                if await member.is_stunned():
                    await self.fail_turn()
                else:
                    round_config = await self.config.get_real_round(real_round)
                    if round_config is None:
                        round_config = await self.config.get_relative_round(current_round)
                    else:
                        self.rel_round_offset -= 1
                    if round_config is not None:
                        for p in round_config.priorities:  # go through rounds priorities
                            if await self.try_execute_config(p):
                                break  # we found a working priority and managed to cast it
                        else:
                            await self.pass_button()
                    else:  # Very bad. Probably using empty config
                        await self.config.handle_no_cards_given()

                self.had_first_round = True  # might go bad on throw
                self.prev_card_count = self.cur_card_count
