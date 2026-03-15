from wizwalker.memory.memory_object import Primitive, PropertyClass, DynamicMemoryObject


class ClientZone(PropertyClass):
    """
    Base class for ClientZones
    """

    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def zone_id(self) -> int:
        """
        This client zone's zone id
        """
        return await self.read_value_from_offset(72, Primitive.int64)

    async def write_zone_id(self, zone_id: int):
        """
        Write this client zone's zone id

        Args:
            zone_id: The zone id to write
        """
        await self.write_value_to_offset(72, zone_id, Primitive.int64)

    async def zone_name(self) -> str:
        """
        This client zone's zone name
        """
        return await self.read_string_from_offset(88)

    async def write_zone_name(self, zone_name: str):
        """
        Write this client zone's zone name

        Args:
            zone_name: The zone name to write
        """
        await self.write_string_to_offset(88, zone_name)


class DynamicClientZone(DynamicMemoryObject, ClientZone):
    """
    Dynamic client zone that can take an address
    """

    pass
