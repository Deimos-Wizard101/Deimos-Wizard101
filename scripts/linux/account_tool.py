"""Account-store helper, run under the prefix's Windows Python.

Deimos keeps accounts in the Windows Credential Manager (target
``Deimos/account/<nick>``) plus ``%APPDATA%/Deimos/account_metadata.json`` --
wizlaunch's own format. Under Proton, Wine implements the credential store
inside the prefix, so no Linux keyring is involved. The one wizlaunch call this
cannot reach from Linux is *saving* a new account: it pops a Win32 credential
dialog (``CredUIPromptForWindowsCredentialsW``) that Wine does not implement.

This writes the same credential directly via ``CredWriteW`` (which Wine does
implement) in the exact layout wizlaunch reads back -- username in ``UserName``,
password as raw UTF-8 bytes in the blob -- then records the account through
wizlaunch so the metadata is written by its own code.

Not called directly; scripts/linux/add-account.sh drives it. Commands:

    add <nick>   read username then password, one per line, from stdin
    list         print saved nicknames
    delete <nick>
"""
import ctypes
import ctypes.wintypes as wt
import sys

import wizlaunch

TARGET_PREFIX = "Deimos/account/"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2

advapi32 = ctypes.windll.advapi32


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wt.DWORD),
        ("Type", wt.DWORD),
        ("TargetName", wt.LPWSTR),
        ("Comment", wt.LPWSTR),
        ("LastWritten", wt.FILETIME),
        ("CredentialBlobSize", wt.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wt.DWORD),
        ("AttributeCount", wt.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wt.LPWSTR),
        ("UserName", wt.LPWSTR),
    ]


def write_credential(nickname: str, username: str, password: str) -> None:
    blob = password.encode("utf-8")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    cred = CREDENTIALW(
        Flags=0,
        Type=CRED_TYPE_GENERIC,
        TargetName=TARGET_PREFIX + nickname,
        CredentialBlobSize=len(blob),
        CredentialBlob=buf,
        Persist=CRED_PERSIST_LOCAL_MACHINE,
        UserName=username,
    )
    if not advapi32.CredWriteW(ctypes.byref(cred), 0):
        raise OSError(f"CredWriteW failed (error {ctypes.get_last_error()})")


def cmd_add(nickname: str) -> None:
    username = sys.stdin.readline().rstrip("\n")
    password = sys.stdin.readline().rstrip("\n")
    if not username or not password:
        raise SystemExit("username and password must both be non-empty")
    write_credential(nickname, username, password)
    # Record it through wizlaunch so the metadata file is written in its format;
    # a Steam-mode flag of False marks the account fully configured (no effect on
    # Linux, where the client always launches through Proton).
    wizlaunch.set_account_steam(nickname, False)
    print(f"saved account '{nickname}'")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: account_tool.py <add|list|delete> [nickname]")
    command = sys.argv[1]
    if command == "add":
        cmd_add(sys.argv[2])
    elif command == "list":
        for nick in wizlaunch.list_accounts():
            print(nick)
    elif command == "delete":
        wizlaunch.delete_account(sys.argv[2])
        print(f"deleted account '{sys.argv[2]}'")
    else:
        raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main()
