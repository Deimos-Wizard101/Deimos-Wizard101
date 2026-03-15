from typing import Optional

from wizwalker.utils import XYZ, Orient
from wizwalker.memory.memory_object import Primitive, PropertyClass, DynamicMemoryObject
from wizwalker.memory import memory_objects


class ActorBody(PropertyClass):
    """
    Base class for ActorBody
    """

    async def read_base_address(self) -> int:
        raise NotImplementedError()

    # note: internal
    async def parent_client_object(self) -> Optional["memory_objects.DynamicClientObject"]:
        addr = await self.read_value_from_offset(72, Primitive.uint64)

        if addr == 0:
            return None

        return memory_objects.DynamicClientObject(self.hook_handler, addr)

    async def position(self) -> XYZ:
        """
        This body's position

        Returns:
            An XYZ representing the position
        """
        return await self.read_xyz(88)

    async def write_position(self, position: XYZ):
        """
        Write this body's position

        Args:
            position: The position to write
        """
        await self.write_xyz(88, position)

    async def orientation(self) -> Orient:
        return await self.read_orient(100)

    async def write_orientation(self, orient: Orient):
        await self.write_orient(100, orient)

    async def pitch(self) -> float:
        """
        This body's pitch

        Returns:
            Float representing pitch
        """
        return await self.read_value_from_offset(100, Primitive.float32)

    async def write_pitch(self, pitch: float):
        """
        Write this body's pitch

        Args:
            pitch: The pitch to write
        """
        await self.write_value_to_offset(100, pitch, Primitive.float32)

    async def roll(self) -> float:
        """
        This body's roll

        Returns:
            Float representing roll
        """
        return await self.read_value_from_offset(104, Primitive.float32)

    async def write_roll(self, roll: float):
        """
        Write this body's roll

        Args:
            roll: The roll to write
        """
        await self.write_value_to_offset(104, roll, Primitive.float32)

    async def yaw(self) -> float:
        """
        The body's yaw

        Returns:
            Float representing yaw
        """
        return await self.read_value_from_offset(108, Primitive.float32)

    async def write_yaw(self, yaw: float):
        """
        Write this body's yaw

        Args:
            yaw: The yaw to write
        """
        await self.write_value_to_offset(108, yaw, Primitive.float32)

    async def height(self) -> float:
        """
        This body's height

        Returns:
            Float representing height
        """
        return await self.read_value_from_offset(132, Primitive.float32)

    async def write_height(self, height: float):
        """
        Write this body's height

        Args:
            height: The height to write
        """
        await self.write_value_to_offset(132, height, Primitive.float32)

    async def scale(self) -> float:
        """
        This body's scale

        Returns:
            Float representing scale
        """
        return await self.read_value_from_offset(112, Primitive.float32)

    async def write_scale(self, scale: float):
        """
        Write this body's scale

        Args:
            scale: The scale to write
        """
        await self.write_value_to_offset(112, scale, Primitive.float32)

    # Note: internal offset
    async def model_update_scheduled(self) -> bool:
        """
        If this body should have their model resynced with it's position

        Returns:
            Boolean representing state
        """
        return await self.read_value_from_offset(136, Primitive.bool)

    async def write_model_update_scheduled(self, state: bool):
        """
        Writes if this body should have their model resynced with it's position

        Args:
            state: The boolean to write
        """
        await self.write_value_to_offset(136, state, Primitive.bool)


class CurrentActorBody(ActorBody):
    """
    Actor body tied to the player hook
    """

    async def read_base_address(self) -> int:
        return await self.hook_handler.read_current_player_base()


class DynamicActorBody(DynamicMemoryObject, ActorBody):
    """
    Dynamic actor body that can take an address
    """

    pass
