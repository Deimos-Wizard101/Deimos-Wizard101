use crate::{credential_store, credui, errors::VaultError, launcher, login, metadata, steam};
use pyo3::prelude::*;
use std::collections::HashMap;

// ── Credential management ──────────────────────────────────────────

#[pyfunction]
fn prompt_save_account(py: Python<'_>, nickname: String) -> PyResult<()> {
    py.allow_threads(|| {
        let (username, password) =
            credui::prompt_credentials("Deimos — Save Account", &format!("Enter credentials for '{nickname}'"))?;
        credential_store::write_credential(&nickname, &username, &password)?;
        metadata::ensure_nickname(&nickname)?;
        Ok::<(), VaultError>(())
    })?;
    Ok(())
}

#[pyfunction]
fn delete_account(nickname: String) -> PyResult<()> {
    credential_store::delete_credential(&nickname)?;
    metadata::remove_nickname(&nickname)?;
    Ok(())
}

#[pyfunction]
fn list_accounts() -> PyResult<Vec<String>> {
    let cred_nicks = credential_store::list_credential_nicknames()?;
    let ordered = metadata::get_ordered_nicknames(&cred_nicks)?;
    Ok(ordered)
}

#[pyfunction]
fn reorder_accounts(ordered: Vec<String>) -> PyResult<()> {
    metadata::reorder(&ordered)?;
    Ok(())
}

#[pyfunction]
fn has_account(nickname: String) -> PyResult<bool> {
    Ok(credential_store::has_credential(&nickname))
}

// ── Per-account settings & validation ──────────────────────────────

/// Validate an account entry, returning a human-readable error string if it
/// needs attention, or `None` if it's fully configured. Older entries saved
/// before Steam support lack a Steam-mode flag and must be updated.
#[pyfunction]
fn validate_account(nickname: String) -> PyResult<Option<String>> {
    match metadata::get_steam(&nickname)? {
        Some(_) => Ok(None),
        None => Ok(Some(
            "This account was saved before Steam support was added. \
             Update it to choose whether it launches in Steam mode."
                .to_string(),
        )),
    }
}

/// Get an account's Steam-mode flag (`None` if unconfigured).
#[pyfunction]
fn get_account_steam(nickname: String) -> PyResult<Option<bool>> {
    Ok(metadata::get_steam(&nickname)?)
}

/// Set whether an account launches in Steam mode.
#[pyfunction]
fn set_account_steam(nickname: String, steam: bool) -> PyResult<()> {
    metadata::set_steam(&nickname, steam)?;
    Ok(())
}

/// Get an account's window placement / resolution config as a tuple
/// `(x, y, w, h, res_w, res_h, locked, borderless)`, or `None` if unset.
#[pyfunction]
fn get_window_config(
    nickname: String,
) -> PyResult<Option<(i32, i32, u32, u32, u32, u32, bool, bool)>> {
    match metadata::get_window(&nickname)? {
        Some(c) => Ok(Some((c.x, c.y, c.w, c.h, c.res_w, c.res_h, c.locked, c.borderless))),
        None => Ok(None),
    }
}

/// Set an account's window placement / resolution config.
#[pyfunction]
#[pyo3(signature = (nickname, x, y, w, h, res_w, res_h, locked, borderless = false))]
fn set_window_config(
    nickname: String,
    x: i32,
    y: i32,
    w: u32,
    h: u32,
    res_w: u32,
    res_h: u32,
    locked: bool,
    borderless: bool,
) -> PyResult<()> {
    metadata::set_window(
        &nickname,
        metadata::WindowConfig { x, y, w, h, res_w, res_h, locked, borderless },
    )?;
    Ok(())
}

/// Clear an account's window config.
#[pyfunction]
fn clear_window_config(nickname: String) -> PyResult<()> {
    metadata::clear_window(&nickname)?;
    Ok(())
}

// ── GID tracking ───────────────────────────────────────────────────

#[pyfunction]
fn update_player_gid(nickname: String, gid: u64) -> PyResult<()> {
    metadata::update_gid(&nickname, gid)?;
    Ok(())
}

#[pyfunction]
fn get_player_gid(nickname: String) -> PyResult<Option<u64>> {
    let gid = metadata::get_gid(&nickname)?;
    Ok(gid)
}

#[pyfunction]
fn get_nickname_by_gid(gid: u64) -> PyResult<Option<String>> {
    let nick = metadata::get_nickname_by_gid(gid)?;
    Ok(nick)
}

// ── Launch + login ─────────────────────────────────────────────────

#[pyfunction]
#[pyo3(signature = (nickname, game_path, login_server=None, timeout_secs=30))]
fn launch_instance(
    py: Python<'_>,
    nickname: String,
    game_path: String,
    login_server: Option<String>,
    timeout_secs: u64,
) -> PyResult<isize> {
    let login_server = login_server.unwrap_or_else(|| "login.us.wizard101.com:12000".to_string());
    // Steam mode is a per-account setting; unconfigured accounts launch normally.
    let steam = metadata::get_steam(&nickname)?.unwrap_or(false);
    py.allow_threads(|| {
        if steam {
            steam::ensure_steam_ready(steam::STEAM_LOGIN_TIMEOUT_SECS)?;
            steam::ensure_steam_appid(&game_path)?;
        }

        let before: std::collections::HashSet<isize> =
            launcher::get_wizard_handles().into_iter().collect();

        launcher::launch_game(&game_path, &login_server, steam)?;

        let handle = launcher::wait_for_new_handle(&before, timeout_secs)?;

        launcher::enable_window(handle, false);
        std::thread::sleep(std::time::Duration::from_secs(2));

        let (username, password) = credential_store::read_credential(&nickname)?;
        login::login_to_instance(handle, &username, &password)?;

        launcher::enable_window(handle, true);

        Ok::<isize, VaultError>(handle)
    })
    .map_err(Into::into)
}

#[pyfunction]
#[pyo3(signature = (nicknames, game_path, login_server=None, timeout_secs=30))]
fn launch_instances(
    py: Python<'_>,
    nicknames: Vec<String>,
    game_path: String,
    login_server: Option<String>,
    timeout_secs: u64,
) -> PyResult<HashMap<String, isize>> {
    let login_server = login_server.unwrap_or_else(|| "login.us.wizard101.com:12000".to_string());
    // Resolve per-account Steam mode up front so we can prepare Steam once.
    let mut steam_flags: Vec<bool> = Vec::with_capacity(nicknames.len());
    for nickname in &nicknames {
        steam_flags.push(metadata::get_steam(nickname)?.unwrap_or(false));
    }
    let any_steam = steam_flags.iter().any(|&s| s);
    py.allow_threads(|| {
        if any_steam {
            steam::ensure_steam_ready(steam::STEAM_LOGIN_TIMEOUT_SECS)?;
            steam::ensure_steam_appid(&game_path)?;
        }

        let mut known: std::collections::HashSet<isize> =
            launcher::get_wizard_handles().into_iter().collect();

        // Launch simultaneously: spawn EVERY client up front — regardless of Steam
        // mode — so they all load in parallel (the slow part). Each account's Steam
        // flag only affects the `-ST` spawn argument, which is known per-account, so
        // there's no reason to serialize the modes. We record each spawned PID and,
        // once its window appears, pair it back to the exact account by that PID (the
        // client doesn't re-exec, so the window's owning process is the one we
        // spawned). That keeps account↔window pairing exact even when a batch mixes
        // Steam and non-Steam accounts.
        //
        // (The previous version processed one Steam-mode group at a time, fully
        // launching + logging in group A before spawning group B — which serialized
        // any mixed batch into back-to-back launches.)
        let mut pid_to_nick: HashMap<u32, String> = HashMap::new();
        let mut spawn_order: Vec<String> = Vec::with_capacity(nicknames.len());
        for (nickname, &steam) in nicknames.iter().zip(steam_flags.iter()) {
            match launcher::launch_game(&game_path, &login_server, steam) {
                Ok(pid) => {
                    pid_to_nick.insert(pid, nickname.clone());
                    spawn_order.push(nickname.clone());
                }
                Err(e) => eprintln!("Failed to spawn client '{nickname}': {e}"),
            }
        }
        let want = spawn_order.len();

        // Collect the new windows as clients finish loading (in parallel), pairing
        // each to its account by the spawning PID.
        let mut handle_for_nick: HashMap<String, isize> = HashMap::new();
        let mut leftover_handles: Vec<isize> = Vec::new();
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(timeout_secs);
        while handle_for_nick.len() < want && std::time::Instant::now() < deadline {
            for h in launcher::get_wizard_handles() {
                if !known.insert(h) {
                    continue; // already seen (pre-existing or handled)
                }
                let pid = launcher::get_window_pid(h);
                match pid_to_nick.remove(&pid) {
                    Some(nick) => {
                        handle_for_nick.insert(nick, h);
                    }
                    None => leftover_handles.push(h),
                }
            }
            if handle_for_nick.len() < want {
                std::thread::sleep(std::time::Duration::from_millis(500));
            }
        }

        // Fallback: if any window couldn't be matched by PID (unexpected — e.g. the
        // client re-execed), pair leftover windows to still-unmatched accounts in
        // spawn order so a launched client is never silently dropped.
        if handle_for_nick.len() < want && !leftover_handles.is_empty() {
            let mut leftovers = leftover_handles.into_iter();
            for nick in &spawn_order {
                if handle_for_nick.contains_key(nick) {
                    continue;
                }
                match leftovers.next() {
                    Some(h) => {
                        handle_for_nick.insert(nick.clone(), h);
                    }
                    None => break,
                }
            }
        }

        // Freeze input on every window, let them finish initializing (they've been
        // loading in parallel), then log each in. Login is a memory write (no window
        // focus), so any-order logins are safe.
        for &handle in handle_for_nick.values() {
            launcher::enable_window(handle, false);
        }
        std::thread::sleep(std::time::Duration::from_secs(2));

        let mut results = HashMap::new();
        for (nickname, handle) in handle_for_nick {
            let (username, password) = credential_store::read_credential(&nickname)?;
            login::login_to_instance(handle, &username, &password)?;
            launcher::enable_window(handle, true);
            results.insert(nickname, handle);
        }

        Ok::<HashMap<String, isize>, VaultError>(results)
    })
    .map_err(Into::into)
}

// ── Utilities ──────────────────────────────────────────────────────

#[pyfunction]
fn kill_instance(handle: isize) -> PyResult<bool> {
    let result = launcher::kill_process_by_handle(handle)?;
    Ok(result)
}

#[pyfunction]
fn get_wizard_handles() -> PyResult<Vec<isize>> {
    Ok(launcher::get_wizard_handles())
}

// ── Module ─────────────────────────────────────────────────────────

#[pymodule]
pub fn wizlaunch(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", "0.3.1")?;  // 0.3.1: spawn all clients up front (mixed Steam modes no longer serialize); pair windows to accounts by PID
    m.add_function(wrap_pyfunction!(prompt_save_account, m)?)?;
    m.add_function(wrap_pyfunction!(delete_account, m)?)?;
    m.add_function(wrap_pyfunction!(list_accounts, m)?)?;
    m.add_function(wrap_pyfunction!(reorder_accounts, m)?)?;
    m.add_function(wrap_pyfunction!(has_account, m)?)?;
    m.add_function(wrap_pyfunction!(validate_account, m)?)?;
    m.add_function(wrap_pyfunction!(get_account_steam, m)?)?;
    m.add_function(wrap_pyfunction!(set_account_steam, m)?)?;
    m.add_function(wrap_pyfunction!(get_window_config, m)?)?;
    m.add_function(wrap_pyfunction!(set_window_config, m)?)?;
    m.add_function(wrap_pyfunction!(clear_window_config, m)?)?;
    m.add_function(wrap_pyfunction!(update_player_gid, m)?)?;
    m.add_function(wrap_pyfunction!(get_player_gid, m)?)?;
    m.add_function(wrap_pyfunction!(get_nickname_by_gid, m)?)?;
    m.add_function(wrap_pyfunction!(launch_instance, m)?)?;
    m.add_function(wrap_pyfunction!(launch_instances, m)?)?;
    m.add_function(wrap_pyfunction!(kill_instance, m)?)?;
    m.add_function(wrap_pyfunction!(get_wizard_handles, m)?)?;
    Ok(())
}
