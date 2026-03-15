import asyncio
import struct
import warnings
from functools import cached_property, partial
from typing import Callable, List, Optional

import pymem

from . import (
    CacheHandler,
    Keycode,
    MemoryReadError,
    ReadingEnumFailed,
    utils, ExceptionalTimeout,
)
from .constants import WIZARD_SPEED, Primitive
from .errors import PatternMultipleResults
from .memory import (
    CurrentActorBody,
    CurrentClientObject,
    CurrentDuel,
    CurrentGameStats,
    CurrentQuestPosition,
    CurrentRootWindow,
    CurrentGameClient,
    CurrentSocialSystemsManager,
    DuelPhase,
    HookHandler,
    CurrentRenderContext,
    TeleportHelper,
    MovementTeleportHook,
)
from .memory.memory_objects.character_registry import DynamicCharacterRegistry
from .memory.memory_objects.quest_client_manager import QuestClientManager
from .memory.memory_objects.core_object import CoreObject
from .memory.memory_objects.game_object_template import WizGameObjectTemplate
from .memory.memory_objects.enums import ObjectType
from .mouse_handler import MouseHandler
from .utils import (
    XYZ,
    check_if_process_running,
    get_window_title,
    set_window_title,
    get_window_rectangle,
    wait_for_value,
    maybe_wait_for_any_value_with_timeout, maybe_wait_for_value_with_timeout,
    make_string_id,
)


class Client:
    """
    Represents a connected wizard client

    Args:
        window_handle: A handle to the window this client connects to
    """

    def __init__(self, window_handle: int):
        self.window_handle = window_handle

        self._pymem = pymem.Pymem()
        self._pymem.open_process_from_id(self.process_id)
        self.hook_handler = HookHandler(self._pymem, self)

        self.cache_handler = CacheHandler()
        self.mouse_handler = MouseHandler(self)

        self.stats = CurrentGameStats(self.hook_handler)
        self.body = CurrentActorBody(self.hook_handler)
        self.duel = CurrentDuel(self.hook_handler)
        self.quest_position = CurrentQuestPosition(self.hook_handler)
        self.client_object = CurrentClientObject(self.hook_handler)
        self.root_window = CurrentRootWindow(self.hook_handler)
        self.render_context = CurrentRenderContext(self.hook_handler)
        self.game_client = CurrentGameClient(self.hook_handler)
        self.social_systems_manager = CurrentSocialSystemsManager(self.hook_handler)

        self._teleport_helper = TeleportHelper(self.hook_handler)

        self._template_ids = None
        self._world_view_window = None
        self._character_registry_addr = None
        self._quest_client_manager_addr = None

        self._movement_update_address = None
        self._movement_update_original_bytes = None
        self._movement_update_patched = False

        # for teleport
        self._je_instruction_forward_backwards = None

    def __repr__(self):
        return f"<Client {self.window_handle=} {self.process_id=}>"

    @property
    def title(self) -> str:
        """
        Get or set this window's title
        """
        return get_window_title(self.window_handle)

    @title.setter
    def title(self, window_title: str):
        set_window_title(self.window_handle, window_title)

    @property
    def is_foreground(self) -> bool:
        """
        If this client is the foreground window

        Set this to True to bring it to the foreground
        """
        return utils.get_foreground_window() == self.window_handle

    @is_foreground.setter
    def is_foreground(self, value: bool):
        if value is False:
            return

        utils.set_foreground_window(self.window_handle)

    @property
    def window_rectangle(self):
        """
        Get this client's window rectangle
        """
        return get_window_rectangle(self.window_handle)

    @cached_property
    def process_id(self) -> int:
        """
        Client's process id
        """
        return utils.get_pid_from_handle(self.window_handle)

    def is_running(self):
        """
        If this client is still running
        """
        return check_if_process_running(self._pymem.process_handle)

    async def zone_name(self) -> Optional[str]:
        """
        Client's current zone name
        """
        client_zone = await self.client_object.client_zone()

        if client_zone is not None:
            # noinspection PyBroadException
            try:
                return await client_zone.zone_name()
            except Exception:
                return None

        return None

    # TODO: 2.0 remove the base_ here and in sub methods
    async def get_base_entity_list(self):
        """
        List of WizClientObjects currently loaded
        """
        # A wizard101 update made this cause race conditions.
        # It now tries to find the root of the tree until it works or runs out of time.
        async def _impl(self):
            async def _is_root_object(x):
                object_template = await x.object_template()
                return object_template == None

            root_client = await self.client_object.parent()
            while not (await _is_root_object(root_client)):
                root_client = await root_client.parent()
            return await root_client.children()
        return await maybe_wait_for_any_value_with_timeout(partial(_impl, self), sleep_time=0.05, timeout=3.0)

    # TODO: add example
    async def get_base_entities_with_predicate(self, predicate: Callable):
        """
        Get entities with a predicate

        Args:
            predicate: Awaitable that returns True or False on if to add an entity

        Returns:
            The matching entities
        """
        entities = []

        for entity in await self.get_base_entity_list():
            if await predicate(entity):
                entities.append(entity)

        return entities

    async def get_base_entities_with_name(self, name: str):
        """
        Get entities with a name

        Args:
            name: The name to search for

        Returns:
            List of the matching entities
        """
        async def _pred(entity):
            object_template = await entity.object_template()
            return await object_template.object_name() == name

        return await self.get_base_entities_with_predicate(_pred)

    async def get_base_entities_with_display_name(self, display_name: str):
        """
        Get entities with a display name

        Args:
            display_name: The name to search for

        Returns:
            List of the matching entities
        """
        async def predicate(entity):
            mob_display_name = await entity.display_name()

            if mob_display_name is None:
                return False

            return display_name.lower() in mob_display_name.lower()

        return await self.get_base_entities_with_predicate(predicate)

    async def get_world_view_window(self):
        """
        Get the world view window
        """
        if self._world_view_window:
            return self._world_view_window

        pos = await self.root_window.get_windows_with_name("WorldView")
        # TODO: test this claim on login screen
        # world view always exists
        self._world_view_window = pos[0]
        return self._world_view_window

    async def activate_hooks(
            self, *, wait_for_ready: bool = True, timeout: float = None
    ):
        """
        Activate all memory hooks but mouseless

        Keyword Args:
            wait_for_ready: If this should wait for hooks to be ready to use (duel exempt)
            timeout: How long to wait for hook values to be witten (None for no timeout)
        """
        await self.hook_handler.activate_all_hooks(
            wait_for_ready=wait_for_ready, timeout=timeout
        )

    async def close(self):
        """
        Closes this client; unhooking all active hooks
        """
        # if the client isn't running there isn't anything to unhook
        if not self.is_running():
            return

        await self._unpatch_movement_update()
        await self.hook_handler.close()

    async def get_template_ids(self) -> dict:
        """
        Get a dict of template ids mapped to their value
        ids are str
        """
        if self._template_ids:
            return self._template_ids

        self._template_ids = await self.cache_handler.get_template_ids()
        return self._template_ids

    async def quest_manager(self) -> QuestClientManager:
        if not self._quest_client_manager_addr:
            mov_instruction_addr = await self.hook_handler.pattern_scan(
                b"\x48\x8B.....\x48\x8B\x97....\x48\x8B.\xE8....\x33\xD2",
                module="WizardGraphicalClient.exe",
                return_multiple=False
            )
            rip_offset = await self.hook_handler.read_typed(
                mov_instruction_addr + 3, Primitive.int32
            )
            # 7 is the length of this instruction
            self._quest_client_manager_addr = await self.hook_handler.read_typed(mov_instruction_addr + 7 + rip_offset, Primitive.uint64)
        return QuestClientManager(self.hook_handler, self._quest_client_manager_addr)

    async def character_registry(self) -> DynamicCharacterRegistry:
        if not self._character_registry_addr:
            # WizardGraphicalClient.exe+FC46F0 - 48 8B 05 89AA4202     - mov rax,[WizardGraphicalClient.exe+33EF180] { (20EA3A70810) }
            # WizardGraphicalClient.exe+FC46F7 - 48 8B 88 30010000     - mov rcx,[rax+00000130]
            # WizardGraphicalClient.exe+FC46FE - 48 8B C2              - mov rax,rdx
            # WizardGraphicalClient.exe+FC4701 - 48 89 0A              - mov [rdx],rcx
            mov_instruction_addrs = await self.hook_handler.pattern_scan(
                b"\x48\x8B\x05....\x48\x8B\x88\x30\x01\x00\x00",
                module="WizardGraphicalClient.exe",
                return_multiple=True
            )
            if len(mov_instruction_addrs) != 2:
                raise PatternMultipleResults("")
            mov_instruction_addr = mov_instruction_addrs[0]
            rip_offset = await self.hook_handler.read_typed(
                mov_instruction_addr + 3, Primitive.int32
            )
            # 7 is the length of this instruction
            self._character_registry_addr = await self.hook_handler.read_typed(mov_instruction_addr + 7 + rip_offset, Primitive.uint64)
        return DynamicCharacterRegistry(self.hook_handler, self._character_registry_addr)

    async def quest_id(self) -> int:
        """
        Get the client's current quest id
        """
        registry = await self.character_registry()
        return await registry.active_quest_id()

    async def goal_id(self) -> int:
        """
        Get the client's current goal id
        """
        registry = await self.character_registry()
        return await registry.active_goal_id()

    async def in_battle(self) -> bool:
        """
        If the client is in battle or not
        """
        try:
            duel_phase = await self.duel.duel_phase()
        except (ReadingEnumFailed, MemoryReadError):
            return False
        else:
            return duel_phase is not DuelPhase.ended

    async def is_loading(self) -> bool:
        """
        If the client is currently in a loading screen
        (does not apply to character load in)
        """
        view = await self.get_world_view_window()
        try:
            # if this window exists we are loading
            await view.get_child_by_name("TransitionWindow")
        except ValueError:
            try:
                await self.root_window.get_child_by_name("PageFlip")
            except ValueError:
                return False
            else:
                return True
        else:
            return True

    async def is_in_dialog(self) -> bool:
        """
        If the client is in dialog
        """
        world_view = await self.get_world_view_window()
        for child in await world_view.children():
            # TODO: check if we also need to check for wndDialogMain child
            if (child_name := await child.name()) == "NPCServicesWin":
                return True

            elif child_name == "wndDialogMain":
                return True

        return False

    async def is_in_npc_range(self) -> bool:
        """
        If the client is within an npc interact range
        """
        world_view = await self.get_world_view_window()
        for child in await world_view.children():
            if await child.name() == "NPCRangeWin":
                return True

        return False

    async def backpack_space(self) -> tuple[int, int]:
        """
        This client's backpack space used and max
        """
        async def should_count_item(obj: CoreObject) -> bool:
            template = await obj.object_template()
            template = WizGameObjectTemplate(self.hook_handler, await template.read_base_address())
            if await template.object_type() in [ObjectType.deed, ObjectType.structure]:
                return False
            exclusion_set = set([make_string_id(x) for x in ["NotCounted", "Jewel", "Emote"]])
            propset = await template.object_property_hashset()
            if len(exclusion_set.intersection(propset)) > 0:
                return False
            return True

        item_count = 0

        inventory_behavior = await self.client_object.try_get_inventory_behavior()
        if inventory_behavior:
            for item in await inventory_behavior.item_list():
                if await should_count_item(item):
                    item_count += 1

        equipment_behavior = await self.client_object.try_get_equipment_behavior()
        if equipment_behavior:
            for item in await equipment_behavior.item_list():
                if await should_count_item(item):
                    item_count += 1

        backpack_capacity = await inventory_behavior.num_items_allowed()
        return item_count, backpack_capacity

    async def wait_for_zone_change(
            self, name: Optional[str] = None, *, sleep_time: Optional[float] = 0.5
    ):
        """
        Wait for the client's zone to change

        Args:
            name: The name of the zone to wait to be changed from or None to read
            sleep_time: How long to sleep between reads or None to not
        """
        if name is None:
            name = await self.zone_name()

        while await self.zone_name() == name:
            await asyncio.sleep(sleep_time)

        while await self.is_loading():
            await asyncio.sleep(sleep_time)

    async def current_energy(self) -> int | None:
        """
        Client's current energy
        """
        if (behavior := await self.client_object.search_behavior_by_name("PetOwnerBehavior")) is not None:
            return await behavior.read_value_from_offset(132, Primitive.int32)
        
        return None

    def login(self, username: str, password: str):
        """
        Login this client

        Args:
            username: The username to login with
            password: The password to login with
        """
        utils.instance_login(self.window_handle, username, password)

    async def send_key(self, key: Keycode, seconds: float = 0):
        """
        Send a key

        Args:
            key: The Keycode to send
            seconds: How long to send it for
        """
        await utils.timed_send_key(self.window_handle, key, seconds)

    async def send_hotkey(self, modifers: List[Keycode], key: Keycode):
        """
        send a hotkey

        Args:
            modifers: The key modifers i.e CTRL, ALT
            key: The key being modified
        """
        await utils.send_hotkey(self.window_handle, modifers, key)

    async def goto(self, x: float, y: float):
        """
        Moves the player to a specific x and y

        Args:
            x: X to move to
            y: Y to move to
        """
        client_obj = self.client_object
        body = await client_obj.actor_body()
        current_xyz = await body.position()
        # (40 / 100) + 1 = 1.4
        speed_multiplier = ((await client_obj.speed_multiplier()) / 100) + 1
        target_xyz = utils.XYZ(x, y, current_xyz.z)
        distance = current_xyz - target_xyz
        move_seconds = distance / (WIZARD_SPEED * speed_multiplier)
        yaw = utils.calculate_perfect_yaw(current_xyz, target_xyz)

        await body.write_yaw(yaw)
        await utils.timed_send_key(self.window_handle, Keycode.W, move_seconds)

    async def teleport(
            self,
            xyz: XYZ,
            yaw: float = None,
            *,
            wait_on_inuse: bool = True,
            wait_on_inuse_timeout: float = 1.0,
            purge_on_after_unuser_fixer: bool = True,
            purge_on_after_unuser_fixer_timeout: float = 0.6,
    ):
        """
        Teleport the client

        Args:
            xyz: xyz to teleport to
            yaw: yaw to set or None to not change

        Keyword Args:
            wait_on_inuse: If we should wait for the update bool to be False
            wait_on_inuse_timeout: Time to wait for inuse flag to be setback
            purge_on_after_unuser_fixer: If should wait for inuse flag after and reset if not set
            purge_on_after_unuser_fixer_timeout: Time to wait for inuse flag to reset if not set
        """
        client_object_addr = await self.client_object.read_base_address()

        await self._teleport_object(
            client_object_addr,
            xyz,
            wait_on_inuse,
            wait_on_inuse_timeout,
            purge_on_after_unuser_fixer,
            purge_on_after_unuser_fixer_timeout,
        )

        if yaw is not None:
            await self.body.write_yaw(yaw)

    async def _teleport_object(
            self,
            object_address: int,
            xyz: XYZ,
            wait_on_inuse: bool = True,
            wait_on_inuse_timeout: float = 1.0,
            purge_on_after_unuser_fixer: bool = True,
            purge_on_after_unuser_fixer_timeout: float = 0.6,
    ):
        if not self.hook_handler._check_if_hook_active(MovementTeleportHook):
            raise RuntimeError("Movement teleport not active")

        if await self._teleport_helper.should_update():
            if not wait_on_inuse:
                raise ValueError("Tried to teleport while should update bool is set")

            await maybe_wait_for_value_with_timeout(
                self._teleport_helper.should_update,
                value=False,
                timeout=wait_on_inuse_timeout,
            )

        jes = await self._get_je_instruction_forward_backwards()

        await self._teleport_helper.write_target_object_address(object_address)
        await self._teleport_helper.write_position(xyz)
        await self._teleport_helper.write_should_update(True)

        for je in jes:
            await self.hook_handler.write_bytes(je, b"\x90" * 6)

        if purge_on_after_unuser_fixer:
            try:
                await maybe_wait_for_value_with_timeout(
                    self._teleport_helper.should_update,
                    value=False,
                    timeout=purge_on_after_unuser_fixer_timeout,
                )
            except ExceptionalTimeout:
                movement_teleport_hook = self.hook_handler._get_hook_by_type(MovementTeleportHook)
                for je, old_bytes in zip(jes, movement_teleport_hook._old_jes_bytes):
                    await self.hook_handler.write_bytes(je, old_bytes)

                await self._teleport_helper.write_should_update(False)

    async def _get_je_instruction_forward_backwards(self):
        """
        this method returns the two je instruction addresses :)
        """
        if self._je_instruction_forward_backwards is not None:
            return self._je_instruction_forward_backwards

        movement_state_instruction_addr = await self.hook_handler.pattern_scan(
            rb"\x8B\x5F\x70\xF3",
            module="WizardGraphicalClient.exe"
        )

        self._je_instruction_forward_backwards = (
            movement_state_instruction_addr + 15,
            movement_state_instruction_addr + 24,
        )

        return self._je_instruction_forward_backwards

    async def camera_swap(self, seamless_freecam=True):
        """
        Swaps the current camera controller
        """
        if await self.game_client.is_freecam():
            await self.camera_elastic()

        else:
            await self.camera_freecam(seamless_from_elastic=seamless_freecam)

    async def camera_freecam(self, seamless_from_elastic=True):
        """
        Switches to the freecam camera controller
        """
        await self._patch_movement_update()

        await self.game_client.write_is_freecam(True)

        elastic = await self.game_client.elastic_camera_controller()
        free = await self.game_client.free_camera_controller()

        elastic_address = await elastic.read_base_address()
        free_address = await free.read_base_address()

        await self._switch_camera(free_address, elastic_address)

        if seamless_from_elastic:
            await free.write_position(await elastic.position())
            await free.update_orientation(await elastic.orientation())

    async def camera_elastic(self):
        """
        Switches to the elastic camera controller
        """
        await self._unpatch_movement_update()

        await self.game_client.write_is_freecam(False)

        elastic = await self.game_client.elastic_camera_controller()
        free = await self.game_client.free_camera_controller()

        elastic_address = await elastic.read_base_address()
        free_address = await free.read_base_address()

        await self._switch_camera(elastic_address, free_address)

    async def _patch_movement_update(self):
        """
        Causes movement update to not run, means your character doesn't move
        """
        if self._movement_update_patched:
            return

        movement_update_address = await self._get_movement_update_address()
        self._movement_update_original_bytes = await self.hook_handler.read_bytes(movement_update_address, 3)
        # 3x nop
        await self.hook_handler.write_bytes(movement_update_address, b"\x90\x90\x90")

        self._movement_update_patched = True

    async def _unpatch_movement_update(self):
        if not self._movement_update_patched:
            return

        movement_update_address = await self._get_movement_update_address()
        await self.hook_handler.write_bytes(movement_update_address, self._movement_update_original_bytes)

        self._movement_update_patched = False

    async def _get_movement_update_address(self):
        if self._movement_update_address:
            return self._movement_update_address

        self._movement_update_address = await self.hook_handler.pattern_scan(
            rb"\xFF\x50.\x48\x8B\x83....\x48\x8D..\x48\x2B",
            module="WizardGraphicalClient.exe"
        )

        # OLD PATTERN; DO NOT REMOVE. Might be helpful to update the new pattern in case it breaks.
        # self._movement_update_address = await self.hook_handler.pattern_scan(
        #     rb"\x48\x8B\xC4\x55\x56\x57\x41\x54\x41\x55\x41\x56\x41\x57\x48"
        #     rb"\x8D\xA8....\x48\x81\xEC....\x48\xC7.........\x48\x89\x58."
        #     rb"\x0F\x29\x70.\x0F\x29\x78.\x44\x0F\x29\x40.\x44\x0F\x29\x48."
        #     rb"\x44\x0F\x29.....\x44\x0F\x29.....\x44\x0F\x29.....\x48\x8B"
        #     rb"\x05....\x48\x33\xC4\x48\x89\x85....\x44",
        #     module="WizardGraphicalClient.exe",
        # )

        return self._movement_update_address

    async def _switch_camera(self, new_camera_address: int, old_camera_address: int):
        def _pack(address):
            return struct.pack("<Q", address)

        game_client_address = await self.game_client.read_base_address()
        packed_game_client_address = _pack(game_client_address)

        packed_new_camera_address = _pack(new_camera_address)
        packed_old_camera_address = _pack(old_camera_address)

        # fmt: off
        shellcode = (
                # setup
                b"\x50"  # push rax
                b"\x51"  # push rcx
                b"\x52"  # push rdx
                b"\x41\x50"  # push r8
                b"\x41\x51"  # push r9

                # call set_cam(client, new_cam, ?, cam_swap_fn)
                b"\x48\xB9" + packed_game_client_address +  # mov rcx, client_addr
                b"\x48\xBA" + packed_new_camera_address +  # mov rdx, new_cam_addr
                b"\x49\xC7\xC0\x01\x00\x00\x00"  # mov r8, 0x1
                b"\x48\x8B\x01"  # mov rax, [rcx]
                b"\x48\x8B\x80\x70\x04\x00\x00"  # mov rax, [rax+0x470]
                b"\x49\x89\xC1"  # mov r9, rax
                b"\xFF\xD0"  # call rax

                # call register_input_handlers(cam, active) [new_cam]
                b"\x48\xB9" + packed_game_client_address +  # mov rcx, client_addr
                b"\x48\xB8" + packed_new_camera_address +  # mov rax, new_cam_addr
                b"\x48\x89\xC1"  # mov rcx, rax
                b"\x48\x8B\x01"  # mov rax, [rcx]
                b"\x48\x8B\x40\x70"  # mov rax, [rax+0x70]
                b"\x48\xC7\xC2\x01\x00\x00\x00"  # mov rdx, 1
                b"\xFF\xD0"  # call rax

                # call register_input_handlers(cam, active) [old_cam]
                b"\x48\xB9" + packed_game_client_address +  # mov rcx, client_addr
                b"\x48\xB8" + packed_old_camera_address +  # mov rax, old_cam_addr
                b"\x48\x89\xC1"  # mov rcx, rax
                b"\x48\x8B\x01"  # mov rax, [rcx]
                b"\x48\x8B\x40\x70"  # mov rax, [rax+0x70]
                b"\x48\xC7\xC2\x00\x00\x00\x00"  # mov rdx, 0
                b"\xFF\xD0"  # call rax

                # cleanup
                b"\x41\x59"  # pop r9
                b"\x41\x58"  # pop r8
                b"\x5A"  # pop rdx
                b"\x59"  # pop rcx
                b"\x58"  # pop rax

                # end
                b"\xC3"  # ret
        )
        # fmt: on

        shell_ptr = await self.hook_handler.allocate(len(shellcode))
        await self.hook_handler.write_bytes(shell_ptr, shellcode)
        await self.hook_handler.start_thread(shell_ptr)
        # we can free here because start_thread waits for the thread to return
        await self.hook_handler.free(shell_ptr)
