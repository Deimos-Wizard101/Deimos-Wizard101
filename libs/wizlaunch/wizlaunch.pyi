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
