from wizwalker import XYZ
from wizwalker.memory.memory_object import MemoryObject


class CurrentQuestPosition(MemoryObject):
    async def read_base_address(self) -> int:
        return await self.hook_handler.read_current_quest_base()

    async def position(self) -> XYZ:
        return await self.read_xyz(0)

    async def write_position(self, position: XYZ):
        await self.write_xyz(0, position)
