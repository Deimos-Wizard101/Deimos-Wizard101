from wizwalker.memory.memory_object import PropertyClass, DynamicMemoryObject
from .behavior_template import DynamicBehaviorTemplate


class CoreTemplate(DynamicMemoryObject, PropertyClass):
    async def behaviors(self) -> list[DynamicBehaviorTemplate]:
        result = []
        for elem in await self.read_dynamic_vector(72):
            if elem != 0:
                result.append(DynamicBehaviorTemplate(self.hook_handler, elem))
        return result
