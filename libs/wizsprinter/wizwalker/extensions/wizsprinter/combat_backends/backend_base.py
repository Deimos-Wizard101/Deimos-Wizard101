from typing import *

from .combat_config_parser import PriorityLine

class BaseCombatBackend:
    def __init__(self, cast_time: float = 0.3):
        self.cast_time = cast_time
        self.combat = None

    def attach_combat(self, combat): # TODO: Import+type hint not working because of circular import
        self.combat = combat

    async def get_real_round(self, r: int) -> Optional[PriorityLine]:
        raise NotImplementedError()

    async def get_relative_round(self, r: int) -> Optional[PriorityLine]:
        raise NotImplementedError()

    async def handle_no_cards_given(self):
        pass
