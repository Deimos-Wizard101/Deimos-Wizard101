from .madlib_arg import MadlibArg
from wizwalker.memory.memory_object import DynamicMemoryObject


# real name unknown
class MadlibBlock(DynamicMemoryObject):
    async def identifier(self) -> str:
        return await self.read_string_from_offset(0x60)

    async def entries(self) -> list[MadlibArg]:
        result = []
        for addr in await self.read_shared_linked_list(0x48):
            result.append(MadlibArg(self.hook_handler, addr))
        return result
