from wizwalker.combat import CombatCard
from wizwalker.memory import DynamicSpellEffect, SpellEffects

async def dump_card_effect(effect: DynamicSpellEffect, indent: int = 0):
    def printi(s):
        print(f"{' '*indent*4}{s}")
    
    printi(f"type_name: {await effect.read_type_name()}")
    indent += 1

    printi(f"effect_type: {await effect.effect_type()}")
    printi(f"effect_target: {await effect.effect_target()}")
    printi(f"effect_param: {await effect.effect_param()}")
    printi(f"act: {await effect.act()}")
    printi(f"act_num: {await effect.act_num()}")
    printi(f"converted: {await effect.converted()}")
    printi(f"damage_type: {await effect.string_damage_type()}")
    printi(f"disposition: {await effect.disposition()}")
    printi(f"num_rounds: {await effect.num_rounds()}")
    printi(f"param_per_round: {await effect.param_per_round()}")
    printi(f"pip_num: {await effect.pip_num()}")
    printi(f"protected: {await effect.protected()}")
    printi(f"enchantment_spell_template_id: {await effect.enchantment_spell_template_id()}")
    printi(f"rank: {await effect.rank()}")
    printi(f"chance_per_target: {await effect.chance_per_target()}")
    printi(f"armor_piercing_param: {await effect.armor_piercing_param()}")
    printi(f"cloaked: {await effect.cloaked()}")
    
    if await effect.effect_type() == SpellEffects.invalid_spell_effect:
        for sub in await effect.maybe_effect_list():
            await dump_card_effect(sub, indent)

async def dump_card_data(card: CombatCard):
    indent = 0
    def printi(s):
        print(f"{' '*indent*4}{s}")
    
    printi(f"{await card.name()} - {await card.display_name()}")
    indent += 1
    printi(f"type_name: {await card.type_name()}")
    printi(f"accuracy: {await card.accuracy()}")
    printi(f"is_item_card: {await card.is_item_card()}")
    printi(f"is_treasure_card: {await card.is_treasure_card()}")
    printi(f"is_side_board: {await card.is_side_board()}")
    printi(f"is_pve_only: {await card.is_pve_only()}")

    printi("effects:")
    for eff in await card.get_spell_effects():
        await dump_card_effect(eff, indent=indent+1)

class CombatLiftingEnvironment:

    async def lift_card_effects(self, card: CombatCard):
        pass

    async def calculate_card_score(self, card: CombatCard) -> int:
        # TODO: Make sure card is actually safe to use (memory valid)
        pass
