from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass

class SpellRank(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError

    async def spell_rank(self) -> int:
        """
        The number of regular pips this spell costs
        """
        return await self.read_value_from_offset(80, Primitive.uint8)

    async def write_spell_rank(self, spell_rank: int):
        """
        Write the number of regular pips this spell costs

        Args:
            spell_rank: The regular pip cost to write
        """
        await self.write_value_to_offset(80, spell_rank, Primitive.uint8)

    async def balance_pips(self) -> int:
        """
        The number of balance pips this spell costs
        """
        return await self.read_value_from_offset(81, Primitive.uint8)

    async def write_balance_pips(self, balance_pips: int):
        """
        Write the number of death pips this spell costs

        Args:
            balance_pips: The balance pip cost to write
        """
        await self.write_value_to_offset(81, balance_pips, Primitive.uint8)

    async def death_pips(self) -> int:
        """
        The number of death pips this spell costs
        """
        return await self.read_value_from_offset(82, Primitive.uint8)

    async def write_death_pips(self, death_pips: int):
        """
        Write the number of death pips this spell costs

        Args:
            death_pips: The death pip cost to write
        """
        await self.write_value_to_offset(82, death_pips, Primitive.uint8)

    async def fire_pips(self) -> int:
        """
        The number of fire pips this spell costs
        """
        return await self.read_value_from_offset(83, Primitive.uint8)

    async def write_fire_pips(self, fire_pips: int):
        """
        Write the number of fire pips this spell costs

        Args:
            fire_pips: The fire pip cost to write
        """
        await self.write_value_to_offset(83, fire_pips, Primitive.uint8)


    async def ice_pips(self) -> int:
        """
        The number of ice pips this spell costs
        """
        return await self.read_value_from_offset(84, Primitive.uint8)

    async def write_ice_pips(self, ice_pips: int):
        """
        Write the number of ice pips this spell costs

        Args:
            ice_pips: The ice pip cost to write
        """
        await self.write_value_to_offset(84, ice_pips, Primitive.uint8)

    async def life_pips(self) -> int:
        """
        The number of life pips this spell costs
        """
        return await self.read_value_from_offset(85, Primitive.uint8)

    async def write_life_pips(self, life_pips: int):
        """
        Write the number of life pips this spell costs

        Args:
            life_pips: The life pip cost to write
        """
        await self.write_value_to_offset(85, life_pips, Primitive.uint8)

    async def myth_pips(self) -> int:
        """
        The number of myth pips this spell costs
        """
        return await self.read_value_from_offset(86, Primitive.uint8)

    async def write_myth_pips(self, myth_pips: int):
        """
        Write the number of myth pips this spell costs

        Args:
            myth_pips: The myth pip cost to write
        """
        await self.write_value_to_offset(86, myth_pips, Primitive.uint8)

    async def storm_pips(self) -> int:
        """
        The number of storm pips this spell costs
        """
        return await self.read_value_from_offset(87, Primitive.uint8)

    async def write_storm_pips(self, storm_pips: int):
        """
        Write the number of storm pips this spell costs

        Args:
            storm_pips: The storm pip cost to write
        """
        await self.write_value_to_offset(87, storm_pips, Primitive.uint8)

    async def shadow_pips(self) -> int:
        """
        The number of shadow pips this spell costs
        """
        return await self.read_value_from_offset(88, Primitive.uint8)

    async def write_shadow_pips(self, shadow_pips: int):
        """
        Write the number of shadow pips this spell costs

        Args:
            shadow_pips: The shadow pip cost to write
        """
        await self.write_value_to_offset(88, shadow_pips, Primitive.uint8)

    async def is_xpip_spell(self) -> bool:
        """
        If this spell is a x pip cost spell
        """
        return await self.read_value_from_offset(90, Primitive.bool)

    async def write_is_xpip_spell(self, is_xpip: bool):
        """
        Write if this spell is a x pip cost spell

        Args:
            shadow_pips: write if it is a x pip cost spell; True for it is.
        """
        await self.write_value_to_offset(90, is_xpip, Primitive.bool)

class DynamicSpellRank(DynamicMemoryObject, SpellRank):
    pass