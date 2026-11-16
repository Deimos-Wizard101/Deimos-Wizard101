//! Non-Windows stub for the account vault (the real one uses Windows Credential
//! Manager). Deimos hooks an already-running client without the vault, so these
//! return errors / empty — the app runs and the account UI is just non-functional.
use crate::errors::VaultError;

pub fn write_credential(_nickname: &str, _username: &str, _password: &str) -> Result<(), VaultError> {
    Err(VaultError::CredentialWrite(
        "the account vault is not supported on this platform".into(),
    ))
}

pub fn read_credential(nickname: &str) -> Result<(String, String), VaultError> {
    Err(VaultError::CredentialNotFound(nickname.to_string()))
}

pub fn delete_credential(_nickname: &str) -> Result<(), VaultError> {
    Err(VaultError::CredentialDelete(
        "the account vault is not supported on this platform".into(),
    ))
}

pub fn list_credential_nicknames() -> Result<Vec<String>, VaultError> {
    Ok(Vec::new())
}

pub fn has_credential(_nickname: &str) -> bool {
    false
}
