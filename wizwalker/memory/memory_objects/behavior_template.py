from enum import Enum

from wizwalker.memory.memory_object import PropertyClass, DynamicMemoryObject, Primitive
from wizwalker.utils import Color


class BehaviorTemplate(PropertyClass):
    """
    Base class for behavior templates
    """

    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def behavior_name(self) -> str:
        """
        This behavior template's name
        """
        return await self.read_string_from_offset(72)

    async def write_behavior_name(self, behavior_name: str):
        """
        Write this behavior template's name

        Args:
            behavior_name: The behavior name to write
        """
        await self.write_string_to_offset(72, behavior_name)


class DynamicBehaviorTemplate(DynamicMemoryObject, BehaviorTemplate):
    """
    Dynamic behavior template that can be given an address
    """

    pass



class NpcBehaviorTemplateTitleType(Enum):
    easy = 0
    normal = 1
    elite = 2
    boss = 3
    minion = 4

class NPCBehaviorTemplate(DynamicBehaviorTemplate):
    async def starting_health(self) -> int:
        return await self.read_value_from_offset(120, Primitive.int32)

    async def hide_current_hp(self) -> bool:
        return await self.read_value_from_offset(124, Primitive.bool)

    async def level(self) -> int:
        return await self.read_value_from_offset(128, Primitive.int32)

    async def intelligence(self) -> float:
        return await self.read_value_from_offset(132, Primitive.float32)

    async def selfish_factor(self) -> float:
        return await self.read_value_from_offset(136, Primitive.bool)

    async def aggressive_factor(self) -> int:
        return await self.read_value_from_offset(140, Primitive.int32)

    async def boss_mob(self) -> bool:
        return await self.read_value_from_offset(144, Primitive.bool)

    async def turn_towards_player(self) -> bool:
        return await self.read_value_from_offset(145, Primitive.bool)

    async def mob_title(self) -> NpcBehaviorTemplateTitleType:
        return await self.read_enum(148, NpcBehaviorTemplateTitleType)

    async def name_color(self) -> Color:
        return await self.read_color(152)

    async def write_name_color(self, val: Color):
        await self.write_color(152, val)

    async def school_of_focus(self) -> str:
        return await self.read_string_from_offset(160)

    async def secondary_school_of_focus(self) -> str:
        return await self.read_string_from_offset(200)

    async def cylinder_scale_value(self) -> float:
        return await self.read_value_from_offset(268, Primitive.float32)

    async def max_shadow_pips(self) -> int:
        return await self.read_value_from_offset(272, Primitive.int32)
