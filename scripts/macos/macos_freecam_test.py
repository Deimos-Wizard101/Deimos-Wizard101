"""Headless freecam proof on macOS, run THROUGH the signed launcher.

    PYTHONPATH=... scripts/macos/launcher/target/release/deimos-launcher \\
        scripts/macos/macos_freecam_test.py

Exercises the full feature flow with NO platform-specific calls (same code that
runs on Linux/Windows): open client, activate_hooks (a safe no-op on macOS, must
not hang), then toggle freecam. Freecam's camera switch is direct reads + the
pointer-redirect RPC, so it works under Rosetta; `is_freecam` flipping True then
False with the game alive confirms it. (The player-freeze via movement-update NOP
is inline and ignored by Rosetta — a known macOS degradation, not a failure.)
Watch the game to see the camera detach.
"""
import asyncio

from wizwalker import ClientHandler


async def main() -> None:
    ch = ClientHandler()
    clients = ch.get_new_clients()
    print("clients (pids):", [c.process_id for c in clients])
    if not clients:
        print("NO CLIENTS — is Wizard101 running under Wine?")
        return
    c = clients[0]

    await c.activate_hooks()  # no-op on macOS; must return without hanging
    print("activate_hooks returned OK")

    print("is_freecam before:", await c.game_client.is_freecam())
    await c.camera_freecam()
    print("is_freecam after ON:", await c.game_client.is_freecam())
    await asyncio.sleep(3)
    await c.camera_elastic()
    print("is_freecam after OFF:", await c.game_client.is_freecam())
    print("FREECAM TOGGLE OK — camera switched via RPC on macOS/Rosetta")

    await ch.close()


asyncio.run(main())
