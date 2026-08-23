//! Steam client detection, launch, and per-app setup for Wizard101.
//!
//! Wizard101's Steam build authenticates against a running, logged-in Steam
//! client. When we spawn `WizardGraphicalClient.exe` directly (rather than
//! through the `steam://` protocol) the Steamworks API needs a
//! `steam_appid.txt` next to the executable to know which app to initialize.
//!
//! Login/run state is read from the registry tree Steam maintains under
//! `HKCU\Software\Valve\Steam`:
//!   - `ActiveProcess\pid`        — 0 when the client isn't running.
//!   - `ActiveProcess\ActiveUser` — 0 when running but not signed in; the
//!                                  logged-in account id once a user logs in.
//!   - `SteamExe`                 — full path to `steam.exe`.

use crate::errors::VaultError;
use std::fs;
use std::path::Path;
use std::process::Command;
use std::thread;
use std::time::{Duration, Instant};
use windows::core::PCWSTR;
use windows::Win32::Foundation::ERROR_SUCCESS;
use windows::Win32::System::Registry::{
    RegCloseKey, RegOpenKeyExW, RegQueryValueExW, HKEY, HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE,
    KEY_READ, KEY_WOW64_32KEY, REG_DWORD, REG_SAM_FLAGS, REG_SZ, REG_VALUE_TYPE,
};

/// Wizard101's Steam App ID.
pub const WIZARD101_APP_ID: &str = "799960";

/// How long to wait for the user to sign into Steam before giving up.
pub const STEAM_LOGIN_TIMEOUT_SECS: u64 = 180;

const STEAM_KEY: &str = "Software\\Valve\\Steam";

fn to_wide_null(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

/// Read a REG_DWORD from `root\subkey\value`. Returns `None` if the key/value
/// is missing or isn't a DWORD.
fn read_dword(root: HKEY, subkey: &str, value: &str, sam: REG_SAM_FLAGS) -> Option<u32> {
    let subkey_w = to_wide_null(subkey);
    let value_w = to_wide_null(value);

    unsafe {
        let mut hkey = HKEY(std::ptr::null_mut());
        if RegOpenKeyExW(root, PCWSTR(subkey_w.as_ptr()), 0, sam, &mut hkey) != ERROR_SUCCESS {
            return None;
        }

        let mut data: u32 = 0;
        let mut size = std::mem::size_of::<u32>() as u32;
        let mut kind = REG_VALUE_TYPE::default();
        let result = RegQueryValueExW(
            hkey,
            PCWSTR(value_w.as_ptr()),
            None,
            Some(&mut kind),
            Some(&mut data as *mut u32 as *mut u8),
            Some(&mut size),
        );
        let _ = RegCloseKey(hkey);

        if result == ERROR_SUCCESS && kind == REG_DWORD {
            Some(data)
        } else {
            None
        }
    }
}

/// Read a REG_SZ from `root\subkey\value`. Returns `None` if the key/value is
/// missing or isn't a string.
fn read_string(root: HKEY, subkey: &str, value: &str, sam: REG_SAM_FLAGS) -> Option<String> {
    let subkey_w = to_wide_null(subkey);
    let value_w = to_wide_null(value);

    unsafe {
        let mut hkey = HKEY(std::ptr::null_mut());
        if RegOpenKeyExW(root, PCWSTR(subkey_w.as_ptr()), 0, sam, &mut hkey) != ERROR_SUCCESS {
            return None;
        }

        // First call with a null data pointer to learn the size (in bytes).
        let mut size: u32 = 0;
        let mut kind = REG_VALUE_TYPE::default();
        let probe = RegQueryValueExW(
            hkey,
            PCWSTR(value_w.as_ptr()),
            None,
            Some(&mut kind),
            None,
            Some(&mut size),
        );
        if probe != ERROR_SUCCESS || kind != REG_SZ || size == 0 {
            let _ = RegCloseKey(hkey);
            return None;
        }

        // size is in bytes; round up to a u16 count.
        let count = (size as usize).div_ceil(2);
        let mut buf = vec![0u16; count];
        let mut read_size = size;
        let result = RegQueryValueExW(
            hkey,
            PCWSTR(value_w.as_ptr()),
            None,
            None,
            Some(buf.as_mut_ptr() as *mut u8),
            Some(&mut read_size),
        );
        let _ = RegCloseKey(hkey);

        if result != ERROR_SUCCESS {
            return None;
        }

        // Trim the trailing NUL(s) the API includes in the count.
        let s = String::from_utf16_lossy(&buf);
        Some(s.trim_end_matches('\0').to_string())
    }
}

/// Whether the Steam client process is currently running.
pub fn is_steam_running() -> bool {
    read_dword(HKEY_CURRENT_USER, &format!("{STEAM_KEY}\\ActiveProcess"), "pid", KEY_READ)
        .map(|pid| pid != 0)
        .unwrap_or(false)
}

/// Whether a user is signed into the running Steam client.
pub fn is_steam_logged_in() -> bool {
    read_dword(
        HKEY_CURRENT_USER,
        &format!("{STEAM_KEY}\\ActiveProcess"),
        "ActiveUser",
        KEY_READ,
    )
    .map(|user| user != 0)
    .unwrap_or(false)
}

/// Locate `steam.exe`, preferring the path Steam records for itself.
pub fn steam_exe_path() -> Option<String> {
    // Per-user value, set by Steam to its own executable path.
    if let Some(exe) = read_string(HKEY_CURRENT_USER, STEAM_KEY, "SteamExe", KEY_READ) {
        if !exe.is_empty() && Path::new(&exe).exists() {
            return Some(exe);
        }
    }

    // Fallback: machine-wide install path (32-bit view) + steam.exe.
    if let Some(install) = read_string(
        HKEY_LOCAL_MACHINE,
        STEAM_KEY,
        "InstallPath",
        KEY_READ | KEY_WOW64_32KEY,
    ) {
        let exe = Path::new(&install).join("steam.exe");
        if exe.exists() {
            return Some(exe.to_string_lossy().into_owned());
        }
    }

    None
}

/// Spawn the Steam client (e.g. to bring up its login window).
pub fn launch_steam() -> Result<(), VaultError> {
    let exe = steam_exe_path().ok_or_else(|| {
        VaultError::SteamUnavailable("could not locate steam.exe (is Steam installed?)".to_string())
    })?;

    Command::new(&exe)
        .spawn()
        .map_err(|e| VaultError::SteamUnavailable(format!("failed to launch Steam: {e}")))?;
    Ok(())
}

/// Ensure the Steam client is running and signed in, launching it if needed
/// and waiting up to `timeout_secs` for the user to log in.
pub fn ensure_steam_ready(timeout_secs: u64) -> Result<(), VaultError> {
    if is_steam_logged_in() {
        return Ok(());
    }

    if !is_steam_running() {
        launch_steam()?;
    }

    let deadline = Instant::now() + Duration::from_secs(timeout_secs);
    while Instant::now() < deadline {
        if is_steam_logged_in() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(1000));
    }

    Err(VaultError::SteamLoginTimeout(format!(
        "Steam was not signed in within {timeout_secs}s"
    )))
}

/// Ensure `<game_path>/Bin/steam_appid.txt` contains Wizard101's App ID so the
/// directly-launched client can initialize the Steamworks API. Idempotent.
pub fn ensure_steam_appid(game_path: &str) -> Result<(), VaultError> {
    let bin_dir = Path::new(game_path).join("Bin");
    if !bin_dir.is_dir() {
        return Err(VaultError::LaunchFailed(format!(
            "Bin directory not found: {}",
            bin_dir.display()
        )));
    }

    let appid_file = bin_dir.join("steam_appid.txt");
    let needs_write = match fs::read_to_string(&appid_file) {
        Ok(existing) => existing.trim() != WIZARD101_APP_ID,
        Err(_) => true,
    };

    if needs_write {
        fs::write(&appid_file, WIZARD101_APP_ID).map_err(|e| {
            VaultError::LaunchFailed(format!("failed to write steam_appid.txt: {e}"))
        })?;
    }

    Ok(())
}
