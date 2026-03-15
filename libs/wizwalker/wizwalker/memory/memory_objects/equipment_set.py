from wizwalker.memory.memory_object import Primitive, PropertyClass, DynamicMemoryObject


class EquipmentSet(DynamicMemoryObject, PropertyClass):
    async def equipment_set_name(self) -> int:
        return await self.read_value_from_offset(88, Primitive.uint32)

    async def write_equipment_set_name(self, val: int):
        await self.write_value_to_offset(88, val, Primitive.uint32)

    async def is_equipped(self) -> bool:
        return await self.read_value_from_offset(128, Primitive.bool)

    async def write_is_equipped(self, val: bool):
        await self.write_value_to_offset(128, val, Primitive.bool)
