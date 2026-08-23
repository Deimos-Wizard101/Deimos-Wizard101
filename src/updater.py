"""Self-update support for Deimos.

This module is deliberately self-contained — it never imports ``Deimos`` (to
avoid an import cycle) and takes the version / repo coordinates as arguments.

Flow (frozen builds only):

  1. ``get_latest_release`` queries the GitHub Releases API.
  2. ``is_newer`` compares it against the running version (semver-aware,
     including pre-release ordering).
  3. ``download_update`` streams the new ``Deimos.exe`` into ``%APPDATA%`` and
     verifies its SHA256.
  4. ``apply_and_relaunch`` extracts the embedded ``deimos-updater.exe`` helper
     and spawns it detached; the helper waits for us to exit, swaps the exe and
     relaunches it.

Every step degrades gracefully: network failures, missing assets or a missing
helper binary return ``None``/``False`` rather than raising into startup.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests
from loguru import logger

# Windows process-creation flags (see CreateProcess docs). Defined locally so
# the module imports cleanly on non-Windows dev machines.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000

_UPDATER_BINARY_NAME = "deimos-updater.exe"


@dataclass
class ReleaseInfo:
    version: str  # version number without leading 'v', e.g. "3.14.0"
    exe_url: Optional[str]  # direct download URL for Deimos.exe
    sha256: Optional[str]  # expected SHA256 of Deimos.exe (lowercase hex) or None
    notes_url: str  # human-facing release page
    prerelease: bool


def is_frozen() -> bool:
    """True when running as a PyInstaller bundle (i.e. a real Deimos.exe)."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def update_dir() -> Path:
    """Writable scratch directory for downloads / the helper / its log."""
    appdata = os.environ.get("APPDATA", "")
    d = Path(appdata) / "Deimos" / "update" if appdata else Path(os.getcwd()) / "update"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Version comparison (semver core + pre-release ordering)
# ---------------------------------------------------------------------------


def _parse_version(v: str) -> tuple[list[int], list]:
    """Split a version into (release-core, pre-release-identifiers).

    "3.14.0"        -> ([3, 14, 0], [])           # [] sorts *after* any pre-release
    "3.14.0-beta.1" -> ([3, 14, 0], ['beta', 1])
    """
    v = v.strip().lstrip("vV")
    core, _, pre = v.partition("-")
    core_parts: list[int] = []
    for part in core.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        core_parts.append(int(digits) if digits else 0)
    pre_parts: list = []
    if pre:
        for ident in pre.split("."):
            pre_parts.append(int(ident) if ident.isdigit() else ident)
    return core_parts, pre_parts


def _cmp_pre(a: list, b: list) -> int:
    """Compare pre-release identifier lists per semver §11.

    An empty list (a normal release) outranks any non-empty list.
    """
    if not a and not b:
        return 0
    if not a:
        return 1  # release > pre-release
    if not b:
        return -1
    for x, y in zip(a, b):
        xi, yi = isinstance(x, int), isinstance(y, int)
        if xi and yi:
            if x != y:
                return 1 if x > y else -1
        elif xi != yi:
            # numeric identifiers have lower precedence than alphanumeric
            return -1 if xi else 1
        else:
            if x != y:
                return 1 if x > y else -1
    if len(a) != len(b):
        return 1 if len(a) > len(b) else -1
    return 0


def compare_versions(a: str, b: str) -> int:
    """Return 1 if a > b, -1 if a < b, 0 if equal."""
    a_core, a_pre = _parse_version(a)
    b_core, b_pre = _parse_version(b)
    n = max(len(a_core), len(b_core))
    a_core += [0] * (n - len(a_core))
    b_core += [0] * (n - len(b_core))
    if a_core != b_core:
        return 1 if a_core > b_core else -1
    return _cmp_pre(a_pre, b_pre)


def is_newer(remote: str, local: str) -> bool:
    """True if ``remote`` is a strictly newer version than ``local``."""
    try:
        return compare_versions(remote, local) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Release discovery
# ---------------------------------------------------------------------------


def get_latest_release(
    author: str,
    repo: str,
    *,
    include_prerelease: bool = False,
    timeout: float = 10.0,
) -> Optional[ReleaseInfo]:
    """Query the GitHub Releases API for the latest applicable release.

    Returns ``None`` on any network/parse failure so callers can simply skip.
    """
    headers = {"Accept": "application/vnd.github+json"}
    try:
        if include_prerelease:
            resp = requests.get(
                f"https://api.github.com/repos/{author}/{repo}/releases",
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            releases = [r for r in resp.json() if not r.get("draft")]
            if not releases:
                return None
            data = releases[0]
        else:
            resp = requests.get(
                f"https://api.github.com/repos/{author}/{repo}/releases/latest",
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.debug(f"Update check failed: {e}")
        return None

    tag = (data.get("tag_name") or "").lstrip("vV")
    if not tag:
        return None

    exe_url = None
    sha_url = None
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name == "Deimos.exe":
            exe_url = asset.get("browser_download_url")
        elif name in ("Deimos.exe.sha256", "Deimos.sha256"):
            sha_url = asset.get("browser_download_url")

    sha256 = None
    if sha_url:
        try:
            r = requests.get(sha_url, timeout=timeout)
            r.raise_for_status()
            # Accept either "<hash>" or "<hash>  Deimos.exe"
            sha256 = r.text.strip().split()[0].lower()
        except Exception as e:
            logger.debug(f"Could not fetch checksum: {e}")

    return ReleaseInfo(
        version=tag,
        exe_url=exe_url,
        sha256=sha256,
        notes_url=data.get("html_url", f"https://github.com/{author}/{repo}/releases"),
        prerelease=bool(data.get("prerelease")),
    )


# ---------------------------------------------------------------------------
# Download + verify
# ---------------------------------------------------------------------------


def download_update(
    url: str,
    expected_sha256: Optional[str],
    *,
    progress_cb: Optional[Callable[[int], None]] = None,
    timeout: float = 30.0,
) -> Optional[Path]:
    """Stream the new exe to the update dir, verifying its SHA256.

    ``progress_cb`` receives an integer percentage (0-100) when the content
    length is known. Returns the downloaded path, or ``None`` on failure.
    """
    dest = update_dir() / "Deimos.new.exe"
    hasher = hashlib.sha256()
    try:
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0))
            downloaded = 0
            last_pct = -1
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total > 0:
                        pct = int(downloaded * 100 / total)
                        if pct != last_pct:
                            last_pct = pct
                            progress_cb(pct)
    except Exception as e:
        logger.error(f"Update download failed: {e}")
        _safe_unlink(dest)
        return None

    if expected_sha256:
        actual = hasher.hexdigest().lower()
        if actual != expected_sha256.lower():
            logger.error(
                f"Update checksum mismatch (expected {expected_sha256}, got {actual}); discarding."
            )
            _safe_unlink(dest)
            return None
        logger.debug("Update checksum verified.")
    else:
        logger.warning("No checksum published for this release; skipping verification.")

    return dest


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def _updater_source_path() -> Optional[Path]:
    """Locate the embedded helper binary inside the bundle."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    p = Path(base) / _UPDATER_BINARY_NAME
    return p if p.exists() else None


def _bootloader_parent_pid() -> Optional[int]:
    """PID of the PyInstaller bootloader parent, when there is one.

    A one-file bundle runs *two* processes off the same image: the bootloader
    that unpacks ``_MEIPASS`` and the Python child that runs this code. Both
    hold a lock on Deimos.exe, so the helper has to wait for both — waiting only
    on ``os.getpid()`` returns while the parent is still cleaning up, and the
    swap then burns half its retry budget on sharing violations.

    Returns ``None`` unless the parent is running our own image, so a one-dir
    build (or a run from a shell) never leaves the helper waiting on
    explorer.exe until its timeout.
    """
    if sys.platform != "win32" or not is_frozen():
        return None
    try:
        ppid = os.getppid()
    except (AttributeError, OSError):
        return None
    if ppid <= 0:
        return None

    try:
        import ctypes
        import ctypes.wintypes

        _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.windll.kernel32

        def image_of(pid: int) -> Optional[str]:
            handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return None
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = ctypes.wintypes.DWORD(len(buf))
                if not k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                    return None
                return os.path.normcase(buf.value)
            finally:
                k32.CloseHandle(handle)

        # Compare against our *running image* rather than sys.executable: the
        # two diverge under a venv (where sys.executable is the shim), and this
        # keeps the check honest in every environment.
        ours = image_of(os.getpid())
        theirs = image_of(ppid)
    except Exception as e:
        logger.debug(f"Could not inspect parent process: {e}")
        return None

    return ppid if ours is not None and ours == theirs else None


def apply_and_relaunch(new_exe: Path, *, relaunch: bool = True) -> bool:
    """Spawn the detached helper to swap ``new_exe`` over the running exe.

    Must be called right before the process exits. Returns ``False`` (without
    side effects) when the helper isn't available, so the caller can fall back
    to telling the user to update manually.
    """
    src = _updater_source_path()
    if src is None:
        logger.error(
            "Update helper binary not found in bundle; cannot self-update. "
            "Please download the latest release manually."
        )
        return False

    target = Path(sys.executable)
    helper = update_dir() / _UPDATER_BINARY_NAME
    try:
        # Copy the helper out of the (temp) bundle dir to a stable location so
        # it survives the bundle being cleaned up on exit.
        helper.write_bytes(src.read_bytes())
    except Exception as e:
        logger.error(f"Could not stage update helper: {e}")
        return False

    # --pid is repeatable; the helper waits on every PID before swapping. Pass
    # the bootloader parent as well as ourselves — both hold the image lock.
    args = [str(helper), "--pid", str(os.getpid())]
    parent_pid = _bootloader_parent_pid()
    if parent_pid is not None:
        args += ["--pid", str(parent_pid)]
    args += [
        "--new",
        str(new_exe),
        "--target",
        str(target),
        "--log",
        str(update_dir() / "updater.log"),
    ]
    if relaunch:
        args.append("--relaunch")

    try:
        subprocess.Popen(
            args,
            creationflags=(
                _DETACHED_PROCESS
                | _CREATE_NEW_PROCESS_GROUP
                | _CREATE_BREAKAWAY_FROM_JOB
            ),
            close_fds=True,
            cwd=str(update_dir()),
        )
    except Exception as e:
        logger.error(f"Failed to launch update helper: {e}")
        return False

    logger.info(f"Update helper launched; swapping to v-from {new_exe.name} on exit.")
    return True


def _safe_unlink(p: Path):
    try:
        p.unlink()
    except OSError:
        pass
