import struct
from typing import List, Tuple

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject
from .behavior_instance import DynamicBehaviorInstance


class SpellData(DynamicMemoryObject):
    """
    Entry in a DeckBehavior or TreasureBookBehavior spell list.

    RTTI: SpellData (confirmed via live client read_type_name)
    Ghidra: SpellData RegisterProperties @ 0x141a332c0 (r792258)
        m_templateID  at +0x48 (72) -- uint32, spell template ID
        m_enchantment at +0x4C (76) -- uint32, enchantment spell ID (0 = none)
        m_quantity    at +0x50 (80) -- uint32, number of copies (default 1)
    """

    async def template_id(self) -> int:
        """The spell template ID."""
        return await self.read_value_from_offset(72, Primitive.uint32)

    async def enchantment(self) -> int:
        """The enchantment spell ID (0 = no enchantment)."""
        return await self.read_value_from_offset(76, Primitive.uint32)

    async def quantity(self) -> int:
        """Number of copies of this spell in the deck."""
        return await self.read_value_from_offset(80, Primitive.uint32)


class ClientDeckBehavior(DynamicBehaviorInstance):
    """
    Wrapper for the player's active deck behavior.

    Contains the deck configuration (main deck spells).
    Found on the equipped deck item, NOT on the player CoreObject.
    Access via equipment behavior: search equipment items for "BasicDeckBehavior".

    Ghidra: DeckBehavior__RegisterProperties @ 0x141a44c50 (r792258)
        m_spellList                at +0x78 (120) -- SpellDataList (linked list of SpellData)
        m_exclusionMap             at +0x88 (136) -- std::map<uint32, uint16> (RB-tree, internal)
        m_exclusionCount           at +0x90 (144) -- uint16, entry count in the map
        m_serializedExclusionList  at +0x98 (152) -- std::string (binary), SSO layout:
                                      +0x98: data ptr or inline buffer (16 bytes)
                                      +0xA8: length (size_t)
                                      +0xB0: capacity (size_t, >= 16 means heap-allocated)
        m_archmasterySchool        at +0xB8 (184) -- uint32
    """

    async def spell_list(self) -> List[SpellData]:
        """Read m_spellList -- all spells in the deck configuration."""
        result = []
        for addr in await self.read_shared_linked_list(120):  # 0x78
            if addr != 0:
                result.append(SpellData(self.hook_handler, addr))
        return result

    async def archmastery_school(self) -> int:
        """Read m_archmasterySchool."""
        return await self.read_value_from_offset(184, Primitive.uint32)  # 0xB8

    async def exclusion_list(self) -> List[Tuple[int, int]]:
        """Read m_serializedExclusionList and parse the binary format.

        The exclusion list contains item cards the player has excluded
        from their deck configuration.

        Binary format (from DeckBehavior__SerializeExclusionList @ 0x141a45bc0, r792258):
            2 bytes: count (uint16)
            Per entry (6 bytes each):
                4 bytes: spell_id (uint32)
                2 bytes: quantity (uint16)

        Returns:
            List of (spell_id, quantity) tuples.
        """
        base = await self.read_base_address()

        # Read std::string length at +0xA8 (SSO layout: +0x98 + 0x10)
        str_len = await self.read_value_from_offset(0xA8, Primitive.uint32)
        if str_len == 0:
            return []

        # Read std::string capacity at +0xB0 to determine SSO vs heap
        capacity = await self.read_value_from_offset(0xB0, Primitive.uint64)
        if capacity >= 16:
            # Heap-allocated: read pointer at +0x98
            data_ptr = await self.read_value_from_offset(0x98, Primitive.uint64)
            raw = self.hook_handler.process.read_bytes(data_ptr, str_len)
        else:
            # SSO inline buffer at +0x98
            raw = self.hook_handler.process.read_bytes(base + 0x98, str_len)

        count = struct.unpack_from("<H", raw, 0)[0]
        entries = []
        for i in range(count):
            off = 2 + i * 6
            spell_id = struct.unpack_from("<I", raw, off)[0]
            qty = struct.unpack_from("<H", raw, off + 4)[0]
            entries.append((spell_id, qty))
        return entries

    async def deck_template_ids(self) -> List[int]:
        """Convenience: get template IDs of all deck spells."""
        return [await s.template_id() for s in await self.spell_list()]

    async def deck_contents(self) -> List[dict]:
        """Get full deck contents: template_id, enchantment, quantity per entry."""
        result = []
        for entry in await self.spell_list():
            result.append({
                "template_id": await entry.template_id(),
                "enchantment": await entry.enchantment(),
                "quantity": await entry.quantity(),
            })
        return result


class ClientTreasureBookBehavior(DynamicBehaviorInstance):
    """
    Wrapper for the player's treasure card collection.

    Ghidra: TreasureBookBehavior__RegisterProperties @ 0x141a720c0 (r792258)
    Behavior name: "BasicTreasureBookBehavior"
        m_spellList at +0x78 (120) -- SpellDataList (linked list of SpellData)
    """

    async def spell_list(self) -> List[SpellData]:
        """Read m_spellList -- all treasure cards in the player's collection."""
        result = []
        for addr in await self.read_shared_linked_list(120):  # 0x78
            if addr != 0:
                result.append(SpellData(self.hook_handler, addr))
        return result

    async def treasure_card_template_ids(self) -> List[int]:
        """Convenience: get template IDs of all treasure cards."""
        return [await s.template_id() for s in await self.spell_list()]

    async def treasure_card_contents(self) -> List[dict]:
        """Get full TC contents: template_id, enchantment, quantity per entry."""
        result = []
        for entry in await self.spell_list():
            result.append({
                "template_id": await entry.template_id(),
                "enchantment": await entry.enchantment(),
                "quantity": await entry.quantity(),
            })
        return result
