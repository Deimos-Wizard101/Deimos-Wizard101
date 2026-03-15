from wizwalker.memory.memory_object import Primitive, MemoryObject, DynamicMemoryObject
from wizwalker.memory.memory_objects.scene_manager import DynamicSceneManager


class GamebryoPresenter(MemoryObject):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def default_background_color_red(self) -> int:
        return await self.read_value_from_offset(0x48, Primitive.int32)

    async def write_default_background_color_red(self, red: int):
        await self.write_value_to_offset(0x48, red, Primitive.int32)

    async def default_background_color_green(self) -> int:
        return await self.read_value_from_offset(0x4C, Primitive.int32)

    async def write_default_background_color_green(self, green: int):
        await self.write_value_to_offset(0x4C, green, Primitive.int32)

    async def default_background_color_blue(self) -> int:
        return await self.read_value_from_offset(0x50, Primitive.int32)

    async def write_default_background_color_blue(self, blue: int):
        await self.write_value_to_offset(0x50, blue, Primitive.int32)

    async def scene_manager(self) -> DynamicSceneManager:
        addr = await self.read_value_from_offset(0x68, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicSceneManager(self.hook_handler, addr)

    async def shadow_detail(self) -> int:
        return await self.read_value_from_offset(0x8C, Primitive.int32)

    async def write_shadow_detail(self, value: int):
        await self.write_value_to_offset(0x8C, value, Primitive.int32)

    async def master_scene_root(self) -> int:
        """
        Only defined for later
        """
        return await self.read_value_from_offset(0x90, Primitive.uint64)

    async def master_collision_scene(self) -> int:
        """
        Only defined for later
        """
        return await self.read_value_from_offset(0xA8, Primitive.uint64)

    async def nametag_flags(self) -> int:
        return await self.read_value_from_offset(0x190, Primitive.int32)

    async def write_nametag_flags(self, flags: int):
        await self.write_value_to_offset(0x190, flags, Primitive.int32)


class DynamicGamebryoPresenter(DynamicMemoryObject, GamebryoPresenter):
    pass
