import asyncio
from wizwalker.extensions.scripting.utils import _maybe_get_named_window
from wizwalker import ClientHandler, MemoryReadError, ReadingEnumFailed
from wizwalker.combat import CombatHandler, CombatCard, CombatMember
from wizwalker.memory.memory_objects.spell_effect import DynamicSpellEffect
from wizwalker import Client, utils
from wizwalker.memory.memory_objects.window import Window
from wizwalker.memory.memory_objects.enums import SpellEffects, EffectTarget, DuelPhase, WindowFlags
import math
import time
from loguru import logger
from wizwalker import Primitive

from src.deimoslang import parser
from wizwalker.utils import maybe_wait_for_any_value_with_timeout
# Credits to Major for inspiration 
school_ids = {0: 2343174, 1: 72777, 2: 83375795, 3: 2448141, 4: 2330892, 5: 78318724, 6: 1027491821, 7: 2625203, 8: 78483, 9: 2504141, 10: 663550619, 11: 1429009101, 12: 1488274711, 13: 1760873841, 14: 806477568, 15: 931528087}
school_list_ids = {index: i for i, index in school_ids.items()}
school_id_list = list(school_ids.values())
opposite_school_ids = {72777: 2343174, 2330892: 78318724, 2343174: 72777, 2448141: 83375795, 78318724: 2330892, 83375795: 2448141}


DAMAGE_EFFECTS = [
    SpellEffects.damage,
    SpellEffects.damage_no_crit,
    SpellEffects.damage_over_time,
    SpellEffects.damage_per_total_pip_power,
    SpellEffects.max_health_damage,
    SpellEffects.steal_health
]
DAMAGE_ENCHANT_EFFECTS = [
    SpellEffects.modify_card_damage,
    SpellEffects.modify_card_accuracy,
    SpellEffects.modify_card_armor_piercing, 
    SpellEffects.modify_card_damage_by_rank,
    SpellEffects.collect_essence
]
STRICT_DAMAGE_ENCHANT_EFFECTS = [
    SpellEffects.modify_card_damage,
    SpellEffects.modify_card_damage_by_rank
]
HEALING_EFFECTS = [
    SpellEffects.heal,
    SpellEffects.heal_over_time,
    SpellEffects.heal_percent,
    SpellEffects.heal_by_ward,
    SpellEffects.max_health_heal
]
TRAP_ENCHANT_EFFECTS = [
    SpellEffects.modify_card_incoming_damage, 
    SpellEffects.protect_card_harmful,
]
CHARM_ENCHANT_EFFECTS = [
    SpellEffects.modify_card_outgoing_damage, 
    SpellEffects.protect_card_beneficial
]
FRIENDLY_TARGETS = [
    EffectTarget.friendly_single, 
    EffectTarget.friendly_team, 
    EffectTarget.friendly_team_all_at_once
]
ENEMY_TARGETS = [
    EffectTarget.enemy_single, 
    EffectTarget.enemy_team, 
    EffectTarget.enemy_team_all_at_once
]
DAMAGE_AURA_GLOBAL_EFFECTS = [
    SpellEffects.modify_outgoing_damage, 
    SpellEffects.modify_outgoing_armor_piercing
]
AURA_GLOBAL_TARGETS = [
    EffectTarget.self, 
    EffectTarget.target_global
]
AURA_GLOBAL_EFFECTS = [
    SpellEffects.pip_conversion, 
    SpellEffects.power_pip_conversion, 
    SpellEffects.modify_power_pip_chance, 
    SpellEffects.modify_outgoing_armor_piercing, 
    SpellEffects.modify_outgoing_heal, 
    SpellEffects.modify_accuracy
]
CHARM_EFFECTS = [
    SpellEffects.modify_outgoing_damage,
    SpellEffects.modify_accuracy,
    SpellEffects.dispel
]
NONE_TARGETS = [
    EffectTarget.self, 
    EffectTarget.enemy_team, 
    EffectTarget.enemy_team_all_at_once, 
    EffectTarget.target_global, 
    EffectTarget.friendly_team, 
    EffectTarget.friendly_team_all_at_once
]
DAMAGE_AOE_TARGETS = [
    EffectTarget.enemy_team,
    EffectTarget.enemy_team_all_at_once
]
HEAL_ENCHANT_EFFECTS = [
    SpellEffects.modify_card_heal
]

async def time_check(coro):
    timestamp = time.time()
    res = await coro()
    logger.debug(f"{coro.__name__} {time.time() - timestamp} seconds")
    return res

async def read_spell_effect(spell: CombatCard):
    spell_types = []
    for effect in await spell.get_spell_effects():
        type_name = await effect.maybe_read_type_name()
        if "random" in type_name.lower() or "variable" in type_name.lower():
            subeffects = await effect.maybe_effect_list()
            for sub in subeffects:
                spell_types.append(await sub.effect_type())

        else:
            spell_types.append(await effect.effect_type())

    return spell_types

async def read_spell_target(spell: CombatCard):
    spell_targets = []
    for effect in await spell.get_spell_effects():
        type_name = await effect.maybe_read_type_name()
        if "random" in type_name.lower() or "variable" in type_name.lower():
            subeffects = await effect.maybe_effect_list()
            for sub in subeffects:
                spell_targets.append(await sub.effect_target())

        else:
            spell_targets.append(await effect.effect_target())

    return spell_targets

class Sunshine(CombatHandler):
    def __init__(self, client, clients: list[Client] = None):
        self.client: Client = client
        self._spell_check_boxes = None
        self.clients = clients
    
    async def handle_combat(self):
        """
        Handles an entire combat interaction
        """
        while await self.in_combat():
            await self.wait_for_planning_phase()
            try:
                if await self.client.duel.duel_phase() != DuelPhase.planning:
                    break
            except (ReadingEnumFailed, MemoryReadError):
                break
            round_number = await self.round_number()
            await asyncio.sleep(0.2) # make sure game manages to display UI in time
            # TODO: handle this taking longer than planning timer time
            await time_check(self.handle_round)
            await self.wait_until_next_round(round_number)

        self._spell_check_boxes = None

    async def assign_stats(self):
        '''Assign client-specific stats and member/participant objects and stats'''
        self.members = await self.get_members()
        self.client_member = None
        self.member_participants = {}
        for m in self.members:
            if await m.is_client():
                self.client_member = m
            self.member_participants[m] = await m.get_participant()
        self.client_participant = await self.client_member.get_participant()
        self.client_school_id = await self.client_participant.primary_magic_school_id()
        self.client_team_id = await self.client_participant.team_id()

        # Assign lists of ally members and enemy members
        self.allies = []
        self.mobs = []
        for member in self.members:
            member_id = await self.member_participants[member].team_id()
            if member_id == self.client_team_id:
                self.allies.append(member)
            else:
                self.mobs.append(member)

        # assign combat member stat dictionaries and such
        self.member_stats = {}
        self.member_resistances = {}
        self.member_flat_resistances = {}
        self.member_damages = {}
        self.member_flat_damages = {}
        self.member_hanging_effects = {}
        self.member_school_ids = {}
        self.member_pierce = {}
        self.member_aura_effects = {}
        self.member_shadow_effects = {}
        self.member_pips = {}
        self.member_power_pips = {}
        self.member_shadow_pips = {}
        self.member_critical_ratings = {}
        self.member_block_ratings = {}
        self.member_names = {}
        self.member_balance_pips = {}
        self.member_fire_pips = {}
        self.member_ice_pips = {}
        self.member_life_pips = {}
        self.member_death_pips = {}
        self.member_storm_pips = {}
        self.member_myth_pips = {}
        for m in self.members:
            self.member_school_ids[m] = await self.member_participants[m].primary_magic_school_id()
            self.member_stats[m] = await m.get_stats()
            # calculate actual resistances/damages/pierces/criticals/blocks for this combat member
            m_pierce = await self.member_stats[m].ap_bonus_percent()
            m_damages = await self.member_stats[m].dmg_bonus_percent()
            m_flat_damages = await self.member_stats[m].dmg_bonus_flat()
            m_universal_pierce = float(await self.member_stats[m].ap_bonus_percent_all())
            m_universal_damage = float(await self.member_stats[m].dmg_bonus_percent_all())
            m_universal_flat_damage = float(await self.member_stats[m].dmg_bonus_flat_all())
            self.member_pierce[m] = [r + m_universal_pierce for r in m_pierce]
            self.member_damages[m] = [r + m_universal_damage for r in m_damages]
            self.member_flat_damages[m] = [r + m_universal_flat_damage for r in m_flat_damages]
            m_resistances = await self.member_stats[m].dmg_reduce_percent()
            m_universal_resistance = float(await self.member_stats[m].dmg_reduce_percent_all())
            self.member_resistances[m] = [r + m_universal_resistance for r in m_resistances]
            m_flat_resistances = await self.member_stats[m].dmg_reduce_flat()
            m_universal_flat_resistance = float(await self.member_stats[m].dmg_reduce_flat_all())
            self.member_flat_resistances[m] = [r + m_universal_flat_resistance for r in m_flat_resistances]
            m_critical_ratings = await self.member_stats[m].critical_hit_rating_by_school()
            m_universal_critical = await self.member_stats[m].critical_hit_rating_all()
            self.member_critical_ratings[m] = [r + m_universal_critical for r in m_critical_ratings]
            m_block_ratings = await self.member_stats[m].block_rating_by_school()
            m_universal_block = await self.member_stats[m].block_rating_all()
            self.member_block_ratings[m] = [r + m_universal_block for r in m_block_ratings]
            # get hanging effects for this combat member
            self.member_hanging_effects[m] = await self.member_participants[m].hanging_effects()
            self.member_aura_effects[m] = await self.member_participants[m].aura_effects()
            self.member_shadow_effects[m] = await self.member_participants[m].shadow_spell_effects()
            # get member pips
            self.member_pips[m] = await m.normal_pips()
            self.member_power_pips[m] = await m.power_pips()
            self.member_shadow_pips[m] = await m.shadow_pips()
            part = await m.get_participant()
            pip_count = await part.pip_count()
            self.member_balance_pips[m] = await pip_count.balance_pips()
            self.member_fire_pips[m] = await pip_count.fire_pips()
            self.member_ice_pips[m] = await pip_count.ice_pips()
            self.member_life_pips[m] = await pip_count.life_pips()
            self.member_death_pips[m] = await pip_count.death_pips()
            self.member_storm_pips[m] = await pip_count.storm_pips()
            self.member_myth_pips[m] = await pip_count.myth_pips()
            
            # assigns members name
            self.member_names[m] = await m.name()

        # assigns mobs health values in a dictionary & selects highest health mob as target. 
        self.mob_healths = {}
        self.damage_potential_to_self = {}
        self.selected_enemy = None
        for m in self.mobs:
            self.mob_healths[m] = await m.health()
        self.selected_enemy: CombatMember = max(self.mob_healths, key = lambda h: self.mob_healths[h])
    
    async def read_spell_effect(self, spell: CombatCard):
        spell_types = []
        for effect in await spell.get_spell_effects():
            type_name = await effect.maybe_read_type_name()
            if "random" in type_name.lower() or "variable" in type_name.lower():
                subeffects = await effect.maybe_effect_list()
                for sub in subeffects:
                    spell_types.append(await sub.effect_type())

            else:
                spell_types.append(await effect.effect_type())

        return spell_types

    async def get_card_by_id(self, id: int):
        cards = await self.get_cards()
        for c in cards:
            if await c.spell_id() == id:
                return c
    
    async def idle_check(self):
        try:
            if window := await _maybe_get_named_window(self.client.root_window, "rightButton"):
                await self.client.mouse_handler.click_window(window)
                return True
        except ValueError:
            return False
        return False
    
    async def forever_idle_check(self):
        while True:
            await self.idle_check()
            await asyncio.sleep(1)
    
    async def handle_round(self):
        self.cast = False
        await self.assign_stats()
        self.combat_resolver = await self.client.duel.combat_resolver()
        await self.handle_enchants()
        await self.effect_enchant_ID()

        if not self.cast:
            card = await self.handle_card_selection()
            await self.handle_card_casting(card)

    async def card_casting(self, card: CombatCard = None): # type: ignore
        if card:
            target = None
            final_targets = await read_spell_target(card)
            if EffectTarget.enemy_single in final_targets:
                target = self.selected_enemy
            if EffectTarget.friendly_single in final_targets:
                    target = self.client_member
            if target:
                logger.debug(f"{self.member_names[self.client_member]} casting {await card.display_name()} at {self.member_names[target]}")
            else:
                logger.debug(f"{self.member_names[self.client_member]} casting {await card.display_name()}")
            async with self.client.mouse_handler:
                await card.cast(target, sleep_time=0.25)
        else:
            await self.pass_button()
    
    async def handle_card_casting(self, card: CombatCard = None):
        await self.card_casting(card)
        await asyncio.sleep(3)
        # handle if card miss clicked
        if await self.client.duel.duel_phase() == DuelPhase.planning:
            if window := await _maybe_get_named_window(self.client.root_window, "WaitingForOthers"):
                window: Window
                if not WindowFlags.visible in await window.flags():
                    logger.debug("card miss clicked recasting")
                    await self.card_casting(card)
        while await self.client.duel.duel_phase() == DuelPhase.planning:
            await asyncio.sleep(1)

    async def handle_card_selection(self) -> CombatCard:
        async def get_school_template_name(member: CombatMember):
            part = await member.get_participant()
            school_id = await part.primary_magic_school_id()
            return await self.client.cache_handler.get_template_name(school_id)
        to_cast = None
        to_cast_value = 0

        for card in self.cards:

            if not await card.is_castable() or await card.spell_id() in self.all_enchants:
                continue
            if "PetPower" in await card.name():
                async with self.client.mouse_handler:
                    await card.cast(self.selected_enemy)
                continue

            card_value = 0
            effect_types = await read_spell_effect(card)
            effect_targets = await read_spell_target(card)

            # Heals
            if (await self.client_member.health() / await self.client_member.max_health()) < 0.4:
                if any(effects in effect_types for effects in HEALING_EFFECTS):
                    card_value += 20

            # Prisms
            if self.selected_enemy:
                if (SpellEffects.modify_incoming_damage_type in effect_types) and (await get_school_template_name(self.selected_enemy) == await get_school_template_name(self.client_member)):
                    card_value += 11
                    if await self.is_spell_in_hanging_effect(card, self.selected_enemy):
                        if card_value > 0:
                            card_value = card_value//2

            # Mass Traps
            if (SpellEffects.modify_incoming_damage in effect_types) and any(effects in effect_targets for effects in DAMAGE_AOE_TARGETS):
                card_value += 10
                if await self.is_spell_in_hanging_effect(card, self.selected_enemy):
                    if card_value > 0:
                        card_value = card_value//2
            # Traps
            if self.selected_enemy:
                if (SpellEffects.modify_incoming_damage in effect_types) and any(effects in effect_targets for effects in ENEMY_TARGETS):
                    card_value += 9
                    if await self.is_spell_in_hanging_effect(card, self.selected_enemy):
                        if card_value > 0:
                            card_value = card_value//2

            # Globals
            if SpellEffects.modify_outgoing_damage in effect_types and EffectTarget.target_global in effect_targets:
                card_value += 8

            # Blades
            if (SpellEffects.modify_outgoing_damage in effect_types) and (any(effects in effect_targets for effects in FRIENDLY_TARGETS)):
                card_value += 7

            # Auras
            if SpellEffects.modify_outgoing_damage in effect_types and EffectTarget.self in effect_targets:
                if not self.member_aura_effects[self.client_member]:
                    card_value += 7
                else:
                    card_value -= 10
            
            # Reshuffle
            if SpellEffects.reshuffle in effect_types:
                if len(self.cards) <= 5:
                    damage_effect_in_deck: bool = False
                    for _card in self.cards:
                        if not await _card.is_castable() or await _card.spell_id() in self.all_enchants:
                            continue
                        _effect_types = await read_spell_effect(_card)
                        logger.debug(_effect_types)
                        logger.debug(f"{any(effects in _effect_types for effects in DAMAGE_EFFECTS)}")
                        if any(effects in _effect_types for effects in DAMAGE_EFFECTS):
                            damage_effect_in_deck = True
                            break
                    if damage_effect_in_deck == False:
                        to_cast = card
                        return to_cast
            # Damage
            if any(effects in effect_types for effects in DAMAGE_EFFECTS):
                if any(effects in effect_targets for effects in DAMAGE_AOE_TARGETS):
                    card_value += 4

                elif any(effects in effect_types for effects in DAMAGE_EFFECTS):
                    card_value += 5

                if SpellEffects.steal_health in effect_types:
                    card_value += 1
                #attempts to overide spell selection logic   

                if await self.will_kill(card): 
                    # card_value += 20
                    logger.debug("Damage Calc Overide")
                    return card
            # card is already casted 
            
            g_spell = await card.get_graphical_spell()
            regular_rank = await g_spell.read_value_from_offset(176 + 72, Primitive.uint8)
            
            # if card already casted on self, put lower weight
            if await self.is_spell_in_hanging_effect(card, self.client_member):
                if card_value > 0:
                    card_value = card_value//2
            
            # if card is enchanted, give it more value than unenchanted
            if await card.is_enchanted():
                card_value += 1
            
            if regular_rank == 0:
                card_value += 1
            # logger.debug(card_value, await card.display_name())
            if card_value > to_cast_value:
                to_cast_value = card_value
                to_cast = card

        return to_cast
    
    async def will_kill(self, card: CombatCard, enchant: CombatCard = None) -> bool:

        kill_counter = 0
        effect_targets = await read_spell_target(card)
        for target in self.mobs:
            target_health = self.mob_healths[target]
            damage = await self.calculate_damage(target, card, enchant)
            if damage >= target_health:
                kill_counter = kill_counter + 1
        #aoe damage
        if any(effects in effect_targets for effects in DAMAGE_AOE_TARGETS):
            if self.client.kill_minions_first: # a bool that checks in config if we should kill minions first
                if kill_counter / len(self.mobs) >= 0.5:
                    return True
            else:
                if kill_counter / len(self.mobs) == 1:
                    return True
        else:
            #single target damage
            if kill_counter / len(self.mobs) == 1:
                    return True
    async def calculate_damage(self, target: CombatMember, card: CombatCard, enchant: CombatCard = None) -> float:
        """
        Calculates damage from a given card, on a specific target combat member.

        Args:
            target: The combat member of the target
            card: a damage card
            enchant_card: a damage enchant
        """

        damage = await self.average_effect_param(card)

        if enchant:
            damage += await self.average_effect_param(enchant)

        final_damage = await self.calculate_damage_from_base(self.client_member, target, damage, card=card)

        return final_damage
    
    async def calculate_damage_from_base(self, caster: CombatMember, target: CombatMember, damage: float, card: CombatCard = None) -> float:
        """
        Calculates damage from a given base damage, from a specific caster onto a specific target combat member.

        Args:
            caster: Combat member of the desired caster
            target: Combat member of the desired caster
            damage: The spell's base damage (enchant added)
            card: Optional card input for exact calculation
        """
        caster_level = await self.member_stats[caster].reference_level()

        caster_damages = self.member_damages[caster]
        caster_flat_damages = self.member_flat_damages[caster]

        caster_hanging_effects = self.member_hanging_effects[caster]
        caster_hanging_effects += self.member_aura_effects[caster]
        caster_hanging_effects += self.member_shadow_effects[caster]
        if self.combat_resolver:  # Globals
            global_effect = await self.combat_resolver.global_effect()
            if global_effect is not None:
                caster_hanging_effects.append(global_effect)

        if card:
            card_graphical_spell = await card.get_graphical_spell()
            card_school = await card_graphical_spell.magic_school_id()
        else:
            card_school = self.member_school_ids[caster]

        target_resistances = self.member_resistances[target]
        target_flat_resistances = self.member_flat_resistances[target]

        target_hanging_effects = self.member_hanging_effects[target]
        target_hanging_effects += self.member_aura_effects[target]
        target_hanging_effects += self.member_shadow_effects[target]

        caster_pierce_values = self.member_pierce[caster]

        caster_crit_ratings = self.member_critical_ratings[caster]
        caster_crit_rating = caster_crit_ratings[school_list_ids[card_school]]

        target_block_ratings = self.member_critical_ratings[target]
        target_block_rating = target_block_ratings[school_list_ids[card_school]]


        # assign params and types and such for every hanging effect so we only have to read these values once per turn
        total_hanging_effects = caster_hanging_effects + target_hanging_effects
        effect_params = {}
        effect_types = {}
        effect_schools = {}
        effect_templates = {}
        effect_enchant_templates = {}
        effect_atrs = {}
        if total_hanging_effects:
            for effect in total_hanging_effects:
                effect_params[effect] = await effect.effect_param()
                effect_types[effect] = await effect.effect_type()
                effect_schools[effect] = await effect.damage_type()
                effect_templates[effect] = await effect.spell_template_id()
                effect_enchant_templates[effect] = await effect.enchantment_spell_template_id()
                effect_atrs[effect] = (effect_templates[effect], effect_enchant_templates[effect], effect_schools[effect], effect_types[effect])


        # remove duplicate effects from caster hanging effects list
        if caster_hanging_effects:
            checked_effect_atrs = []
            for effect in caster_hanging_effects.copy():
                if not effect_atrs[effect] in checked_effect_atrs:
                    checked_effect_atrs.append(effect_atrs[effect])
                else:
                    caster_hanging_effects.reverse()
                    caster_hanging_effects.remove(effect)
                    caster_hanging_effects.reverse()


        # remove duplicate effects from target hanging effects list
        if target_hanging_effects:
            checked_effect_atrs = []
            for effect in target_hanging_effects.copy():
                if not effect_atrs[effect] in checked_effect_atrs:
                    checked_effect_atrs.append(effect_atrs[effect])
                else:
                    target_hanging_effects.reverse()
                    target_hanging_effects.remove(effect)
                    target_hanging_effects.reverse()


        # redo the total effects list
        total_hanging_effects = target_hanging_effects + caster_hanging_effects


        # get relevant damage %, with damage limit
        caster_damage = caster_damages[school_list_ids[card_school]]
        caster_damage_percent = caster_damage * 100
        # Get max limit, read k and read n values from the duel object
        l = await self.client.duel.damage_limit()
        k0 = await self.client.duel.d_k0()
        n0 = await self.client.duel.d_n0()

        if caster_damage > (k0 + n0) / 100:
            limit = float(l) * 100

            # Calculate k, thank you charlied134 and Major
            if k0 != 0:
                k = math.log(limit / (limit - k0)) / k0
            else:
                k = 1 / limit

            # Calculate n, thank you charlied134 and Major
            n = math.log(1 - (k0 + n0) / limit) + k * (k0 + n0)

            caster_damage = l - l * math.e ** (-1 * k * caster_damage_percent + n)

        caster_damage += 1
        caster_damage_percent = caster_damage * 100

        # get relevant flat damage
        caster_flat_damage = caster_flat_damages[school_list_ids[card_school]]

        # get relevant pierce value
        caster_pierce = caster_pierce_values[school_list_ids[card_school]]

        # apply percentage damage
        damage *= caster_damage

        # apply flat damage
        damage += caster_flat_damage

        # calculates critical multiplier and chance
        if caster_crit_rating > 0:
            if caster_level > 100:
                caster_level = 100
            crit_damage_multiplier = (2 - ((target_block_rating)/((caster_crit_rating / 3) + target_block_rating)))
            client_school_critical = (0.03 * caster_level * caster_crit_rating)
            mob_block = (3 * caster_crit_rating + target_block_rating)
            crit_chance = client_school_critical / mob_block
            # applying the crit multiplier if the chance is above a certain threshold
            if crit_chance >= 0.85:
                damage *= crit_damage_multiplier

        # outgoing hanging effects (caster)
        if caster_hanging_effects:
            for effect in caster_hanging_effects:
                # only consider effects that matches the school or are universal
                if effect_schools[effect] == card_school or effect_schools[effect] == 80289:
                    match effect_types[effect]:
                        case SpellEffects.modify_outgoing_damage:
                            damage *= (effect_params[effect] / 100) + 1

                        case SpellEffects.modify_outgoing_damage_flat:
                            damage += effect_params[effect]

                        case SpellEffects.modify_outgoing_armor_piercing:
                            caster_pierce += effect_params[effect]

                        case SpellEffects.modify_outgoing_damage_type:
                            if card_school in opposite_school_ids:
                                card_school = opposite_school_ids[effect_schools[effect]]

                        case _:
                            pass

        # incoming hanging effects (target)
        if target_hanging_effects:
            for effect in target_hanging_effects:
                if effect_schools[effect] == card_school or effect_schools[effect] == 80289:
                    match effect_types[effect]:
                        # traps/shields, and pierce handling
                        case SpellEffects.modify_incoming_damage:
                            ward_param = effect_params[effect]
                            if ward_param < 0:
                                ward_param += caster_pierce
                                caster_pierce += effect_params[effect]
                                if ward_param > 0:
                                    ward_param = 0
                                if caster_pierce < 0:
                                    caster_pierce = 0
                            damage *= (ward_param / 100) + 1

                        case SpellEffects.intercept:
                            damage *= (effect_params[effect] / 100) + 1

                        case SpellEffects.modify_incoming_damage_flat:
                            damage += effect_params[effect]

                        case SpellEffects.absorb_damage:
                            damage += effect_params[effect]

                        case SpellEffects.modify_incoming_armor_piercing:
                            caster_pierce += effect_params[effect]
                        # prism handling
                        case SpellEffects.modify_incoming_damage_type:
                            if card_school in opposite_school_ids:
                                card_school = opposite_school_ids[effect_schools[effect]]

                        case _:
                            pass

        # get school relevant target resist
        target_resist = target_resistances[school_list_ids[card_school]]

        # get school relevant target flat resist
        target_flat_resist = target_flat_resistances[school_list_ids[card_school]]

        # apply flat resist
        damage -= target_flat_resist

        # apply resist, accounting for pierce and potential boost
        if target_resist > 0:
            target_resist -= caster_pierce
            if target_resist <= 0:
                target_resist = 1
            else:
                target_resist = 1 - target_resist
        else:
            target_resist = abs(target_resist) + 1

        damage *= target_resist

        return damage

    async def average_effect_param(self, card: CombatCard, compared_effects : list[SpellEffects] = DAMAGE_EFFECTS):
        subeffect_params = []
        effect_params = []

        client_pips = (self.member_pips[self.client_member] +
        (self.member_power_pips[self.client_member] * 2) +
        (self.member_balance_pips[self.client_member] * 2) +
        (self.member_fire_pips[self.client_member] * 2) +
        (self.member_ice_pips[self.client_member] * 2) +
        (self.member_life_pips[self.client_member] * 2) +
        (self.member_death_pips[self.client_member] * 2) +
        (self.member_storm_pips[self.client_member] * 2) +
        (self.member_myth_pips[self.client_member] * 2))

        for effect in await card.get_spell_effects():
            type_name = await effect.maybe_read_type_name()

            if "random" in type_name.lower() or "variable" in type_name.lower():
                subeffects = await effect.maybe_effect_list()

                for i, subeffect in enumerate(subeffects):
                    subeffect_type = await subeffect.effect_type()

                    if subeffect_type in compared_effects:
                        if len(subeffects) == 14:
                            if i == (client_pips - 1):
                                subeffect_params.append(await subeffect.effect_param())
                        else:
                            subeffect_params.append(await subeffect.effect_param())

                if subeffect_params:
                    total = 0
                    for effect_param in subeffect_params:
                        total += effect_param

                    return (total / len(subeffect_params))

            else:

                effect_type = await effect.effect_type()

                if effect_type in compared_effects:
                    effect_params.append(await effect.effect_param())

        total_param = 0
        for effect_param in effect_params:
            total_param += effect_param

        return total_param

    async def draw_tc(self, num_of_cards:int = 1) -> bool:
        if window := await _maybe_get_named_window(self.client.root_window, "Draw"):
            for _ in range(num_of_cards):
                await self.client.mouse_handler.click_window(window)
            self.card_names = await self.get_card_names()
            return True
        return False
    
    async def get_card_names(self) -> list[str]:
        self.cards = await self.get_cards()
        named_cards = []
        for c in self.cards:
            named_cards.append(await c.display_name())
        return named_cards

    async def sort_enchants(self) -> list[int]:
        """Sort card enchants"""
        self.damage_enchants:list[int] = []
        self.heal_enchants:list[int] = []
        self.charm_enchants:list[int] = []
        self.trap_enchants:list[int] = []
        self.normals:list[int] = []
        self.cards = await self.get_cards()
        
        for card in self.cards:
            effect_types = await self.read_spell_effect(card)
            if any(effects in effect_types for effects in DAMAGE_ENCHANT_EFFECTS):
                self.damage_enchants.append(await card.spell_id())
            elif any(effects in effect_types for effects in HEAL_ENCHANT_EFFECTS):
                self.heal_enchants.append(await card.spell_id())
            elif any(effects in effect_types for effects in CHARM_ENCHANT_EFFECTS):
                self.charm_enchants.append(await card.spell_id())
            elif any(effects in effect_types for effects in TRAP_ENCHANT_EFFECTS):
                self.trap_enchants.append(await card.spell_id())
            else:
                self.normals.append(await card.spell_id())
        
        return self.damage_enchants + self.heal_enchants + self.charm_enchants + self.trap_enchants
    
    async def handle_enchants(self):
        self.all_enchants = await self.sort_enchants()
        for enchant_id in self.all_enchants:
            self.cards = await self.get_cards()
            card_len = len(self.cards)
            for c in self.cards:
                # make sure it's not an enchant enchanting an enchanted card, itemcard, enchant or tc
                if (await self.get_card_by_id(c) in self.all_enchants) or await c.is_enchanted() or await c.is_item_card() or await c.is_treasure_card():
                    continue
                c_type = await c.type_name()
                enchant_card: CombatCard = await self.get_card_by_id(enchant_id)
                if enchant_card:
                    if (c_type in ['Steal', 'Damage', 'AOE'] and enchant_id in self.damage_enchants) or (c_type == 'Heal' and enchant_id in self.heal_enchants) or (c_type == 'Charm' and enchant_id in self.charm_enchants) or (c_type == 'Ward' and enchant_id in self.trap_enchants):
                        card_name = await c.display_name()
                        ench_name = await enchant_card.display_name()
                        logger.debug(f"{self.member_names[self.client_member]} Enchanting {card_name} with {ench_name}")
                        async with self.client.mouse_handler:
                            await enchant_card.cast(c, sleep_time=.25)
                        
                        async def wait_for_enchant():
                            while card_len == len(await self.get_cards()):
                                await asyncio.sleep(0.1) # give a little room for wiz
                            return True
                        
                        await maybe_wait_for_any_value_with_timeout(wait_for_enchant, sleep_time=0.1, timeout=5)
                        self.cards = await self.get_cards()
                        break
    
    async def wait_for_combat(self, sleep_time: float = 0.5):
        """
        Wait until in combat
        """
        await utils.wait_for_value(self.client.in_battle, True, sleep_time)
        
        self.error = False
        self.combat_task = asyncio.create_task(self.forever_idle_check())
        while await self.client.in_battle():
            try:
                await self.handle_combat()
                self.error = False
            except Exception as e:
                logger.debug(f"{self.client.title} something went wrong: {e}")
                self.error = True
            else:
                break

        if self.combat_task:
            self.combat_task.cancel()
        self.combat_task = None

    async def get_cards(self):
        enchants: list[CombatCard] = []
        other_cards: list[CombatCard] = []

        for c in await CombatHandler(self.client).get_cards():
            if "PetPower" in await c.name():
                continue
            elif await c.is_enchanted() or await c.is_enchanted_from_item_card() or await c.is_treasure_card():
                enchants.append(c)
            else:
                other_cards.append(c)

        # sort them by enchant first
        return enchants + other_cards

    async def is_spell_in_hanging_effect(self, spell: CombatCard, member:CombatMember):
        
        graphical_spell = await spell.get_graphical_spell()
        card_atr = (await graphical_spell.template_id(), await graphical_spell.enchantment())
        if self.hanging_effect_IDs:
            for i in self.hanging_effect_IDs[member]:
                if i[0] == card_atr[0] and i[1] == card_atr[1]:
                    return True
        return False
    
    async def effect_enchant_ID(self):
        #makes lists of card ID's with enchant ID to compare with later on 
        self.hanging_effect_IDs = {}
        hanging_atr_list = []
        for member in self.members:
            for effect in self.member_hanging_effects[member]: 
                effect: DynamicSpellEffect
                hanging_atr_list.append((await effect.spell_template_id(), await effect.enchantment_spell_template_id(), await effect.effect_param(), await effect.string_damage_type(), await effect.effect_type()))
            self.hanging_effect_IDs[member] = hanging_atr_list

async def main():
    handler = ClientHandler()
    client = handler.get_new_clients()[0]
    try:
        logger.debug("Preparing")
        await client.activate_hooks()
        logger.debug("Ready for battle")
        while True:
            client.kill_minions_first = True
            async with client.mouse_handler:
                await Sunshine(client).wait_for_combat()
    finally:
        logger.debug("Closing")
        await handler.close()


if __name__ == "__main__":
    asyncio.run(main())