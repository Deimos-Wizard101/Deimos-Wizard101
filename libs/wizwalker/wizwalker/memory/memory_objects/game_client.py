from typing import Union, Optional

from wizwalker.memory.memory_object import Primitive, MemoryObject
from .camera_controller import (
    DynamicCameraController,
    CameraController,
    DynamicFreeCameraController,
    DynamicElasticCameraController,
)
from .client_object import DynamicClientObject
from .character_registry import DynamicCharacterRegistry
from .enums import AccountPermissions
from .gamebryo_presenter import DynamicGamebryoPresenter
from .fishing_manager import FishingManager


# note: not defined
class GameClient(MemoryObject):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def elastic_camera_controller(self) -> Optional[DynamicElasticCameraController]:
        offset = await self.pattern_scan_offset_cached(
            rb"\x48\x8B\x93\xD8\x1F\x02\x00\x41\xFF\xD1\x32"
            rb"\xC0\xEB\x05\x41\xFF\xD1\xB0\x01\x88\x83\x20"
            rb"\x20\x02\x00\x48\x8B\x07\x33\xD2\x48\x8B\xCF",
            3,
            "elastic_camera_controller",
            0x22260
        )

        addr = await self.read_value_from_offset(offset, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicElasticCameraController(self.hook_handler, addr)

    async def free_camera_controller(self) -> Optional[DynamicFreeCameraController]:
        offset = await self.pattern_scan_offset_cached(
            rb"\x48\x8B\x93....\x48\x8B\x03\x4C\x8B\x88...."
            rb"\x41\xB8\x01\x00\x00\x00\x48\x8B\xCB\x48\x3B\xFA\x75",
            3,
            "free_camera_controller",
            0x22270
        )

        addr = await self.read_value_from_offset(offset, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicFreeCameraController(self.hook_handler, addr)

    async def selected_camera_controller(self) -> Optional[DynamicCameraController]:
        """
        The in use camera controller
        """
        offset = await self.pattern_scan_offset_cached(
            rb"\x48\x89\x87\x08\x20\x02\x00\x48\x8D\x8F"
            rb"\x10\x20\x02\x00\x48\x8D\x54\x24\x40\xE8"
            rb"....\x90\x48\x8B\x4C\x24",
            3,
            "selected_camera_controller",
            0x22290
        )

        addr = await self.read_value_from_offset(offset, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicCameraController(self.hook_handler, addr)

    async def write_selected_camera_controller(self, selected_camera_controller: Union[CameraController, int]):
        """
        Write the in use camera controller
        """
        if isinstance(selected_camera_controller, CameraController):
            selected_camera_controller = await selected_camera_controller.read_base_address()

        offset = await self.pattern_scan_offset_cached(
            rb"\x48\x89\x87\x08\x20\x02\x00\x48\x8D\x8F"
            rb"\x10\x20\x02\x00\x48\x8D\x54\x24\x40\xE8"
            rb"....\x90\x48\x8B\x4C\x24",
            3,
            "selected_camera_controller",
            0x22290
        )

        await self.write_value_to_offset(offset, selected_camera_controller, Primitive.uint64)

    async def is_freecam(self) -> bool:
        """
        If the game is currently in freecam mode
        """
        offset = await self.pattern_scan_offset_cached(
            rb"\x0F\xB6\x88\x20\x20\x02\x00\x88\x8B\x6A"
            rb"\x02\x00\x00\x84\xC9\x0F\x85....\x48\x8D"
            rb"\x55\xE0\x48\x8B\xCB\xE8",
            3,
            "is_freecam",
            0x222A8
        )
        return await self.read_value_from_offset(offset, Primitive.bool)

    async def write_is_freecam(self, is_freecam: bool):
        """
        Write if the game is currently in freecam mode
        """
        offset = await self.pattern_scan_offset_cached(
            rb"\x0F\xB6\x88\x20\x20\x02\x00\x88\x8B\x6A"
            rb"\x02\x00\x00\x84\xC9\x0F\x85....\x48\x8D"
            rb"\x55\xE0\x48\x8B\xCB\xE8",
            3,
            "is_freecam",
            0x222A8
        )
        await self.write_value_to_offset(offset, is_freecam, Primitive.bool)

    async def root_client_object(self) -> Optional[DynamicClientObject]:
        """
        The root client object, all other client objects are its children
        """
        offset = await self.pattern_scan_offset_cached(
            rb"\x48\x8D\x93\xA0\x12\x02\x00\xFF\x90\xB8\x01"
            rb"\x00\x00\x90\x48\x8B\x7C\x24\x30\x48\x85\xFF\x74\x2E\xBE"
            rb"\xFF\xFF\xFF\xFF\x8B\xC6\xF0\x0F\xC1\x47\x08 ",
            3,
            "root_client_object",
            0x21318
        )

        addr = await self.read_value_from_offset(offset, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicClientObject(self.hook_handler, addr)

    async def frames_per_second(self) -> float:
        """
        The number of frames processed the last second, updated every 5 seconds by default
        """
        offset = await self.pattern_scan_offset_cached(
            rb"\xF3\x0F\x11\x8B\xFC\x19\x02\x00\xC7\x05........\xF2\x0F"
            rb"\x11.....\x48\x8B\x8B\x00\x13\x02\x00\x48\x85\xC9\x74\x09",
            4,
            "frames_per_second",
            0x219FC
        )
        return await self.read_value_from_offset(offset, Primitive.float32)

    async def shutdown_signal(self) -> int:
        """
        Signal used to check if the main loop should close
        """
        offset = await self.pattern_scan_offset_cached(
            rb"\x38\x9F\xB8\x11\x02\x00\x74\xBE\xE8....\x83\xF8\x64\x0F\x8F....\xB9\x0F\x00\x00\x00",
            2,
            "shutdown_signal",
            0x211B8
        )
        return await self.read_value_from_offset(offset, Primitive.int32)

    async def write_shutdown_signal(self, shutdown_signal: int):
        """
        Writing 1 into the shutdown signal will close the program (exits main loop)
        """
        offset = await self.pattern_scan_offset_cached(
            rb"\x38\x9F\xB8\x11\x02\x00\x74\xBE\xE8....\x83\xF8\x64\x0F\x8F....\xB9\x0F\x00\x00\x00",
            2,
            "shutdown_signal",
            0x211B8
        )
        await self.write_value_to_offset(offset, shutdown_signal, Primitive.int32)

    async def user_id(self) -> int:
        """Account-level UserID from MSG_USER_VALIDATE / MSG_CHARACTERSELECTED."""
        return await self.read_value_from_offset(0x21258, Primitive.uint64)

    async def player_gid(self) -> int:
        """Current character's global ID (CharID from MSG_CHARACTERSELECTED)."""
        return await self.read_value_from_offset(0x214C0, Primitive.uint64)

    async def machine_id(self) -> int:
        """MachineID sent during login."""
        return await self.read_value_from_offset(0x214C8, Primitive.uint64)

    async def character_registry(self) -> Optional[DynamicCharacterRegistry]:
        """
        Get the character registry
        """
        # TODO: find where this loaded in for offset pattern
        addr = await self.read_value_from_offset(0x224A8, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicCharacterRegistry(self.hook_handler, addr)

    async def account_permissions(self) -> AccountPermissions:
        offset = await self.pattern_scan_offset_cached(
            rb"\x41\x89\x86\x3C\x1D\x02\x00\x4D\x8B\x06\x8B"
            rb"\xD0\x49\x8B\xCE\x41\xFF\x90\x10\x04\x00\x00"
            rb"\x49\x8B\x06\x49\x8B\xCE\xFF\x90\x58\x01\x00\x00",
            3,
            "account_permissions",
            0x21D3C
        )
        return await self.read_enum(offset, AccountPermissions)

    async def write_account_permissions(self, account_permissions: AccountPermissions):
        offset = await self.pattern_scan_offset_cached(
            rb"\x41\x89\x86\x3C\x1D\x02\x00\x4D\x8B\x06\x8B"
            rb"\xD0\x49\x8B\xCE\x41\xFF\x90\x10\x04\x00\x00"
            rb"\x49\x8B\x06\x49\x8B\xCE\xFF\x90\x58\x01\x00\x00",
            3,
            "account_permissions",
            0x21D3C
        )
        await self.write_enum(offset, account_permissions)

    async def has_membership(self) -> bool:
        offset = await self.pattern_scan_offset_cached(
            rb"\x83\xBB\x40\x1D\x02\x00\x00\x75\x04\xB2\x01\xEB\x02\x33\xD2\x48\x8B.....\xE8",
            2,
            "has_membership",
            0x21D40
        )
        return await self.read_value_from_offset(offset, Primitive.bool)

    # no, this doesn't let you go in membership areas
    async def write_has_membership(self, has_membership: bool):
        offset = await self.pattern_scan_offset_cached(
            rb"\x83\xBB\x40\x1D\x02\x00\x00\x75\x04\xB2\x01\xEB\x02\x33\xD2\x48\x8B.....\xE8",
            2,
            "has_membership",
            0x21D40
        )
        await self.write_value_to_offset(offset, has_membership, Primitive.bool)

    async def gamebryo_presenter(self) -> DynamicGamebryoPresenter:
        """
        Thing used for rendering
        """
        offset = await self.pattern_scan_offset_cached(
            rb".......\x48\x8B\x01\xFF\x50\x40\x84\xC0\x75.\xE8",
            3,
            "gamebryo_presenter",
            0x21FB8
        )

        addr = await self.read_value_from_offset(offset, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicGamebryoPresenter(self.hook_handler, addr)

    async def fishing_manager(self) -> FishingManager:
        addr = await self.read_value_from_offset(0x23140, Primitive.uint64)
        return FishingManager(self.hook_handler, addr)

class CurrentGameClient(GameClient):
    _base_address = None

    async def read_base_address(self) -> int:
        if self._base_address is not None:
            return self._base_address

        addr = await self.pattern_scan(rb"\x48\x8b.....\x48\x8b.\x80\xb8....\x00\x74.\x4c\x8b", module="WizardGraphicalClient.exe")
        offset = await self.read_typed(addr + 3, Primitive.int32)

        self._base_address = await self.read_typed(addr + 7 + offset, Primitive.uint64)
        return self._base_address
