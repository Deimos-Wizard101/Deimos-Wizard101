from __future__ import annotations

import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

# wizpatch draws an in-place progress bar with carriage returns + ANSI escapes,
# which is meant for a TTY. In the GUI log that becomes many lines of escape-code
# noise, so we strip ANSI and skip the progress snapshots — the manifest header
# and the trailing "Done. …" summary are what's worth logging.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PROGRESS_RE = re.compile(r"\d+/\d+ files")
# Detect the verify -> patch transition from the progress line. During pure CRC
# verification everything is idle ("0.0 MiB | 0.0 MiB/s | small=  0 large=0/N");
# once a download starts, the in-flight worker counts (and, for large files, the
# MiB) become non-zero. Watching the workers catches even small-file downloads
# whose byte totals round to 0.0 MiB.
_MIB_RE = re.compile(r"([\d.]+)\s*MiB\b")
_WORKERS_RE = re.compile(r"small=\s*(\d+)\s+large=\s*(\d+)/")


def _is_downloading(progress_line: str) -> bool:
    """Whether a wizpatch progress line indicates an active download (patching)."""
    m = _MIB_RE.search(progress_line)
    if m and float(m.group(1)) > 0.0:
        return True
    w = _WORKERS_RE.search(progress_line)
    if w and (int(w.group(1)) > 0 or int(w.group(2)) > 0):
        return True
    return False


# CreateProcess flag: don't pop a console window for the child (Deimos is a
# windowed app). Harmless/no-op off Windows.
_CREATE_NO_WINDOW = 0x08000000

_BINARY_NAME = "wizpatch.exe" if sys.platform == "win32" else "wizpatch"


def _is_frozen() -> bool:
    """True when running as a PyInstaller bundle (a real Deimos.exe)."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def wizpatch_binary_path() -> Optional[Path]:
    """Locate the wizpatch binary, or ``None`` if it isn't available.

    Frozen builds carry it next to the bundle (added via ``Deimos.spec``); a dev
    checkout uses the cargo build output under ``libs/wizpatch/target/release``.
    """
    if _is_frozen():
        p = Path(sys._MEIPASS) / _BINARY_NAME  # type: ignore[attr-defined]
        return p if p.exists() else None
    # Dev: repo root is two levels up from this file (src/wizpatch_runner.py).
    repo_root = Path(__file__).resolve().parent.parent
    p = repo_root / "libs" / "wizpatch" / "target" / "release" / _BINARY_NAME
    return p if p.exists() else None


def patch_game_files(
    game_path: str,
    *,
    revision: Optional[str] = None,
    timeout: float = 1800.0,
    status_cb: Optional[Callable[[str], None]] = None,
) -> bool:
    """CRC-verify and patch the Wizard101 install at ``game_path``.

    Runs ``wizpatch patch Data/* Bin/* --path <game_path> [--revision …]``,
    streaming its progress to the log. Returns ``True`` on a clean (exit 0) run,
    ``False`` on any failure (binary missing, spawn error, timeout, non-zero
    exit). Blocking — call it off the event loop (``asyncio.to_thread``).

    ``status_cb`` is invoked once with ``"patching"`` the moment a download begins
    (the caller has already shown "verifying"); it may run on a worker thread, so it
    must only do thread-safe, non-blocking work.
    """
    exe = wizpatch_binary_path()
    if exe is None:
        logger.warning(
            "[wizpatch] patcher binary not found; skipping game-file verification."
        )
        return False

    # Scope to the actual game content — Data/* (WADs, GameData) and Bin/* (client
    # executables/DLLs) — passed as literal globs (subprocess uses no shell, so the
    # '*' reaches wizpatch, which globs it across '/'). This deliberately skips:
    #   • PatchClient/* — the KI launcher/patcher, server-403'd and irrelevant
    #     (wizlaunch runs the client directly, never the launcher); and
    #   • the platform wrapper dirs, whose stray files would otherwise be downloaded
    #     into a Steam install.
    # The binary's default platform (windows on this Windows-only tool) is used for
    # every install: its file list is the shared game content and fetches reliably,
    # whereas the Steam file-list endpoint intermittently 403s (total failure). No
    # --verbose: it prints a line per file (thousands when already current); the
    # trailing "Done. …" summary is the right amount of log for a pre-launch verify.
    args = [str(exe), "patch", "Data/*", "Bin/*", "--path", game_path]
    if revision:
        args += ["--revision", revision]

    logger.info(f"[wizpatch] verifying game files at '{game_path}'...")
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(exe.parent),
            creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception as e:
        logger.error(f"[wizpatch] failed to start patcher: {e}")
        return False

    # Iterating stdout blocks until the child closes it, so a watchdog timer
    # enforces the overall bound: if the patch exceeds `timeout`, kill the child,
    # which EOFs stdout and unblocks the loop (returncode then reflects the kill).
    timed_out = threading.Event()

    def _kill_on_timeout():
        timed_out.set()
        proc.kill()

    watchdog = threading.Timer(timeout, _kill_on_timeout)
    watchdog.start()
    patching_signaled = False
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = _ANSI_RE.sub("", raw).strip()
            if not line:
                continue
            if _PROGRESS_RE.search(line):
                # Progress snapshot: don't log it, but use it to detect the
                # verify -> patch transition (a download becoming active).
                if (
                    status_cb is not None
                    and not patching_signaled
                    and _is_downloading(line)
                ):
                    patching_signaled = True
                    try:
                        status_cb("patching")
                    except Exception:
                        pass
                continue
            logger.info(f"[wizpatch] {line}")
        proc.wait()
    except Exception as e:
        logger.error(f"[wizpatch] patch errored: {e}")
        return False
    finally:
        watchdog.cancel()

    if timed_out.is_set():
        logger.error(
            f"[wizpatch] patch timed out after {timeout:.0f}s; aborting verify."
        )
        return False
    if proc.returncode == 0:
        logger.info("[wizpatch] game files verified/patched successfully.")
        return True
    logger.warning(f"[wizpatch] patcher exited with code {proc.returncode}.")
    return False
