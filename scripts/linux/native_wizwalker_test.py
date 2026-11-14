"""Native-Linux smoke test: hook a running Wizard101 client and read game state.

Run with the native venv and xdotool on PATH, from the repo root:

    nix-shell -p xdotool --run \
      '<venv>/bin/python3 scripts/linux/native_wizwalker_test.py'

Requires: the zhol extension (zhol.so) and src/linux_backend on PYTHONPATH (set
below relative to the repo), and a running client. With an *in-game* character
it prints position/zone/stats; at the login screen only hook installation is
exercised (no character to read).
"""
import asyncio
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# zhol.so location: built from the zhol crate's `python` feature. Override with
# ZHOL_SO_DIR; defaults to a conventional spot.
ZHOL_SO_DIR = os.environ.get("ZHOL_SO_DIR", os.path.expanduser("~/.local/share/Deimos-linux/py"))

for p in (
    os.path.join(REPO, "src", "linux_backend"),   # pymem shim
    ZHOL_SO_DIR,                                   # zhol.so
    os.path.join(REPO, "libs", "wizwalker"),       # wizwalker
    os.path.join(REPO, "libs", "wizsprinter"),
):
    sys.path.insert(0, p)

import wizwalker
from wizwalker import ClientHandler
from wizwalker.utils import override_wiz_install_location

GAME = os.environ.get(
    "WIZLAUNCH_GAME_PATH",
    os.path.expanduser("~/.local/share/Steam/steamapps/common/Wizard101"),
)
override_wiz_install_location(GAME)

HOOKS = [
    "activate_player_hook", "activate_duel_hook", "activate_quest_hook",
    "activate_player_stat_hook", "activate_client_hook", "activate_root_window_hook",
]


async def main():
    handler = ClientHandler()
    clients = handler.get_new_clients()
    print(f"clients: pids {[c.process_id for c in clients]}")
    if not clients:
        print("no running client found")
        return
    client = clients[-1]
    print(f"using pid={client.process_id} handle={client.window_handle}")

    try:
        hh = client.hook_handler
        for name in HOOKS:
            fn = getattr(hh, name, None)
            if fn is None:
                continue
            try:
                await fn(wait_for_ready=False)
                print(f"  {name}: OK")
            except Exception as e:
                print(f"  {name}: FAIL {type(e).__name__}: {str(e)[:70]}")
        print("active hooks:", sorted(h.__name__ for h in hh._active_hooks))

        await asyncio.sleep(1.0)
        for name, coro in [
            ("is_loading", client.is_loading()),
            ("zone_name", client.zone_name()),
        ]:
            try:
                print(f"  {name} -> {await coro!r}")
            except Exception as e:
                print(f"  {name} -> ERR {type(e).__name__}: {str(e)[:60]}")
        try:
            pos = await client.body.position()
            print(f"  PLAYER POSITION -> x={pos.x:.1f} y={pos.y:.1f} z={pos.z:.1f}")
        except Exception as e:
            print(f"  position -> ERR {type(e).__name__}: {str(e)[:70]}")
    finally:
        print("unhooking...")
        try:
            await handler.close()
        except Exception as e:
            print(f"  close err: {e}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
