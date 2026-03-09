from typing import *

from lark import Lark

from .backend_base import BaseCombatBackend
from .combat_config_parser import CombatConfig, PriorityLine, get_sprinty_grammar, TreeToConfig, Move, MoveConfig
from ..sprinty_combat import SprintyCombat

class CombatConfigProvider(BaseCombatBackend):
    def __init__(self, path: str, cast_time: float = 0.2):
        super().__init__(cast_time=cast_time)
        self.filename = path
        with open(path) as file:
            self.config: CombatConfig = self.parse_config(file.read())

    def parse_config(self, file_contents) -> CombatConfig:
        grammar = get_sprinty_grammar()

        parser = Lark(grammar)
        tree = parser.parse(file_contents)
        return self._expand_config(TreeToConfig().transform(tree))

    async def get_real_round(self, r: int) -> Optional[PriorityLine]:
        if r in self.config.specific_rounds:
            return self.config.specific_rounds[r]
        return None

    async def get_relative_round(self, r: int) -> Optional[PriorityLine]:
        if len(self.config.infinite_rounds) > 0:
            return self.config.infinite_rounds[r % len(self.config.infinite_rounds)]
        return None

    async def handle_no_cards_given(self):
        raise RuntimeError(f"Full config fail! \"{self.filename}\" might be empty or contains only explicit rounds. Consider adding a pass or something else")

    def _expand_config(self, config: CombatConfig) -> CombatConfig:
        old_rounds = [x for x in config.specific_rounds.values()] + config.infinite_rounds
        rounds = []
        for old_round in old_rounds:
            priorities = []
            for old_priority in old_round.priorities:
                if old_priority.move.enchant is None:
                    priorities.append(old_priority)
                else:
                    priorities.append(old_priority)
                    enchantless_move = Move(old_priority.move.card, None)
                    enchantless = MoveConfig(enchantless_move, old_priority.target)
                    priorities.append(enchantless)
            rounds.append(PriorityLine(priorities, old_round.round))

        return CombatConfig(rounds)