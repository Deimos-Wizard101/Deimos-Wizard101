from wizwalker import Client, utils
from wizwalker.combat import CombatCard, CombatMember
from wizwalker.memory.memory_objects.enums import EffectTarget, HangingDisposition, SpellEffects
from wizwalker.memory.memory_objects.spell_effect import DynamicSpellEffect
from wizwalker.extensions.wizsprinter import CombatConfigProvider
from wizwalker.extensions.wizsprinter.combat_backends.backend_base import BaseCombatBackend
from wizwalker.extensions.wizsprinter.combat_backends.combat_api import CombatConfig, Move, MoveConfig, NamedSpell, PriorityLine, TargetData, TargetType, SpellType, TemplateSpell
from wizwalker.extensions.wizsprinter.combat_backends.config_backend import get_sprinty_grammar, Lark, TreeToConfig
from wizwalker.extensions.wizsprinter import SprintyCombat
from typing import List, Dict, Tuple, Any, Optional, Set
from loguru import logger
# from wizwalker.client import Client

import re


default_config = 'Mass | "Detonate All 200 - Amulet" | Willcast @ enemy & Willcast @ boss & "Pet - Sharpened Blade" @ spell(any<blade>) & "Sharpened Blade - Amulet" @ spell(any<blade>) & Sharpened @ spell(any<blade>) & Sharpened @ spell(any<blade>) & "Potent Trap - Amulet" @ spell("Feint") & "Potent Trap - Tear" @ spell("Feint") & "Potent Trap - Tear" @ spell(any<trap>) & "Potent Trap - Amulet" @ spell(any<trap>) & Potent @ spell(any<trap>) & Potent @ spell(any<trap>) & any<mod_damage> @ spell(any<damage>) & any<mod_damage> @ spell(any<damage>) & any<blade> @ self | any<trap> @ boss | any<trap> @ enemy | any<aura> | any<global> | any<damage&aoe> @ aoe | any<damage> @ boss | any<damage> @ enemy | any<damage> @ enemies | ?(self.health < 25%) any<heal> @ self'
# "any<damage>[epic] @ enemy | any<damage>[colossal] @ enemy | any<damage>[gargantuan] @ enemy | any<damage>[monstrous] @ enemy | any<damage>[giant] @ enemy | any<damage>[strong] @ enemy"

_profile_option_pattern = re.compile(r"^\s*#\s*([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*$")
MYTH_LEVEL_12_PROFILE_NAME = "Myth Level 12 Questing"
MYTH_LEVEL_15_PROFILE_NAME = "Myth Level 15 Questing"
STORM_LEVEL_130_RUSHER_PROFILE_NAME = "Storm Level 130 Rusher"
MYTH_SCHOOL_ID = 2448141
STORM_SCHOOL_ID = 83375795
UNIVERSAL_SCHOOL_ID = 80289
MYTH_LEVEL_12_FINISHER_HEALTH = 150
MYTH_LEVEL_15_LOW_HEALTH = 150
MYTH_LEVEL_15_HIGH_HEALTH = 350
TROLL_PIP_COST = 2
CYCLOPS_PIP_COST = 3
UNREADABLE_COMBAT_VALUE = object()
MYTH_LEVEL_15_DAMAGE_ESTIMATES = {
    "Wand Hit": 75,
    "Blood Bat": 85,
    "Troll": 170,
    "Cyclops": 265,
}
MYTH_LEVEL_15_KILL_MARGIN = 1.10
TEMPEST_DAMAGE_PER_PIP = 80
EPIC_DAMAGE_BONUS = 300
STORM_LORD_DAMAGE = 690
STORM_LORD_PIP_COST = 7

MYTH_BLADE_EFFECT_TYPES = {
    SpellEffects.modify_outgoing_damage,
    SpellEffects.modify_outgoing_damage_flat,
}
MYTH_TRAP_EFFECT_TYPES = {
    SpellEffects.modify_incoming_damage,
    SpellEffects.modify_incoming_damage_flat,
    SpellEffects.modify_incoming_damage_over_time,
}
PRISM_EFFECT_TYPES = {
    SpellEffects.modify_incoming_damage_type,
    SpellEffects.modify_outgoing_damage_type,
}


def _parse_bool_option(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _parse_health_threshold(value: str):
    try:
        threshold = float(value.strip().rstrip("%"))
    except ValueError:
        return None

    if threshold > 1:
        threshold /= 100.0

    if threshold <= 0:
        return None

    return min(threshold, 1.0)


def _parse_float_option(value: str):
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return None


def _parse_int_option(value: str):
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


def parse_combat_profile_options(config_data: str) -> Dict[str, Any]:
    '''
    Reads Deimos-only profile options from comment lines in playstyle configs.
    The combat parser ignores these comments, so default combat behavior stays unchanged.
    '''
    profile_options: Dict[str, Any] = {}

    for line in config_data.splitlines():
        option_match = _profile_option_pattern.match(line)
        if option_match is None:
            continue

        key = option_match.group(1).strip().lower().replace("-", "_")
        value = option_match.group(2).strip()

        if key == "deimos_profile":
            profile_options["deimos_profile"] = value
        elif key == "scan_nearby_side_quests":
            profile_options["scan_nearby_side_quests"] = _parse_bool_option(value)
        elif key in {"health_wisp_threshold", "collect_health_wisp_at_or_below_percent"}:
            threshold = _parse_health_threshold(value)
            if threshold is not None:
                profile_options["health_wisp_threshold"] = threshold
        elif key == "collect_object_fallback_enabled":
            profile_options["collect_object_fallback_enabled"] = _parse_bool_option(value)
        elif key in {"collect_object_scan_radius", "collect_object_scan_timeout_seconds", "collect_object_scan_step_size"}:
            number_value = _parse_float_option(value)
            if number_value is not None and number_value > 0:
                profile_options[key] = number_value
        elif key == "collect_object_max_failed_attempts":
            number_value = _parse_int_option(value)
            if number_value is not None and number_value > 0:
                profile_options[key] = number_value
        elif key == "collect_object_interact_key":
            profile_options["collect_object_interact_key"] = value.strip().upper()

    return profile_options


def apply_combat_profile_options(client: Client, config_data: str):
    profile_options = parse_combat_profile_options(config_data)
    client.combat_profile_options = profile_options
    client.combat_profile_name = profile_options.get("deimos_profile", "")
    client.scan_nearby_side_quests = bool(profile_options.get("scan_nearby_side_quests", False))
    client.health_wisp_threshold = profile_options.get("health_wisp_threshold")
    client.collect_object_fallback_enabled = bool(profile_options.get("collect_object_fallback_enabled", False))
    client.collect_object_scan_radius = profile_options.get("collect_object_scan_radius")
    client.collect_object_scan_timeout_seconds = profile_options.get("collect_object_scan_timeout_seconds")
    client.collect_object_interact_key = profile_options.get("collect_object_interact_key", "X")
    client.collect_object_max_failed_attempts = profile_options.get("collect_object_max_failed_attempts")
    client.collect_object_scan_step_size = profile_options.get("collect_object_scan_step_size")


def is_myth_level_12_questing_profile(client: Client) -> bool:
    return getattr(client, "combat_profile_name", "").strip().casefold() == MYTH_LEVEL_12_PROFILE_NAME.casefold()


def is_myth_level_15_questing_profile(client: Client) -> bool:
    return getattr(client, "combat_profile_name", "").strip().casefold() == MYTH_LEVEL_15_PROFILE_NAME.casefold()


def is_storm_level_130_rusher_profile(client: Client) -> bool:
    return getattr(client, "combat_profile_name", "").strip().casefold() == STORM_LEVEL_130_RUSHER_PROFILE_NAME.casefold()


class StrCombatConfigProvider(CombatConfigProvider):
    '''
    Handles string-based combat configuration. The GUI handles files so this is modified to just use a string.
    '''
    def __init__(self, config_data: str = "", cast_time: float = 0.2):
        super(CombatConfigProvider, self).__init__(cast_time) #Bypass init function of parent
        self.filename = "Config"
        self.config: CombatConfig = self.parse_config(config_data)

    async def handle_no_cards_given(self):
        raise RuntimeError("Full config fail! Config might be empty or contains only explicit rounds. Consider adding a pass or something else.")

    def parse_config(self, file_contents) -> CombatConfig:
        grammar = get_sprinty_grammar()

        parser = Lark(grammar)
        tree = parser.parse(file_contents)
        return self._expand_config(TreeToConfig().transform(tree))


class MythLevel12QuestingCombatProvider(StrCombatConfigProvider):
    '''
    Profile-scoped combat backend for early Myth questing before Humongofrog and Orthrus.
    It keeps the default playstyle parser intact while adding checks the text format cannot express.
    '''
    def __init__(self, config_data: str = "", cast_time: float = 0.2):
        super().__init__(config_data, cast_time)

    async def get_real_round(self, r: int) -> Optional[PriorityLine]:
        return None

    async def get_relative_round(self, r: int) -> Optional[PriorityLine]:
        if self.combat is None:
            return await super().get_relative_round(r)

        try:
            return await self._build_priority_line()
        except Exception:
            fallback = await super().get_relative_round(r)
            return fallback if fallback is not None else PriorityLine([self._pass()])

    async def _build_priority_line(self) -> PriorityLine:
        caster = await self.combat.get_client_member()
        enemy, enemy_index, enemy_health = await self._select_enemy_target()
        if caster is None or enemy is None:
            return PriorityLine([self._pass()])

        enemy_school_id = await self._enemy_school_id(enemy)
        enemy_is_myth = enemy_school_id == MYTH_SCHOOL_ID
        prism_in_hand = await self._card_in_hand("Myth Prism")
        discard_prism = prism_in_hand and not enemy_is_myth
        pip_value = await self._pip_value(caster)
        target_has_myth_shield = await self._enemy_has_myth_shield(enemy)
        blood_bat_castable = await self._card_castable("Blood Bat")
        logger.debug(
            f'Myth Level 12 combat target enemy({enemy_index}) health={enemy_health}, '
            f'school_id={enemy_school_id}, myth_shield={target_has_myth_shield}, '
            f'blood_bat_castable={blood_bat_castable}, prism_in_hand={prism_in_hand}.'
        )

        actions: List[MoveConfig] = []

        if enemy_is_myth and prism_in_hand and not await self._enemy_has_myth_prism(enemy):
            actions.append(self._cast("Myth Prism", TargetType.type_enemy, enemy_index))

        if target_has_myth_shield:
            if blood_bat_castable:
                logger.debug(f'Myth Level 12 selecting Blood Bat to break Myth Shield on enemy({enemy_index}).')
                actions.append(self._hit("Blood Bat", enemy_index))
            else:
                logger.debug('Myth Level 12 detected Myth Shield but Blood Bat is not castable; continuing normal priorities.')

        if enemy_health <= MYTH_LEVEL_12_FINISHER_HEALTH:
            actions.extend(self._low_health_actions(pip_value, enemy_index))
        else:
            if not await self._caster_has_myth_blade(caster):
                actions.append(self._cast("Mythblade", TargetType.type_self))
            if not await self._enemy_has_myth_trap(enemy):
                actions.append(self._cast("Myth Trap", TargetType.type_enemy, enemy_index))
            if not await self._minion_active():
                actions.append(self._cast("Golem Minion", TargetType.type_self))
            actions.extend(self._high_health_attacks(pip_value, enemy_index))

        actions.append(self._pass())
        if discard_prism:
            actions = [self._with_myth_prism_discard(action) for action in actions]

        logger.debug(f'Myth Level 12 priority line: {self._debug_action_names(actions)}')
        return PriorityLine(actions)

    async def _select_enemy_target(self):
        enemies = await self._safe_call(self.combat.get_enemies, [])
        if not enemies:
            return None, 0, MYTH_LEVEL_12_FINISHER_HEALTH + 1

        readable_enemies = []
        for index, enemy in enumerate(enemies):
            health = await self._safe_call(enemy.health, None)
            if health is None:
                continue
            if health <= 0:
                continue
            readable_enemies.append((index, enemy, health))

        if not readable_enemies:
            enemy = enemies[0]
            return enemy, 0, await self._safe_call(enemy.health, MYTH_LEVEL_12_FINISHER_HEALTH + 1)

        low_health_enemies = [candidate for candidate in readable_enemies if candidate[2] <= MYTH_LEVEL_12_FINISHER_HEALTH]
        if low_health_enemies:
            index, enemy, health = min(low_health_enemies, key=lambda candidate: candidate[2])
            return enemy, index, health

        index, enemy, health = readable_enemies[0]
        return enemy, index, health

    def _low_health_actions(self, pip_value: int, target_index: int) -> List[MoveConfig]:
        actions = [
            self._hit("Blood Bat", target_index),
        ]

        if pip_value >= TROLL_PIP_COST:
            actions.append(self._hit("Troll", target_index))
        if pip_value >= CYCLOPS_PIP_COST:
            actions.append(self._hit("Cyclops", target_index))

        actions.append(self._template_hit([SpellType.type_damage], target_index, use_enchant=False))
        return actions

    def _high_health_attacks(self, pip_value: int, target_index: int) -> List[MoveConfig]:
        actions: List[MoveConfig] = []

        if pip_value >= TROLL_PIP_COST:
            actions.append(self._hit("Troll", target_index))
        if pip_value >= CYCLOPS_PIP_COST:
            actions.append(self._hit("Cyclops", target_index))

        return actions

    def _cast(self, spell_name: str, target_type: TargetType, target_index: int = None) -> MoveConfig:
        return MoveConfig(
            Move(NamedSpell(spell_name, True)),
            TargetData(target_type, target_index),
        )

    def _hit(self, spell_name: str, target_index: int) -> MoveConfig:
        return MoveConfig(
            Move(NamedSpell(spell_name, True), self._optional_damage_enchant()),
            TargetData(TargetType.type_enemy, target_index),
        )

    def _template_hit(self, requirements: List[SpellType], target_index: int, use_enchant: bool = True) -> MoveConfig:
        enchant = self._optional_damage_enchant() if use_enchant else None
        return MoveConfig(
            Move(TemplateSpell(requirements), enchant),
            TargetData(TargetType.type_enemy, target_index),
        )

    def _pass(self) -> MoveConfig:
        return MoveConfig(Move(NamedSpell("pass", True)))

    def _with_myth_prism_discard(self, action: MoveConfig) -> MoveConfig:
        return MoveConfig(
            [Move(NamedSpell("discard", True)), action.move],
            [TargetData(TargetType.type_spell, NamedSpell("Myth Prism", True)), action.target],
        )

    def _optional_damage_enchant(self) -> TemplateSpell:
        return TemplateSpell([SpellType.type_mod_damage], optional=True)

    async def _card_in_hand(self, spell_name: str) -> bool:
        try:
            return await self.combat.try_get_spell(NamedSpell(spell_name, True), castable=False) is not None
        except Exception:
            return False

    async def _card_castable(self, spell_name: str) -> bool:
        try:
            return await self.combat.try_get_spell(NamedSpell(spell_name, True), castable=True) is not None
        except Exception:
            return False

    async def _pip_value(self, caster: CombatMember) -> int:
        normal_pips = await self._safe_call(caster.normal_pips, 0)
        power_pips = await self._safe_call(caster.power_pips, 0)
        return int(normal_pips) + (int(power_pips) * 2)

    async def _enemy_school_id(self, enemy: CombatMember) -> Optional[int]:
        try:
            participant = await enemy.get_participant()
            return await participant.primary_magic_school_id()
        except Exception:
            return None

    async def _caster_has_myth_blade(self, caster: CombatMember) -> bool:
        return await self._has_school_hanging_effect(
            caster,
            MYTH_BLADE_EFFECT_TYPES,
            HangingDisposition.beneficial,
            MYTH_SCHOOL_ID,
        )

    async def _enemy_has_myth_trap(self, enemy: CombatMember) -> bool:
        return await self._has_school_hanging_effect(
            enemy,
            MYTH_TRAP_EFFECT_TYPES,
            HangingDisposition.harmful,
            MYTH_SCHOOL_ID,
        )

    async def _enemy_has_myth_shield(self, enemy: CombatMember) -> bool:
        effects = await self._hanging_effects(enemy)
        if effects is None:
            logger.debug('Myth questing could not read enemy wards/shields; Myth/Tower Shield detection unavailable.')
            return False

        readable_effects = []
        detected = False
        uncertain = False
        for effect in effects:
            effect_type = await self._safe_effect_value(effect.effect_type)
            disposition = await self._safe_effect_value(effect.disposition)
            effect_param = await self._safe_effect_value(effect.effect_param)
            damage_type = await self._safe_effect_value(effect.damage_type)
            readable_effects.append({
                "type": getattr(effect_type, "name", effect_type),
                "disposition": getattr(disposition, "name", disposition),
                "param": effect_param,
                "damage_type": damage_type,
            })

            if effect_type not in MYTH_TRAP_EFFECT_TYPES:
                continue
            if effect_param is UNREADABLE_COMBAT_VALUE:
                uncertain = True
                continue
            if effect_param >= 0:
                continue
            if not self._disposition_matches(disposition, HangingDisposition.beneficial):
                continue
            if damage_type is UNREADABLE_COMBAT_VALUE:
                uncertain = True
                detected = True
                continue
            if damage_type in {MYTH_SCHOOL_ID, UNIVERSAL_SCHOOL_ID}:
                detected = True

        logger.debug(f'Myth questing enemy ward/shield effects: {readable_effects}; myth_or_tower_shield_detected={detected}; uncertain={uncertain}.')
        return detected

    async def _enemy_has_myth_prism(self, enemy: CombatMember) -> bool:
        effects = await self._hanging_effects(enemy)
        if effects is None:
            return True

        for effect in effects:
            effect_type = await self._safe_effect_value(effect.effect_type)
            if effect_type not in PRISM_EFFECT_TYPES:
                continue

            disposition = await self._safe_effect_value(effect.disposition)
            if not self._disposition_matches(disposition, HangingDisposition.harmful):
                continue

            damage_type = await self._safe_effect_value(effect.damage_type)
            effect_param = await self._safe_effect_value(effect.effect_param)
            if damage_type is UNREADABLE_COMBAT_VALUE or effect_param is UNREADABLE_COMBAT_VALUE:
                return True
            if damage_type == MYTH_SCHOOL_ID or effect_param == STORM_SCHOOL_ID:
                return True

        return False

    async def _has_school_hanging_effect(
        self,
        member: CombatMember,
        effect_types: Set[SpellEffects],
        expected_disposition: HangingDisposition,
        school_id: int,
    ) -> bool:
        effects = await self._hanging_effects(member)
        if effects is None:
            return True

        for effect in effects:
            effect_type = await self._safe_effect_value(effect.effect_type)
            if effect_type not in effect_types:
                continue

            disposition = await self._safe_effect_value(effect.disposition)
            if not self._disposition_matches(disposition, expected_disposition):
                continue

            effect_param = await self._safe_effect_value(effect.effect_param)
            if effect_param is not UNREADABLE_COMBAT_VALUE and effect_param <= 0:
                continue

            damage_type = await self._safe_effect_value(effect.damage_type)
            if damage_type is UNREADABLE_COMBAT_VALUE:
                return True
            if damage_type == school_id:
                return True

        return False

    async def _hanging_effects(self, member: CombatMember) -> Optional[List[DynamicSpellEffect]]:
        try:
            participant = await member.get_participant()
            return list(await participant.hanging_effects())
        except Exception:
            return None

    def _disposition_matches(self, actual: Any, expected: HangingDisposition) -> bool:
        if actual is UNREADABLE_COMBAT_VALUE:
            return True
        return actual in {expected, HangingDisposition.both}

    async def _minion_active(self) -> bool:
        try:
            allies = await self.combat.get_allies()
            for ally in allies:
                if await ally.is_minion():
                    return True
            return False
        except Exception:
            return True

    async def _safe_call(self, callback, default):
        try:
            return await callback()
        except Exception:
            return default

    async def _safe_effect_value(self, callback):
        try:
            return await callback()
        except Exception:
            return UNREADABLE_COMBAT_VALUE

    def _debug_action_names(self, actions: List[MoveConfig]) -> List[str]:
        names = []
        for action in actions:
            moves = action.move if isinstance(action.move, list) else [action.move]
            move_names = []
            for move in moves:
                card = getattr(move, "card", None)
                if isinstance(card, TemplateSpell):
                    requirements = []
                    for requirement in card.requirements:
                        requirement_name = getattr(requirement, "name", repr(requirement))
                        if requirement_name.startswith("type_"):
                            requirement_name = requirement_name[5:]
                        requirements.append(requirement_name)
                    move_names.append(f'any<{"&".join(requirements)}>')
                else:
                    move_names.append(getattr(card, "name", repr(card)))
            names.append(" + ".join(move_names))
        return names


class MythLevel15QuestingCombatProvider(MythLevel12QuestingCombatProvider):
    '''
    Profile-scoped combat backend for level 15 Myth questing.
    This keeps the normal parser as fallback, but builds a combat-state-aware
    priority list so low-health enemies are killed before setup is considered.
    '''
    def __init__(self, config_data: str = "", cast_time: float = 0.2):
        super().__init__(config_data, cast_time)
        self._planned_setup_keys: Set[Tuple[str, int]] = set()

    async def _build_priority_line(self) -> PriorityLine:
        caster = await self.combat.get_client_member()
        enemy, enemy_index, enemy_health = await self._select_enemy_target()
        if caster is None or enemy is None:
            logger.debug('Myth Level 15 has no readable caster/enemy; passing.')
            return PriorityLine([self._pass()])

        enemy_max_health = await self._safe_call(enemy.max_health, None)
        enemy_school_id = await self._enemy_school_id(enemy)
        enemy_is_myth = enemy_school_id == MYTH_SCHOOL_ID
        pip_value = await self._pip_value(caster)
        hand_cards = await self._card_names(castable=False)
        castable_cards = await self._card_names(castable=True)
        normalized_hand_cards = [self._normalize_card_name(card_name) for card_name in hand_cards]
        normalized_castable_cards = [self._normalize_card_name(card_name) for card_name in castable_cards]
        card_state = await self._level_15_card_state(hand_cards, castable_cards)
        myth_blade_active = await self._caster_has_myth_blade_or_memory(caster)
        myth_trap_active = await self._enemy_has_myth_trap_or_memory(enemy, enemy_index)
        myth_prism_active = await self._enemy_has_myth_prism_or_memory(enemy, enemy_index)
        minion_active = await self._minion_active_or_memory()
        myth_shield_active = await self._enemy_has_myth_shield(enemy)
        has_any_damage = await self._any_damage_castable()
        discard_prism = card_state["Myth Prism"]["in_hand"] and not enemy_is_myth
        damage_multiplier, damage_multiplier_details = await self._level_15_damage_multiplier(
            caster,
            enemy,
            myth_shield_active,
            myth_blade_active,
            myth_trap_active,
        )
        context = (
            f'enemy({enemy_index}) hp={enemy_health}/{enemy_max_health}, school_id={enemy_school_id}, '
            f'pips={pip_value}, myth_shield_or_tower={myth_shield_active}, myth_trap={myth_trap_active}, '
            f'myth_prism={myth_prism_active}, mythblade={myth_blade_active}, minion={minion_active}, '
            f'raw_hand={hand_cards}, normalized_hand={normalized_hand_cards}, '
            f'raw_castable={castable_cards}, normalized_castable={normalized_castable_cards}, '
            f'card_state={card_state}, damage_multiplier={damage_multiplier}, '
            f'damage_multiplier_details={damage_multiplier_details}, any_damage_castable={has_any_damage}'
        )
        logger.debug(f'Myth Level 15 combat state: {context}.')

        actions: List[MoveConfig] = []
        skip_reasons: List[str] = []

        kill_action = self._first_level_15_kill_action(enemy_health, enemy_index, card_state, damage_multiplier)
        if kill_action is not None:
            self._remember_level_15_action(kill_action, enemy_index)
            actions.append(kill_action)
            logger.debug(f'Myth Level 15 selected emergency kill action: {self._debug_action_names([kill_action])}.')
            return self._level_15_priority(actions, discard_prism)
        skip_reasons.append('no preferred known damage spell was estimated to kill immediately')

        if myth_shield_active:
            if card_state["Blood Bat"]["castable"]:
                action = self._level_15_hit("Blood Bat", enemy_index, card_state)
                self._remember_level_15_action(action, enemy_index)
                actions.append(action)
                logger.debug('Myth Level 15 selected Blood Bat to break Myth/Tower/relevant shield before larger Myth hits.')
                return self._level_15_priority(actions, discard_prism)
            skip_reasons.append('enemy shield detected but Blood Bat was not castable')

        if enemy_is_myth:
            if card_state["Myth Prism"]["castable"] and not myth_prism_active:
                action = self._cast("Myth Prism", TargetType.type_enemy, enemy_index)
                self._remember_level_15_action(action, enemy_index)
                actions.append(action)
                logger.debug('Myth Level 15 selected Myth Prism because target is Myth and no prism is active.')
                return self._level_15_priority(actions, discard_prism)
            if myth_prism_active:
                skip_reasons.append('target is Myth but Myth Prism is already active')
            elif not card_state["Myth Prism"]["castable"]:
                skip_reasons.append('target is Myth but Myth Prism is not castable')
        elif card_state["Myth Prism"]["in_hand"]:
            skip_reasons.append('target is not Myth; Myth Prism is ignored so it cannot block a useful cast')

        if enemy_health <= MYTH_LEVEL_15_LOW_HEALTH:
            low_action = self._first_castable_named_hit(["Wand Hit", "Blood Bat", "Troll", "Cyclops"], enemy_index, card_state)
            if low_action is not None:
                self._remember_level_15_action(low_action, enemy_index)
                actions.append(low_action)
                logger.debug(f'Myth Level 15 selected low-health finisher: {self._debug_action_names([low_action])}.')
                return self._level_15_priority(actions, discard_prism)
            if has_any_damage:
                action = self._template_hit([SpellType.type_damage], enemy_index, use_enchant=False)
                actions.append(action)
                logger.debug('Myth Level 15 selected low-health any<damage> fallback.')
                return self._level_15_priority(actions, discard_prism)
            skip_reasons.append('enemy low HP but no castable damage spell was readable')

        if enemy_health <= MYTH_LEVEL_15_HIGH_HEALTH:
            medium_kill = self._first_level_15_kill_action(enemy_health, enemy_index, card_state, damage_multiplier, names=("Troll", "Cyclops"))
            if medium_kill is not None:
                self._remember_level_15_action(medium_kill, enemy_index)
                actions.append(medium_kill)
                logger.debug(f'Myth Level 15 selected medium-health killing hit: {self._debug_action_names([medium_kill])}.')
                return self._level_15_priority(actions, discard_prism)

            setup_action = self._first_level_15_setup_action(
                enemy_index,
                card_state,
                myth_blade_active,
                myth_trap_active,
                minion_active=False,
                allow_minion=False,
            )
            if setup_action is not None:
                self._remember_level_15_action(setup_action, enemy_index)
                actions.append(setup_action)
                logger.debug(f'Myth Level 15 selected medium-health setup: {self._debug_action_names([setup_action])}.')
                return self._level_15_priority(actions, discard_prism)
            skip_reasons.append('medium-health setup skipped because blade/trap were active or unavailable')

            useful_hit = self._best_castable_named_hit(["Troll", "Cyclops"], enemy_index, card_state, damage_multiplier)
            if useful_hit is not None:
                self._remember_level_15_action(useful_hit, enemy_index)
                actions.append(useful_hit)
                logger.debug(f'Myth Level 15 selected medium-health useful hit: {self._debug_action_names([useful_hit])}.')
                return self._level_15_priority(actions, discard_prism)
            if card_state["Blood Bat"]["castable"] and not card_state["Troll"]["castable"] and not card_state["Cyclops"]["castable"]:
                action = self._hit("Blood Bat", enemy_index)
                actions.append(action)
                logger.debug('Myth Level 15 selected Blood Bat because no better medium-health damage spell was castable.')
                return self._level_15_priority(actions, discard_prism)
            skip_reasons.append('medium-health preferred attacks unavailable')

        setup_action = self._first_level_15_setup_action(
            enemy_index,
            card_state,
            myth_blade_active,
            myth_trap_active,
            minion_active,
            allow_minion=True,
        )
        if setup_action is not None:
            self._remember_level_15_action(setup_action, enemy_index)
            actions.append(setup_action)
            logger.debug(f'Myth Level 15 selected high-health setup: {self._debug_action_names([setup_action])}.')
            return self._level_15_priority(actions, discard_prism)
        skip_reasons.append('high-health setup skipped because setup was active, remembered, unavailable, or not useful')

        useful_hit = self._best_castable_named_hit(["Troll", "Cyclops"], enemy_index, card_state, damage_multiplier)
        if useful_hit is not None:
            self._remember_level_15_action(useful_hit, enemy_index)
            actions.append(useful_hit)
            logger.debug(f'Myth Level 15 selected preferred damage after setup: {self._debug_action_names([useful_hit])}.')
            return self._level_15_priority(actions, discard_prism)
        skip_reasons.append('Troll/Cyclops not castable after setup checks')

        if card_state["Blood Bat"]["castable"]:
            action = self._level_15_hit("Blood Bat", enemy_index, card_state)
            actions.append(action)
            logger.debug('Myth Level 15 selected Blood Bat as final named-damage fallback.')
            return self._level_15_priority(actions, discard_prism)

        if has_any_damage:
            action = self._template_hit([SpellType.type_damage], enemy_index, use_enchant=False)
            actions.append(action)
            logger.debug('Myth Level 15 selected final no-timeout any<damage> fallback.')
            return self._level_15_priority(actions, discard_prism)

        late_setup = self._first_level_15_setup_action(
            enemy_index,
            card_state,
            myth_blade_active,
            myth_trap_active,
            minion_active,
            allow_minion=True,
            include_unpreferred=True,
        )
        if late_setup is not None:
            self._remember_level_15_action(late_setup, enemy_index)
            actions.append(late_setup)
            logger.debug(f'Myth Level 15 selected final setup fallback: {self._debug_action_names([late_setup])}.')
            return self._level_15_priority(actions, discard_prism)

        logger.debug(f'Myth Level 15 passing; no useful castable action found. Skip reasons: {skip_reasons}.')
        return self._level_15_priority([self._pass()], discard_prism)

    async def _level_15_card_state(self, hand_cards: List[str], castable_cards: List[str]) -> Dict[str, Dict[str, Any]]:
        spell_aliases = {
            "Blood Bat": {"bloodbat"},
            "Troll": {"troll"},
            "Cyclops": {"cyclops"},
            "Mythblade": {"mythblade"},
            "Myth Trap": {"mythtrap"},
            "Myth Prism": {"mythprism"},
            "Golem Minion": {"golemminion"},
        }
        state = {}
        for spell_name, aliases in spell_aliases.items():
            hand_match = self._first_card_name_match(hand_cards, aliases)
            castable_match = self._first_card_name_match(castable_cards, aliases)
            state[spell_name] = {
                "in_hand": hand_match is not None,
                "castable": castable_match is not None,
                "card_name": castable_match or hand_match or spell_name,
            }

        hand_wand = self._first_wand_damage_name(hand_cards)
        castable_wand = self._first_wand_damage_name(castable_cards)
        state["Wand Hit"] = {
            "in_hand": hand_wand is not None,
            "castable": castable_wand is not None,
            "card_name": castable_wand or hand_wand or "Wand Hit",
        }
        logger.debug(f'Myth Level 15 normalized card state: {state}.')
        return state

    def _first_level_15_kill_action(
        self,
        enemy_health: int,
        target_index: int,
        card_state: Dict[str, Dict[str, Any]],
        damage_multiplier: float,
        names: Tuple[str, ...] = ("Wand Hit", "Blood Bat", "Troll", "Cyclops"),
    ) -> Optional[MoveConfig]:
        kill_candidates = []
        for spell_name in names:
            if not card_state.get(spell_name, {}).get("castable", False):
                logger.debug(f'Myth Level 15 skipped {spell_name} as emergency kill: not castable.')
                continue
            estimated_damage = self._level_15_estimated_damage(spell_name, damage_multiplier)
            logger.debug(
                f'Myth Level 15 damage estimate: spell={spell_name}, '
                f'raw_card={card_state[spell_name].get("card_name")!r}, '
                f'estimated_damage={estimated_damage}, enemy_health={enemy_health}, '
                f'kills={estimated_damage >= enemy_health}.'
            )
            if estimated_damage >= enemy_health:
                kill_candidates.append((estimated_damage, spell_name))
                continue
            logger.debug(
                f'Myth Level 15 skipped {spell_name} as emergency kill: '
                f'estimated_damage={estimated_damage}, enemy_health={enemy_health}.'
            )

        if not kill_candidates:
            return None

        reliable_kills = [
            candidate for candidate in kill_candidates
            if candidate[0] >= enemy_health * MYTH_LEVEL_15_KILL_MARGIN
        ]
        selected_damage, selected_spell = min(reliable_kills or kill_candidates, key=lambda candidate: candidate[0])
        if not reliable_kills:
            selected_damage, selected_spell = max(kill_candidates, key=lambda candidate: candidate[0])
        logger.debug(
            f'Myth Level 15 kill candidates={kill_candidates}; '
            f'selected={selected_spell} estimated_damage={selected_damage}.'
        )
        return self._level_15_hit(selected_spell, target_index, card_state)

    def _first_castable_named_hit(
        self,
        spell_names: List[str],
        target_index: int,
        card_state: Dict[str, Dict[str, Any]],
    ) -> Optional[MoveConfig]:
        for spell_name in spell_names:
            if card_state.get(spell_name, {}).get("castable", False):
                return self._level_15_hit(spell_name, target_index, card_state)
            logger.debug(f'Myth Level 15 skipped {spell_name}: not castable.')
        return None

    def _best_castable_named_hit(
        self,
        spell_names: List[str],
        target_index: int,
        card_state: Dict[str, Dict[str, Any]],
        damage_multiplier: float,
    ) -> Optional[MoveConfig]:
        hit_candidates = []
        for spell_name in spell_names:
            if not card_state.get(spell_name, {}).get("castable", False):
                logger.debug(f'Myth Level 15 skipped {spell_name} as useful hit: not castable.')
                continue
            estimated_damage = self._level_15_estimated_damage(spell_name, damage_multiplier)
            hit_candidates.append((estimated_damage, spell_name))
            logger.debug(f'Myth Level 15 useful-hit estimate: spell={spell_name}, estimated_damage={estimated_damage}.')

        if not hit_candidates:
            return None

        selected_damage, selected_spell = max(hit_candidates, key=lambda candidate: candidate[0])
        logger.debug(
            f'Myth Level 15 useful-hit candidates={hit_candidates}; '
            f'selected={selected_spell} estimated_damage={selected_damage}.'
        )
        return self._level_15_hit(selected_spell, target_index, card_state)

    def _first_level_15_setup_action(
        self,
        target_index: int,
        card_state: Dict[str, Dict[str, Any]],
        myth_blade_active: bool,
        myth_trap_active: bool,
        minion_active: bool,
        allow_minion: bool,
        include_unpreferred: bool = False,
    ) -> Optional[MoveConfig]:
        if card_state["Mythblade"]["castable"] and not myth_blade_active:
            return self._cast("Mythblade", TargetType.type_self)
        logger.debug(
            f'Myth Level 15 skipped Mythblade setup: castable={card_state["Mythblade"]["castable"]}, '
            f'already_active_or_remembered={myth_blade_active}.'
        )

        if card_state["Myth Trap"]["castable"] and not myth_trap_active:
            return self._cast("Myth Trap", TargetType.type_enemy, target_index)
        logger.debug(
            f'Myth Level 15 skipped Myth Trap setup: castable={card_state["Myth Trap"]["castable"]}, '
            f'already_active_or_remembered={myth_trap_active}.'
        )

        if allow_minion:
            if card_state["Golem Minion"]["castable"] and not minion_active:
                return self._cast("Golem Minion", TargetType.type_self)
            logger.debug(
                f'Myth Level 15 skipped Golem Minion setup: castable={card_state["Golem Minion"]["castable"]}, '
                f'already_active_or_remembered={minion_active}.'
            )
        elif include_unpreferred:
            logger.debug('Myth Level 15 kept Golem Minion unavailable for this setup phase by policy.')

        return None

    def _level_15_estimated_damage(self, spell_name: str, damage_multiplier: float) -> int:
        damage = MYTH_LEVEL_15_DAMAGE_ESTIMATES.get(spell_name, 0)
        return int(damage * damage_multiplier)

    def _level_15_priority(self, actions: List[MoveConfig], discard_prism: bool) -> PriorityLine:
        if discard_prism:
            logger.debug(
                'Myth Level 15 did not generate a compound discard action for Myth Prism; '
                'compound discard+cast actions are disabled to avoid invalid priority lines.'
            )
        if not any(self._debug_action_names([action])[0] == "pass" for action in actions):
            actions.append(self._pass())
        action_names = self._debug_action_names(actions)
        logger.debug(f'Myth Level 15 priority line: {action_names}; parser_valid_single_action={self._priority_is_single_action(actions)}.')
        return PriorityLine(actions)

    def _level_15_hit(self, spell_name: str, target_index: int, card_state: Dict[str, Dict[str, Any]]) -> MoveConfig:
        raw_card_name = card_state.get(spell_name, {}).get("card_name", spell_name)
        return MoveConfig(
            Move(NamedSpell(raw_card_name, True), self._optional_damage_enchant()),
            TargetData(TargetType.type_enemy, target_index),
        )

    def _priority_is_single_action(self, actions: List[MoveConfig]) -> bool:
        for action in actions:
            moves = action.move if isinstance(action.move, list) else [action.move]
            if len(moves) > 1:
                return False
        return True

    def _normalize_card_name(self, card_name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", card_name.casefold())

    def _first_card_name_match(self, card_names: List[str], normalized_aliases: Set[str]) -> Optional[str]:
        for card_name in card_names:
            if self._normalize_card_name(card_name) in normalized_aliases:
                return card_name
        return None

    def _first_wand_damage_name(self, card_names: List[str]) -> Optional[str]:
        for card_name in card_names:
            normalized_name = self._normalize_card_name(card_name)
            if "wand" in normalized_name:
                return card_name
        return None

    async def _level_15_damage_multiplier(
        self,
        caster: CombatMember,
        enemy: CombatMember,
        shield_active: bool,
        myth_blade_active: bool,
        myth_trap_active: bool,
    ) -> Tuple[float, Dict[str, Any]]:
        blade_bonus = await self._level_15_school_damage_bonus(
            caster,
            MYTH_BLADE_EFFECT_TYPES,
            HangingDisposition.beneficial,
            MYTH_SCHOOL_ID,
        )
        trap_bonus = await self._level_15_school_damage_bonus(
            enemy,
            MYTH_TRAP_EFFECT_TYPES,
            HangingDisposition.harmful,
            MYTH_SCHOOL_ID,
        )
        if blade_bonus == 0.0 and myth_blade_active:
            blade_bonus = 0.35
        if trap_bonus == 0.0 and myth_trap_active:
            trap_bonus = 0.25
        shield_multiplier = 0.2 if shield_active else 1.0
        multiplier = max(0.0, (1.0 + blade_bonus) * (1.0 + trap_bonus) * shield_multiplier)
        details = {
            "blade_bonus": blade_bonus,
            "trap_bonus": trap_bonus,
            "shield_multiplier": shield_multiplier,
        }
        logger.debug(f'Myth Level 15 damage multiplier details: {details}; final_multiplier={multiplier}.')
        return multiplier, details

    async def _level_15_school_damage_bonus(
        self,
        member: CombatMember,
        effect_types: Set[SpellEffects],
        expected_disposition: HangingDisposition,
        school_id: int,
    ) -> float:
        effects = await self._hanging_effects(member)
        if effects is None:
            logger.debug('Myth Level 15 could not read hanging effects for damage bonus estimate; assuming no bonus.')
            return 0.0

        bonus = 0.0
        readable_effects = []
        for effect in effects:
            effect_type = await self._safe_effect_value(effect.effect_type)
            disposition = await self._safe_effect_value(effect.disposition)
            effect_param = await self._safe_effect_value(effect.effect_param)
            damage_type = await self._safe_effect_value(effect.damage_type)
            readable_effects.append({
                "type": getattr(effect_type, "name", effect_type),
                "disposition": getattr(disposition, "name", disposition),
                "param": effect_param,
                "damage_type": damage_type,
            })

            if effect_type not in effect_types:
                continue
            if not self._disposition_matches(disposition, expected_disposition):
                continue
            if effect_param is UNREADABLE_COMBAT_VALUE or effect_param <= 0:
                continue
            if damage_type is UNREADABLE_COMBAT_VALUE or damage_type in {school_id, UNIVERSAL_SCHOOL_ID}:
                bonus += float(effect_param) / 100.0

        logger.debug(f'Myth Level 15 damage bonus effects read: {readable_effects}; matched_bonus={bonus}.')
        return bonus

    async def _any_damage_castable(self) -> bool:
        try:
            return await self.combat.try_get_spell(TemplateSpell([SpellType.type_damage]), castable=True) is not None
        except Exception:
            logger.debug('Myth Level 15 could not determine whether any<damage> is castable.')
            return False

    async def _card_names(self, castable: bool) -> List[str]:
        try:
            cards = await self.combat.get_castable_cards() if castable else await self.combat.get_cards()
        except Exception:
            return []

        names = []
        for card in cards:
            try:
                names.append(await card.name())
            except Exception:
                names.append("<unreadable>")
        return names

    async def _caster_has_myth_blade_or_memory(self, caster: CombatMember) -> bool:
        if ("Mythblade", 0) in self._planned_setup_keys:
            return True
        return await self._caster_has_myth_blade(caster)

    async def _enemy_has_myth_trap_or_memory(self, enemy: CombatMember, target_index: int) -> bool:
        if ("Myth Trap", target_index) in self._planned_setup_keys:
            return True
        return await self._enemy_has_myth_trap(enemy)

    async def _enemy_has_myth_prism_or_memory(self, enemy: CombatMember, target_index: int) -> bool:
        if ("Myth Prism", target_index) in self._planned_setup_keys:
            return True
        return await self._enemy_has_myth_prism(enemy)

    async def _minion_active_or_memory(self) -> bool:
        if ("Golem Minion", 0) in self._planned_setup_keys:
            return True
        return await self._minion_active()

    def _remember_level_15_action(self, action: MoveConfig, target_index: int):
        action_name = self._debug_action_names([action])[0]
        if "Mythblade" in action_name:
            self._planned_setup_keys.add(("Mythblade", 0))
        elif "Myth Trap" in action_name:
            self._planned_setup_keys.add(("Myth Trap", target_index))
        elif "Myth Prism" in action_name:
            self._planned_setup_keys.add(("Myth Prism", target_index))
        elif "Golem Minion" in action_name:
            self._planned_setup_keys.add(("Golem Minion", 0))


class CarriedSupportCombatProvider(StrCombatConfigProvider):
    '''
    Carry Follow-only combat backend for the carried quester.
    It supports the configured hitter and never falls back to unrelated attacks.
    '''
    SUPPORT_PRIORITY = ("Feint", "Elemental Blade", "Dark Tribute", "Curse")

    def __init__(self, hitter_owner_id: Optional[int], hitter_label: str = "hitter", cast_time: float = 0.2):
        super().__init__("pass", cast_time)
        self.hitter_owner_id = hitter_owner_id
        self.hitter_label = hitter_label
        self._planned_actions: Dict[Tuple[str, int], int] = {}

    async def get_real_round(self, r: int) -> Optional[PriorityLine]:
        return None

    async def get_relative_round(self, r: int) -> Optional[PriorityLine]:
        if self.combat is None:
            return PriorityLine([self._pass()])

        try:
            return await self._build_support_priority(r)
        except Exception:
            logger.exception('Carried support combat decision failed; passing safely.')
            return PriorityLine([self._pass()])

    async def _build_support_priority(self, round_number: int) -> PriorityLine:
        if self.hitter_owner_id is None:
            logger.debug('Carried support passing: configured hitter owner ID is unavailable.')
            return PriorityLine([self._pass()])

        hitter, hitter_ally_index, ally_state = await self._find_hitter_ally()
        enemy_state = await self._enemy_state()
        castable_cards = await self._castable_support_cards()
        logger.debug(
            f'Carried support state: round={round_number}, hitter={self.hitter_label}, '
            f'hitter_owner_id={self.hitter_owner_id}, hitter_ally_index={hitter_ally_index}, '
            f'allies={ally_state}, enemies={self._readable_enemy_state(enemy_state)}, '
            f'castable={list(castable_cards)}, hitter_selected_target=unavailable.'
        )

        if hitter is None or hitter_ally_index is None:
            logger.debug('Carried support passing: configured hitter is not an ally in this combat.')
            return PriorityLine([self._pass()])

        living_enemies = [enemy for enemy in enemy_state if enemy['health'] > 0]
        bosses = [enemy for enemy in living_enemies if enemy['is_boss']]
        best_boss = max(bosses, key=lambda enemy: enemy['health'], default=None)
        best_enemy = max(living_enemies, key=lambda enemy: enemy['health'], default=None)
        if len(bosses) > 1:
            logger.debug(
                f'Carried support found multiple bosses; p2 selected target is unavailable, '
                f'using highest-health boss enemy({best_boss["index"]}) health={best_boss["health"]}.'
            )

        candidates = []
        if best_boss is not None and "Feint" in castable_cards:
            candidates.append(("Feint", castable_cards["Feint"], best_boss['member'], best_boss['index'], TargetType.type_enemy))
        elif "Feint" in castable_cards:
            logger.debug('Carried support skipped Feint: no living boss exists; Feint is boss-only.')

        if "Elemental Blade" in castable_cards:
            candidates.append(("Elemental Blade", castable_cards["Elemental Blade"], hitter, hitter_ally_index, TargetType.type_ally))

        if "Dark Tribute" in castable_cards:
            candidates.append(("Dark Tribute", castable_cards["Dark Tribute"], hitter, hitter_ally_index, TargetType.type_ally))

        curse_target = best_boss or best_enemy
        if "Curse" in castable_cards and curse_target is not None:
            candidates.append(("Curse", castable_cards["Curse"], curse_target['member'], curse_target['index'], TargetType.type_enemy))

        for spell_name, card, target_member, target_index, target_type in candidates:
            target_owner_id = await self._safe_call(target_member.owner_id, target_index)
            duplicate, duplicate_reason = await self._support_effect_already_present(
                spell_name,
                card,
                target_member,
                int(target_owner_id),
                round_number,
            )
            if duplicate:
                logger.debug(
                    f'Carried support skipped {spell_name} on {target_type.name}({target_index}): '
                    f'{duplicate_reason}.'
                )
                continue

            self._planned_actions[(spell_name, int(target_owner_id))] = round_number
            logger.info(
                f'Carried support selected {spell_name} on {target_type.name}({target_index}); '
                f'priority={self.SUPPORT_PRIORITY}, target_owner_id={target_owner_id}.'
            )
            action = MoveConfig(
                Move(NamedSpell(await card.name(), True)),
                TargetData(target_type, target_index),
            )
            return PriorityLine([action, self._pass()])

        logger.debug('Carried support passing: no useful non-duplicate support spell is castable.')
        return PriorityLine([self._pass()])

    async def _find_hitter_ally(self):
        allies = await self._safe_call(self.combat.get_allies, [])
        ally_state = []
        for index, ally in enumerate(allies):
            owner_id = await self._safe_call(ally.owner_id, None)
            name = await self._safe_call(ally.name, '<unreadable>')
            health = await self._safe_call(ally.health, 0)
            ally_state.append({'index': index, 'owner_id': owner_id, 'name': name, 'health': health})
            if owner_id == self.hitter_owner_id:
                return ally, index, ally_state
        return None, None, ally_state

    async def _enemy_state(self) -> List[Dict[str, Any]]:
        enemies = await self._safe_call(self.combat.get_enemies, [])
        state = []
        for index, enemy in enumerate(enemies):
            state.append({
                'index': index,
                'member': enemy,
                'owner_id': await self._safe_call(enemy.owner_id, index),
                'name': await self._safe_call(enemy.name, '<unreadable>'),
                'health': await self._safe_call(enemy.health, 0),
                'is_boss': bool(await self._safe_call(enemy.is_boss, False)),
            })
        return state

    def _readable_enemy_state(self, enemy_state: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {key: value for key, value in enemy.items() if key != 'member'}
            for enemy in enemy_state
        ]

    async def _castable_support_cards(self) -> Dict[str, CombatCard]:
        cards = await self._safe_call(self.combat.get_castable_cards, [])
        wanted = {self._normalize_name(name): name for name in self.SUPPORT_PRIORITY}
        matches = {}
        for card in cards:
            card_name = await self._safe_call(card.name, '')
            canonical_name = wanted.get(self._normalize_name(card_name))
            if canonical_name is not None and canonical_name not in matches:
                matches[canonical_name] = card
        return matches

    async def _support_effect_already_present(
        self,
        spell_name: str,
        card: CombatCard,
        target_member: CombatMember,
        target_owner_id: int,
        round_number: int,
    ) -> Tuple[bool, str]:
        action_key = (spell_name, target_owner_id)
        planned_round = self._planned_actions.get(action_key)
        card_template_id = await self._card_template_id(card)
        effects = await self._hanging_effects(target_member)

        if card_template_id is not None and effects is not None:
            for effect in effects:
                effect_template_id = await self._safe_call(effect.spell_template_id, None)
                if effect_template_id == card_template_id:
                    return True, f'active matching effect template {card_template_id} detected'

            if planned_round is not None and round_number - planned_round <= 1:
                return True, f'cast was selected in round {planned_round}; waiting for combat state to settle'
            return False, 'no matching active effect detected'

        if planned_round is not None:
            return True, f'duplicate detection is unavailable; safely remembering round {planned_round} selection'

        logger.debug(
            f'Carried support duplicate detection uncertain for {spell_name}: '
            f'card_template_id={card_template_id}, hanging_effects_readable={effects is not None}.'
        )
        return False, 'duplicate detection unavailable before first cast'

    async def _card_template_id(self, card: CombatCard) -> Optional[int]:
        try:
            graphical_spell = await card.get_graphical_spell()
            return await graphical_spell.template_id()
        except Exception:
            return None

    async def _hanging_effects(self, member: CombatMember) -> Optional[List[DynamicSpellEffect]]:
        try:
            participant = await member.get_participant()
            return list(await participant.hanging_effects())
        except Exception:
            return None

    async def _safe_call(self, callback, default):
        try:
            return await callback()
        except Exception:
            return default

    def _normalize_name(self, value: str) -> str:
        return re.sub(r'[^a-z0-9]', '', value.casefold())

    def _pass(self) -> MoveConfig:
        return MoveConfig(Move(NamedSpell("pass", True)))


class StormLevel130RusherCombatProvider(MythLevel15QuestingCombatProvider):
    '''
    Profile-scoped combat backend for a level 130 Storm carry/rusher.
    It prefers Epic Tempest, then Epic Storm Lord, then wand/damage fallback.
    '''
    def __init__(self, config_data: str = "", cast_time: float = 0.2):
        super().__init__(config_data, cast_time)

    async def _build_priority_line(self) -> PriorityLine:
        caster = await self.combat.get_client_member()
        enemies = await self._safe_call(self.combat.get_enemies, [])
        enemy_infos = await self._storm_enemy_infos(enemies)
        hand_cards = await self._card_names(castable=False)
        castable_cards = await self._card_names(castable=True)
        normalized_hand = [self._normalize_card_name(card_name) for card_name in hand_cards]
        normalized_castable = [self._normalize_card_name(card_name) for card_name in castable_cards]
        effective_pips = await self._pip_value(caster) if caster is not None else 0
        card_state = await self._storm_card_state(hand_cards, castable_cards)
        target = TargetData(TargetType.type_enemies)
        logger.debug(
            f'Storm Level 130 Rusher state: round=relative, enemy_count={len(enemy_infos)}, '
            f'enemies={enemy_infos}, raw_hand={hand_cards}, normalized_hand={normalized_hand}, '
            f'raw_castable={castable_cards}, normalized_castable={normalized_castable}, '
            f'effective_storm_pips={effective_pips}, card_state={card_state}, '
            f'target=enemies because Tempest/Storm Lord are AoE spells. '
            f'Effective pip value uses normal_pips + power_pips*2; school-pip specifics are not separately exposed here.'
        )

        action, reason = self._storm_select_action(card_state, effective_pips, enemy_infos, target)
        if action is None:
            logger.debug(f'Storm Level 130 Rusher passing: {reason}.')
            return self._storm_priority([self._pass()], fallback_used=True, reason=reason)

        logger.debug(f'Storm Level 130 Rusher final selected action: {self._debug_action_names([action])}; reason={reason}.')
        return self._storm_priority([action], fallback_used=reason.startswith("fallback"), reason=reason)

    def _storm_select_action(
        self,
        card_state: Dict[str, Dict[str, Any]],
        effective_pips: int,
        enemy_infos: List[Dict[str, Any]],
        aoe_target: TargetData,
    ) -> Tuple[Optional[MoveConfig], str]:
        tempest_estimate = self._storm_damage_estimate("Tempest", effective_pips, epic_applied=True)
        storm_lord_estimate = self._storm_damage_estimate("Storm Lord", effective_pips, epic_applied=True)
        unenchanted_tempest_estimate = self._storm_damage_estimate("Tempest", effective_pips, epic_applied=False)
        enemies_low_for_tempest = self._storm_all_enemies_killable(enemy_infos, unenchanted_tempest_estimate["final_estimated_damage"])

        self._log_storm_candidate("Tempest", card_state["Tempest"], tempest_estimate, effective_pips)
        self._log_storm_candidate("Storm Lord", card_state["Storm Lord"], storm_lord_estimate, effective_pips)
        self._log_storm_candidate("Unenchanted Tempest", card_state["Tempest"], unenchanted_tempest_estimate, effective_pips)

        if card_state["Epic Tempest"]["castable"]:
            return self._storm_named_aoe(card_state["Epic Tempest"]["card_name"], aoe_target), "Epic-enchanted Tempest already castable"

        if card_state["Tempest"]["castable"] and card_state["Epic"]["castable"]:
            return self._storm_named_aoe(card_state["Tempest"]["card_name"], aoe_target, enchant_name=card_state["Epic"]["card_name"]), "Tempest and Epic available; enchanting Tempest"

        if card_state["Tempest"]["castable"] and card_state["Tempest"]["enchanted"]:
            return self._storm_named_aoe(card_state["Tempest"]["card_name"], aoe_target), "already-enchanted Tempest castable"

        if card_state["Epic Storm Lord"]["castable"] and effective_pips >= STORM_LORD_PIP_COST:
            return self._storm_named_aoe(card_state["Epic Storm Lord"]["card_name"], aoe_target), "Epic-enchanted Storm Lord castable with enough pips"

        if card_state["Storm Lord"]["castable"] and card_state["Epic"]["castable"] and effective_pips >= STORM_LORD_PIP_COST:
            return self._storm_named_aoe(card_state["Storm Lord"]["card_name"], aoe_target, enchant_name=card_state["Epic"]["card_name"]), "Storm Lord and Epic available with enough pips"

        if card_state["Storm Lord"]["castable"] and card_state["Storm Lord"]["enchanted"] and effective_pips >= STORM_LORD_PIP_COST:
            return self._storm_named_aoe(card_state["Storm Lord"]["card_name"], aoe_target), "already-enchanted Storm Lord castable with enough pips"

        if card_state["Tempest"]["castable"] and not card_state["Epic"]["in_hand"] and enemies_low_for_tempest:
            return self._storm_named_aoe(card_state["Tempest"]["card_name"], aoe_target), "fallback unenchanted Tempest because Epic is missing and estimate kills"

        if card_state["Wand Hit"]["castable"]:
            return self._storm_single_enemy_hit(card_state["Wand Hit"]["card_name"]), "fallback wand hit while building pips or missing preferred AoE"

        if card_state["Tempest"]["castable"]:
            return self._storm_named_aoe(card_state["Tempest"]["card_name"], aoe_target), "fallback unenchanted Tempest to avoid timing out"

        if card_state["Storm AoE"]["castable"]:
            return MoveConfig(Move(TemplateSpell([SpellType.type_damage, SpellType.type_aoe])), aoe_target), "fallback any castable Storm/AoE damage template"

        if card_state["Any Damage"]["castable"]:
            return MoveConfig(Move(TemplateSpell([SpellType.type_damage])), TargetData(TargetType.type_enemy, 0)), "fallback any castable damage spell"

        return None, "no Tempest, Storm Lord, wand, AoE damage, or generic damage card was castable"

    async def _storm_card_state(self, hand_cards: List[str], castable_cards: List[str]) -> Dict[str, Dict[str, Any]]:
        state = {
            "Tempest": self._storm_named_state("Tempest", {"tempest"}, hand_cards, castable_cards, allow_contains=True),
            "Epic Tempest": self._storm_named_state("Epic Tempest", {"epictempest", "tempestepic"}, hand_cards, castable_cards, allow_contains=True),
            "Storm Lord": self._storm_named_state("Storm Lord", {"stormlord"}, hand_cards, castable_cards, allow_contains=True),
            "Epic Storm Lord": self._storm_named_state("Epic Storm Lord", {"epicstormlord", "stormlordepic"}, hand_cards, castable_cards, allow_contains=True),
            "Epic": self._storm_named_state("Epic", {"epic"}, hand_cards, castable_cards),
        }
        state["Tempest"]["enchanted"] = await self._storm_card_is_enchanted(state["Tempest"]["card_name"], state["Tempest"]["castable"])
        state["Storm Lord"]["enchanted"] = await self._storm_card_is_enchanted(state["Storm Lord"]["card_name"], state["Storm Lord"]["castable"])

        hand_wand = self._first_wand_damage_name(hand_cards)
        castable_wand = self._first_wand_damage_name(castable_cards)
        state["Wand Hit"] = {
            "in_hand": hand_wand is not None,
            "castable": castable_wand is not None,
            "card_name": castable_wand or hand_wand or "Wand Hit",
            "normalized": self._normalize_card_name(castable_wand or hand_wand or "Wand Hit"),
            "enchanted": False,
        }
        state["Storm AoE"] = {
            "in_hand": False,
            "castable": await self._storm_template_castable([SpellType.type_damage, SpellType.type_aoe]),
            "card_name": "any<damage&aoe>",
            "normalized": "anydamageaoe",
            "enchanted": False,
        }
        state["Any Damage"] = {
            "in_hand": False,
            "castable": await self._storm_template_castable([SpellType.type_damage]),
            "card_name": "any<damage>",
            "normalized": "anydamage",
            "enchanted": False,
        }
        logger.debug(f'Storm Level 130 Rusher normalized card state: {state}.')
        return state

    def _storm_named_state(self, label: str, aliases: Set[str], hand_cards: List[str], castable_cards: List[str], allow_contains: bool = False) -> Dict[str, Any]:
        hand_match = self._storm_first_card_name_match(hand_cards, aliases, allow_contains=allow_contains)
        castable_match = self._storm_first_card_name_match(castable_cards, aliases, allow_contains=allow_contains)
        card_name = castable_match or hand_match or label
        return {
            "in_hand": hand_match is not None,
            "castable": castable_match is not None,
            "card_name": card_name,
            "normalized": self._normalize_card_name(card_name),
            "enchanted": False,
        }

    def _storm_first_card_name_match(self, card_names: List[str], normalized_aliases: Set[str], allow_contains: bool = False) -> Optional[str]:
        for card_name in card_names:
            normalized_name = self._normalize_card_name(card_name)
            if normalized_name in normalized_aliases:
                return card_name
            if allow_contains and any(alias in normalized_name for alias in normalized_aliases):
                return card_name
        return None

    async def _storm_card_is_enchanted(self, card_name: str, castable: bool) -> bool:
        if not castable:
            return False
        try:
            card = await self.combat.try_get_spell(NamedSpell(card_name, True), castable=True)
            if card is None or isinstance(card, str):
                return False
            return bool(await card.is_enchanted())
        except Exception:
            logger.debug(f'Storm Level 130 Rusher could not read enchant state for {card_name!r}; assuming not already enchanted.')
            return False

    async def _storm_template_castable(self, requirements: List[SpellType]) -> bool:
        try:
            return await self.combat.try_get_spell(TemplateSpell(requirements), castable=True) is not None
        except Exception:
            return False

    async def _storm_enemy_infos(self, enemies: List[CombatMember]) -> List[Dict[str, Any]]:
        infos = []
        for index, enemy in enumerate(enemies):
            health = await self._safe_call(enemy.health, None)
            max_health = await self._safe_call(enemy.max_health, None)
            school_id = await self._enemy_school_id(enemy)
            infos.append({
                "index": index,
                "health": health,
                "max_health": max_health,
                "school_id": school_id,
            })
        return infos

    def _storm_damage_estimate(self, spell_name: str, effective_pips: int, epic_applied: bool) -> Dict[str, Any]:
        if spell_name == "Tempest":
            pip_cost = "X"
            base_damage = TEMPEST_DAMAGE_PER_PIP * max(0, effective_pips)
        elif spell_name == "Storm Lord":
            pip_cost = STORM_LORD_PIP_COST
            base_damage = STORM_LORD_DAMAGE
        else:
            pip_cost = None
            base_damage = 0

        epic_bonus = EPIC_DAMAGE_BONUS if epic_applied else 0
        final_damage = base_damage + epic_bonus
        return {
            "spell_name": spell_name,
            "pip_cost": pip_cost,
            "effective_pips": effective_pips,
            "base_spell_damage": base_damage,
            "epic_bonus": epic_bonus,
            "outgoing_damage_multiplier": "not read by this rusher profile",
            "storm_blade_or_aura_multiplier": "not read by this rusher profile",
            "enemy_resist_or_ward_multiplier": "not read by this rusher profile",
            "final_estimated_damage": final_damage,
        }

    def _storm_all_enemies_killable(self, enemy_infos: List[Dict[str, Any]], estimated_damage: int) -> bool:
        readable_healths = [enemy["health"] for enemy in enemy_infos if enemy.get("health") is not None and enemy.get("health") > 0]
        return bool(readable_healths) and all(estimated_damage >= health for health in readable_healths)

    def _log_storm_candidate(self, label: str, state: Dict[str, Any], estimate: Dict[str, Any], effective_pips: int):
        logger.debug(
            f'Storm Level 130 Rusher damage candidate: label={label}, raw_card={state.get("card_name")!r}, '
            f'normalized={state.get("normalized")!r}, castable={state.get("castable")}, '
            f'enchanted={state.get("enchanted")}, epic_applied={estimate["epic_bonus"] > 0}, '
            f'pip_cost={estimate["pip_cost"]}, effective_pips={effective_pips}, '
            f'base_spell_damage={estimate["base_spell_damage"]}, epic_bonus={estimate["epic_bonus"]}, '
            f'outgoing_damage_multiplier={estimate["outgoing_damage_multiplier"]}, '
            f'storm_blade_or_aura_multiplier={estimate["storm_blade_or_aura_multiplier"]}, '
            f'enemy_resist_or_ward_multiplier={estimate["enemy_resist_or_ward_multiplier"]}, '
            f'final_estimated_damage={estimate["final_estimated_damage"]}.'
        )

    def _storm_named_aoe(self, card_name: str, target: TargetData, enchant_name: str = None) -> MoveConfig:
        enchant = NamedSpell(enchant_name, True) if enchant_name else None
        return MoveConfig(Move(NamedSpell(card_name, True), enchant), target)

    def _storm_single_enemy_hit(self, card_name: str) -> MoveConfig:
        return MoveConfig(Move(NamedSpell(card_name, True)), TargetData(TargetType.type_enemy, 0))

    def _storm_priority(self, actions: List[MoveConfig], fallback_used: bool, reason: str) -> PriorityLine:
        if not any(self._debug_action_names([action])[0] == "pass" for action in actions):
            actions.append(self._pass())
        action_names = self._debug_action_names(actions)
        logger.debug(
            f'Storm Level 130 Rusher priority line: {action_names}; fallback_used={fallback_used}; '
            f'parser_valid_single_action={self._priority_is_single_action(actions)}; reason={reason}.'
        )
        return PriorityLine(actions)


def combat_config_provider_for_client(client: Client) -> BaseCombatBackend:
    if is_storm_level_130_rusher_profile(client):
        return StormLevel130RusherCombatProvider(client.combat_config)

    if is_myth_level_15_questing_profile(client):
        return MythLevel15QuestingCombatProvider(client.combat_config)

    if is_myth_level_12_questing_profile(client):
        return MythLevel12QuestingCombatProvider(client.combat_config)

    return StrCombatConfigProvider(client.combat_config)



def delegate_combat_configs(input_data: str, fallback_clients: int = 1, line_seperator: str = "\n") -> Dict[int, str]:
    '''
    Handles turning a raw string of file content into a dict of client combat configs.

    Args:
    - input_data (str): File content to use
    - fallback_clients(int): In the event of no clients specified, use the
    - line_seperator (str): Symbol or string that seperates lines of the file, newline by default
    '''

    config_lines = input_data.split(line_seperator)
    client_configs: Dict[int, str] = {}

    #Match number in "###pX", where X is a number. This determines the client index. This also strips all whitespace.
    pattern = re.compile(r'###\s*p\s*(\d+)')
    client_to_match = -1
    local_configs: List[str] = []

    for i, line in enumerate(config_lines):
        client_match = re.search(pattern, line)
        if client_match is not None:
            if client_to_match != -1:
                client_configs[client_to_match] = line_seperator.join(local_configs)
            client_to_match = int(client_match.group(1)) - 1
            local_configs.clear()
            continue

        local_configs.append(line)

    #If no client was ever specified, just assign entire config to all clients
    if client_to_match == -1:
        for i in range(fallback_clients):
            client_configs[i] = line_seperator.join(config_lines)

    else:
        client_configs[client_to_match] = line_seperator.join(local_configs)

    return client_configs
