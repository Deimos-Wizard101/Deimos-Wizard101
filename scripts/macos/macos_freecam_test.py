"""Headless freecam diagnostic on macOS, run THROUGH the signed launcher.

    PYTHONPATH=... scripts/macos/launcher/target/release/deimos-launcher \\
        scripts/macos/macos_freecam_test.py

Same code path as Linux/Windows (no platform-specific calls). The real signal is
the *selected camera controller* address (which camera is actually active),
independent of the `is_freecam` flag (the game may rewrite that flag from the live
camera state each frame). After ON the selected controller should equal the FREE
controller; after OFF it should equal the ELASTIC controller — proof the
`_switch_camera` RPC actually switched the camera each way. Guaranteed cleanup in
`finally` so the game isn't left stuck in freecam.
"""
import asyncio

from wizwalker import ClientHandler


def hx(addr):
    return f"{addr:#x}" if addr else "None"


def tag(addr, elastic, free):
    if addr == elastic:
        return "ELASTIC"
    if addr == free:
        return "FREE"
    return "other"


async def selected_addr(c):
    try:
        sel = await c.game_client.selected_camera_controller()
        return await sel.read_base_address()
    except Exception as e:  # noqa: BLE001
        print("  (selected_camera_controller error:", e, ")")
        return None


async def sample(c, label, elastic, free):
    for _ in range(3):
        sel = await selected_addr(c)
        fc = await c.game_client.is_freecam()
        print(f"  {label}: selected={hx(sel)} ({tag(sel, elastic, free)}) is_freecam={fc}")
        await asyncio.sleep(0.4)


async def main() -> None:
    ch = ClientHandler()
    clients = ch.get_new_clients()
    print("clients (pids):", [c.process_id for c in clients])
    if not clients:
        print("NO CLIENTS — is Wizard101 running under Wine?")
        return
    c = clients[0]
    await c.activate_hooks()
    print("activate_hooks returned OK")

    elastic = await (await c.game_client.elastic_camera_controller()).read_base_address()
    free = await (await c.game_client.free_camera_controller()).read_base_address()
    print(f"elastic_controller={hx(elastic)}  free_controller={hx(free)}")

    try:
        sel = await selected_addr(c)
        print(f"selected before: {hx(sel)} ({tag(sel, elastic, free)})  is_freecam={await c.game_client.is_freecam()}")

        print("--- camera_freecam() ---")
        await c.camera_freecam()
        await asyncio.sleep(0.4)
        await sample(c, "after ON ", elastic, free)

        print("--- camera_elastic() ---")
        await c.camera_elastic()
        await asyncio.sleep(0.4)
        await sample(c, "after OFF", elastic, free)
    finally:
        # Never leave the game stuck in freecam.
        try:
            await c.camera_elastic()
        except Exception as e:  # noqa: BLE001
            print("cleanup camera_elastic error:", e)
        final_sel = await selected_addr(c)
        print(f"FINAL: selected={hx(final_sel)} ({tag(final_sel, elastic, free)})  is_freecam={await c.game_client.is_freecam()}")

    await ch.close()


asyncio.run(main())
