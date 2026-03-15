from typing import Optional, Union

from wizwalker import utils
from wizwalker import XYZ, Orient
from wizwalker.memory.memory_object import Primitive, MemoryObject, DynamicMemoryObject
from wizwalker.memory.memory_objects.gamebryo_camera import DynamicGamebryoCamera

from .client_object import DynamicClientObject, ClientObject


class CameraController(MemoryObject):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    # TODO: camera 0x88 offset

    async def position(self) -> XYZ:
        return await self.read_xyz(108)

    async def write_position(self, position: XYZ):
        await self.write_xyz(108, position)

    async def orientation(self) -> Orient:
        return await self.read_orient(120)

    async def write_orientation(self, orientation: Orient):
        await self.write_orient(120, orientation)

    async def pitch(self) -> float:
        return await self.read_value_from_offset(120, Primitive.float32)

    async def write_pitch(self, pitch: float):
        await self.write_value_to_offset(120, pitch, Primitive.float32)

    async def roll(self) -> float:
        return await self.read_value_from_offset(124, Primitive.float32)

    async def write_roll(self, roll: float):
        await self.write_value_to_offset(124, roll, Primitive.float32)

    async def yaw(self) -> float:
        return await self.read_value_from_offset(128, Primitive.float32)

    async def write_yaw(self, yaw: float):
        await self.write_value_to_offset(128, yaw, Primitive.float32)

    async def gamebryo_camera(self) -> Optional[DynamicGamebryoCamera]:
        addr = await self.read_value_from_offset(136, Primitive.int64)

        if addr == 0:
            return None

        return DynamicGamebryoCamera(self.hook_handler, addr)

    async def update_orientation(self, orientation: Orient = None):
        """
        Utility function that sets the camera's matrix using pitch, yaw and roll
        """
        gcam = await self.gamebryo_camera()
        view = await gcam.cam_view()
        mat = await gcam.base_matrix()
        if orientation is None:
            orientation = await self.orientation()
        else:
            await self.write_orientation(orientation)
        mat = utils.make_ypr_matrix(mat, orientation)
        await view.write_view_matrix(mat)


class FreeCameraController(CameraController):
    async def read_base_address(self) -> int:
        raise NotImplementedError()


class ElasticCameraController(CameraController):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def attached_client_object(self) -> Optional[DynamicClientObject]:
        addr = await self.read_value_from_offset(264, Primitive.uint64)

        if addr == 0:
            return None

        return DynamicClientObject(self.hook_handler, addr)

    async def write_attached_client_object(self, attached_client_object: Union[ClientObject, int]):
        if isinstance(attached_client_object, ClientObject):
            attached_client_object = await attached_client_object.read_base_address()

        await self.write_value_to_offset(264, attached_client_object, Primitive.uint64)

    async def check_collisions(self) -> bool:
        return await self.read_value_from_offset(608, Primitive.bool)

    async def write_check_collisions(self, check_collisions: bool):
        await self.write_value_to_offset(608, check_collisions, Primitive.bool)

    async def distance(self) -> float:
        return await self.read_value_from_offset(300, Primitive.float32)

    async def write_distance(self, distance: float):
        await self.write_value_to_offset(300, distance, Primitive.float32)

    async def distance_target(self) -> float:
        return await self.read_value_from_offset(304, Primitive.float32)

    async def write_distance_target(self, distance_target: float):
        await self.write_value_to_offset(304, distance_target, Primitive.float32)

    async def zoom_resolution(self) -> float:
        return await self.read_value_from_offset(324, Primitive.float32)

    async def write_zoom_resolution(self, zoom_resolution: float):
        await self.write_value_to_offset(324, zoom_resolution, Primitive.float32)

    async def max_distance(self) -> float:
        return await self.read_value_from_offset(328, Primitive.float32)

    async def write_max_distance(self, max_distance: float):
        await self.write_value_to_offset(328, max_distance, Primitive.float32)

    async def min_distance(self) -> float:
        return await self.read_value_from_offset(332, Primitive.float32)

    async def write_min_distance(self, min_distance: float):
        await self.write_value_to_offset(332, min_distance, Primitive.float32)


class DynamicCameraController(DynamicMemoryObject, CameraController):
    pass


class DynamicFreeCameraController(DynamicMemoryObject, FreeCameraController):
    pass


class DynamicElasticCameraController(DynamicMemoryObject, ElasticCameraController):
    pass
