from typing import Optional

from wizwalker.memory.memory_object import Primitive, MemoryObject, DynamicMemoryObject
from wizwalker.memory.memory_objects.cam_view import DynamicCamView


class GamebryoCamera(MemoryObject):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def base_matrix(self) -> list[float]:
        return list(await self.read_vector(164, 9))

    async def write_base_matrix(self, vals: list[float]):
        await self.write_vector(164, vals)

    async def cam_view(self) -> Optional[DynamicCamView]:
        addr = await self.read_value_from_offset(200, Primitive.int64)

        if addr == 0:
            return None

        return DynamicCamView(self.hook_handler, addr)


class DynamicGamebryoCamera(DynamicMemoryObject, GamebryoCamera):
    pass
