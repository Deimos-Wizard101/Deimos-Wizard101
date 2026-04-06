from enum import Enum, auto
from typing import *

class TargetType(Enum):
    type_self = auto()
    type_boss = auto()
    type_enemy = auto()
    type_ally = auto()
    type_aoe = auto()
    type_named = auto()
    type_spell = auto()
    type_select = auto()


class SpellType(Enum):
    type_damage = auto()
    type_inc_damage = auto()
    type_out_damage = auto()
    type_aoe = auto()
    type_heal = auto()
    type_inc_heal = auto()
    type_out_heal = auto()
    type_heal_self = auto()
    type_heal_other = auto()
    type_blade = auto()
    type_charm = auto()
    type_ward = auto()
    type_trap = auto()
    type_enchant = auto()
    #Slack added types
    type_aura = auto()
    type_global = auto()
    type_polymorph = auto()
    type_shadow = auto()
    type_shadow_creature = auto()
    type_pierce = auto()
    type_prism = auto()
    type_dispel = auto()
    #Fix for enchants
    type_mod_damage = auto()
    type_mod_heal = auto()
    type_mod_pierce = auto()


class Spell:
    pass


class DrawSpell(Spell):
    def __init__(self, draw_amount: int = 1):
        self.draw_amount = draw_amount

    def __repr__(self) -> str:
        return f"DrawSpell(draw_amount={self.draw_amount})"

class NamedSpell(Spell):
    def __init__(self, name: str, is_literal: bool = False):
        self.name = name
        self.is_literal = is_literal

    def __repr__(self) -> str:
        return f"NamedSpell(name=\"{self.name}\", is_literal={self.is_literal})"


class TemplateSpell(Spell):
    def __init__(self, requirements: List[SpellType], optional=False) -> None:
        self.requirements = requirements
        self.optional = optional

    def __repr__(self) -> str:
        return f"TemplateSpell(requirements={self.requirements}, optional={self.optional})"


class Move:
    def __init__(self, card: Spell, enchant: Spell = None, second_enchant: Spell = None):
        self.card = card
        self.enchant = enchant
        self.second_enchant = second_enchant

    def __repr__(self) -> str:
        return f"Move(card={self.card}, enchant={self.enchant}, second_enchant={self.second_enchant})"


class TargetData:
    def __init__(self, target_type: TargetType, extra_data: Any = None, is_literal: bool = False):
        self.target_type = target_type
        self.extra_data = extra_data
        self.is_literal = is_literal

    def __repr__(self) -> str:
        return f"TargetData(target_type={self.target_type}, extra_data={self.extra_data}, is_literal={self.is_literal})"


class MoveConfig:
    def __init__(self, move: Union[Move, List], target: Union[TargetData, List] = None):
        self.move = move
        self.target = target

    def __repr__(self) -> str:
        return f"MoveConfig(move={self.move}, target={self.target})"


class PriorityLine:
    def __init__(self, priorities: List[MoveConfig], _round: int = None):
        self.priorities = priorities
        self.round = _round

    def __repr__(self) -> str:
        return f"PriorityLine(priorities={self.priorities}, round={self.round})"


class CombatConfig:
    def __init__(self, rounds: List[PriorityLine]):
        self.specific_rounds: dict[int, PriorityLine] = {}
        self.infinite_rounds: list[PriorityLine] = []
        for _round in rounds:
            if _round.round is None:
                self.infinite_rounds.append(_round)
            else:
                self.specific_rounds[_round.round] = _round

    def __repr__(self) -> str:
        return f"CombatConfig(specific_rounds={self.specific_rounds}, infinite_rounds={self.infinite_rounds})"
