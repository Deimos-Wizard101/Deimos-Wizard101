from wizwalker.memory.memory_object import DynamicMemoryObject

class MadlibArg(DynamicMemoryObject):
    async def identifier(self) -> str:
        return await self.read_string_from_offset(0x50)

    async def maybe_data_str(self) -> str:
        return await self.read_string_from_offset(0x70)

