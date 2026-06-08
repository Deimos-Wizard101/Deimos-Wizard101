import asyncio
import struct

from wizwalker.memory.memory_object import MemoryObject, DynamicMemoryObject


# The buddy add function (FUN_141710e10) receives the target GID as
# param_2 (a raw value). The hook stores it at buddy_obj+0xE0 and
# reads it back into RDX before calling the function.
_BUDDY_GID_OFFSET = 0xE0

# DirectedChatRequest struct layout (param_2 of FUN_1416e5ac0):
#
# MSVC x64 std::wstring (32 bytes) + target GID (8 bytes) = 40 bytes
#
#   0x00  union { wchar_t buf[8]; wchar_t* ptr; }  (16 bytes)
#   0x10  uint64 size       (wchar count)
#   0x18  uint64 capacity   (<=7 means SSO inline, >7 means heap ptr at 0x00)
#   0x20  uint64 target_id  (GID)
_STRUCT_SIZE = 0x28

# The game allows messages longer than 79 characters but when the
# server relays that message to another client it looks to be capped
# at 79 characters.
_MAX_MESSAGE_WCHARS = 79

# Offset from the send_directed_chat function (FUN_1416e5ac0) start
# to the CALL operator_new instruction (E8 <rel32>).
_OPERATOR_NEW_CALL_OFFSET = 0xF4


class ChatOwner(MemoryObject):
    """The chat module object captured by ChatHook.

    Provides send_msg() to whisper another player and add_player()
    to send a buddy request. Both execute on the game's main thread
    via ChatSendHook, calling the game's own validated functions.
    """

    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def _resolve_operator_new(self) -> int:
        """Resolve the game's operator new address, cached.

        Extracted from the CALL at send_func + 0xF4 inside
        FUN_1416e5ac0. This is the same allocator the game uses
        for SSO heap strings, so operator delete can safely free it.
        """
        cache_key = "_operator_new_addr"
        cached = getattr(self.hook_handler, cache_key, None)
        if cached is not None:
            return cached

        # Get the send function address from the ChatSendHook
        from wizwalker.memory.hooks import ChatSendHook
        hook = self.hook_handler._active_hooks.get(ChatSendHook)
        if hook is None:
            raise RuntimeError("ChatSendHook not active")

        send_func = await hook._resolve_send_func()

        # Read the E8 rel32 CALL at send_func + 0xF4
        call_addr = send_func + _OPERATOR_NEW_CALL_OFFSET
        rel32_bytes = await self.hook_handler.read_bytes(call_addr + 1, 4)
        rel32 = struct.unpack("<i", rel32_bytes)[0]
        operator_new = call_addr + 5 + rel32

        setattr(self.hook_handler, cache_key, operator_new)
        return operator_new

    async def _alloc_game_heap(self, size: int) -> int:
        """Allocate memory using the game's operator new.

        This memory can be safely freed by the game's operator delete
        (used by the wstring destructor). Uses a minimal internal
        helper executed via start_thread.

        Args:
            size: Number of bytes to allocate

        Returns:
            Address of the allocated buffer in the game process
        """
        operator_new = await self._resolve_operator_new()

        # Allocate a slot to receive the result pointer
        result_addr = await self.hook_handler.allocate(8)

        # Build a minimal helper:
        #   sub rsp, 0x28       ; shadow space + alignment
        #   mov ecx, <size>     ; param for operator new
        #   mov rax, <op_new>   ; operator new address
        #   call rax            ; rax = allocated buffer
        #   mov [result], rax   ; store result
        #   add rsp, 0x28
        #   ret
        q = lambda v: struct.pack("<Q", v)
        helper = (
            b"\x48\x81\xEC\x28\x00\x00\x00"
            b"\xB9" + struct.pack("<I", size) +
            b"\x48\xB8" + q(operator_new) +
            b"\xFF\xD0"
            b"\x48\xA3" + q(result_addr) +
            b"\x48\x81\xC4\x28\x00\x00\x00"
            b"\xC3"
        )

        helper_addr = await self.hook_handler.allocate(len(helper))
        await self.hook_handler.write_bytes(helper_addr, helper)

        try:
            await self.hook_handler.start_thread(helper_addr)
            result_bytes = await self.hook_handler.read_bytes(result_addr, 8)
            heap_ptr = struct.unpack("<Q", result_bytes)[0]
            if heap_ptr == 0:
                raise RuntimeError("operator new returned NULL")
            return heap_ptr
        finally:
            await self.hook_handler.free(helper_addr)
            await self.hook_handler.free(result_addr)

    async def send_msg(self, message: str, target_gid: int):
        """Send a directed chat (whisper) to a player.

        The message is written to the ChatSendHook's export buffer,
        then a trigger flag is set. The hook (running on the game's
        main thread each frame) picks it up and calls the game's own
        send_directed_chat function.

        For messages <= 7 characters, the wstring is stored inline (SSO).
        For longer messages, a heap buffer is allocated using the game's
        own operator new so the destructor can safely free it.

        Args:
            message: The chat message text
            target_gid: The target player's GID

        Raises:
            ValueError: If message exceeds max length
            RuntimeError: If ChatSendHook is not active
        """
        if len(message) > _MAX_MESSAGE_WCHARS:
            raise ValueError(
                f"Message too long ({len(message)} chars, max {_MAX_MESSAGE_WCHARS})"
            )

        if not message:
            raise ValueError("Message cannot be empty")

        trigger_addr = self.hook_handler._base_addrs.get("send_trigger")
        struct_addr = self.hook_handler._base_addrs.get("send_struct")
        if trigger_addr is None or struct_addr is None:
            raise RuntimeError(
                "ChatSendHook not active. Call "
                "hook_handler.activate_chat_send_hook() first."
            )

        wchars = message.encode("utf-16-le")
        wchar_count = len(message)

        # Allocate the wstring buffer via the game's operator new so
        # the destructor can safely call operator delete after send.
        heap_ptr = await self._alloc_game_heap(len(wchars) + 2)
        await self.hook_handler.write_bytes(heap_ptr, wchars + b"\x00\x00")

        # Build the DirectedChatRequest struct.
        # Capacity must be > 7 so the game reads from the heap pointer
        # at offset 0x00 instead of treating it as inline SSO data.
        struct_data = bytearray(_STRUCT_SIZE)
        struct.pack_into("<Q", struct_data, 0x00, heap_ptr)
        struct.pack_into("<Q", struct_data, 0x10, wchar_count)
        struct.pack_into("<Q", struct_data, 0x18, max(wchar_count, 8))
        struct.pack_into("<Q", struct_data, 0x20, target_gid)

        # Write struct to the hook's export buffer
        await self.hook_handler.write_bytes(struct_addr, bytes(struct_data))

        # Set trigger — the main thread hook picks this up next frame
        await self.hook_handler.write_bytes(trigger_addr, b"\x01")

        # Wait for the hook to clear the trigger (send complete).
        # The game's destructor handles freeing any heap buffer.
        for _ in range(100):  # ~5 seconds at 20 FPS
            await asyncio.sleep(0.05)
            result = await self.hook_handler.read_bytes(trigger_addr, 1)
            if result == b"\x00":
                return

        raise RuntimeError("Chat send timed out — trigger was not cleared by hook")

    async def recv_message(self):
        """Read the last received directed chat message.

        Returns the sender GID, message text, and message counter.
        The counter increments each time a new whisper arrives,
        allowing callers to detect new messages by comparing against
        a previously stored counter value.

        Requires ChatHook to be active.

        Returns:
            Tuple of (sender_gid: int, message: str, counter: int)

        Raises:
            RuntimeError: If ChatHook is not active or no message received yet
        """
        gid_addr = self.hook_handler._base_addrs.get("recv_source_gid")
        buf_addr = self.hook_handler._base_addrs.get("recv_message_buf")
        len_addr = self.hook_handler._base_addrs.get("recv_message_len")
        cnt_addr = self.hook_handler._base_addrs.get("recv_counter")
        if any(a is None for a in (gid_addr, buf_addr, len_addr, cnt_addr)):
            raise RuntimeError(
                "ChatHook not active. Call "
                "hook_handler.activate_chat_hook() first."
            )

        counter_bytes = await self.hook_handler.read_bytes(cnt_addr, 8)
        counter = struct.unpack("<Q", counter_bytes)[0]
        if counter == 0:
            raise RuntimeError("No message received yet")

        gid_bytes = await self.hook_handler.read_bytes(gid_addr, 8)
        sender_gid = struct.unpack("<Q", gid_bytes)[0]

        len_bytes = await self.hook_handler.read_bytes(len_addr, 8)
        wchar_count = struct.unpack("<Q", len_bytes)[0]

        # Read the message text (UTF-16LE), capped at export buffer size
        byte_count = min(wchar_count * 2, 160)
        msg_bytes = await self.hook_handler.read_bytes(buf_addr, byte_count)
        message = msg_bytes.decode("utf-16-le", errors="replace")

        return sender_gid, message, counter

    async def wait_for_message(self, timeout: float = 10.0):
        """Wait for a new directed chat message to arrive.

        Polls the message counter until it changes from its current value,
        indicating a new message was received.

        Args:
            timeout: Max seconds to wait (default 10)

        Returns:
            Tuple of (sender_gid: int, message: str, counter: int)

        Raises:
            RuntimeError: If ChatHook is not active
            asyncio.TimeoutError: If no message arrives within timeout
        """
        cnt_addr = self.hook_handler._base_addrs.get("recv_counter")
        if cnt_addr is None:
            raise RuntimeError(
                "ChatHook not active. Call "
                "hook_handler.activate_chat_hook() first."
            )

        # Read current counter
        counter_bytes = await self.hook_handler.read_bytes(cnt_addr, 8)
        old_counter = struct.unpack("<Q", counter_bytes)[0]

        # Poll until counter changes
        elapsed = 0.0
        interval = 0.05
        while elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval
            counter_bytes = await self.hook_handler.read_bytes(cnt_addr, 8)
            new_counter = struct.unpack("<Q", counter_bytes)[0]
            if new_counter != old_counter:
                return await self.recv_message()

        raise asyncio.TimeoutError(
            f"No message received within {timeout} seconds"
        )

    async def add_player(self, target_gid: int):
        """Send a buddy/friend request to a player.

        Writes the target GID to the ChatSendHook's buddy_obj export
        at offset 0xE0, then sets buddy_trigger. The main-thread hook
        reads the GID, sets up a fake BuddyListManager with the
        GameClient pointer, and calls FUN_141710e10.

        Args:
            target_gid: The target player's GID to send a friend request to

        Raises:
            RuntimeError: If ChatSendHook is not active
        """
        trigger_addr = self.hook_handler._base_addrs.get("buddy_trigger")
        obj_addr = self.hook_handler._base_addrs.get("buddy_obj")
        if trigger_addr is None or obj_addr is None:
            raise RuntimeError(
                "ChatSendHook not active. Call "
                "hook_handler.activate_chat_send_hook() first."
            )

        # Write target GID at offset 0xE0 in the buddy_obj export.
        await self.hook_handler.write_bytes(
            obj_addr + _BUDDY_GID_OFFSET,
            struct.pack("<Q", target_gid),
        )

        # Set trigger — the main thread hook picks this up next frame
        await self.hook_handler.write_bytes(trigger_addr, b"\x01")

        # Wait for the hook to clear the trigger
        for _ in range(100):
            await asyncio.sleep(0.05)
            result = await self.hook_handler.read_bytes(trigger_addr, 1)
            if result == b"\x00":
                return

        raise RuntimeError("Buddy add timed out — trigger was not cleared by hook")


class DynamicChatOwner(DynamicMemoryObject, ChatOwner):
    pass


class CurrentChatOwner(ChatOwner):
    """Reads the chat owner address from the ChatHook export.

    Note: send_msg() and add_player() do not require ChatHook — they
    use ChatSendHook instead. The ChatHook is only needed for reading
    incoming message data.
    """

    async def read_base_address(self) -> int:
        return await self.hook_handler.read_chat_owner_base()
