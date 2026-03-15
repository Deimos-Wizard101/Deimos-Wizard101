from wizwalker.memory.memory_object import Primitive, PropertyClass, DynamicMemoryObject


class EquippedSlotInfo(DynamicMemoryObject, PropertyClass):
    async def item_id(self) -> int:
        """
        this is a gid
        """
        return await self.read_value_from_offset(72, Primitive.uint64)

    async def write_item_id(self, val: int):
        await self.write_value_to_offset(72, val, Primitive.uint64)

    async def item_slot_name_id(self) -> int:
        return await self.read_value_from_offset(80, Primitive.uint32)

    async def write_item_slot_name_id(self, val: int):
        await self.write_value_to_offset(80, val, Primitive.uint32)
