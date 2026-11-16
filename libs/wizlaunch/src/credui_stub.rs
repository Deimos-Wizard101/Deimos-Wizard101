//! Non-Windows stub for the OS credential dialog (Windows CredUI backs the real one).
use crate::errors::VaultError;

pub fn prompt_credentials(_caption: &str, _message: &str) -> Result<(String, String), VaultError> {
    Err(VaultError::CredUiFailed(
        "the credential dialog is not supported on this platform".into(),
    ))
}
