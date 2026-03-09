from typing import Optional

from wizwalker.memory.memory_object import Primitive, MemoryObject, DynamicMemoryObject, Primitive
from .spell import DynamicSpell


# TODO: document
class CombatAction(MemoryObject):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def spell_caster(self) -> int:
        return await self.read_value_from_offset(72, Primitive.int32)

    async def write_spell_caster(self, spell_caster: int):
        await self.write_value_to_offset(72, spell_caster, Primitive.int32)

    async def spell(self) -> Optional[DynamicSpell]:
        addr = await self.read_value_from_offset(104, Primitive.int64)

        if addr == 0:
            return None

        return DynamicSpell(self.hook_handler, addr)

    async def spell_hits(self) -> int:
        return await self.read_value_from_offset(120, Primitive.char)

    async def write_spell_hits(self, spell_hits: int):
        await self.write_value_to_offset(120, spell_hits, Primitive.char)

    async def interrupt(self) -> bool:
        return await self.read_value_from_offset(121, Primitive.bool)

    async def write_interrupt(self, interrupt: bool):
        await self.write_value_to_offset(121, interrupt, Primitive.bool)

    async def sigil_spell(self) -> bool:
        return await self.read_value_from_offset(122, Primitive.bool)

    async def write_sigil_spell(self, sigil_spell: bool):
        await self.write_value_to_offset(122, sigil_spell, Primitive.bool)

    async def show_cast(self) -> bool:
        return await self.read_value_from_offset(123, Primitive.bool)

    async def write_show_cast(self, show_cast: bool):
        await self.write_value_to_offset(123, show_cast, Primitive.bool)

    async def critical_hit_roll(self) -> int:
        return await self.read_value_from_offset(124, Primitive.uint8)

    async def write_critical_hit_roll(self, critical_hit_roll: int):
        await self.write_value_to_offset(124, critical_hit_roll, Primitive.uint8)

    async def stun_resist_roll(self) -> int:
        return await self.read_value_from_offset(125, Primitive.uint8)

    async def write_stun_resist_roll(self, stun_resist_roll: int):
        await self.write_value_to_offset(125, stun_resist_roll, Primitive.uint8)

    async def blocks_calculated(self) -> bool:
        return await self.read_value_from_offset(160, Primitive.bool)

    async def write_blocks_calculated(self, blocks_calculated: bool):
        await self.write_value_to_offset(160, blocks_calculated, Primitive.bool)

    async def serialized_blocks(self) -> str:
        return await self.read_string_from_offset(168)

    async def write_serialized_blocks(self, serialized_blocks: str):
        await self.write_string_to_offset(168, serialized_blocks)
    
    async def effect_chosen(self) -> int:
        return await self.read_value_from_offset(220, Primitive.uint32)

    async def write_effect_chosen(self, effect_chosen: int):
        await self.write_value_to_offset(220, effect_chosen, Primitive.uint32)

    async def string_key_message(self) -> str:
        return await self.read_string_from_offset(224)

    async def write_string_key_message(self, string_key_message: str):
        await self.write_string_to_offset(224, string_key_message)

    async def sound_file_name(self) -> str:
        return await self.read_string_from_offset(256)

    async def write_sound_file_name(self, sound_file_name: str):
        await self.write_string_to_offset(256, sound_file_name)

    async def duration_modifier(self) -> float:
        return await self.read_value_from_offset(288, Primitive.float32)

    async def write_duration_modifier(self, duration_modifier: float):
        await self.write_value_to_offset(288, duration_modifier, Primitive.float32)

    async def serialized_targets_affected(self) -> str:
        return await self.read_string_from_offset(296)

    async def write_serialized_targets_affected(self, serialized_targets_affected: str):
        await self.write_string_to_offset(296, serialized_targets_affected)

    async def target_subcircle_list(self) -> int:
        return await self.read_value_from_offset(80, Primitive.int32)

    async def write_target_subcircle_list(self, target_subcircle_list: int):
        await self.write_value_to_offset(80, target_subcircle_list, Primitive.int32)

    async def pip_conversion_roll(self) -> int:
        return await self.read_value_from_offset(128, Primitive.int32)

    async def write_pip_conversion_roll(self, pip_conversion_roll: int):
        await self.write_value_to_offset(128, pip_conversion_roll, Primitive.int32)

    async def random_spell_effect_per_target_rolls(self) -> int:
        return await self.read_value_from_offset(136, Primitive.int32)

    async def write_random_spell_effect_per_target_rolls(self, random_spell_effect_per_target_rolls: int):
        await self.write_value_to_offset(136, random_spell_effect_per_target_rolls, Primitive.int32)

    async def handled_random_spell_per_target(self) -> bool:
        return await self.read_value_from_offset(132, Primitive.bool)

    async def write_handled_random_spell_per_target(self, handled_random_spell_per_target: bool):
        await self.write_value_to_offset(132, handled_random_spell_per_target, Primitive.bool)

    async def confused_target(self) -> bool:
        return await self.read_value_from_offset(216, Primitive.bool)

    async def write_confused_target(self, confused_target: bool):
        await self.write_value_to_offset(216, confused_target, Primitive.bool)

    async def force_spell(self) -> bool:
        return await self.read_value_from_offset(344, Primitive.bool)

    async def write_force_spell(self, force_spell: bool):
        await self.write_value_to_offset(344, force_spell, Primitive.bool)

    async def after_died(self) -> bool:
        return await self.read_value_from_offset(217, Primitive.bool)

    async def write_after_died(self, after_died: bool):
        await self.write_value_to_offset(217, after_died, Primitive.bool)

    async def delayed(self) -> bool:
        return await self.read_value_from_offset(345, Primitive.bool)

    async def write_delayed(self, delayed: bool):
        await self.write_value_to_offset(345, delayed, Primitive.bool)

    async def delayed_enchanted(self) -> bool:
        return await self.read_value_from_offset(346, Primitive.bool)

    async def write_delayed_enchanted(self, delayed_enchanted: bool):
        await self.write_value_to_offset(346, delayed_enchanted, Primitive.bool)

    async def pet_cast(self) -> bool:
        return await self.read_value_from_offset(347, Primitive.bool)

    async def write_pet_cast(self, pet_cast: bool):
        await self.write_value_to_offset(347, pet_cast, Primitive.bool)

    async def pet_casted(self) -> bool:
        return await self.read_value_from_offset(348, Primitive.bool)

    async def write_pet_casted(self, pet_casted: bool):
        await self.write_value_to_offset(348, pet_casted, Primitive.bool)

    async def pet_cast_target(self) -> int:
        return await self.read_value_from_offset(352, Primitive.int32)

    async def write_pet_cast_target(self, pet_cast_target: int):
        await self.write_value_to_offset(352, pet_cast_target, Primitive.int32)
        
    # async def x_pip_cost(self) -> class TargetCritHit:
    #     return await self.read_value_from_offset(356, Primitive.uint8)

    # async def crit_hit_list(self) -> class TargetCritHit:
    #     return await self.read_value_from_offset(376, "class TargetCritHit")


class DynamicCombatAction(DynamicMemoryObject, CombatAction):
    pass
