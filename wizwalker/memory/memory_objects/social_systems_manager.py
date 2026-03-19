import struct
from typing import Optional

import regex
import pymem.process

from wizwalker.constants import Primitive
from wizwalker.errors import PatternFailed
from wizwalker.memory.memory_object import DynamicMemoryObject, PropertyClass
from wizwalker.memory.handler import HookHandler
from .unlock_trigger_list import DynamicUnlockTriggerList
from .adventure_party_list import DynamicAdventurePartyList


# C++ class: SocialSystemsManager
# Source: WizardGraphicalClient\SocialSystems\SocialSystemsManager.cpp
# Constructor: FUN_141203f30 (r792258)
#
# Class layout (from constructor FUN_141203f30, r792258):
# ==============================================
# Offset  Type                    Description
# ------  ----                    -----------
# 0x000   vtable*                 Main vtable
# 0x048   vtable*                 MessageHandler vtable
# 0x0A8   shared_ptr              -> AdventurePartyList* (MSG_RequestAdventureParty)
# 0x0C8   uint64                  Join requesting player GID (Status 3)
# 0x0E0   uint64                  Join requesting player GID (Status 1)
# 0x0E8   uint64                  Join request party GID (Status 3)
# 0x100   bool                    Group quest flag (MSG_SetGroupQuest)
# 0x108   uint64                  Group Quest GID (MSG_SetGroupQuest)
# 0x110   uint64                  Group Goal GID (MSG_SetGroupQuest)
# 0x128   uint64                  Player GID
# 0x1B0   uint64                  Stored Party GID 1
# 0x1D8   uint64                  Current Party GID
# 0x1E0   UnlockTriggerList       Embedded PropertyClass (0x58 bytes)
# 0x260   uint64                  Group GID
# 0x268   int32                   Adventure party state
# 0x26C   int32                   Adventure party param
# 0x30A   bool                    Guild house flag
# 0x360   float32                 Float (8.0 in guild house)
# 0x364   uint32                  Join cooldown (MSG_RequestAdventureParty)
# 0x378   uint32                  Permission mask (init 0x7F)
# 0x37D   bool                    Zone loaded flag

_EXE_NAME = "WizardGraphicalClient.exe"

# Constructor triple-vtable-write pattern (patch-survivable).
#
# The SSM constructor writes three vtable pointers in consecutive
# LEA RAX,[rip+disp32] / MOV pairs immediately after base-class init:
#
#   LEA RAX, [rip+disp32]    ; main vtable (obj+0x00)
#   MOV [RDI], RAX
#   LEA RAX, [rip+disp32]    ; MessageHandler sub-vtable (obj+0x48)
#   MOV [RSI], RAX            ; RSI was set to RDI+0x48 earlier
#   LEA RAX, [rip+disp32]    ; third sub-vtable (obj+0x68)
#   MOV [RDI+0x68], RAX
#
# The fixed opcode bytes are stable across patches — only the disp32
# operands change as vtables shift in .rdata. This three-write sequence
# (targeting [RDI], [RSI], and [RDI+0x68]) is unique to the SSM
# constructor and serves as a reliable anchor for extracting the vtable
# address at runtime.
_SSM_CONSTRUCTOR_PATTERN = (
    b"\x48\x8D\x05"        # LEA RAX, [rip+disp32]  (main vtable)
    b"...."                 # disp32 wildcard
    b"\x48\x89\x07"        # MOV [RDI], RAX
    b"\x48\x8D\x05"        # LEA RAX, [rip+disp32]  (secondary vtable)
    b"...."                 # disp32 wildcard
    b"\x48\x89\x06"        # MOV [RSI], RAX
    b"\x48\x8D\x05"        # LEA RAX, [rip+disp32]  (third vtable)
    b"...."                 # disp32 wildcard
    b"\x48\x89\x47\x68"    # MOV [RDI+0x68], RAX
)


class SocialSystemsManager(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    # -------------------------------------------------------------------------
    # Guild / Party GID fields
    # -------------------------------------------------------------------------

    async def player_gid(self) -> int:
        return await self.read_value_from_offset(0x128, Primitive.uint64)

    async def stored_party_gid(self) -> int:
        """Stored Party GID at 0x1B0.
        Compared in HandleCharacterChanged (FUN_1412223a0, r792258);
        if it differs from the guild's PartyGID, MSG_UNLOCKTRIGGERDATA is re-sent.
        """
        return await self.read_value_from_offset(0x1B0, Primitive.uint64)

    async def current_party_gid(self) -> int:
        """Current Party GID at 0x1D8.
        Written by MSG_UnlockTriggerData and MSG_UpdateGuildUnlockTrigger
        from the "PartyGID" DML field.
        """
        return await self.read_value_from_offset(0x1D8, Primitive.uint64)

    # -------------------------------------------------------------------------
    # UnlockTriggerList (embedded PropertyClass at 0x1E0)
    # -------------------------------------------------------------------------

    async def unlock_trigger_list(self) -> DynamicUnlockTriggerList:
        """Returns the embedded UnlockTriggerList sub-object at offset 0x1E0.

        This PropertyClass is the deserialization target for the "Buffer"
        DML field in MSG_UnlockTriggerData. Its m_unlockTriggerList (at
        sub-object offset 0x48 = SocialSystemsManager offset 0x228) is a
        std::list<shared_ptr<UnlockTriggerInfo>>.
        """
        addr = await self.read_base_address()
        return DynamicUnlockTriggerList(self.hook_handler, addr + 0x1E0)

    # -------------------------------------------------------------------------
    # Zone / guild state flags
    # -------------------------------------------------------------------------

    async def is_guild_house(self) -> bool:
        """Guild house flag at 0x30A.
        True when zone is "GuildHouse" or "GuildGallery".
        """
        return await self.read_value_from_offset(0x30A, Primitive.bool)

    async def zone_loaded_flag(self) -> bool:
        """Zone loaded flag at 0x37D. Cleared on OnZoneLoaded."""
        return await self.read_value_from_offset(0x37D, Primitive.bool)

    async def guild_house_float(self) -> float:
        """Float at 0x360. Set to 8.0 in guild house zones."""
        return await self.read_value_from_offset(0x360, Primitive.float32)

    # -------------------------------------------------------------------------
    # Adventure Party data (MSG_RequestAdventureParty / MSG_RequestJoinAdventureParty)
    # -------------------------------------------------------------------------

    async def adventure_party_list(self) -> Optional[DynamicAdventurePartyList]:
        """Shared pointer to deserialized AdventurePartyList at 0xA8.

        Populated by MSG_RequestAdventureParty (FUN_141208900, r792258) from the
        "Buffer" DML field. Contains the full party hierarchy:
          AdventurePartyList -> [AdventurePartyInfo] -> [AdventurePartyEntryInfo]

        Returns None if no adventure party data has been received yet.
        """
        ptr = await self.read_value_from_offset(0xA8, Primitive.uint64)
        if ptr == 0:
            return None
        return DynamicAdventurePartyList(self.hook_handler, ptr)

    async def join_requesting_player_gid_status3(self) -> int:
        """RequestingPlayerGID at 0xC8.
        Written by MSG_RequestJoinAdventureParty when Status==3
        (join request accepted / you are being invited to a party).
        """
        return await self.read_value_from_offset(0xC8, Primitive.uint64)

    async def join_requesting_player_gid_status1(self) -> int:
        """RequestingPlayerGID at 0xE0.
        Written by MSG_RequestJoinAdventureParty when Status==1
        (someone is asking to join YOUR party).
        """
        return await self.read_value_from_offset(0xE0, Primitive.uint64)

    async def join_request_party_gid(self) -> int:
        """PartyGID at 0xE8.
        Written by MSG_RequestJoinAdventureParty when Status==3
        (the party GID for the join invitation).
        """
        return await self.read_value_from_offset(0xE8, Primitive.uint64)

    async def join_cooldown(self) -> int:
        """Join cooldown at 0x364 (uint32).
        Written by MSG_RequestAdventureParty from the "JoinCooldown" DML field.
        """
        return await self.read_value_from_offset(0x364, Primitive.uint32)

    # -------------------------------------------------------------------------
    # Adventure Party / Group fields
    # -------------------------------------------------------------------------

    async def adventure_party_state(self) -> int:
        """State flag at 0x268. Non-zero triggers party creation in OnZoneLoaded."""
        return await self.read_value_from_offset(0x268, Primitive.int32)

    async def adventure_party_param(self) -> int:
        return await self.read_value_from_offset(0x26C, Primitive.int32)

    async def group_gid(self) -> int:
        return await self.read_value_from_offset(0x260, Primitive.uint64)

    # -------------------------------------------------------------------------
    # Group Quest fields (MSG_SetGroupQuest)
    # -------------------------------------------------------------------------

    async def has_group_quest(self) -> bool:
        """Group quest flag at 0x100. Set by MSG_SetGroupQuest handler."""
        return await self.read_value_from_offset(0x100, Primitive.bool)

    async def group_quest_gid(self) -> int:
        """Group Quest GID at 0x108 (uint64).
        Written by MSG_SetGroupQuest from the "QuestGID" DML field.
        """
        return await self.read_value_from_offset(0x108, Primitive.uint64)

    async def group_goal_gid(self) -> int:
        """Group Goal GID at 0x110 (uint64).
        Written by MSG_SetGroupQuest from the "GoalGID" DML field.
        """
        return await self.read_value_from_offset(0x110, Primitive.uint64)

    # -------------------------------------------------------------------------
    # Misc fields
    # -------------------------------------------------------------------------

    async def default_permission_mask(self) -> int:
        """Permission mask at 0x378. Init 0x7F (7-bit bitmask)."""
        return await self.read_value_from_offset(0x378, Primitive.uint32)


class DynamicSocialSystemsManager(DynamicMemoryObject, SocialSystemsManager):
    pass


class CurrentSocialSystemsManager(SocialSystemsManager):
    """Finds the live SocialSystemsManager singleton via constructor pattern.

    Why the singleton getter's cached global doesn't work
    =====================================================
    The SSM has getter functions (e.g. FUN_14122bb40, FUN_141203ea0, r792258) that
    look like standard singleton accessors — they check a lock flag, call a
    registry lookup, and store the result to a global (e.g. DAT_14328de88).
    However, these getters are never called at runtime. The initialization
    lock flag stays 0 and the code path that would populate the global is
    never executed.

    Instead, the SSM is created directly by a parent object's constructor
    (FUN_1412c6570, r792258) and stored at parent+0x23280 via shared_ptr. It lives on
    the heap at an arbitrary address that the getter's global never learns
    about. Pattern scanning for the getter code correctly locates the global
    address, but reading from it always returns 0 — hence the MemoryReadError
    at address 0x100 (base=0, offset=0x100).

    Why not hardcode vtable RVAs
    ============================
    The vtable RVA (e.g. 0x2B3A700) changes with every game patch as code
    and data are recompiled and relocated. Hardcoded RVAs require manual
    updates after each patch.

    Why not RTTI
    ============
    SocialSystemsManager has no standard MSVC RTTI TypeDescriptor
    (.?AVSocialSystemsManager@@). Only a pointer-type descriptor
    (.PEAVSocialSystemsManager@@) exists, which is used for exception
    handling, not for vtable discovery. RTTI-based approaches fail for
    this class.

    Constructor pattern approach (patch-survivable)
    ================================================
    The SSM constructor writes three vtable pointers in three consecutive
    LEA RAX,[rip+disp32] / MOV pairs:

      1. LEA RAX,[rip+disp32]; MOV [RDI],RAX       — main vtable at +0x00
      2. LEA RAX,[rip+disp32]; MOV [RSI],RAX       — sub-vtable at +0x48
      3. LEA RAX,[rip+disp32]; MOV [RDI+0x68],RAX  — sub-vtable at +0x68

    This triple-write pattern is unique in the binary. The fixed opcode bytes
    (LEA/MOV encodings, target registers, displacement) are stable across
    patches — only the disp32 operands change as vtables shift in .rdata.

    From the match we extract the first LEA's disp32 to compute the main
    vtable address, then scan process memory for an 8-byte pointer to that
    vtable to find the heap-allocated SSM object. The result is cached.
    """

    def __init__(self, hook_handler: HookHandler):
        super().__init__(hook_handler)
        self._ssm_addr = None

    async def read_base_address(self) -> int:
        if self._ssm_addr is None:
            self._ssm_addr = await self._find_ssm_via_constructor_pattern()
        return self._ssm_addr

    async def _find_ssm_via_constructor_pattern(self) -> int:
        """Locate the SSM singleton via constructor vtable pattern + heap scan."""
        module = pymem.process.module_from_name(
            self.hook_handler.process.process_handle, _EXE_NAME
        )
        if module is None:
            raise RuntimeError(f"{_EXE_NAME} module not found")
        module_base = module.lpBaseOfDll
        module_end = module_base + module.SizeOfImage

        # Step 1: Find the constructor's triple vtable write pattern.
        # This matches the unique sequence of three consecutive LEA/MOV
        # pairs that write vtable pointers to obj+0, obj+0x48, obj+0x68.
        match_addr = await self.hook_handler.pattern_scan(
            _SSM_CONSTRUCTOR_PATTERN,
            module=_EXE_NAME,
        )

        # Step 2: Extract the main vtable address from the first LEA.
        # LEA RAX, [rip+disp32] is at match_addr (bytes 0-6):
        #   48 8D 05 [disp32]
        # The disp32 is a signed 32-bit offset relative to the next
        # instruction (match_addr + 7).
        disp32_bytes = await self.hook_handler.read_bytes(match_addr + 3, 4)
        disp32 = struct.unpack("<i", disp32_bytes)[0]
        vtable_addr = (match_addr + 7) + disp32

        # Sanity check: the vtable must be within the module's address space.
        if not (module_base <= vtable_addr < module_end):
            raise RuntimeError(
                f"Extracted vtable address 0x{vtable_addr:X} is outside "
                f"module range [0x{module_base:X}, 0x{module_end:X})"
            )

        # Step 3: Scan all process memory for the 8-byte vtable pointer to
        # find the heap-allocated SSM object. Filter out hits inside the
        # module itself (.rdata vtable references, code pointers).
        vtable_pattern = regex.escape(struct.pack("<Q", vtable_addr))
        try:
            all_matches = await self.hook_handler.pattern_scan(
                vtable_pattern, return_multiple=True
            )
        except PatternFailed:
            raise RuntimeError(
                "SocialSystemsManager object not found in process memory — "
                "the game may not be fully loaded yet"
            )
        if isinstance(all_matches, int):
            all_matches = [all_matches]

        # Filter out hits inside the module (.rdata vtable references)
        heap_hits = [
            a for a in all_matches if a < module_base or a >= module_end
        ]

        if len(heap_hits) == 1:
            return heap_hits[0]

        # Multiple candidates — validate via the MessageHandler sub-vtable
        # at +0x48. A real SSM object has a second vtable pointer here that
        # points back into the module's .rdata section.
        candidates = heap_hits if heap_hits else all_matches
        for addr in candidates:
            try:
                sub_vtable = await self.hook_handler.read_typed(
                    addr + 0x48, Primitive.uint64
                )
                if module_base <= sub_vtable < module_end:
                    return addr
            except Exception:
                continue

        if candidates:
            return candidates[0]

        raise RuntimeError(
            "SocialSystemsManager object not found in process memory — "
            "the game may not be fully loaded yet"
        )
