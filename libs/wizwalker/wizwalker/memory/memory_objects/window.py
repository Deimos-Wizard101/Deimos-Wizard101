import struct
from typing import Callable, List, Optional
from contextlib import suppress

from loguru import logger

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass
from .enums import WindowFlags, WindowStyle
from .spell import DynamicGraphicalSpell
from .combat_participant import DynamicCombatParticipant
from wizwalker import AddressOutOfRange, MemoryReadError, Rectangle, utils


# TODO: Window.click
class Window(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def debug_print_ui_tree(self):
        print(await self.get_ui_tree_stringified())

    async def get_ui_tree_stringified(self, indent_str = "-") -> str:
        async def traverse_tree(branch, depth):
            nonlocal indent_str
            if type(branch) == str:
                return f"{indent_str * depth} {branch}\n"
            else:
                result = ""
                for x in branch:
                    result += await traverse_tree(x, depth + 1)
                return result
        return await traverse_tree(await self.get_ui_tree_strings(), 0)

    async def get_ui_tree_strings(self) -> list:
        result = [f"[{await self.name()}] {await self.maybe_read_type_name()}"]
        for child in await utils.wait_for_non_error(self.children):
            result.append(await child.get_ui_tree_strings())
        return result

    async def debug_paint(self):
        rect = await self.scale_to_client()
        rect.paint_on_screen(self.hook_handler.client.window_handle)

    async def scale_to_client(self):
        rect = await self.window_rectangle()

        parent_rects = []
        for parent in await self.get_parents():
            parent_rects.append(await parent.window_rectangle())

        ui_scale = await self.hook_handler.client.render_context.ui_scale()

        return rect.scale_to_client(parent_rects, ui_scale)

    async def get_windows_with_type(self, type_name: str) -> List["DynamicWindow"]:
        async def _pred(window):
            return await window.maybe_read_type_name() == type_name

        return await self.get_windows_with_predicate(_pred)

    async def get_windows_with_name(self, name: str) -> List["DynamicWindow"]:
        async def _pred(window):
            return await window.name() == name

        return await self.get_windows_with_predicate(_pred)

    async def _recursive_get_windows_by_predicate(self, predicate, windows):
        with suppress(ValueError, MemoryReadError, AddressOutOfRange):
            for child in await self.children():
                if await predicate(child):
                    windows.append(child)

                await child._recursive_get_windows_by_predicate(predicate, windows)

    async def get_windows_with_predicate(self, predicate: Callable) -> List["DynamicWindow"]:
        """
        async def my_pred(window) -> bool:
            if await window.name() == "friend's list":
              return True

            return False

        await client.root_window.get_windows_by_predicate(my_pred)
        """
        windows = []

        # check our own children
        try:
            children = await self.children()
        except (ValueError, MemoryReadError, AddressOutOfRange):
            children = []

        for child in children:
            if await predicate(child):
                windows.append(child)

        for child in children:
            await child._recursive_get_windows_by_predicate(predicate, windows)

        return windows

    async def get_parents(self) -> List["DynamicWindow"]:
        parents = []
        current = self
        while (parent := await current.parent()) is not None:
            parents.append(parent)
            current = parent

        return parents

    async def get_child_by_name(self, name: str) -> "DynamicWindow":
        children = await self.children()
        for child in children:
            if await child.name() == name:
                return child

        raise ValueError(f"No child named {name}")

    async def is_visible(self):
        return WindowFlags.visible in await self.flags()

    # This is here because checking in .children slows down window filtering majorly
    async def maybe_graphical_spell(self, *, check_type: bool = False) -> Optional[DynamicGraphicalSpell]:
        if check_type:
            type_name = await self.maybe_read_type_name()
            if type_name != "SpellCheckBox":
                raise ValueError(f"This object is a {type_name} not a SpellCheckBox.")

        addr = await self.read_value_from_offset(960, Primitive.int64)

        if addr == 0:
            return None

        return DynamicGraphicalSpell(self.hook_handler, addr)

    async def maybe_checked(self) -> bool:
        return await self.read_value_from_offset(884, Primitive.bool)

    # see maybe_graphical_spell
    # note: not defined
    async def maybe_spell_grayed(self, *, check_type: bool = False) -> bool:
        if check_type:
            type_name = await self.maybe_read_type_name()
            if type_name != "SpellCheckBox":
                raise ValueError(f"This object is a {type_name} not a SpellCheckBox")

        return await self.read_value_from_offset(1064, Primitive.bool)

    # See maybe_graphical_spell
    async def maybe_combat_participant(self, *, check_type: bool = False) -> Optional[DynamicCombatParticipant]:
        if check_type:
            type_name = await self.maybe_read_type_name()
            if type_name != "CombatantDataControl":
                raise ValueError(
                    f"This object is a {type_name} not a CombatantDataControl."
                )

        addr = await self.read_value_from_offset(1680, Primitive.int64)

        if addr == 0:
            return None

        return DynamicCombatParticipant(self.hook_handler, addr)

    # See maybe_graphical_spell
    async def maybe_text(self, *, check_type: bool = False) -> str:
        # TODO: see if all types with .text have Control prefix
        #  and if so check that they have it
        base_address = await self.read_base_address() + 584
        string_len = await self.read_typed(base_address + 16, Primitive.int32)
        if string_len == 0:
            return ""

        # wide chars take 2 bytes
        string_len *= 2

        # this is a guess, but it seems like its awlways a pointer regardless of length

        string_address = await self.read_typed(base_address, Primitive.int64)

        try:
            return (await self.read_bytes(string_address, string_len)).decode("utf-16")
        except UnicodeDecodeError:
            return ""
        #return await self.read_wide_string_from_offset(584)

    async def write_maybe_text(self, text: str):
        """
        Writing to this when there isn't actually a .text could crash
        """
        address = await self.read_base_address() + 584
        string_len_addr = address + 16
        encoded = text.encode("utf-16-le")
        # len(encoded) instead of string bc it can be larger in some encodings
        string_len = len(encoded)

        current_string_len = await self.read_typed(address + 16, Primitive.int32)

        # we need to create a pointer to the string data
        #if string_len >= 7 > current_string_len:
        #    # +1 for 0 byte after
        #    pointer_address = await self.allocate(string_len + 1)

            # need 0 byte for some c++ null termination standard
        #   await self.write_bytes(pointer_address, encoded + b"\x00")
        #    await self.write_typed(address, pointer_address, Primitive.int64)

        # string is already a pointer
        #elif string_len >= 7 and current_string_len >= 8:
        
        
        # Assume Maybe Text is always a Pointer
        
        pointer_address = await self.read_typed(address, Primitive.int64)
        await self.write_bytes(pointer_address, encoded + b"\x00")

        # normal buffer string
        #else:
        #    await self.write_bytes(address, encoded + b"\x00")

        # take 2 bytes
        await self.write_typed(string_len_addr, string_len // 2, Primitive.int32)
        #await self.write_wide_string_to_offset(584, text)

    async def name(self) -> str:
        return await self.read_string_from_offset(80)

    async def write_name(self, name: str):
        await self.write_string_to_offset(80, name)

    async def children(self) -> List["DynamicWindow"]:
        try:
            pointers = await self.read_shared_vector(112)
        except (ValueError, MemoryReadError):
            logger.error("Issue while reading children vector raised to upper level")
            return []

        windows = []
        for addr in pointers:
            if addr == 0:
                logger.error("0 address while reading children")

            else:
                windows.append(DynamicWindow(self.hook_handler, addr))

        return windows

    async def parent(self) -> Optional["DynamicWindow"]:
        addr = await self.read_value_from_offset(136, Primitive.int64)
        # the root window has no parents
        if addr == 0:
            return None

        return DynamicWindow(self.hook_handler, addr)

    async def style(self) -> WindowStyle:
        style = await self.read_value_from_offset(152, Primitive.uint32)
        return WindowStyle(style)

    async def write_style(self, style: WindowStyle):
        await self.write_value_to_offset(152, int(style), Primitive.uint32)

    async def flags(self) -> WindowFlags:
        flags = await self.read_value_from_offset(156, Primitive.uint32)
        return WindowFlags(flags)

    async def write_flags(self, flags: WindowFlags):
        await self.write_value_to_offset(156, int(flags), Primitive.uint32)

    async def window_rectangle(self) -> Rectangle:
        rect = await self.read_vector(160, 4, Primitive.int32)
        return Rectangle(*rect)

    async def write_window_rectangle(self, window_rectangle: Rectangle):
        await self.write_vector(160, tuple(window_rectangle), 4, Primitive.int32)

    async def target_alpha(self) -> float:
        return await self.read_value_from_offset(212, Primitive.float32)

    async def write_target_alpha(self, target_alpha: float):
        await self.write_value_to_offset(212, target_alpha, Primitive.float32)

    async def disabled_alpha(self) -> float:
        return await self.read_value_from_offset(216, Primitive.float32)

    async def write_disabled_alpha(self, disabled_alpha: float):
        await self.write_value_to_offset(216, disabled_alpha, Primitive.float32)

    async def alpha(self) -> float:
        return await self.read_value_from_offset(208, Primitive.float32)

    async def write_alpha(self, alpha: float):
        await self.write_value_to_offset(208, alpha, Primitive.float32)

    # async def window_style(self) -> class SharedPointer<class WindowStyle>:
    #     return await self.read_value_from_offset(232, "class SharedPointer<class WindowStyle>")

    async def help(self) -> str:
        return await self.read_string_from_offset(248)

    async def write_help(self, _help: str):
        await self.write_string_to_offset(248, _help)

    async def script(self) -> str:
        return await self.read_string_from_offset(352)

    async def write_script(self, script: str):
        await self.write_string_to_offset(352, script)

    async def offset(self) -> tuple:
        return await self.read_vector(192, 2, Primitive.int32)

    async def write_offset(self, offset: tuple):
        await self.write_vector(192, offset, 2, Primitive.int32)

    async def scale(self) -> tuple:
        return await self.read_vector(200, 2)

    async def write_scale(self, scale: tuple):
        await self.write_vector(200, scale, 2)

    async def tip(self) -> str:
        return await self.read_string_from_offset(392)

    async def write_tip(self, tip: str):
        await self.write_string_to_offset(392, tip)

    # async def bubble_list(self) -> class WindowBubble:
    #     return await self.read_value_from_offset(424, "class WindowBubble")

    async def parent_offset(self) -> tuple:
        return await self.read_vector(176, 4, Primitive.int32)

    async def write_parent_offset(self, parent_offset: tuple):
        await self.write_vector(176, parent_offset, 4, Primitive.int32)

    async def is_control_grayed(self):
        # Note this is from "class ControlButton", base class is window so it works. Likely should have its own class - Click
        return await self.read_value_from_offset(688, Primitive.bool)


class DeckListControlSpellEntry(DynamicMemoryObject):
    async def graphical_spell(self) -> Optional[DynamicGraphicalSpell]:
        addr = await self.read_value_from_offset(0, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicGraphicalSpell(self.hook_handler, addr)

    async def valid_graphical_spell(self) -> int:
        return await self.read_value_from_offset(0x10, Primitive.int32)


class SpellListControlSpellEntry(DynamicMemoryObject):
    async def graphical_spell(self) -> Optional[DynamicGraphicalSpell]:
        addr = await self.read_value_from_offset(0x0, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicGraphicalSpell(self.hook_handler, addr)

    async def max_copies(self) -> int:
        return await self.read_value_from_offset(0x10, Primitive.uint32)

    async def current_copies(self) -> int:
        return await self.read_value_from_offset(0x14, Primitive.uint32)

    async def enabled(self) -> bool:
        return bool(await self.read_value_from_offset(0xA0, Primitive.uint8))

    async def _read_vector(self, address: int, size: int = 3, data_type: Primitive = Primitive.float32):
        type_str = data_type.value.format.replace("<", "")
        size_per_type = struct.calcsize(type_str)

        vector_bytes = await self.read_bytes(
            address, size_per_type * size
        )

        return struct.unpack("<" + type_str * size, vector_bytes)

    async def window_rectangle(self) -> Rectangle:
        rect_addr = await self.read_value_from_offset(0x18, Primitive.uint64)

        rect = await self._read_vector(rect_addr, 4, Primitive.int32)
        return Rectangle(*rect)


class GraphicalSpellWindow(Window):
    async def graphical_spell(self) -> Optional[DynamicGraphicalSpell]:
        addr = await self.read_value_from_offset(584, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicGraphicalSpell(self.hook_handler, addr)

class DeckListControl(Window):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def spell_entries(self) -> List[DeckListControlSpellEntry]:
        return await self.read_inlined_vector(0x280, 0x28, DeckListControlSpellEntry)

    async def card_size_horizontal(self) -> int:
        return await self.read_value_from_offset(0x2A4, Primitive.uint32)

    async def card_size_vertical(self) -> int:
        return await self.read_value_from_offset(0x2A8, Primitive.uint32)

    async def card_spacing(self) -> int:
        return await self.read_value_from_offset(0x2AC, Primitive.uint32)

    async def card_spacing_vertical_adjust(self) -> int:
        return await self.read_value_from_offset(0x2B0, Primitive.uint32)


class SpellListControl(Window):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def spell_entries(self) -> List[SpellListControlSpellEntry]:
        return await self.read_inlined_vector(0x280, 0xA8, SpellListControlSpellEntry)

    async def card_size_horizontal(self) -> int:
        return await self.read_value_from_offset(0x30C, Primitive.uint32)

    async def card_size_vertical(self) -> int:
        return await self.read_value_from_offset(0x310, Primitive.uint32)

    async def start_index(self) -> int:
        return await self.read_value_from_offset(0x308, Primitive.uint32)

    async def write_start_index(self, start_index: int):
        return await self.write_value_to_offset(0x308, start_index, Primitive.uint32)


class DynamicWindow(DynamicMemoryObject, Window):
    pass


class DynamicDeckListControl(DynamicWindow, DeckListControl):
    pass


class DynamicSpellListControl(DynamicWindow, SpellListControl):
    pass


class SpellFusionListControl(SpellListControl):
    """SpellFusionListControl (0x440 bytes) - shows tiered spell variants.
    Inherits from SpellListControl. Same offsets apply.
    Child window name: "SpellFusionList" (DeckPage offset +0x2E0)
    """
    async def read_base_address(self) -> int:
        raise NotImplementedError()


class DynamicSpellFusionListControl(DynamicWindow, SpellFusionListControl):
    pass


class DynamicGraphicalSpellWindow(DynamicWindow, GraphicalSpellWindow):
    pass


class CurrentRootWindow(Window):
    async def read_base_address(self) -> int:
        return await self.hook_handler.read_current_root_window_base()
