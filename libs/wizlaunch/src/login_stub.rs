//! Non-Windows stub for in-client auto-login (Win32 RPM/WPM back the real one).
use crate::errors::VaultError;

pub fn login_to_instance(_hwnd: isize, _username: &str, _password: &str) -> Result<(), VaultError> {
    Err(VaultError::LoginFailed(
        "automatic login is not supported on this platform".into(),
    ))
}
