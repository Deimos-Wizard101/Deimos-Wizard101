"""Read trained spells, treasure cards, main deck, excluded item cards,
and equipped item cards from the live client.

Usage:
  py read_deck.py <wad_path> <types_path>

Arguments:
  wad_path   - Path to Root.wad, typically found at:
               C:/ProgramData/KingsIsle Entertainment/Wizard101/Data/GameData/Root.wad
  types_path - Path to types.json for deserialization

To generate types.json, install wiztype (https://github.com/wizspoil/wiztype):
  pip install wiztype
  wiztype --version 2 --indent 4
  (the game must be running when you run wiztype)

If no arguments are provided, the item card section is skipped.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from wizwalker import ClientHandler
from wizwalker.memory.memory_objects.game_object_template import WizGameObjectTemplate

# Optional katsuba import for WAD-based item card lookup
try:
    from katsuba import wad as katsuba_wad
    from katsuba.op import TypeList, SerializerOptions, Serializer, STATEFUL_FLAGS
    HAS_KATSUBA = True
except ImportError:
    HAS_KATSUBA = False


def _decode(val) -> str:
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return str(val) if val is not None else ""


def load_item_card_lookup(wad_path: Path, types_path: Path) -> dict[int, list[tuple[str, int]]]:
    """Build template_id -> [(spell_name, num_copies)] from Root.wad."""
    archive = katsuba_wad.Archive.mmap(str(wad_path))
    types = TypeList.open(str(types_path))
    opts = SerializerOptions()
    opts.flags = STATEFUL_FLAGS
    opts.shallow = False
    opts.skip_unknown_types = True
    ser = Serializer(opts, types)

    lookup = {}
    for path in archive.iter_glob("ObjectData/**/*.xml"):
        try:
            data = archive[path]
            if data.startswith(b"BINd"):
                data = data[4:]
            obj = ser.deserialize(data)

            template_id = obj.get("m_templateID")
            if template_id is None:
                continue
            template_id = int(template_id)

            effects = obj.get("m_equipEffects")
            if not effects:
                continue

            cards = []
            for effect in effects:
                try:
                    eff_name = effect.get("m_effectName")
                    if not eff_name or _decode(eff_name) != "ProvideSpell":
                        continue
                    spell_name = _decode(effect.get("m_spellName") or b"")
                    num_spells = effect.get("m_numSpells")
                    num_spells = int(num_spells) if num_spells is not None else 1
                    if spell_name:
                        cards.append((spell_name, num_spells))
                except Exception:
                    continue

            if cards:
                lookup[template_id] = cards
        except Exception:
            continue

    return lookup


async def main(wad_path: Path | None = None, types_path: Path | None = None):
    handler = ClientHandler()
    client = handler.get_new_clients()[0]

    try:
        print("Activating hooks...")
        await client.activate_hooks()
        print("Ready.\n")

        client_obj = client.client_object

        # === Trained Spells ===
        print("=== Trained Spells ===")
        spellbook = await client_obj.try_get_spellbook_behavior()
        if spellbook:
            entries = await spellbook.spell_id_list()
            for entry in entries:
                sid = await entry.spell_id()
                retired = await entry.is_retired()
                tier = await entry.tiered_spell_group_index()
                flags = []
                if retired:
                    flags.append("RETIRED")
                if tier != -1:
                    flags.append(f"tier={tier}")
                flag_str = f"  ({', '.join(flags)})" if flags else ""
                print(f"  {sid}{flag_str}")
            print(f"  Total: {len(entries)}\n")
        else:
            print("  Not found!\n")

        # === Treasure Cards ===
        print("=== Treasure Cards ===")
        tc_book = await client_obj.try_get_treasure_book_behavior()
        if tc_book:
            tcs = await tc_book.spell_list()
            total = 0
            for tc in tcs:
                tid = await tc.template_id()
                ench = await tc.enchantment()
                qty = await tc.quantity()
                total += qty
                ench_str = f"  [enchant={ench}]" if ench else ""
                print(f"  {tid} x{qty}{ench_str}")
            print(f"  Total: {len(tcs)} unique, {total} copies\n")
        else:
            print("  Not found!\n")

        # === Main Deck ===
        print("=== Main Deck ===")
        equip = await client_obj.try_get_equipment_behavior()
        deck = await client_obj.try_get_deck_behavior()

        if deck:

            spells = await deck.spell_list()
            total = 0
            for sp in spells:
                tid = await sp.template_id()
                ench = await sp.enchantment()
                qty = await sp.quantity()
                total += qty
                ench_str = f"  [enchant={ench}]" if ench else ""
                print(f"  {tid} x{qty}{ench_str}")
            print(f"  Total: {len(spells)} unique, {total} cards")

            archmastery = await deck.archmastery_school()
            print(f"  Archmastery: {archmastery}\n")

            # === Excluded Item Cards (blacklist) ===
            print("=== Excluded Item Cards ===")
            exclusions = await deck.exclusion_list()
            if exclusions:
                total_excl = 0
                for spell_id, qty in exclusions:
                    total_excl += qty
                    print(f"  {spell_id} x{qty}")
                print(f"  Total: {len(exclusions)} unique, {total_excl} excluded\n")
            else:
                print("  (none excluded)\n")
        else:
            print("  Deck not found!\n")

        # === Equipped Items & Item Cards ===
        print("=== Equipped Items & Item Cards ===")
        if equip:
            # Build item card lookup from WAD if paths were provided
            item_card_lookup = {}
            if wad_path is not None:
                print("  Loading item card data from WAD...")
                item_card_lookup = load_item_card_lookup(wad_path, types_path)
                print(f"  {len(item_card_lookup)} items with cards indexed.\n")
            else:
                print("  (no WAD path provided — run with arguments to enable item card lookup)")
                print("  Usage: py read_deck.py <wad_path> <types_path>\n")

            items = await equip.item_list()
            total_item_cards = 0
            for item in items:
                try:
                    ct = await item.object_template()
                    if ct is None:
                        continue
                    template = WizGameObjectTemplate(ct.hook_handler, ct.base_address)
                    name = await template.object_name()
                    tid = await template.template_id()

                    cards = item_card_lookup.get(tid, [])
                    if cards:
                        print(f"  {name} (id={tid}):")
                        for spell_name, num_copies in cards:
                            total_item_cards += num_copies
                            print(f"    {spell_name} x{num_copies}")
                    else:
                        print(f"  {name} (id={tid})")
                except Exception as e:
                    print(f"  (error reading item: {e})")

            print(f"\n  Total item cards from equipment: {total_item_cards}\n")
        else:
            print("  Equipment not found!\n")

    finally:
        print("Closing...")
        await handler.close()
        print("Done.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read deck, spells, and equipped item cards from the live Wizard101 client.",
        epilog=(
            "To generate types.json, install wiztype (https://github.com/wizspoil/wiztype):\n"
            "  pip install wiztype\n"
            "  wiztype --version 2 --indent 4\n"
            "  (the game must be running when you run wiztype)\n"
            "\n"
            "Root.wad is typically found at:\n"
            "  C:/ProgramData/KingsIsle Entertainment/Wizard101/Data/GameData/Root.wad"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "wad_path", nargs="?", type=Path, default=None,
        help="Path to Root.wad (omit to skip item card lookup)",
    )
    parser.add_argument(
        "types_path", nargs="?", type=Path, default=None,
        help="Path to types.json (omit to skip item card lookup)",
    )
    args = parser.parse_args()

    # If one is provided, both must be provided
    if (args.wad_path is None) != (args.types_path is None):
        parser.error("must provide both wad_path and types_path, or neither")

    if args.wad_path is not None:
        if not HAS_KATSUBA:
            print("ERROR: katsuba is required for item card lookup: pip install katsuba", file=sys.stderr)
            sys.exit(1)
        if not args.wad_path.exists():
            print(f"ERROR: WAD file not found: {args.wad_path}", file=sys.stderr)
            print("Root.wad is typically at: C:/ProgramData/KingsIsle Entertainment/Wizard101/Data/GameData/Root.wad", file=sys.stderr)
            sys.exit(1)
        if not args.types_path.exists():
            print(f"ERROR: Types file not found: {args.types_path}", file=sys.stderr)
            print("Generate with: pip install wiztype && wiztype --version 2 --indent 4 (game must be running)", file=sys.stderr)
            sys.exit(1)

    return args


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(wad_path=args.wad_path, types_path=args.types_path))
