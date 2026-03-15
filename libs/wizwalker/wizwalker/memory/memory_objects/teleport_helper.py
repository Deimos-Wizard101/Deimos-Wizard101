from wizwalker.utils import XYZ
from wizwalker.memory.memory_object import Primitive, MemoryObject


class TeleportHelper(MemoryObject):
    async def read_base_address(self) -> int:
        return await self.hook_handler.read_teleport_helper()

    async def position(self) -> XYZ:
        return await self.read_xyz(0)

    async def write_position(self, xyz: XYZ):
        await self.write_xyz(0, xyz)

    async def should_update(self) -> bool:
        return await self.read_value_from_offset(12, Primitive.bool)

    async def write_should_update(self, should_update: bool = True):
        await self.write_value_to_offset(12, should_update, Primitive.bool)

    async def target_object_address(self) -> int:
        return await self.read_value_from_offset(13, Primitive.uint64)

    async def write_target_object_address(self, target_object_address: int):
        await self.write_value_to_offset(13, target_object_address, Primitive.uint64)
