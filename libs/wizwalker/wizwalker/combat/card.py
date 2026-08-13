import asyncio
from typing import List, Optional, Union

import wizwalker


# TODO: add way to cast divide spells (remember to click the confirm button after targeting)
#  cast_divide?
class CombatCard:
    """
    Represents a spell card
    """

    def __init__(
        self,
        combat_handler,
        spell_window: "wizwalker.memory.window.DynamicWindow",
    ):
        self.combat_handler = combat_handler

        self._spell_window = spell_window

    # TODO: add checks before casting
    async def cast(
        self,
        target: Union["CombatCard", "wizwalker.combat.CombatMember", "List", None],
        *,
        sleep_time: Optional[float] = 1.0,
        debug_paint: bool = False,
    ):
        """
        Cast this Card on another Card; a Member or with no target

        Args:
            target: Card, Member, or None if there is no target
            sleep_time: How long to sleep after enchants and between multicasts or None for no sleep
            debug_paint: If the card should be highlighted before clicking
        """
        if isinstance(target, CombatCard):
            cards_len_before = len(await self.combat_handler.get_cards())

            await self.combat_handler.client.mouse_handler.click_window(
                self._spell_window
            )

            if sleep_time is not None:
                await asyncio.sleep(sleep_time)

            await self.combat_handler.client.mouse_handler.set_mouse_position_to_window(
                target._spell_window
            )

            if sleep_time is not None:
                await asyncio.sleep(sleep_time)

            if debug_paint:
                await target._spell_window.debug_paint()

            await self.combat_handler.client.mouse_handler.click_window(
                target._spell_window
            )

            # wait until card number goes down
            while len(await self.combat_handler.get_cards()) > cards_len_before:
                await asyncio.sleep(0.1)

            # wiz can't keep up with how fast we can cast
            if sleep_time is not None:
                await asyncio.sleep(sleep_time)

        elif target is None:
            await self.combat_handler.client.mouse_handler.click_window(
                self._spell_window
            )
            # we don't need to sleep because nothing will be casted after

        elif isinstance(target, List):
            await self.combat_handler.client.mouse_handler.click_window(
                self._spell_window
            )

            # see above
            if sleep_time is not None:
                await asyncio.sleep(sleep_time)

            for t in target:
                await self.combat_handler.client.mouse_handler.click_window(
                    await t.get_health_text_window()
                )
                if sleep_time is not None:
                    await asyncio.sleep(sleep_time)

            confirm_window = (await self.combat_handler.client.root_window.get_windows_with_name("ConfirmTargetsWindow"))[0]
            if await confirm_window.is_visible():
                try:
                    await self.combat_handler.client.mouse_handler.click_window_with_name("ConfirmTargetsConfirm")
                except ValueError:
                    pass

        else:
            await self.combat_handler.client.mouse_handler.click_window(
                self._spell_window
            )

            # see above
            if sleep_time is not None:
                await asyncio.sleep(sleep_time)

            await self.combat_handler.client.mouse_handler.click_window(
                await target.get_health_text_window()
            )

    async def discard(self, *, sleep_time: Optional[float] = 1.0):
        """
        Discard this Card

        Args:
            sleep_time: Time to sleep after discard or None to not
        """
        cards_len_before = len(await self.combat_handler.get_cards())
        await self.combat_handler.client.mouse_handler.click_window(
            self._spell_window, right_click=True
        )

        # wait until card number goes down
        while len(await self.combat_handler.get_cards()) > cards_len_before:
            await asyncio.sleep(0.1)

        if sleep_time is not None:
            await asyncio.sleep(sleep_time)

    # TODO: 2.0 rename get_* effects to just attr name i.e async def graphical_spell
    async def get_graphical_spell(
        self,
    ) -> "wizwalker.memory.memory_objects.spell.DynamicGraphicalSpell":
        """
        The GraphicalSpell with information about this card
        """
        res = await self._spell_window.maybe_graphical_spell()
        if res is None:
            raise ValueError("Graphical spell not found; probably reading too fast")

        return res

    async def wait_for_graphical_spell(
        self,
        *,
        timeout: float = 2,
    ) -> "wizwalker.memory.memory_objects.spell.DynamicGraphicalSpell":
        """
        Wait for GraphicalSpell

        Raises:
            ExceptionalTimeout: if passed timeout; getting graphical spell took too long
        """
        return await wizwalker.utils.maybe_wait_for_value_with_timeout(
            self.get_graphical_spell, inverse_value=True, timeout=timeout
        )

    async def get_spell_effects(
        self,
    ) -> List["wizwalker.memory.memory_objects.spell_effect.DynamicSpellEffect"]:
        spell = await self.wait_for_graphical_spell()
        return await spell.spell_effects()

    async def name(self) -> str:
        """
        The name of this card
        """
        graphical_spell = await self.wait_for_graphical_spell()
        spell_template = await graphical_spell.spell_template()
        return await spell_template.name()

    async def display_name_code(self) -> str:
        """
        The display name code of this card
        """
        graphical_spell = await self.wait_for_graphical_spell()
        spell_template = await graphical_spell.spell_template()
        return await spell_template.display_name()

    async def display_name(self) -> str:
        """
        the display name of this card
        """
        code = await self.display_name_code()
        return await self.combat_handler.client.cache_handler.get_langcode_name(code)

    async def type_name(self) -> str:
        """
        The type name of this card
        """
        graphical_spell = await self.wait_for_graphical_spell()
        spell_template = await graphical_spell.spell_template()
        return await spell_template.type_name()

    async def template_id(self) -> int:
        """
        This card's template id
        """
        graphical_spell = await self.wait_for_graphical_spell()
        return await graphical_spell.template_id()

    async def spell_id(self) -> int:
        """
        This card's spell id
        """
        graphical_spell = await self.wait_for_graphical_spell()
        return await graphical_spell.spell_id()

    async def accuracy(self) -> int:
        """
        Current accuracy of this card
        """
        graphical_spell = await self.wait_for_graphical_spell()
        return await graphical_spell.accuracy()

    async def is_castable(self) -> bool:
        """
        If this card can be casted

        Note: computed from the player's current pips vs this card's pip
        cost, rather than the game's own "grayed" UI flag. Re-derived
        2026-08-12 (client revision r799379.Wizard_1_590): live A/B memory
        diffing (same hand, same cards, contrasting an affordable-everything
        state against a 4-pip state where only the 6-pip card should be
        unaffordable) found no memory offset whose value tracked pip
        affordability at all - the previous hardcoded offset (1208) just
        read stale/unrelated data. See SESSION_NOTES_2026-08-12.md.
        """
        graphical_spell = await self.wait_for_graphical_spell()
        pip_cost = await graphical_spell.pip_cost()
        if pip_cost is None:
            spell_window = self._spell_window
            return not await spell_window.maybe_spell_grayed()

        member = await self.combat_handler.get_client_member()
        participant = await member.get_participant()
        pip_count = await participant.pip_count()

        # Power pips (gold) AND school-colored pips (Balance/Fire/Ice/...)
        # are each worth 2 toward casting cost - only white/generic pips are
        # worth 1. Only shadow pips are a fully separate resource.
        # Re-derived 2026-08-12: first pass summed all pip counts at weight
        # 1, which undercounted (confirmed live: "1 balance + 1 power" pip
        # is actually 4 pips worth, not 2). See SESSION_NOTES_2026-08-12.md.
        colored_pips = (
            await pip_count.power_pips()
            + await pip_count.balance_pips()
            + await pip_count.death_pips()
            + await pip_count.fire_pips()
            + await pip_count.ice_pips()
            + await pip_count.life_pips()
            + await pip_count.myth_pips()
            + await pip_count.storm_pips()
        )
        available_pips = await pip_count.generic_pips() + colored_pips * 2

        if await pip_cost.is_xpip_spell():
            return available_pips >= 1

        needed_pips = await pip_cost.spell_rank()
        needed_shadow = await pip_cost.shadow_pips()
        available_shadow = await pip_count.shadow_pips()

        return available_pips >= needed_pips and available_shadow >= needed_shadow

    async def is_enchanted(self) -> bool:
        """
        If this card is enchanted or not
        """
        grapical_spell = await self.wait_for_graphical_spell()
        return await grapical_spell.enchantment() != 0

    async def is_treasure_card(self) -> bool:
        """
        If this card is a treasure card
        """
        graphical_spell = await self.wait_for_graphical_spell()
        return await graphical_spell.treasure_card()

    async def is_item_card(self) -> bool:
        """
        If this card is an item card
        """
        graphical_spell = await self.wait_for_graphical_spell()
        return await graphical_spell.item_card()

    async def is_side_board(self) -> bool:
        """
        If this card is from the side deck
        """
        graphical_spell = await self.wait_for_graphical_spell()
        return await graphical_spell.side_board()

    async def is_cloaked(self) -> bool:
        """
        If this card is cloaked
        """
        graphical_spell = await self.wait_for_graphical_spell()
        return await graphical_spell.cloaked()

    async def is_enchanted_from_item_card(self) -> bool:
        """
        If this card was enchanted from an item card
        """
        graphical_spell = await self.wait_for_graphical_spell()
        return await graphical_spell.enchantment_spell_is_item_card()

    async def is_pve_only(self) -> bool:
        """
        If this card can only be used in pve
        """
        graphical_spell = await self.wait_for_graphical_spell()
        return await graphical_spell.pve()
