import asyncio
from typing import Callable, List
from warnings import warn

from .member import CombatMember
from .card import CombatCard
from ..memory import DuelPhase, EffectTarget, SpellEffects, WindowFlags
from wizwalker import utils, WizWalkerMemoryError, MemoryInvalidated, MemoryReadError, ReadingEnumFailed


class CombatHandler:
    """
    Handles client's battles
    """

    def __init__(self, client):
        self.client = client

        self._spell_check_boxes = None

    async def handle_round(self):
        """
        Called at the start of each round
        """
        raise NotImplementedError()

    async def handle_combat(self):
        """
        Handles an entire combat interaction
        """
        while await self.in_combat():
            await self.wait_for_planning_phase()
            try:
                if await self.client.duel.duel_phase() != DuelPhase.planning:
                    break
            except (ReadingEnumFailed, MemoryReadError):
                break
            round_number = await self.round_number()
            await asyncio.sleep(0.2) # make sure game manages to display UI in time
            # TODO: handle this taking longer than planning timer time
            await self.handle_round()
            await self.wait_until_next_round(round_number)

        self._spell_check_boxes = None

    async def wait_for_planning_phase(self, sleep_time: float = 0.5):
        """
        Wait for the duel to enter the planning phase

        Args:
            sleep_time: Time to sleep between checks
        """
        while True:
            try:
                phase = await self.client.duel.duel_phase()
                if phase in (DuelPhase.planning, DuelPhase.ended):
                    break

                await asyncio.sleep(sleep_time)

            except WizWalkerMemoryError:
                break

    async def wait_for_combat(self, sleep_time: float = 0.5):
        """
        Wait until in combat
        """
        await utils.maybe_wait_for_value_with_timeout(
            self.client.duel.read_base_address,
            value=0,
            inverse_value=True,
        )
        await utils.wait_for_value(self.in_combat, True, sleep_time)
        await self.handle_combat()

    async def wait_until_next_round(self, current_round: int, sleep_time: float = 0.5):
        """
        Wait for the round number to change
        """
        # can't use wait_for_value bc of the special in_combat condition
        # so we don't get stuck waiting if combat ends
        while await self.in_combat():
            new_round_number = await self.round_number()
            if new_round_number > current_round:
                return

            await asyncio.sleep(sleep_time)

    async def in_combat(self) -> bool:
        """
        If the client is in combat or not
        """
        return await self.client.in_battle()

    async def _get_card_windows(self):
        # these can be cached bc they are static
        if self._spell_check_boxes:
            return self._spell_check_boxes

        spell_checkbox_windows = await self.client.root_window.get_windows_with_type(
            "SpellCheckBox"
        )
        spell_checkbox_windows = [x for x in spell_checkbox_windows if await x.name() != "PetCard"]

        self._spell_check_boxes = spell_checkbox_windows
        return self._spell_check_boxes

    async def get_cards(self) -> List[CombatCard]:
        """
        List of active CombatCards
        """
        spell_checkbox_windows = await self._get_card_windows()

        cards = []
        # cards are ordered right to left so we need to flip them
        for spell_checkbox in spell_checkbox_windows[::-1]:
            if WindowFlags.visible in await spell_checkbox.flags():
                card = CombatCard(self, spell_checkbox)
                cards.append(card)

        return cards

    async def get_cards_with_predicate(self, pred: Callable) -> List[CombatCard]:
        """
        Return cards that match a predicate

        Args:
            pred: The predicate function
        """
        cards = []

        for card in await self.get_cards():
            if await pred(card):
                cards.append(card)

        return cards

    async def get_cards_with_name(self, name: str) -> List[CombatCard]:
        """
        Args:
            name: The name (debug name) of the cards to find

        Returns: list of possible CombatCards with the name
        """
        async def _pred(card):
            return name.lower() == (await card.name()).lower()

        return await self.get_cards_with_predicate(_pred)

    async def get_card_named(self, name: str) -> CombatCard:
        """
        Args:
            name: The name (display name) of the card to find

        Returns: The first Card with name
        """
        possible = await self.get_cards_with_name(name)

        if possible:
            return possible[0]

        raise ValueError(f"Couldn't find a card named {name}")

    async def get_cards_with_display_name(self, display_name: str) -> List[CombatCard]:
        """
        Args:
            display_name: The display name of the cards to find

        Returns: list of possible CombatCards with the display name
        """
        async def _pred(card: CombatCard):
            return display_name.lower() in (await card.display_name()).lower()

        return await self.get_cards_with_predicate(_pred)

    async def get_card_with_display_name(self, display_name: str) -> CombatCard:
        """
        Args:
            display_name: The display name of the card to find

        Returns: The first Card with display name
        """
        possible = await self.get_cards_with_display_name(display_name)

        if possible:
            return possible[0]

        raise ValueError(f"Couldn't find a card display named {display_name}")

    # TODO: add allow_treasure_cards that defaults to False
    async def get_damaging_aoes(self, *, check_enchanted: bool = None):
        """
        Get a list of all damaging aoes in hand

        Keyword Args:
            check_enchanted: None -> don't check enchanted; False -> non-enchanted; True -> enchanted
        """
        async def _pred(card: CombatCard):
            if check_enchanted is True:
                if not await card.is_enchanted():
                    return False

            elif check_enchanted is False:
                if await card.is_enchanted():
                    return False

            if await card.type_name() not in ("AOE", "Steal"):
                return False

            effects = await card.get_spell_effects()

            for effect in effects:
                effect_type = await effect.maybe_read_type_name()
                if any(substr in effect_type.lower() for substr in ("variable", "random")):
                    for sub_effect in await effect.maybe_effect_list():
                        if await sub_effect.effect_target() in (
                            EffectTarget.enemy_team,
                            EffectTarget.enemy_team_all_at_once,
                        ):
                            return True

                else:
                    if await effect.effect_target() in (
                        EffectTarget.enemy_team,
                        EffectTarget.enemy_team_all_at_once,
                    ):
                        return True
            return False

        return await self.get_cards_with_predicate(_pred)

    async def get_damage_enchants(self, *, sort_by_damage: bool = False):
        """
        Get enchants that increase the damage of spells

        Keyword Args:
            sort_by_damage: If enchants should be sorted by how much damage they add
        """

        async def _pred(card):
            if await card.type_name() != "Enchantment":
                return False

            for effect in await card.get_spell_effects():
                if await effect.effect_type() == SpellEffects.modify_card_damage:
                    return True

            return False

        damage_enchants = await self.get_cards_with_predicate(_pred)

        if not sort_by_damage:
            return damage_enchants

        async def _sort_by_damage(card):
            effect = (await card.get_spell_effects())[0]
            return await effect.effect_param()

        return await utils.async_sorted(damage_enchants, key=_sort_by_damage)

    async def get_members(self) -> List[CombatMember]:
        """
        List of active CombatMembers
        """
        combatant_windows = await self.client.root_window.get_windows_with_name(
            "CombatantControl"
        )

        members = []

        for window in combatant_windows:
            members.append(CombatMember(self, window))

        return members

    async def get_members_with_predicate(self, pred: Callable) -> List[CombatMember]:
        """
        Return members that match a predicate

        Args:
            pred: The predicate function
        """
        members = []

        for member in await self.get_members():
            if await pred(member):
                members.append(member)

        return members

    async def get_client_member(self, *, retries: int = 5, sleep_time: float = 0.5) -> CombatMember:
        """
        Get the client's CombatMember
        """
        for _ in range(retries):
            members = await self.get_members()

            for member in members:
                if await member.is_client():
                    return member

            await asyncio.sleep(sleep_time)

        raise ValueError("Couldn't find client's CombatMember")

    async def get_all_monster_members(self) -> List[CombatMember]:
        """
        Get all members who are monsters
        """
        members = await self.get_members()

        monsters = []
        for member in members:
            if await member.is_monster():
                monsters.append(member)

        return monsters

    async def get_all_player_members(self) -> List[CombatMember]:
        """
        Get all members who are players
        """
        members = await self.get_members()

        players = []
        for member in members:
            if await member.is_player():
                players.append(member)

        return players

    async def get_member_named(self, name: str) -> CombatMember:
        """
        Returns the first Member with name
        """
        members = await self.get_members()

        for member in members:
            if name.lower() in (await member.name()).lower():
                return member

        raise ValueError(f"Couldn't find a member named {name}")

    # TODO: 2.0 switch to display name
    async def attempt_cast(
        self,
        name: str,
        *,
        on_member: str = None,
        on_card: str = None,
        on_client: bool = False,
    ):
        """
        Attempt to cast a card

        Args:
            name: Name of the card to cast
            on_member: Name of the member to cast the card on
            on_card: Name of the card to cast the card on
            on_client: Bool if the card should be cast on the client
        """
        try:
            card = await self.get_card_named(name)

            if on_member:
                target = await self.get_member_named(on_member)
                await card.cast(target)

            elif on_card:
                target = await self.get_card_named(on_card)
                await card.cast(target)

            elif on_client:
                target = await self.get_client_member()
                await card.cast(target)

            else:
                await card.cast(None)

            return True

        except ValueError:
            return False

    async def attempt_willcast(self,
        *,
        on_member: str = None,
        on_client: bool = False
        ):
        """
        Cast a willcast card

        Args:
            on_member: Name of the member to cast the card on
            on_client: Bool if the card should be cast on the client
        """
        try:

            spell_checkbox_windows = await self.client.root_window.get_windows_with_type("SpellCheckBox")
            card = CombatCard(self, ([x for x in spell_checkbox_windows if await x.name() == "PetCard"])[0])
            
            if on_member:
                target = await self.get_member_named(on_member)
                await card.cast(target)

            elif on_client:
                target = await self.get_client_member()
                await card.cast(target)

            else:
                await card.cast(None)

            return True

        except ValueError:
            return False

    async def round_number(self) -> int:
        """
        Current round number
        """
        return await self.client.duel.round_num()

    async def pass_button(self):
        """
        Click the pass button
        """
        pos_done_window = await self.client.root_window.get_windows_with_name(
            "DoneWindow"
        )
        if pos_done_window:
            done_window = pos_done_window[0]

            if await done_window.is_visible():
                pos_defeated_pass_button = await done_window.get_windows_with_name(
                    "DefeatedPassButton"
                )
                defeated_pass_button = pos_defeated_pass_button[0]

                return await self.client.mouse_handler.click_window(
                    defeated_pass_button
                )

        await self.client.mouse_handler.click_window_with_name("Focus")

    async def draw_button(self):
        """
        Click the draw button
        """
        await self.client.mouse_handler.click_window_with_name("Draw")

    async def flee_button(self):
        """
        Click the flee button
        """
        pos_done_window = await self.client.root_window.get_windows_with_name(
            "DoneWindow"
        )
        if pos_done_window:
            done_window = pos_done_window[0]

            if await done_window.is_visible():
                pos_defeated_flee_button = await done_window.get_windows_with_name(
                    "DefeatedFleeButton"
                )
                defeated_flee_button = pos_defeated_flee_button[0]

                return await self.client.mouse_handler.click_window(
                    defeated_flee_button
                )

        await self.client.mouse_handler.click_window_with_name("Flee")


class AoeHandler(CombatHandler):
    """
    Subclass of CombatHandler that just casts enchanted aoes
    """

    async def _wait_for_non_planning_phase(self, sleep_time: float = 0.5):
        while True:
            try:
                phase = await self.client.duel.duel_phase()
                if phase != DuelPhase.planning or phase == DuelPhase.ended:
                    break

                await asyncio.sleep(sleep_time)

            except WizWalkerMemoryError:
                break

    async def handle_combat(self):
        """
        Handles an entire combat interaction
        """
        while await self.in_combat():
            await self.wait_for_planning_phase()

            if await self.client.duel.duel_phase() == DuelPhase.ended:
                break

            # TODO: handle this taking longer than planning timer time
            await self.handle_round()
            await self._wait_for_non_planning_phase()

        self._spell_check_boxes = None

    async def get_client_member(self, *, retries: int = 5, sleep_time: float = 0.5) -> CombatMember:
        """
        Get the client's CombatMember
        """
        for _ in range(retries):
            members = await self.get_members()

            for member in members:
                try:
                    if await member.is_client():
                        return member
                except MemoryInvalidated:
                    pass

            await asyncio.sleep(sleep_time)

        raise ValueError("Couldn't find client's CombatMember")

    async def handle_round(self):
        async def _try_do(callback, *args, **kwargs):
            retries = 5
            while True:
                res = await callback(*args, **kwargs)

                if not res:
                    if retries <= 0:
                        return res

                    retries -= 1
                    await asyncio.sleep(0.4)

                else:
                    return res

        enchanted_aoes = await self.get_damaging_aoes(check_enchanted=True)
        if enchanted_aoes:
            await enchanted_aoes[0].cast(None)

        unenchanted_aoes = await _try_do(self.get_damaging_aoes, check_enchanted=False)
        enchants = await _try_do(self.get_damage_enchants, sort_by_damage=True)

        # enchant card then cast card
        if enchants and unenchanted_aoes:
            await enchants[0].cast(unenchanted_aoes[0])
            enchanted_aoes = await _try_do(self.get_damaging_aoes, check_enchanted=True)

            if enchanted_aoes:
                to_cast = enchanted_aoes[0]

                if await to_cast.is_castable():
                    await to_cast.cast(None)

                else:
                    await self.pass_button()

            else:
                await self.pass_button()

        # no enchants so just cast card
        elif not enchants and unenchanted_aoes:
            to_cast = unenchanted_aoes[0]

            if await to_cast.is_castable():
                await to_cast.cast(None)
                return

        # hand full of enchants or enchants + other cards
        elif enchants and not unenchanted_aoes:
            if len(await self.get_cards()) == 7:
                await enchants[0].discard()
                return

            # TODO: draw tc?
            else:
                # try one last time
                await asyncio.sleep(1)
                aoes = await _try_do(self.get_damaging_aoes)

                if not aoes:
                    raise Exception("No hits in hand")

                else:
                    await aoes[0].cast(None)
                    return

        # no enchants or aoes in hand
        else:
            await self.pass_button()
            await self.pass_button()
