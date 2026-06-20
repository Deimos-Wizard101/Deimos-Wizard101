import asyncio

from pymem.exception import MemoryReadError
from wizwalker import HookAlreadyActivated, HookNotActive, HookNotReady, PatternFailed, Client
from wizwalker.memory import HookHandler, SimpleHook

from loguru import logger

_dance_moves_transtable = str.maketrans("abcd", "WDSA")

# Thanks to peechez for this class
class DanceGameMovesHook(SimpleHook):
    signature_name = "rdi"
    pattern = rb"\x48\x8B\xF8\x48\x39\x70\x10"
    instruction_length = 7
    exports = [("dance_game_moves", 8)]
    noops = 2

    async def bytecode_generator(self, packed_exports):
        return (
                b"\x48\x8B\xF8"
                b"\x48\x8B\x00"
                b"\x48\xA3" + packed_exports[0][1] +
                b"\x48\x8B\xC7"
                b"\x48\x39\x70\x10"
        )


class DanceGameMovesHookRbx(SimpleHook):
    signature_name = "rbx"
    pattern = rb"\x48\x8B\xD8\x48\x39\x70\x10\x76.\x8B\xC6"
    instruction_length = 7
    exports = [("dance_game_moves", 8)]
    noops = 2

    async def bytecode_generator(self, packed_exports):
        return (
                b"\x48\x8B\xD8"
                b"\x48\x8B\x00"
                b"\x48\xA3" + packed_exports[0][1] +
                b"\x48\x8B\xC3"
                b"\x48\x39\x70\x10"
        )



async def activate_dance_game_moves_hook(
        self, *, wait_for_ready: bool = False, timeout: float = None
):
    if self._check_if_hook_active(DanceGameMovesHook):
        raise HookAlreadyActivated("DanceGameMovesHook")

    await self._check_for_autobot()

    hook = None
    pattern_errors = []
    for hook_type in (DanceGameMovesHook, DanceGameMovesHookRbx):
        candidate = hook_type(self)
        try:
            await candidate.hook()
        except PatternFailed as error:
            pattern_errors.append(error)
            logger.debug(
                f"Dance game hook signature '{hook_type.signature_name}' did not match; trying fallback."
            )
            continue
        hook = candidate
        break

    if hook is None:
        logger.error("No supported dance game hook signature matched WizardGraphicalClient.exe.")
        raise pattern_errors[-1]

    self._active_hooks[DanceGameMovesHook] = hook
    self._base_addrs["dance_game_moves"] = hook.dance_game_moves
    logger.info(f"Dance game hook activated with signature '{hook.signature_name}'.")

    if wait_for_ready:
        await self._wait_for_value(hook.dance_game_moves, timeout)

    return hook.signature_name


HookHandler.activate_dance_game_moves_hook = activate_dance_game_moves_hook


async def deactivate_dance_game_moves_hook(self):
    if not self._check_if_hook_active(DanceGameMovesHook):
        raise HookNotActive("DanceGameMovesHook")

    hook = self._get_hook_by_type(DanceGameMovesHook)
    del self._active_hooks[DanceGameMovesHook]
    await hook.unhook()

    del self._base_addrs["dance_game_moves"]


HookHandler.deactivate_dance_game_moves_hook = deactivate_dance_game_moves_hook

async def attempt_activate_dance_hook(client: Client, sleep_time: float = 0.1):
    hook_is_active = client.hook_handler._check_if_hook_active(DanceGameMovesHook)
    if client.dance_hook_status and hook_is_active:
        logger.debug(f"Auto Pet - Client {client.title}: Dance game hook already active.")
        await asyncio.sleep(sleep_time)
        return True

    client.dance_hook_status = False
    try:
        signature_name = await client.hook_handler.activate_dance_game_moves_hook()
    except HookAlreadyActivated:
        signature_name = "existing"
    except Exception:
        logger.exception(f"Auto Pet - Client {client.title}: Dance game hook activation failed.")
        await asyncio.sleep(sleep_time)
        return False

    client.dance_hook_status = True
    logger.info(
        f"Auto Pet - Client {client.title}: Dance game hook activation succeeded "
        f"(signature={signature_name})."
    )
    await asyncio.sleep(sleep_time)
    return True

async def attempt_deactivate_dance_hook(client: Client, sleep_time: float = 0.1):
    if client.dance_hook_status or client.hook_handler._check_if_hook_active(DanceGameMovesHook):
        try:
            await client.hook_handler.deactivate_dance_game_moves_hook()
        except HookNotActive:
            logger.debug(f"Auto Pet - Client {client.title}: Dance game hook was already inactive.")
        except Exception:
            logger.exception(f"Auto Pet - Client {client.title}: Dance game hook cleanup failed.")

        client.dance_hook_status = False
    await asyncio.sleep(sleep_time)


async def read_current_dance_game_moves(self) -> str:
    try:
        addr = self._base_addrs["dance_game_moves"]
    except KeyError:
        raise HookNotActive("DanceGameMovesHook")

    try:
        moves = await self.read_bytes(addr, 8)
    except MemoryReadError:
        raise HookNotReady("DanceGameMovesHook")
    return moves.partition(b"\0")[0].decode().translate(_dance_moves_transtable)


HookHandler.read_current_dance_game_moves = read_current_dance_game_moves
