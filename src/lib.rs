mod credential_store;
mod credui;
mod errors;
mod launcher;
mod legacy;
mod login;
mod metadata;

use errors::VaultError;
use pyo3::prelude::*;
use std::collections::HashMap;

// ── Credential management ──────────────────────────────────────────

/// Open a Windows CredUI dialog, collect username/password, and store
/// the credential in Windows Credential Manager under the given nickname.
/// Python never sees the username or password.
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

/// Delete an account from Credential Manager and metadata.
#[pyfunction]
fn delete_account(nickname: String) -> PyResult<()> {
    credential_store::delete_credential(&nickname)?;
    metadata::remove_nickname(&nickname)?;
    Ok(())
}

/// List all account nicknames in stored order.
#[pyfunction]
fn list_accounts() -> PyResult<Vec<String>> {
    let cred_nicks = credential_store::list_credential_nicknames()?;
    let ordered = metadata::get_ordered_nicknames(&cred_nicks)?;
    Ok(ordered)
}

/// Reorder accounts to the given nickname order.
#[pyfunction]
fn reorder_accounts(ordered: Vec<String>) -> PyResult<()> {
    metadata::reorder(&ordered)?;
    Ok(())
}

/// Check if an account exists in Credential Manager.
#[pyfunction]
fn has_account(nickname: String) -> PyResult<bool> {
    Ok(credential_store::has_credential(&nickname))
}

// ── GID tracking ───────────────────────────────────────────────────

/// Update the player GID for a nickname.
#[pyfunction]
fn update_player_gid(nickname: String, gid: u64) -> PyResult<()> {
    metadata::update_gid(&nickname, gid)?;
    Ok(())
}

/// Get the player GID for a nickname, or None.
#[pyfunction]
fn get_player_gid(nickname: String) -> PyResult<Option<u64>> {
    let gid = metadata::get_gid(&nickname)?;
    Ok(gid)
}

/// Look up a nickname by its player GID, or None.
#[pyfunction]
fn get_nickname_by_gid(gid: u64) -> PyResult<Option<String>> {
    let nick = metadata::get_nickname_by_gid(gid)?;
    Ok(nick)
}

// ── Launch + login ─────────────────────────────────────────────────

/// Launch one game instance, log in with stored credentials, and return
/// the window handle. Credentials never enter Python.
/// Blocks the calling thread — call via `asyncio.to_thread()`.
#[pyfunction]
#[pyo3(signature = (nickname, game_path, timeout_secs=30))]
fn launch_instance(
    py: Python<'_>,
    nickname: String,
    game_path: String,
    timeout_secs: u64,
) -> PyResult<isize> {
    py.allow_threads(|| {
        let before: std::collections::HashSet<isize> =
            launcher::get_wizard_handles().into_iter().collect();

        launcher::launch_game(&game_path)?;

        let handle = launcher::wait_for_new_handle(&before, timeout_secs)?;

        // Disable window, wait for login screen, send credentials, re-enable
        launcher::enable_window(handle, false);
        std::thread::sleep(std::time::Duration::from_secs(2));

        let (username, password) = credential_store::read_credential(&nickname)?;
        login::login_to_instance(handle, &username, &password)?;

        launcher::enable_window(handle, true);

        Ok::<isize, VaultError>(handle)
    })
    .map_err(Into::into)
}

/// Launch multiple game instances, log in each, and return a dict of
/// {nickname: window_handle}. Credentials never enter Python.
#[pyfunction]
#[pyo3(signature = (nicknames, game_path, timeout_secs=30))]
fn launch_instances(
    py: Python<'_>,
    nicknames: Vec<String>,
    game_path: String,
    timeout_secs: u64,
) -> PyResult<HashMap<String, isize>> {
    py.allow_threads(|| {
        let mut results = HashMap::new();
        let mut known: std::collections::HashSet<isize> =
            launcher::get_wizard_handles().into_iter().collect();

        for nickname in &nicknames {
            launcher::launch_game(&game_path)?;

            match launcher::wait_for_new_handle(&known, timeout_secs) {
                Ok(handle) => {
                    known.insert(handle);

                    launcher::enable_window(handle, false);
                    std::thread::sleep(std::time::Duration::from_secs(2));

                    let (username, password) = credential_store::read_credential(nickname)?;
                    login::login_to_instance(handle, &username, &password)?;

                    launcher::enable_window(handle, true);
                    results.insert(nickname.clone(), handle);
                }
                Err(e) => {
                    eprintln!("Failed to launch '{nickname}': {e}");
                }
            }
        }

        Ok::<HashMap<String, isize>, VaultError>(results)
    })
    .map_err(Into::into)
}

// ── Utilities ──────────────────────────────────────────────────────

/// Kill the process owning the given window handle.
#[pyfunction]
fn kill_instance(handle: isize) -> PyResult<bool> {
    let result = launcher::kill_process_by_handle(handle)?;
    Ok(result)
}

/// Get all currently open Wizard101 window handles.
#[pyfunction]
fn get_wizard_handles() -> PyResult<Vec<isize>> {
    Ok(launcher::get_wizard_handles())
}

// ── Legacy migration ───────────────────────────────────────────────

/// Import accounts from the old Fernet+DPAPI vault into Credential Manager.
/// Returns the number of accounts successfully imported.
#[pyfunction]
fn import_legacy_vault(vault_path: String, key_path: String) -> PyResult<u32> {
    let count = legacy::import_legacy_vault(&vault_path, &key_path)?;
    Ok(count)
}

// ── Module ─────────────────────────────────────────────────────────

#[pymodule]
fn wizvault(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(prompt_save_account, m)?)?;
    m.add_function(wrap_pyfunction!(delete_account, m)?)?;
    m.add_function(wrap_pyfunction!(list_accounts, m)?)?;
    m.add_function(wrap_pyfunction!(reorder_accounts, m)?)?;
    m.add_function(wrap_pyfunction!(has_account, m)?)?;
    m.add_function(wrap_pyfunction!(update_player_gid, m)?)?;
    m.add_function(wrap_pyfunction!(get_player_gid, m)?)?;
    m.add_function(wrap_pyfunction!(get_nickname_by_gid, m)?)?;
    m.add_function(wrap_pyfunction!(launch_instance, m)?)?;
    m.add_function(wrap_pyfunction!(launch_instances, m)?)?;
    m.add_function(wrap_pyfunction!(kill_instance, m)?)?;
    m.add_function(wrap_pyfunction!(get_wizard_handles, m)?)?;
    m.add_function(wrap_pyfunction!(import_legacy_vault, m)?)?;
    Ok(())
}
