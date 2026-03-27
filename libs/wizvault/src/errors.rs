use pyo3::exceptions::PyRuntimeError;
use pyo3::PyErr;
use std::fmt;

#[derive(Debug)]
pub enum VaultError {
    CredentialNotFound(String),
    CredentialWrite(String),
    CredentialDelete(String),
    CredentialEnumerate(String),
    CredUiCancelled,
    CredUiFailed(String),
    MetadataIo(String),
    MetadataJson(String),
    LaunchFailed(String),
    LaunchTimeout(String),
    LoginFailed(String),
    LegacyDpapi(String),
    LegacyFernet(String),
    LegacyParse(String),
    WindowsApi(String),
}

impl fmt::Display for VaultError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            VaultError::CredentialNotFound(name) => {
                write!(f, "Credential not found: {name}")
            }
            VaultError::CredentialWrite(msg) => write!(f, "Failed to write credential: {msg}"),
            VaultError::CredentialDelete(msg) => write!(f, "Failed to delete credential: {msg}"),
            VaultError::CredentialEnumerate(msg) => {
                write!(f, "Failed to enumerate credentials: {msg}")
            }
            VaultError::CredUiCancelled => write!(f, "Credential dialog was cancelled by user"),
            VaultError::CredUiFailed(msg) => write!(f, "Credential dialog failed: {msg}"),
            VaultError::MetadataIo(msg) => write!(f, "Metadata I/O error: {msg}"),
            VaultError::MetadataJson(msg) => write!(f, "Metadata JSON error: {msg}"),
            VaultError::LaunchFailed(msg) => write!(f, "Launch failed: {msg}"),
            VaultError::LaunchTimeout(nick) => {
                write!(f, "Timed out waiting for window: {nick}")
            }
            VaultError::LoginFailed(msg) => write!(f, "Login failed: {msg}"),
            VaultError::LegacyDpapi(msg) => write!(f, "Legacy DPAPI decryption failed: {msg}"),
            VaultError::LegacyFernet(msg) => write!(f, "Legacy Fernet decryption failed: {msg}"),
            VaultError::LegacyParse(msg) => write!(f, "Legacy vault parse failed: {msg}"),
            VaultError::WindowsApi(msg) => write!(f, "Windows API error: {msg}"),
        }
    }
}

impl From<VaultError> for PyErr {
    fn from(err: VaultError) -> PyErr {
        PyRuntimeError::new_err(err.to_string())
    }
}

impl From<std::io::Error> for VaultError {
    fn from(err: std::io::Error) -> Self {
        VaultError::MetadataIo(err.to_string())
    }
}

impl From<serde_json::Error> for VaultError {
    fn from(err: serde_json::Error) -> Self {
        VaultError::MetadataJson(err.to_string())
    }
}

impl From<windows::core::Error> for VaultError {
    fn from(err: windows::core::Error) -> Self {
        VaultError::WindowsApi(err.to_string())
    }
}
