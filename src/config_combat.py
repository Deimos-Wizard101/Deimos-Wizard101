from wizwalker import Client, utils
from wizwalker.combat import CombatCard
from wizwalker.memory.memory_objects.enums import EffectTarget, SpellEffects
from wizwalker.memory.memory_objects.spell_effect import DynamicSpellEffect
from wizwalker.extensions.wizsprinter import CombatConfigProvider
from wizwalker.extensions.wizsprinter.combat_backends.backend_base import BaseCombatBackend
from wizwalker.extensions.wizsprinter.combat_backends.combat_api import CombatConfig, TargetType, SpellType, TemplateSpell
from wizwalker.extensions.wizsprinter.combat_backends.config_backend import get_sprinty_grammar, Lark, TreeToConfig
from wizwalker.extensions.wizsprinter import SprintyCombat
from typing import List, Dict, Tuple
from src.combat_sections import scan_combat_configs
# from wizwalker.client import Client

import re


default_config = 'Mass | "Detonate All 200 - Amulet" | Willcast @ enemy & Willcast @ boss & "Pet - Sharpened Blade" @ spell(any<blade>) & "Sharpened Blade - Amulet" @ spell(any<blade>) & Sharpened @ spell(any<blade>) & Sharpened @ spell(any<blade>) & "Potent Trap - Amulet" @ spell("Feint") & "Potent Trap - Tear" @ spell("Feint") & "Potent Trap - Tear" @ spell(any<trap>) & "Potent Trap - Amulet" @ spell(any<trap>) & Potent @ spell(any<trap>) & Potent @ spell(any<trap>) & any<mod_damage> @ spell(any<damage>) & any<mod_damage> @ spell(any<damage>) & any<blade> @ self | any<trap> @ boss | any<trap> @ enemy | any<aura> | any<global> | any<damage&aoe> @ aoe | any<damage> @ boss | any<damage> @ enemy | any<damage> @ enemies | ?(self.health < 25%) any<heal> @ self'
# "any<damage>[epic] @ enemy | any<damage>[colossal] @ enemy | any<damage>[gargantuan] @ enemy | any<damage>[monstrous] @ enemy | any<damage>[giant] @ enemy | any<damage>[strong] @ enemy"

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



def delegate_combat_configs(input_data: str, fallback_clients: int = 1, line_seperator: str = "\n") -> Dict[int, str]:
    '''
    Handles turning a raw string of file content into a dict of client combat configs.

    Args:
    - input_data (str): File content to use
    - fallback_clients(int): In the event of no clients specified, use the
    - line_seperator (str): Symbol or string that seperates lines of the file, newline by default
    '''

    return scan_combat_configs(input_data, fallback_clients, line_seperator)[0]
