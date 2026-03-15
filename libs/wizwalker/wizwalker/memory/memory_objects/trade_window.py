from typing import Optional

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject
from .window import Window, DynamicWindow, DynamicDeckListControl, DynamicSpellListControl


class TradeWindow(Window):
    """
    TradeWindow (0x308 bytes) - loaded from TradeWindow.gui
    Inherits the base Window class and adds trade-specific fields
    starting at offset 0x248.

    Constructor: FUN_140d47240
    VTable: PTR_FUN_142aa1670
    Source: WizardGraphicalClient/GUI/HUDWindow.cpp

    Created by HUDWindow::HandleTradePlayerCreateTrade when a trade
    is accepted. Added to the WindowManager as a top-level window.

    Find via: root_window.get_windows_with_name("TradeWindow")

    Widget types (confirmed via Ghidra RTTI type checks):
      - LocalPlayerSpellVaultList: DeckListControl  (FUN_140809ef0)
      - LocalPlayerSpellTradeList: SpellListControl (FUN_140ce7570)
      - RemotePlayerSpellTradeList: SpellListControl (FUN_140ce7570)
    """

    async def read_base_address(self) -> int:
        raise NotImplementedError()

    # === Trade-specific fields (offsets from Ghidra analysis) ===

    async def target_gid(self) -> int:
        """GID of the trade partner (offset 0x288)"""
        return await self.read_value_from_offset(0x288, Primitive.uint64)

    async def is_active(self) -> bool:
        """Whether the trade is currently active (offset 0x298)"""
        return await self.read_value_from_offset(0x298, Primitive.bool)

    async def local_selected_slot(self) -> int:
        """Currently selected item slot on local side, -1 if none (offset 0x29C)"""
        return await self.read_value_from_offset(0x29C, Primitive.int32)

    async def remote_selected_slot(self) -> int:
        """Currently selected item slot on remote side, -1 if none (offset 0x2A4)"""
        return await self.read_value_from_offset(0x2A4, Primitive.int32)

    # === Child widget pointers (typed to their actual control types) ===

    async def local_spell_vault_list(self) -> Optional[DynamicDeckListControl]:
        """LocalPlayerSpellVaultList - items available to trade.
        Type: DeckListControl. Use spell_entries() to read items.
        (offset 0x2B8)"""
        addr = await self.read_value_from_offset(0x2B8, Primitive.uint64)
        if addr == 0:
            return None
        return DynamicDeckListControl(self.hook_handler, addr)

    async def local_spell_trade_list(self) -> Optional[DynamicSpellListControl]:
        """LocalPlayerSpellTradeList - items you've offered.
        Type: SpellListControl. Use spell_entries() to read items.
        (offset 0x2C0)"""
        addr = await self.read_value_from_offset(0x2C0, Primitive.uint64)
        if addr == 0:
            return None
        return DynamicSpellListControl(self.hook_handler, addr)

    async def remote_spell_trade_list(self) -> Optional[DynamicSpellListControl]:
        """RemotePlayerSpellTradeList - items partner has offered.
        Type: SpellListControl. Use spell_entries() to read items.
        (offset 0x2C8)"""
        addr = await self.read_value_from_offset(0x2C8, Primitive.uint64)
        if addr == 0:
            return None
        return DynamicSpellListControl(self.hook_handler, addr)

    async def confirmation_window(self) -> Optional[DynamicWindow]:
        """ConfirmationWindow - the 'are you sure?' dialog (offset 0x2D0)"""
        addr = await self.read_value_from_offset(0x2D0, Primitive.uint64)
        if addr == 0:
            return None
        return DynamicWindow(self.hook_handler, addr)

    async def local_status_text(self) -> Optional[DynamicWindow]:
        """StatusText widget on local player side (offset 0x2D8)"""
        addr = await self.read_value_from_offset(0x2D8, Primitive.uint64)
        if addr == 0:
            return None
        return DynamicWindow(self.hook_handler, addr)

    async def remote_status_text(self) -> Optional[DynamicWindow]:
        """StatusText widget on remote player side (offset 0x2E0)"""
        addr = await self.read_value_from_offset(0x2E0, Primitive.uint64)
        if addr == 0:
            return None
        return DynamicWindow(self.hook_handler, addr)

    async def local_ready_checkbox(self) -> Optional[DynamicWindow]:
        """LocalReadyCheckBox - ready toggle checkbox (offset 0x2E8)"""
        addr = await self.read_value_from_offset(0x2E8, Primitive.uint64)
        if addr == 0:
            return None
        return DynamicWindow(self.hook_handler, addr)

    async def item_count(self) -> int:
        """Number of items in the trade item tree (offset 0x300)"""
        return await self.read_value_from_offset(0x300, Primitive.uint64)


class DynamicTradeWindow(DynamicWindow, TradeWindow):
    """Dynamic version - constructed with a known base address.

    Usage:
        # Find the trade window in the UI tree
        root = client.root_window
        windows = await root.get_windows_with_name("TradeWindow")
        if windows:
            trade = DynamicTradeWindow(client.hook_handler, await windows[0].read_base_address())

            # Read vault (DeckListControl) - items available to trade
            vault = await trade.local_spell_vault_list()
            for entry in await vault.spell_entries():
                spell = await entry.graphical_spell()

            # Read offered items (SpellListControl)
            offered = await trade.local_spell_trade_list()
            for entry in await offered.spell_entries():
                spell = await entry.graphical_spell()
    """
    pass
