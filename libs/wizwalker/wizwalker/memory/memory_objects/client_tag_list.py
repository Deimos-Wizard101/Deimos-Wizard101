from wizwalker.memory.memory_object import DynamicMemoryObject


class ClientTagList(DynamicMemoryObject):
    async def client_tags(self) -> list[str]:
        res = []
        for addr in await self.read_linked_list(0x48):
            res.append(await self.read_string(addr))
        return res
