import json
import os
from pathlib import Path

from cryptography.fernet import Fernet
import win32crypt


class AccountVault:
    def __init__(self, vault_path: str | None = None):
        if vault_path is None:
            appdata = os.environ.get("APPDATA", "")
            vault_dir = Path(appdata) / "Deimos"
            vault_dir.mkdir(parents=True, exist_ok=True)
            self._path = vault_dir / "accounts.vault"
        else:
            self._path = Path(vault_path)

        self._key_path = self._path.with_suffix(".key")
        self._fernet = Fernet(self._load_or_create_key())
        self._accounts: dict[str, dict[str, str]] = {}
        self._load()

    def _load_or_create_key(self) -> bytes:
        """Load existing DPAPI-protected key or generate a new one."""
        if self._key_path.exists():
            protected_key = self._key_path.read_bytes()
            # CryptUnprotectData returns (description, data)
            _, raw_key = win32crypt.CryptUnprotectData(protected_key, None, None, None, 0)
            return raw_key
        else:
            # Generate a new Fernet key and protect it with DPAPI
            raw_key = Fernet.generate_key()
            protected_key = win32crypt.CryptProtectData(raw_key, None, None, None, None, 0)
            self._key_path.write_bytes(protected_key)
            return raw_key

    def _load(self):
        if self._path.exists():
            encrypted = self._path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            self._accounts = json.loads(decrypted)
        else:
            self._accounts = {}

    def _save(self):
        data = json.dumps(self._accounts).encode()
        encrypted = self._fernet.encrypt(data)
        self._path.write_bytes(encrypted)

    def save_account(self, nickname: str, username: str, password: str):
        self._accounts[nickname] = {"username": username, "password": password}
        self._save()

    def delete_account(self, nickname: str):
        self._accounts.pop(nickname, None)
        self._save()

    def get_account(self, nickname: str) -> tuple[str, str]:
        acct = self._accounts[nickname]
        return acct["username"], acct["password"]

    def get_nicknames(self) -> list[str]:
        return list(self._accounts.keys())
