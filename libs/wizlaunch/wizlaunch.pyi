"""Type stubs for the wizlaunch native module."""

def prompt_save_account(nickname: str) -> None:
    """Open a Windows CredUI dialog to collect and store credentials for the given nickname.

    The dialog is OS-owned — Python never sees the username or password.
    Raises RuntimeError if the user cancels or the dialog fails.
    """
    ...

def delete_account(nickname: str) -> None:
    """Delete an account from Windows Credential Manager and metadata."""
    ...

def list_accounts() -> list[str]:
    """List all account nicknames in stored order."""
    ...

def reorder_accounts(ordered: list[str]) -> None:
    """Reorder accounts to the given nickname order."""
    ...

def has_account(nickname: str) -> bool:
    """Check if an account exists in Windows Credential Manager."""
    ...

def validate_account(nickname: str) -> str | None:
    """Validate an account entry.

    Returns a human-readable error string if the entry needs attention (e.g. an
    older account saved before Steam support, which lacks a Steam-mode flag), or
    None if it is fully configured.
    """
    ...

def get_account_steam(nickname: str) -> bool | None:
    """Get an account's Steam-mode flag, or None if it has never been set."""
    ...

def set_account_steam(nickname: str, steam: bool) -> None:
    """Set whether an account launches in Steam mode."""
    ...

def get_window_config(
    nickname: str,
) -> tuple[int, int, int, int, int, int, bool, bool] | None:
    """Get an account's window placement/resolution config, or None if unset.

    Returns ``(x, y, w, h, res_w, res_h, locked, borderless)``: window top-left in
    virtual-desktop screen coords, window client size, forced render resolution,
    whether resolution is locked to the client size (crisp 1:1), and whether the
    window is borderless (title bar / borders stripped).
    """
    ...

def set_window_config(
    nickname: str,
    x: int, y: int, w: int, h: int,
    res_w: int, res_h: int, locked: bool,
    borderless: bool = False,
) -> None:
    """Set an account's window placement/resolution config."""
    ...

def clear_window_config(nickname: str) -> None:
    """Clear an account's window config (revert to default behavior)."""
    ...

def update_player_gid(nickname: str, gid: int) -> None:
    """Update the player GID (global ID) for a nickname."""
    ...

def get_player_gid(nickname: str) -> int | None:
    """Get the player GID for a nickname, or None if not set."""
    ...

def get_nickname_by_gid(gid: int) -> str | None:
    """Look up a nickname by its player GID, or None if not found."""
    ...

def launch_instance(
    nickname: str, game_path: str,
    login_server: str | None = None,
    timeout_secs: int = 30,
) -> int:
    """Launch one game instance, log in, and return the window handle.

    Credentials are read from Credential Manager internally and never enter Python.
    This function blocks — call via ``asyncio.to_thread()``.
    """
    ...

def launch_instances(
    nicknames: list[str], game_path: str,
    login_server: str | None = None,
    timeout_secs: int = 30,
) -> dict[str, int]:
    """Launch multiple game instances and return {nickname: window_handle}.

    Credentials never enter Python.  Blocks — call via ``asyncio.to_thread()``.
    """
    ...

def kill_instance(handle: int) -> bool:
    """Kill the process owning the given window handle. Returns True on success."""
    ...

def get_wizard_handles() -> list[int]:
    """Get all currently open Wizard101 window handles."""
    ...
