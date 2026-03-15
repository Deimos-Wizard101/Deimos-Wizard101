from wizwalker.memory.memory_object import Primitive, MemoryObject


class RenderContext(MemoryObject):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def ui_scale(self) -> float:
        return await self.read_value_from_offset(152, Primitive.float32)


class CurrentRenderContext(RenderContext):
    async def read_base_address(self) -> int:
        return await self.hook_handler.read_current_render_context_base()
