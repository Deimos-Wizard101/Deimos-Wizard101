from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass
from .enums import UnlockTriggerState


# C++ class: UnlockTriggerInfo (PropertyClass, size 0x68)
# Registered: FUN_1413ed1b0("UnlockTriggerInfo") at FUN_141461b10 (r792258)
# Field registration: FUN_141461bb0 (r792258)
#
# Offset  Field                        Type
# ------  -----                        ----
# 0x48    m_unlockTriggerTemplateID    uint32
# 0x4C    m_state                      uint32
# 0x50    m_reagentCount1              uint32
# 0x54    m_reagentCount2              uint32
# 0x58    m_reagentCount3              uint32
# 0x5C    m_reagentCount4              uint32
# 0x60    m_reagentCount5              uint32
# 0x64    m_reagentCount6              uint32
#
# Getter switch at FUN_141462230 (r792258):
#   case 0 -> 0x50, case 1 -> 0x54, case 2 -> 0x58
#   case 3 -> 0x5C, case 4 -> 0x60, case 5 -> 0x64
#
# Setter switch at FUN_1414622a0 (r792258): same layout.


class UnlockTriggerInfo(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def unlock_trigger_template_id(self) -> int:
        return await self.read_value_from_offset(0x48, Primitive.uint32)

    async def state(self) -> UnlockTriggerState:
        return await self.read_enum(0x4C, UnlockTriggerState)

    async def reagent_count_1(self) -> int:
        return await self.read_value_from_offset(0x50, Primitive.uint32)

    async def reagent_count_2(self) -> int:
        return await self.read_value_from_offset(0x54, Primitive.uint32)

    async def reagent_count_3(self) -> int:
        return await self.read_value_from_offset(0x58, Primitive.uint32)

    async def reagent_count_4(self) -> int:
        return await self.read_value_from_offset(0x5C, Primitive.uint32)

    async def reagent_count_5(self) -> int:
        return await self.read_value_from_offset(0x60, Primitive.uint32)

    async def reagent_count_6(self) -> int:
        return await self.read_value_from_offset(0x64, Primitive.uint32)

    async def reagent_count_by_index(self, index: int) -> int:
        """Read reagent count by index (0-5), matching FUN_141462230 (r792258)."""
        if not 0 <= index <= 5:
            raise ValueError(f"ReagentIndex must be 0-5, got {index}")
        return await self.read_value_from_offset(0x50 + (index * 4), Primitive.uint32)


class DynamicUnlockTriggerInfo(DynamicMemoryObject, UnlockTriggerInfo):
    pass
