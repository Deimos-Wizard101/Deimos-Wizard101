from warnings import warn
from functools import partial

import wizwalker


class CombatMember:
    def __init__(
        self,
        combat_handler: "wizwalker.combat.CombatHandler",
        combatant_control: "wizwalker.memory.DynamicWindow",
    ):
        self.combat_handler = combat_handler

        self._combatant_control = combatant_control

    async def get_participant(self) -> "wizwalker.memory.CombatParticipant":
        """
        Get the underlying participant object
        """
        part = await self._combatant_control.maybe_combat_participant()

        if part is None:
            raise wizwalker.MemoryInvalidated(
                "This combat member is no longer valid; you most likely need to reget members"
            )

        return part

    async def get_stats(self) -> "wizwalker.memory.game_stats.DynamicGameStats":
        """
        Get the underlying game stats object
        """
        part = await self.get_participant()
        return await part.game_stats()

    async def get_health_text_window(self) -> "wizwalker.memory.DynamicWindow":
        """
        Get the health text window
        Useful for targeting
        """
        possible = await wizwalker.utils.maybe_wait_for_any_value_with_timeout(
            partial(self._combatant_control.get_windows_with_name, "Health"), timeout=5
        )

        if possible:
            return possible[0]

        raise ValueError("Couldn't find health child")

    async def get_name_text_window(self) -> "wizwalker.memory.DynamicWindow":
        """
        Get the name text window
        """
        possible = await self._combatant_control.get_windows_with_name("Name")
        if possible:
            return possible[0]

        raise ValueError("Couldn't find name child")

    async def is_dead(self) -> bool:
        """
        If this member is dead
        """
        part = await self.get_participant()
        stats = await part.game_stats()
        return await stats.current_hitpoints() == 0

    async def is_client(self) -> bool:
        """
        If this member is the local client
        """
        owner_id = await self.owner_id()
        global_id = await self.combat_handler.client.client_object.global_id_full()
        return owner_id == global_id

    async def is_player(self) -> bool:
        """
        If this member is a player
        """
        part = await self.get_participant()
        return await part.is_player()

    async def is_monster(self) -> bool:
        """
        If this member is not a player and not a minion
        """
        return not await self.is_player() and not await self.is_minion()

    async def is_minion(self) -> bool:
        """
        If this member is a minion
        """
        part = await self.get_participant()
        return await part.is_minion()

    async def is_boss(self) -> bool:
        """
        If this member is a boss
        """
        part = await self.get_participant()
        return await part.boss_mob()

    async def is_stunned(self) -> bool:
        """
        If this member is stunned
        """
        part = await self.get_participant()
        return await part.stunned() != 0

    async def name(self) -> str:
        """
        Name of this member
        """
        name_window = await self.get_name_text_window()
        return await name_window.maybe_text()

    # TODO: finish
    # async def school_name(self) -> str:
    #     pass

    async def owner_id(self) -> int:
        """
        This member's owner id
        """
        part = await self.get_participant()

        if part is None:
            raise ValueError(f"Participant not yet set; try sleeping before calling this")

        return await part.owner_id_full()

    async def template_id(self) -> int:
        """
        This member's template id
        """
        part = await self.get_participant()
        return await part.template_id_full()

    async def normal_pips(self) -> int:
        """
        The number of normal pips this member has
        """
        part = await self.get_participant()
        return await part.num_pips()

    async def power_pips(self) -> int:
        """
        The number of power pips this member has
        """
        part = await self.get_participant()
        return await part.num_power_pips()

    async def shadow_pips(self) -> int:
        """
        The number of shadow pips this member has
        """
        part = await self.get_participant()
        return await part.num_shadow_pips()

    async def health(self) -> int:
        """
        The amount of health this member has
        """
        part = await self.get_participant()
        return await part.player_health()

    async def max_health(self) -> int:
        """
        This member's max health
        """
        stats = await self.get_stats()
        return await stats.max_hitpoints()

    async def mana(self) -> int:
        """
        The amount of mana this member has
        """
        stats = await self.get_stats()
        return await stats.current_mana()

    async def max_mana(self) -> int:
        """
        This member's max mana
        """
        stats = await self.get_stats()
        return await stats.max_mana()

    async def level(self) -> int:
        """
        This member's level
        """
        stats = await self.get_stats()
        return await stats.reference_level()
