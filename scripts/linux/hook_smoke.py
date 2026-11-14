"""Smoke-test wizwalker against the first running client: hook, read, unhook.

Run inside a live scripts/linux/run.sh session, from the repo root:

    scripts/linux/exec.sh 'proton_run "$WIN_PYTHON" "$(winpath scripts/linux/hook_smoke.py)" > "$LOG_DIR/hook_smoke.out" 2>&1'

Expect every hook listed as active and is_loading/in_battle to read; zone_name
raises MemoryReadError until a character is actually in a zone.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.getcwd())

from wizwalker import ClientHandler
from src.utils import override_wiz_install_using_handle


async def main():
    override_wiz_install_using_handle()
    handler = ClientHandler()
    clients = handler.get_new_clients()
    print(f"clients: {len(clients)}")
    if not clients:
        return
    client = clients[0]
    print(f"title={client.title!r} pid={client.process_id}")
    await client.activate_hooks(wait_for_ready=False)
    print("hooks active:", sorted(h.__name__ for h in client.hook_handler._active_hooks))
    await asyncio.sleep(2)
    for name in ("is_loading", "zone_name", "in_battle"):
        try:
            print(f"{name} -> {await getattr(client, name)()!r}")
        except Exception as e:
            print(f"{name} -> {type(e).__name__}: {e}")
    await handler.close()
    print("closed cleanly")


asyncio.run(main())
