//! Non-Windows stub for launching/managing game instances (Win32 process/window
//! APIs back the real one). On macOS the client is started manually (CrossOver)
//! and Deimos hooks it, so these return empty / errors.
use std::collections::HashSet;

use crate::errors::VaultError;

pub fn get_wizard_handles() -> Vec<isize> {
    Vec::new()
}

pub fn launch_game(_game_path: &str, _login_server: &str, _steam: bool) -> Result<u32, VaultError> {
    Err(VaultError::LaunchFailed(
        "launching the game is not supported on this platform; start Wizard101 manually".into(),
    ))
}

pub fn wait_for_new_handle(_before_handles: &HashSet<isize>, _timeout_secs: u64) -> Result<isize, VaultError> {
    Err(VaultError::LaunchTimeout(
        "launching is not supported on this platform".into(),
    ))
}

pub fn get_window_pid(_hwnd: isize) -> u32 {
    0
}

pub fn enable_window(_hwnd: isize, _enable: bool) {}

pub fn is_window_valid(_hwnd: isize) -> bool {
    false
}

pub fn kill_process_by_handle(_hwnd: isize) -> Result<bool, VaultError> {
    Ok(false)
}
