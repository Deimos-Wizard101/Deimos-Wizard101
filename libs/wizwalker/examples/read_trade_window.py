"""
Read the trade window's spell lists.

Prerequisites:
  - Wizard101 client must be running
  - A trade window must be open (you must be actively trading with another player)
"""

import asyncio

from wizwalker import ClientHandler
from wizwalker.memory.memory_objects.trade_window import DynamicTradeWindow


async def read_trade(client):
    trade_windows = await client.root_window.get_windows_with_name("TradeWindow")

    if not trade_windows:
        print("No trade window open. Start a trade first!")
        return

    base_addr = await trade_windows[0].read_base_address()
    trade = DynamicTradeWindow(client.hook_handler, base_addr)

    partner_gid = await trade.target_gid()
    print(f"Trading with GID: {partner_gid}")

    # === Your vault (DeckListControl) - items available to trade ===
    vault = await trade.local_spell_vault_list()
    if vault:
        entries = await vault.spell_entries()
        print(f"\nVault items available: {len(entries)}")
        for i, entry in enumerate(entries):
            try:
                spell = await entry.graphical_spell()
                if spell:
                    tid = await spell.template_id()
                    template = await spell.spell_template()
                    name = await template.name() if template else "???"
                    print(f"  [{i}] template_id={tid} name={name!r}")
                else:
                    print(f"  [{i}] graphical_spell is null")
            except Exception as e:
                print(f"  [{i}] ERROR: {e}")

    # === Your offered items (SpellListControl) ===
    local_trade = await trade.local_spell_trade_list()
    if local_trade:
        entries = await local_trade.spell_entries()
        print(f"\nYour offered items: {len(entries)}")
        for i, entry in enumerate(entries):
            try:
                spell = await entry.graphical_spell()
                if spell:
                    tid = await spell.template_id()
                    template = await spell.spell_template()
                    name = await template.name() if template else "???"
                    copies = await entry.current_copies()
                    max_copies = await entry.max_copies()
                    print(f"  [{i}] template_id={tid} name={name!r} copies={copies}/{max_copies}")
            except Exception as e:
                print(f"  [{i}] ERROR: {e}")

    # === Partner's offered items (SpellListControl) ===
    remote_trade = await trade.remote_spell_trade_list()
    if remote_trade:
        entries = await remote_trade.spell_entries()
        print(f"\nPartner's offered items: {len(entries)}")
        for i, entry in enumerate(entries):
            try:
                spell = await entry.graphical_spell()
                if spell:
                    tid = await spell.template_id()
                    template = await spell.spell_template()
                    name = await template.name() if template else "???"
                    copies = await entry.current_copies()
                    max_copies = await entry.max_copies()
                    print(f"  [{i}] template_id={tid} name={name!r} copies={copies}/{max_copies}")
            except Exception as e:
                print(f"  [{i}] ERROR: {e}")


async def main():
    handler = ClientHandler()
    client = handler.get_new_clients()[0]

    try:
        print("Activating root window hook...")
        await client.hook_handler.activate_root_window_hook()

        await read_trade(client)
    finally:
        print("Closing")
        await handler.close()


if __name__ == "__main__":
    asyncio.run(main())
