from wizwalker.memory.memory_object import PropertyClass, DynamicMemoryObject
from .duel import DynamicDuel


class ClientDuelManager(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def duelmap(self) -> dict[int, DynamicDuel]:
        return await self.read_std_map(8, DynamicDuel)


class DynamicClientDuelManager(DynamicMemoryObject, ClientDuelManager):
    pass