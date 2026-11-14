"""Find running Wizard101 clients by pid (the Linux analogue of wizwalker's
HWND enumeration). Under Proton every client's argv[0] is the game exe path, so
a /proc scan identifies them without any window lookup.
"""
import os

WIZARD_EXE = "WizardGraphicalClient.exe"


def get_wizard_pids() -> list[int]:
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv0 = f.read().split(b"\x00", 1)[0]
        except OSError:
            continue
        base = argv0.rsplit(b"/", 1)[-1].rsplit(b"\\", 1)[-1]
        if base.lower() == WIZARD_EXE.lower().encode():
            pids.append(pid)
    return pids


def is_wizard_running(pid: int) -> bool:
    return os.path.isdir(f"/proc/{pid}")
