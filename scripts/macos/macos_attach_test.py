"""Proof that the signed macOS launcher unblocks attaching to the game.

Run THROUGH the signed launcher (not a bare python), with PYTHONPATH pointing at
the venv site-packages, src/linux_backend, libs/wizwalker, libs/wizsprinter, and
the dir holding zhol.so:

    PYTHONPATH=... scripts/macos/launcher/target/release/deimos-launcher \\
        scripts/macos/macos_attach_test.py

`ClientHandler.get_new_clients()` opens each client process via zhol — that's the
exact `task_for_pid` that returns kr=5 from an unentitled host. If it returns the
game pid here, the entitlement is effective. We then read the PE `MZ` header
directly through zhol (no inline hook — Rosetta ignores those), proving memory
access end to end under the entitled host.
"""
import asyncio

from wizwalker import ClientHandler


async def main() -> None:
    ch = ClientHandler()
    clients = ch.get_new_clients()  # opens each process -> zhol task_for_pid
    print("clients (pids):", [c.process_id for c in clients])
    if not clients:
        print("NO CLIENTS FOUND — is Wizard101 running under Wine?")
        return

    c = clients[0]
    proc = c.hook_handler.process.process_handle  # zhol.Process
    mod = proc.module("WizardGraphicalClient.exe")
    if mod is None:
        print("exe module not found in target")
        await ch.close()
        return
    base, size = mod
    header = proc.read_bytes(base, 2)
    ok = header == b"MZ"
    print(f"exe base={base:#x} size={size:#x} header={header!r} MZ={'OK' if ok else 'NO'}")
    if ok:
        print("PROOF: task_for_pid + memory read via the entitled launcher WORKED.")
    await ch.close()


asyncio.run(main())
