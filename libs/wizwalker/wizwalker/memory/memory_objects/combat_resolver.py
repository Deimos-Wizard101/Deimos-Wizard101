from typing import List, Optional

from wizwalker.memory.memory_object import Primitive, PropertyClass, DynamicMemoryObject
from .spell_effect import DynamicSpellEffect


class CombatResolver(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def bool_global_effect(self) -> bool:
        return await self.read_value_from_offset(112, Primitive.bool)

    async def write_bool_global_effect(self, bool_global_effect: bool):
        await self.write_value_to_offset(112, bool_global_effect, Primitive.bool)

    async def global_effect(self) -> Optional[DynamicSpellEffect]:
        addr = await self.read_value_from_offset(120, Primitive.int64)

        if addr == 0:
            return None

        return DynamicSpellEffect(self.hook_handler, addr)

    async def battlefield_effects(self) -> List[DynamicSpellEffect]:
        effects = []
        for addr in await self.read_shared_vector(136):
            effects.append(DynamicSpellEffect(self.hook_handler, addr))

        return effects


class DynamicCombatResolver(DynamicMemoryObject, CombatResolver):
    pass
