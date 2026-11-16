use crate::errors::VaultError;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

/// Per-account window placement / resolution config (set via the launcher's
/// "proportions" editor). `x`/`y` are the window's top-left in virtual-desktop
/// screen coordinates (encodes which monitor); `w`/`h` is the window CLIENT size;
/// `res_w`/`res_h` is the forced render resolution. When `locked`, res == client
/// size (crisp 1:1).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WindowConfig {
    pub x: i32,
    pub y: i32,
    pub w: u32,
    pub h: u32,
    pub res_w: u32,
    pub res_h: u32,
    pub locked: bool,
    /// Strip the window's title bar / borders (borderless mode). Defaults to
    /// false for configs saved before this field existed.
    #[serde(default)]
    pub borderless: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AccountMetadata {
    pub version: u32,
    pub nicknames_order: Vec<String>,
    pub gid_map: HashMap<String, u64>,
    /// Per-account Steam-mode flag. An account *missing* from this map predates
    /// Steam support and is considered unconfigured (see `validate_account`).
    #[serde(default)]
    pub steam_map: HashMap<String, bool>,
    /// Per-account window placement / resolution config.
    #[serde(default)]
    pub window_map: HashMap<String, WindowConfig>,
}

impl Default for AccountMetadata {
    fn default() -> Self {
        Self {
            version: 1,
            nicknames_order: Vec::new(),
            gid_map: HashMap::new(),
            steam_map: HashMap::new(),
            window_map: HashMap::new(),
        }
    }
}

fn metadata_path() -> Result<PathBuf, VaultError> {
    // Windows: %APPDATA%\Deimos. Off-Windows (macOS/Linux): a per-user config dir
    // (XDG_CONFIG_HOME or ~/Library/Application Support / ~/.config), so the
    // account-metadata store works there too.
    let base = match std::env::var("APPDATA") {
        Ok(a) if !a.is_empty() => PathBuf::from(a),
        _ => {
            if let Ok(xdg) = std::env::var("XDG_CONFIG_HOME") {
                if !xdg.is_empty() {
                    PathBuf::from(xdg)
                } else {
                    default_config_home()?
                }
            } else {
                default_config_home()?
            }
        }
    };
    let dir = base.join("Deimos");
    fs::create_dir_all(&dir)?;
    Ok(dir.join("account_metadata.json"))
}

fn default_config_home() -> Result<PathBuf, VaultError> {
    let home = std::env::var("HOME")
        .map_err(|_| VaultError::MetadataIo("HOME not set".to_string()))?;
    let home = PathBuf::from(home);
    if cfg!(target_os = "macos") {
        Ok(home.join("Library").join("Application Support"))
    } else {
        Ok(home.join(".config"))
    }
}

pub fn load() -> Result<AccountMetadata, VaultError> {
    let path = metadata_path()?;
    if !path.exists() {
        return Ok(AccountMetadata::default());
    }
    let data = fs::read_to_string(&path)?;
    let meta: AccountMetadata = serde_json::from_str(&data)?;
    Ok(meta)
}

pub fn save(meta: &AccountMetadata) -> Result<(), VaultError> {
    let path = metadata_path()?;
    let data = serde_json::to_string_pretty(meta)?;
    fs::write(&path, data)?;
    Ok(())
}

/// Ensure a nickname is in the order list (appended if missing).
pub fn ensure_nickname(nickname: &str) -> Result<(), VaultError> {
    let mut meta = load()?;
    if !meta.nicknames_order.contains(&nickname.to_string()) {
        meta.nicknames_order.push(nickname.to_string());
        save(&meta)?;
    }
    Ok(())
}

/// Remove a nickname from the order list, GID map, and Steam map.
pub fn remove_nickname(nickname: &str) -> Result<(), VaultError> {
    let mut meta = load()?;
    meta.nicknames_order.retain(|n| n != nickname);
    meta.gid_map.remove(nickname);
    meta.steam_map.remove(nickname);
    meta.window_map.remove(nickname);
    save(&meta)?;
    Ok(())
}

/// Reorder nicknames. Only keeps nicknames that exist in the provided list.
pub fn reorder(ordered: &[String]) -> Result<(), VaultError> {
    let mut meta = load()?;
    meta.nicknames_order = ordered.to_vec();
    save(&meta)?;
    Ok(())
}

/// Get nicknames in stored order, falling back to credential store order.
pub fn get_ordered_nicknames(cred_nicknames: &[String]) -> Result<Vec<String>, VaultError> {
    let meta = load()?;
    if meta.nicknames_order.is_empty() {
        return Ok(cred_nicknames.to_vec());
    }
    // Return ordered nicknames that exist in credential store, then any new ones
    let mut result = Vec::new();
    for nick in &meta.nicknames_order {
        if cred_nicknames.contains(nick) {
            result.push(nick.clone());
        }
    }
    for nick in cred_nicknames {
        if !result.contains(nick) {
            result.push(nick.clone());
        }
    }
    Ok(result)
}

pub fn update_gid(nickname: &str, gid: u64) -> Result<(), VaultError> {
    let mut meta = load()?;
    meta.gid_map.insert(nickname.to_string(), gid);
    save(&meta)?;
    Ok(())
}

pub fn get_gid(nickname: &str) -> Result<Option<u64>, VaultError> {
    let meta = load()?;
    Ok(meta.gid_map.get(nickname).copied())
}

pub fn get_nickname_by_gid(gid: u64) -> Result<Option<String>, VaultError> {
    let meta = load()?;
    for (nick, &stored_gid) in &meta.gid_map {
        if stored_gid == gid {
            return Ok(Some(nick.clone()));
        }
    }
    Ok(None)
}

/// Set whether an account launches in Steam mode.
pub fn set_steam(nickname: &str, steam: bool) -> Result<(), VaultError> {
    let mut meta = load()?;
    meta.steam_map.insert(nickname.to_string(), steam);
    save(&meta)?;
    Ok(())
}

/// Get an account's Steam-mode flag. `None` means it's unconfigured (an older
/// entry saved before Steam support existed).
pub fn get_steam(nickname: &str) -> Result<Option<bool>, VaultError> {
    let meta = load()?;
    Ok(meta.steam_map.get(nickname).copied())
}

/// Set an account's window placement / resolution config.
pub fn set_window(nickname: &str, cfg: WindowConfig) -> Result<(), VaultError> {
    let mut meta = load()?;
    meta.window_map.insert(nickname.to_string(), cfg);
    save(&meta)?;
    Ok(())
}

/// Get an account's window config, or `None` if it has none.
pub fn get_window(nickname: &str) -> Result<Option<WindowConfig>, VaultError> {
    let meta = load()?;
    Ok(meta.window_map.get(nickname).cloned())
}

/// Clear an account's window config (revert to default behavior).
pub fn clear_window(nickname: &str) -> Result<(), VaultError> {
    let mut meta = load()?;
    if meta.window_map.remove(nickname).is_some() {
        save(&meta)?;
    }
    Ok(())
}
