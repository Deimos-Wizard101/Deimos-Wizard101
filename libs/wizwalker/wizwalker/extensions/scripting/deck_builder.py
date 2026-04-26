import math
import asyncio
from typing import TYPE_CHECKING, Any, Optional
from wizwalker.extensions.scripting.utils import _maybe_get_named_window
from wizwalker.memory.memory_object import MemoryReadError
from wizwalker.utils import Rectangle
from wizwalker.memory.memory_objects.window import DynamicSpellListControl, DynamicDeckListControl, SpellListControlSpellEntry, DeckListControlSpellEntry
from wizwalker.memory.memory_objects.spell import DynamicGraphicalSpell
from wizwalker.memory.memory_objects import Window
from wizwalker.memory import Window
from wizwalker import Keycode

if TYPE_CHECKING:
    from wizwalker import Client


"""
async with DeckBuilder(client) as db:
    db.add(123)

# entire deck config window
--- [DeckConfigurationWindow] SpellBookPrefsPage

# toolbar parent?
---- [ControlSprite] ControlSprite

# top bar buttons
----- [toolbar] Window

# select school
------ [TabBackground] ControlSprite
------ [Cards_Fire] ControlCheckBox
------ [Cards_Ice] ControlCheckBox
------ [Cards_Storm] ControlCheckBox
------ [Cards_Myth] ControlCheckBox
------ [Cards_All] ControlCheckBox
------ [Cards_Life] ControlCheckBox
------ [RightSideTabs] Window
------- [Cards_Death] ControlCheckBox
------- [Cards_Balance] ControlCheckBox
------- [Cards_Astral] ControlCheckBox
------- [Cards_Shadow] ControlCheckBox
------- [Cards_MonsterMagic] ControlCheckBox


# other pages (unrelated)
------ [GoToTieredWindow] Window
------- [GoToTieredGlow] ControlSprite
------- [GoToTiered] ControlCheckBox
------ [GoToGardening] ControlCheckBox
------ [GoToFishing] ControlCheckBox
------ [GoToCantrips] ControlCheckBox
------ [GoToCastleMagic] ControlCheckBox
------ [GoBackToCastleMagic] ControlCheckBox
------ [GoBackToFishing] ControlCheckBox
------ [GoBackToGardening] ControlCheckBox
------ [GoBackToTieredWindow] Window
------- [GoBackToTieredGlow] ControlSprite
------- [GoBackToTiered] ControlCheckBox


# just parent window?
----- [DeckPage] Window

?
------ [PageUp] ControlButton
------ [PageDown] ControlButton

# cards to add to deck?
------ [SpellList] SpellListControl

# equip icon
------ [EquipBorder] ControlWidget

# ?
------ [InvBorder] ControlWidget

# cards given by items? (most likely)
------ [ItemSpells] DeckListControl

# ?
------ [ControlSprite] ControlSprite

# deck selection
------ [PrevDeck] ControlButton
------ [NextDeck] ControlButton

# deck name
------ [DeckName] ControlText

# equip icon?
------ [equipFist] Window

# spells added to normal deck (may also be used for tc)
------ [CardsInDeck] DeckListControl


# tc info
------ [TreasureCardCountBackground] Window
------ [TreasureCardCount] ControlText
------ [TreasureCardIcon] Window

# rename deck
------ [NewDeckName] ControlButton

# select deck
------ [EquipButton] ControlButton

# next card selection page?
------ [NextItemSpells] ControlButton
------ [PrevItemSpells] ControlButton

# help button
------ [Help] ControlButton

# clear deck (hidden on small decks; try unhiding)
------ [ClearDeckButton] ControlButton

# quick sell tc
------ [QuickSellButton] ControlButton

# ?
----- [ControlSprite] ControlSprite
------ [DeckTitle] ControlText
----- [TutorialLogBackground1] ControlSprite

# switch to tc view
----- [TreasureCardButton] ControlCheckBox


builder.add_card_by_name("unicorn", number_of_copies: int | None)
-> number_of_copies = None: add max copies 
-> raises: ValueError(already at max copies)
-> raises: ValueError(card not found)

builder.remove_card_by_name("unicorn", number_of_copies: int | None)
-> inverse

builder.add_by_predicate(pred, number_of_copies: int | None)
-> see add_card_by_name
def pred(spell: graphical spell):
    return True or False

builder.remove_by_predicate(pred, number_of_copies: int | None)
-> inverse

builder.get_deck_preset() -> dict[...]
{
    normal: {template id: number of copies},
    tc: {template id: number of copies},
    item: {template id: number of copies}
}
-> 


builder.set_deck_preset(dict[see above], ignore_failures: bool = False)
-> removes and adds cards as needed for a preset which is a dict

"""


class DeckBuilder:
    """
    async with DeckBuilder(client) as deck_builder:
        # adds two unicorns
        await deck_builder.add_by_name("Unicorn", 2)
    """

    def __init__(self, client: "Client"):
        self.client = client
        self._deck_config_window = None
        self._on_deck_page = False
        self._deck_open = False

    async def open(self):
        await self.open_deck_page()

    async def close(self):
        await self.close_deck_page()

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @staticmethod
    def calculate_icon_position(
            card_number: int,
            horizontal_size: int = 33,
            vertical_size: int = 33,
            number_of_rows: int = 8,
            horizontal_spacing: int = 6,
            vertical_spacing: int = 0,
    ):
        x = (horizontal_size * card_number) - (horizontal_size // 2) + \
            (horizontal_spacing * (card_number - 1))
        y = (vertical_size * (((card_number - 1) // number_of_rows) + 1))\
            - (vertical_size // 2) + \
            (vertical_spacing * ((card_number - 1) // number_of_rows))
        return x, y

    async def open_deck_page(self) -> None:
        """
        Opens deck page
        """
        if self._deck_open:
            return
        try:
            self._deck_config_window = await _maybe_get_named_window(self.client.root_window, "DeckConfiguration")
        except ValueError:
            self._deck_config_window = None

        if not self._deck_config_window:
            spellbook = await _maybe_get_named_window(self.client.root_window, "btnSpellbook")
            async with self.client.mouse_handler:
                await self.client.send_key(Keycode.P)
            self._deck_config_window = await _maybe_get_named_window(self.client.root_window, "DeckConfiguration")

        deck_button = await _maybe_get_named_window(self._deck_config_window, "Deck")
        async with self.client.mouse_handler:
            await self.client.mouse_handler.click_window(deck_button)
        cards_all = await _maybe_get_named_window(self._deck_config_window, "Cards_All")
        if await cards_all.is_visible():
            async with self.client.mouse_handler:
                await self.client.mouse_handler.click_window(cards_all)
        self._deck_open = True

    async def close_deck_page(self) -> None:
        if not self._deck_open:
            return
        try:
            self._deck_config_window = await _maybe_get_named_window(self.client.root_window, "DeckConfiguration")
        except ValueError:
            self._deck_config_window = None

        if self._deck_config_window:
            spellbook = await _maybe_get_named_window(self.client.root_window, "btnSpellbook")
            async with self.client.mouse_handler:
                await self.client.send_key(Keycode.P)
        # NOTE: True because the next time you open deck, it has to be on deck page
        self._on_deck_page = True
        self._deck_open = False

    async def refresh_deck_page(self) -> None:
        async with self.client.mouse_handler:
            if self._deck_open:
                await self.client.send_key(Keycode.P)
            await self.client.send_key(Keycode.P)
            self._deck_open = True
            self._on_deck_page = True
        self._deck_config_window = await _maybe_get_named_window(self.client.root_window, "DeckConfiguration")
        # spellbook = await _maybe_get_named_window(self.client.root_window, "btnSpellbook")
        # async with self.client.mouse_handler:
        #     if self._deck_open:
        #         await self.client.mouse_handler.click_window(spellbook)
        #     await self.client.mouse_handler.click_window(spellbook)
        #     self._deck_open = True
        #     self._on_deck_page = True
        # self._deck_config_window = await _maybe_get_named_window(self.client.root_window, "DeckConfiguration")

    async def switch_card_type_window(self) -> None:
        await self.open_deck_page()
        # Above clicks all cards so we dont need to do it again
        treasure_card_button = await _maybe_get_named_window(self._deck_config_window, "TreasureCardButton")
        async with self.client.mouse_handler:
            await self.client.mouse_handler.click_window(treasure_card_button)
        self._on_deck_page = not self._on_deck_page

    async def view_deck_cards(self) -> None:
        if not self._on_deck_page:
            await self.switch_card_type_window()

    async def view_tc_cards(self) -> None:
        if self._on_deck_page:
            await self.switch_card_type_window()

    async def get_spell_list(self) -> list[SpellListControlSpellEntry]:
        spell_list_window = await _maybe_get_named_window(self._deck_config_window, "SpellList")
        spell_list_control = DynamicSpellListControl(self.client.hook_handler, await spell_list_window.read_base_address())
        list_of_spell_entries = await spell_list_control.spell_entries()
        list_of_valid_spell_entries = []
        # We are doing this to check for valid spells. Sometimes the returned value isn't valid
        for spell in list_of_spell_entries:
            try:
                graphical = await spell.graphical_spell()
                if (not graphical):
                    continue
                template = await graphical.spell_template()
                if (not template):
                    continue
                await template.name()
                list_of_valid_spell_entries.append(spell)
            except:
                pass
        return list_of_valid_spell_entries

    async def get_tiered_spell_list(self) -> list[SpellListControlSpellEntry]:
        """Get valid spell entries from the TieredSpellMPUnlockedList."""
        tiered_window = await _maybe_get_named_window(self._deck_config_window, "TieredSpellMPUnlockedList")
        tiered_control = DynamicSpellListControl(
            self.client.hook_handler, await tiered_window.read_base_address()
        )
        list_of_spell_entries = await tiered_control.spell_entries()
        list_of_valid_spell_entries = []
        for spell in list_of_spell_entries:
            try:
                graphical = await spell.graphical_spell()
                if not graphical:
                    continue
                template = await graphical.spell_template()
                if not template:
                    continue
                await template.name()
                list_of_valid_spell_entries.append(spell)
            except:
                pass
        return list_of_valid_spell_entries

    async def tiered_spell_list_match_template(self, template_name: str) -> list[SpellListControlSpellEntry]:
        """Search the TieredSpellMPUnlockedList for a spell by template name."""
        async def tiered_get_cards_with_predicate(pred: Any) -> list:
            cards = []
            spell_list = await self.get_tiered_spell_list()
            for spell in spell_list:
                if await pred(spell):
                    cards.append(spell)
            return cards
        return await self._pred_match_template_name(tiered_get_cards_with_predicate, template_name)

    async def get_tiered_spell_list_rectangle(self) -> Rectangle:
        """Get the rectangle for the TieredSpellMPUnlockedList window."""
        tiered_list = await _maybe_get_named_window(self._deck_config_window, "TieredSpellMPUnlockedList")
        return await tiered_list.scale_to_client()

    async def set_tiered_spell_page(self, page_number: int):
        """Set the page for the TieredSpellMPUnlockedList."""
        tiered_window = await _maybe_get_named_window(self._deck_config_window, "TieredSpellMPUnlockedList")
        tiered_control = DynamicSpellListControl(
            self.client.hook_handler, await tiered_window.read_base_address()
        )
        await tiered_control.write_start_index(page_number * 6)

    async def get_graphical_tiered_spell_cards(self) -> list[DynamicGraphicalSpell]:
        """Get graphical spell objects from the tiered spell list."""
        list_of_spell_entries = await self.get_tiered_spell_list()
        list_of_spell_graphicals = []
        for spell in list_of_spell_entries:
            graphical = await spell.graphical_spell()
            list_of_spell_graphicals.append(graphical)
        return list_of_spell_graphicals

    async def calculate_tiered_spell_card_position(self, card_number) -> tuple[int, int]:
        """Calculate click position for a card in the tiered spell list.
        The TieredSpellMPUnlockedList uses a 6-slot grid but the first 2
        slots are spacers. Real cards are in slots 3-6 (1-based).
        """
        tiered_rect = await self.get_tiered_spell_list_rectangle()
        rectangle_list = self.divide_rectangle(tiered_rect)
        # Offset by 2 slots for the spacers
        card_rectangle = rectangle_list[card_number - 1 + 2]
        return card_rectangle.center()

    async def get_deck_count(self) -> int:
        spell_slot_rect = await self.get_deck_list_rectangle()
        spell_slots = self.divide_rectangle(spell_slot_rect, 8, 8)
        min = 0
        max = 64
        idx = int(max/2)
        ever_found = False
        async with self.client.mouse_handler:
            while True:
                found = False
                await self.client.mouse_handler.set_mouse_position(*spell_slots[idx].center())
                world_view = await self.client.get_world_view_window()
                world_view_children = await world_view.children()
                for graphical_spell_window in world_view_children:
                    name = await graphical_spell_window.maybe_read_type_name()
                    if name == 'GraphicalSpellWindow':
                        found = ever_found = True
                        await asyncio.sleep(.05)
                if max-min <= 1:
                    if idx == 0 and not ever_found:
                        return 0
                    return idx+1
                if found:
                    min = idx
                else:
                    max = idx
                idx = int((max-min)/2+min)

    async def get_deck_spell_list(self) -> list[DeckListControlSpellEntry]:
        cards_in_deck_window = await _maybe_get_named_window(self.client.root_window, "CardsInDeck")
        deck_list_control = DynamicDeckListControl(self.client.hook_handler, await cards_in_deck_window.read_base_address())
        list_of_deck_spell_entries = await deck_list_control.spell_entries()
        list_of_valid_deck_spell_entries = []
        deck_count = await self.get_deck_count()
        for idx, entry in enumerate(list_of_deck_spell_entries):
            try:
                graphical = await entry.graphical_spell()
                if not graphical:
                    continue
                template = await graphical.spell_template()
                if not template:
                    continue
                if idx > deck_count-1:
                    break
                list_of_valid_deck_spell_entries.append(entry)
            except MemoryReadError:
                pass
        return list_of_valid_deck_spell_entries

    async def get_item_card_list(self) -> list[DeckListControlSpellEntry]:
        cards_in_item_spell_window = await _maybe_get_named_window(self.client.root_window, "ItemSpells")
        item_list_control = DynamicDeckListControl(self.client.hook_handler, await cards_in_item_spell_window.read_base_address())
        list_of_item_spell_entries = await item_list_control.spell_entries()
        list_of_valid_item_spell_entries = []
        item_count = await self.get_item_card_count()
        for idx, entry in enumerate(list_of_item_spell_entries):
            try:
                graphical = await entry.graphical_spell()
                if not graphical:
                    continue
                template = await graphical.spell_template()
                if not template:
                    continue
                if idx > item_count-1:
                    break
                list_of_valid_item_spell_entries.append(entry)
            except MemoryReadError:
                pass
        return list_of_valid_item_spell_entries

    async def get_item_card_count(self):
        spell_slot_rect = await self.get_item_spells_rectangle()
        spell_slots = self.divide_rectangle(spell_slot_rect, 8, 2)
        min = 0
        max = 16
        idx = int(max/2)
        ever_found = False
        async with self.client.mouse_handler:
            while True:
                found = False
                await self.client.mouse_handler.set_mouse_position(*spell_slots[idx].center())
                world_view = await self.client.get_world_view_window()
                world_view_children = await world_view.children()
                for graphical_spell_window in world_view_children:
                    name = await graphical_spell_window.maybe_read_type_name()
                    if name == 'GraphicalSpellWindow':
                        found = ever_found = True
                        await asyncio.sleep(.05)
                if max-min <= 1:
                    if idx == 0 and not ever_found:
                        return 0
                    return idx+1
                if found:
                    min = idx
                else:
                    max = idx
                idx = int((max-min)/2+min)

    async def get_active_item_card_list(self) -> list[DeckListControlSpellEntry]:
        list_of_active_item_cards = []
        every_item_card = (await self.get_item_card_list())
        item_spells_rect = await self.get_item_spells_rectangle()
        divided_item_spells_rect = self.divide_rectangle(
            item_spells_rect, columns=8, rows=2)
        item_card_window: Window = await _maybe_get_named_window(self.client.root_window, "ItemSpells")
        sprites = await item_card_window.children()
        positions: list[Rectangle] = []
        for sprite in sprites:
            rect = await sprite.scale_to_client()
            positions.append(rect)
        for index, card in enumerate(divided_item_spells_rect):
            for pos in positions:
                if abs(pos.x1 - card.x1) < 15 and abs(pos.y1 - card.y1) < 15:
                    list_of_active_item_cards.append(every_item_card[index])
        return [item for item in every_item_card if item not in list_of_active_item_cards]

    async def get_graphical_spell_cards(self) -> list[DynamicGraphicalSpell]:
        # We use this to get a list of DynamicGraphicalSpell which we then pull the names from later on
        list_of_spell_entries = await self.get_spell_list()
        list_of_spell_graphicals = []
        for spell in list_of_spell_entries:
            graphical = await spell.graphical_spell()
            list_of_spell_graphicals.append(graphical)
        return list_of_spell_graphicals

    async def get_graphical_deck_cards(self) -> list[DynamicGraphicalSpell]:
        list_of_deck_spell_entries = await self.get_deck_spell_list()
        list_of_deck_spell_graphicals = []
        for spell in list_of_deck_spell_entries:
            graphical = await spell.graphical_spell()
            try:
                if (not graphical):
                    continue
                template = await graphical.spell_template()
                if (not template):
                    continue
                valid_graphical_spell = await spell.valid_graphical_spell()
                if await template.name() == '':
                    continue
                elif valid_graphical_spell == 0 or valid_graphical_spell == 3:
                    if not await graphical.maybe_read_type_name() == '':
                        list_of_deck_spell_graphicals.append(graphical)
            except:
                pass
        return list_of_deck_spell_graphicals

    async def clear_item_deck(self) -> None:
        await self.view_deck_cards()
        while (True):
            await asyncio.sleep(.5)
            await self.refresh_deck_page()
            await asyncio.sleep(.5)
            item_spells_rect = await self.get_item_spells_rectangle()
            divided_item_spells_rect = self.divide_rectangle(
                item_spells_rect, columns=8, rows=2)
            item_cards = await self.get_item_card_list()
            active_item_cards = await self.get_active_item_card_list()
            if len(active_item_cards) <= 0:
                break
            cards = []
            for idx, item in enumerate(item_cards):
                is_active = True in [
                    item.base_address == other.base_address for other in active_item_cards]
                if is_active:
                    cards.append(idx)
            for card in cards:
                async with self.client.mouse_handler:
                    await self.client.mouse_handler.click(*divided_item_spells_rect[card].center())

    async def clear_deck(self) -> None:
        await self.view_deck_cards()
        try:
            clear_deck_button = await _maybe_get_named_window(self._deck_config_window, "ClearDeckButton")
            async with self.client.mouse_handler:
                await self.client.mouse_handler.click_window(clear_deck_button)

            message_box_modal_window = await _maybe_get_named_window(self.client.root_window, "MessageBoxModalWindow")
            leftButton = await _maybe_get_named_window(message_box_modal_window, "leftButton")
            async with self.client.mouse_handler:
                await self.client.mouse_handler.click_window(leftButton)
        except:
            number_of_cards = await self.get_deck_count()
            if number_of_cards == 0:
                return
            await self.clear_deck_manual()
            # We run it again because it might be clicking to fast. It's fast enough that I dont care to run it again
            await self.clear_deck()

    async def clear_deck_manual(self) -> None:
        number_of_cards = await self.get_deck_count()
        if number_of_cards == 0:
            return
        first_card_position = await self.calculate_deck_card_position(1)
        for _ in range(number_of_cards):
            async with self.client.mouse_handler:
                await self.client.mouse_handler.click(*first_card_position)

    async def clear_deck_tcs(self) -> None:
        await self.view_tc_cards()
        number_of_cards = await self.get_deck_count()
        if number_of_cards == 0:
            return
        await self.clear_deck_manual()
        # We run it again because it might be clicking to fast. It's fast enough that I dont care to run it again
        await self.clear_deck_tcs()

    async def clear_full_deck(self):
        await self.clear_deck()
        await self.clear_item_deck()
        await self.clear_deck_tcs()

    async def _pred_match_template_name(self, coro: Any, template_name: str):
        # I know it works but I still don't understand predicates.
        """
        Args:
            coro: pred function to call
            template_name: The debug name of the cards to find
        Returns: list of possibility with the name
        """

        async def _pred(card):
            graphical = await card.graphical_spell()
            if not graphical:
                return False
            template = await graphical.spell_template()
            if not template:
                return False
            try:
                return template_name == await template.name()
            except MemoryReadError:
                return False

        return await coro(_pred)

    async def spell_list_match_template(self, template_name: str) -> list[SpellListControlSpellEntry]:
        async def spell_list_get_cards_with_predicate(pred: Any) -> list[DynamicGraphicalSpell]:
            """
            Return cards that match a predicate

            Args:
                pred: The predicate function
            """
            cards = []
            spell_list = await self.get_spell_list()
            for spell in spell_list:
                if await pred(spell):
                    cards.append(spell)

            return cards
        return await self._pred_match_template_name(spell_list_get_cards_with_predicate, template_name)

    async def deck_list_match_template(self, template_name: str) -> SpellListControlSpellEntry:
        async def deck_list_get_cards_with_predicate(pred: Any) -> list[DynamicGraphicalSpell]:
            """
            Return cards that match a predicate

            Args:
                pred: The predicate function
            """
            cards = []
            spell_list = await self.get_deck_spell_list()
            for spell in spell_list:
                if await pred(spell):
                    cards.append(spell)

            return cards
        return await self._pred_match_template_name(deck_list_get_cards_with_predicate, template_name)

    async def set_page(self, page_number: int):
        # Write memory address value to update the card page
        spell_list_window = await _maybe_get_named_window(self._deck_config_window, "SpellList")
        spell_list_control = DynamicSpellListControl(self.client.hook_handler, await spell_list_window.read_base_address())
        await spell_list_control.write_start_index(page_number*6)

    async def get_spell_list_rectangle(self) -> Rectangle:
        # Returns the size of the window as a rectangle so we can subdivide it later
        self._deck_config_window = await _maybe_get_named_window(self.client.root_window, "DeckConfiguration")
        self.spell_list = await _maybe_get_named_window(self._deck_config_window, "SpellList")
        self.spell_list_scaled = await self.spell_list.scale_to_client()
        return self.spell_list_scaled

    async def get_deck_list_rectangle(self) -> Rectangle:
        # Returns the size of the window as a rectangle so we can subdivide it later
        self._deck_config_window = await _maybe_get_named_window(self.client.root_window, "DeckConfiguration")
        self.deck_list = await _maybe_get_named_window(self._deck_config_window, "CardsInDeck")
        self.deck_list_scaled = await self.deck_list.scale_to_client()
        return self.deck_list_scaled

    async def get_item_spells_rectangle(self) -> Rectangle:
        # Returns the size of the window as a rectangle so we can subdivide it later
        self._deck_config_window = await _maybe_get_named_window(self.client.root_window, "DeckConfiguration")
        self.deck_list = await _maybe_get_named_window(self._deck_config_window, "ItemSpells")
        self.deck_list_scaled = await self.deck_list.scale_to_client()
        return self.deck_list_scaled

    def divide_rectangle(self, rectangle: Rectangle, columns: int = 2, rows=3) -> list[Rectangle]:
        # This function takes a window element and subdivides it into Columns X Rows
        # We use this to divide up the CardsInDeck and SpellList windows as the
        # cards inside the windows aren't windows themselves, unfortunately.
        width = rectangle.x2 - rectangle.x1
        height = rectangle.y2 - rectangle.y1

        # Calculate the dimensions of each smaller rectangle
        sub_width = width / columns
        sub_height = height / rows

        rectangles = []

        # Generate the smaller rectangles
        for rows in range(rows):
            for column in range(columns):
                sub_x1 = int(rectangle.x1 + column * sub_width)
                sub_y1 = int(rectangle.y1 + rows * sub_height)
                sub_x2 = int(sub_x1 + sub_width)
                sub_y2 = int(sub_y1 + sub_height)

                rectangles.append(Rectangle(sub_x1, sub_y1, sub_x2, sub_y2))

        return rectangles

    async def calculate_card_position(self, card_number) -> tuple[int, int]:
        spell_list_rectangle = await self.get_spell_list_rectangle()
        rectangle_list = self.divide_rectangle(spell_list_rectangle)
        card_rectangle = rectangle_list[card_number - 1]
        return card_rectangle.center()

    async def calculate_deck_card_position(self, card_number) -> tuple[int, int]:
        spell_list_rectangle = await self.get_deck_list_rectangle()
        rectangle_list = self.divide_rectangle(
            spell_list_rectangle, columns=8, rows=8)
        card_rectangle = rectangle_list[card_number - 1]
        return card_rectangle.center()

    def calcuate_position_of_card_in_page(self, cards: list, name: str) -> tuple[int, int]:
        number_of_cards_per_page = 6
        index_of_card = cards.index(name) + 1
        page_index = math.ceil(index_of_card / number_of_cards_per_page) - 1
        index = (index_of_card) % number_of_cards_per_page
        if index == 0:
            index = 6
        return page_index, index

    async def log_user_in_and_out(self):
        await self.client.send_key(Keycode.ESC, 0.1)
        quit_button = await _maybe_get_named_window(self.client.root_window, "QuitButton")
        async with self.client.mouse_handler:
            await self.client.mouse_handler.click_window(quit_button)

        while True:
            try:
                play_button = await _maybe_get_named_window(self.client.root_window, "btnPlay")
                break
            except ValueError:
                pass
        async with self.client.mouse_handler:
            await self.client.mouse_handler.click_window(play_button)
        while True:
            try:
                await _maybe_get_named_window(self.client.root_window, "btnSpellbook")
                break
            except ValueError:
                pass
        print('User has logged out and logged back in')

    async def add_item_cards(self, section: dict):
        sleep: float = 0
        items = section.items()
        every_item_card = await self.get_item_card_list()
        found = True
        not_found = ""
        for item in items:
            _found = False
            for item_card in every_item_card:
                graphical = await item_card.graphical_spell()
                if (not graphical):
                    print("ERROR: not template")
                    continue
                template = await graphical.spell_template()
                if (not template):
                    print("ERROR: not graphical")
                    continue
                template_name = await template.name()
                if item[0] == template_name:
                    _found = True
            if not _found:
                found = False
                not_found = item[0]
                break
        if not found:
            raise Exception(f"Could not find card: {not_found}")

        # iter_count = 0
        while True:
            await self.refresh_deck_page()
            every_item_card = await self.get_item_card_list()
            active_item_cards = await self.get_active_item_card_list()
            cards = []
            total = 0
            for item in items:
                await asyncio.sleep(sleep)
                await self.add_item_by_name(item[0], item[1], active_item_cards, every_item_card, sleep)
            await asyncio.sleep(0.5)
            await self.refresh_deck_page()
            every_item_card = await self.get_item_card_list()
            active_item_cards = await self.get_active_item_card_list()
            for idx, item in enumerate(items):
                card_count = 0
                total += item[1]
                for card in active_item_cards:
                    graphical = await card.graphical_spell()
                    if (not graphical):
                        print("ERROR: not template")
                        continue
                    template = await graphical.spell_template()
                    if (not template):
                        print("ERROR: not graphical")
                        continue
                    template_name = await template.name()
                    if template_name == item[0]:
                        cards.append((item, idx))
                        card_count += 1
                    if card_count >= item[1]:
                        break
            if len(cards) == total:
                return
            else:
                await self.clear_item_deck()
            if sleep > 2:
                sleep = 2
            else:
                sleep += .2
            # if iter_count > 2:
            #    iter_count = 0

            # iter_count+=1

    async def add_item_by_name(self, name: str, number_of_copies: int, active_item_cards: list[DeckListControlSpellEntry], item_cards: list[DeckListControlSpellEntry], sleep):
        """
        builder.add_card_by_name("unicorn", number_of_copies: int | None)
        -> number_of_copies = None: add max copies
        -> raises: ValueError(already at max copies)
        -> raises: ValueError(card not found)
        """
        item_spells_rect = await self.get_item_spells_rectangle()
        divided_item_spells_rect = self.divide_rectangle(
            item_spells_rect, columns=8, rows=2)
        cards = []
        for idx, item in list(enumerate(item_cards))[::-1]:
            graphical = await item.graphical_spell()
            if (not graphical):
                continue
            template = await graphical.spell_template()
            if (not template):
                continue
            try:
                template_name = await template.name()
            except MemoryReadError:
                return
            if template_name == name:
                cards.append((item, idx))
        inactive_cards = []
        active_cards = []
        for item in cards:
            graphical = await item[0].graphical_spell()
            if (not graphical):
                continue
            template = await graphical.spell_template()
            if (not template):
                continue
            try:
                template_name = await template.name()
            except MemoryReadError:
                return
            found = False
            for card in active_item_cards:
                graphical = await card.graphical_spell()
                if (not graphical):
                    continue
                template = await graphical.spell_template()
                if (not template):
                    continue
                card_template_name = await template.name()
                if template_name == card_template_name:
                    found = True
                    active_cards.append(item)
                    break

            if not found:
                inactive_cards.append(item)

        if len(active_cards) > number_of_copies:
            if len(active_item_cards)-number_of_copies > len(active_cards):
                return
            for index in range(len(active_cards)-number_of_copies):
                async with self.client.mouse_handler:
                    await self.client.mouse_handler.click(*divided_item_spells_rect[active_cards[index][1]].center())
                    await asyncio.sleep(sleep)
        elif len(active_cards) < number_of_copies:
            if number_of_copies-len(active_item_cards) > len(inactive_cards):
                return
            for index in range(number_of_copies-len(active_cards)):
                async with self.client.mouse_handler:
                    await self.client.mouse_handler.click(*divided_item_spells_rect[inactive_cards[index][1]].center())
                    await asyncio.sleep(sleep)

    async def _add_from_spell_list(self, name: str, number_of_copies: int):
        """Add a card by clicking it in the main SpellList."""
        list_of_spells = await self.get_graphical_spell_cards()
        list_of_spell_names = []
        for spell in list_of_spells:
            template = await spell.spell_template()
            if not template:
                continue
            list_of_spell_names.append(await template.name())
        card_page, card_index_on_page = self.calcuate_position_of_card_in_page(
            list_of_spell_names, name)
        card_position_on_page = await self.calculate_card_position(card_index_on_page)
        await self.set_page(card_page)
        async with self.client.mouse_handler:
            for _ in range(number_of_copies):
                await self.client.mouse_handler.click(*card_position_on_page)

    async def _add_from_tiered_spell_list(self, name: str, number_of_copies: int):
        """Add a tiered spell variant by clicking the base spell to open the
        tiered view, then clicking the specific variant.

        Flow: find base spell in SpellList -> click to open tiered view ->
        find variant in TieredSpellMPUnlockedList -> click the variant.
        """
        # Extract the base spell name (everything before " - T")
        base_name_end = name.find(" - T")
        if base_name_end == -1:
            raise Exception(f"Card not found: {name}")

        base_name = name[:base_name_end]

        # Find and click the base spell in the main spell list to open tiered view
        list_of_spells = await self.get_graphical_spell_cards()
        list_of_spell_names = []
        for spell in list_of_spells:
            template = await spell.spell_template()
            if not template:
                continue
            list_of_spell_names.append(await template.name())

        if base_name not in list_of_spell_names:
            raise Exception(f"Base spell '{base_name}' not found for tiered spell '{name}'")

        card_page, card_index_on_page = self.calcuate_position_of_card_in_page(
            list_of_spell_names, base_name)
        card_position_on_page = await self.calculate_card_position(card_index_on_page)
        await self.set_page(card_page)

        # Click the base spell to open the tiered spell list
        async with self.client.mouse_handler:
            await self.client.mouse_handler.click(*card_position_on_page)

        # Find the variant in the tiered spell list
        tiered_cards = await self.tiered_spell_list_match_template(name)
        if len(tiered_cards) <= 0:
            raise Exception(f"Tiered variant '{name}' not found in tiered spell list")

        # Find position and click in the tiered spell list
        tiered_spells = await self.get_graphical_tiered_spell_cards()
        tiered_names = []
        for spell in tiered_spells:
            template = await spell.spell_template()
            if not template:
                continue
            tiered_names.append(await template.name())

        tiered_page, tiered_index = self.calcuate_position_of_card_in_page(
            tiered_names, name)
        tiered_position = await self.calculate_tiered_spell_card_position(tiered_index)
        await self.set_tiered_spell_page(tiered_page)
        async with self.client.mouse_handler:
            for _ in range(number_of_copies):
                await self.client.mouse_handler.click(*tiered_position)

        # Close the tiered spell page and return to the normal spell list
        try:
            close_btn = await _maybe_get_named_window(
                self._deck_config_window, "CloseTSMPUnlockedPageButton"
            )
            async with self.client.mouse_handler:
                await self.client.mouse_handler.click_window(close_btn)
        except ValueError:
            # Button not found, fall back to refreshing the deck page
            await self.refresh_deck_page()

    async def add_by_name(self, name: str, number_of_copies: Optional[int]):
        """
        builder.add_card_by_name("unicorn", number_of_copies: int | None)
        -> number_of_copies = None: add max copies
        -> raises: ValueError(already at max copies)
        -> raises: ValueError(card not found)
        """
        cards: list[SpellListControlSpellEntry] = await self.spell_list_match_template(name)
        is_tiered = len(cards) <= 0

        if is_tiered:
            # Card not in main spell list — check if it's a tiered variant
            # (names containing " - T") behind the TieredSpellMPUnlockedList
            if " - T" not in name:
                raise Exception(f"Card not found: {name}")
            # For tiered spells, we need to open the tiered view to check
            # copies. Just proceed with the requested count.
            if number_of_copies is None or number_of_copies <= 0:
                number_of_copies = 1
            await self._add_from_tiered_spell_list(name, number_of_copies)
        else:
            card = cards[0]

            if number_of_copies is None:
                number_of_copies = (await card.max_copies()) - (await card.current_copies())

            if await card.max_copies() == await card.current_copies():
                raise ValueError(f"already at max copies for {name}")
            elif await card.max_copies() < (await card.current_copies()) + (number_of_copies):
                raise ValueError(
                    f"number of copies is greater than the card allows")

            await self._add_from_spell_list(name, number_of_copies)

    async def remove_by_name(self, name: str, number_of_copies: int):
        desk_list = await self.get_graphical_deck_cards()
        list_of_spell_names = []
        calcuated_copies = 0
        for spell in desk_list:
            template = await spell.spell_template()
            if (not template):
                continue
            list_of_spell_names.append(await template.name())
            if await template.name() == name:
                calcuated_copies = calcuated_copies + 1
        if number_of_copies != calcuated_copies:
            raise ValueError(f"Trying to delete more '{name}' spells than are in the deck")
        index = list_of_spell_names.index(name)
        deck_rect = await self.get_deck_list_rectangle()
        divided_deck_rect = self.divide_rectangle(deck_rect, columns=8, rows=8)
        sign_card = divided_deck_rect[index]
        if (not number_of_copies):
            await asyncio.sleep(1)
            return
        async with self.client.mouse_handler:
            for _ in range(number_of_copies):
                await self.client.mouse_handler.click(*(sign_card.center()))
                await asyncio.sleep(1)

    async def parse_deck_cards(self, tc: bool = False) -> list:
        list_of_deck_spells = await self.get_graphical_deck_cards()
        card_names = []
        for spell in list_of_deck_spells:
            template = await spell.spell_template()
            if (not template):
                continue
            card_name = await template.name()
            is_tc = await template.treasure()
            if not tc and is_tc:
                continue
            elif card_name is None:
                continue
            card_names.append(card_name)
        list_of_deck_spells = []
        return card_names

    async def get_deck_preset(self) -> dict:
        # get_deck_preset works but objects in memory cause artifacting with treasure cards
        """
        builder.get_deck_preset() -> dict[...]
        {
            normal: {template id: number of copies},
            tc: {template id: number of copies},
            item: {template id: number of copies}
        }
        """
        def dict_maker(_list: list):
            d = {}
            for card in _list:
                if card in d:
                    d[card] = d[card] + 1
                else:
                    d[card] = 1
            return d
        normal_cards = []
        tc_cards = []
        item_cards = []
        assert (self._deck_config_window is not None)
        # Below we are checking if deck window is already open because
        # we can't determine what page the user is on (tc/normal)
        await self.refresh_deck_page()
        normal_cards = await self.parse_deck_cards()
        await self.view_deck_cards()
        item_cards_spell_list = await self.get_active_item_card_list()
        await self.view_tc_cards()
        tc_cards = await self.parse_deck_cards(True)
        for card in item_cards_spell_list:
            graphical = await card.graphical_spell()
            if (not graphical):
                continue
            template = await graphical.spell_template()
            if (not template):
                continue
            card_name = await template.name()
            item_cards.append(card_name)
        deck = {
            'normal': dict_maker(normal_cards),
            'item': dict_maker(item_cards),
            'tc': dict_maker(tc_cards),
        }
        return deck

    async def set_deck_preset(self, preset: dict):
        await self.refresh_deck_page()
        await self.clear_full_deck()
        deck_section = preset.keys()
        for section in deck_section:
            if section == "normal":
                await self.view_deck_cards()
                for card in (preset[section]).keys():
                    await self.add_by_name(card, (preset[section])[card])
            elif section == "item":
                await self.view_deck_cards()
                await self.add_item_cards(preset[section])
            elif section == "tc":
                await self.view_tc_cards()
                for card in (preset[section]).keys():
                    await self.add_by_name(card, (preset[section])[card])


if __name__ == "__main__":
    pass
