//! Non-Windows stub for Steam detection/launch (Win32 registry backs the real one).
use crate::errors::VaultError;

pub const WIZARD101_APP_ID: &str = "799960";
pub const STEAM_LOGIN_TIMEOUT_SECS: u64 = 180;

pub fn is_steam_running() -> bool {
    false
}

pub fn is_steam_logged_in() -> bool {
    false
}

pub fn steam_exe_path() -> Option<String> {
    None
}

pub fn launch_steam() -> Result<(), VaultError> {
    Err(VaultError::SteamUnavailable(
        "Steam is not supported on this platform".into(),
    ))
}

pub fn ensure_steam_ready(_timeout_secs: u64) -> Result<(), VaultError> {
    Err(VaultError::SteamUnavailable(
        "Steam is not supported on this platform".into(),
    ))
}

pub fn ensure_steam_appid(_game_path: &str) -> Result<(), VaultError> {
    Err(VaultError::SteamUnavailable(
        "Steam is not supported on this platform".into(),
    ))
}
