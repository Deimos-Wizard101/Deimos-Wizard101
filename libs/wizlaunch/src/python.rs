use crate::{credential_store, credui, errors::VaultError, launcher, login, metadata};
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
    py.allow_threads(|| {
        let before: std::collections::HashSet<isize> =
            launcher::get_wizard_handles().into_iter().collect();

        launcher::launch_game(&game_path, &login_server)?;

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
    py.allow_threads(|| {
        let mut results = HashMap::new();
        let mut known: std::collections::HashSet<isize> =
            launcher::get_wizard_handles().into_iter().collect();

        for nickname in &nicknames {
            launcher::launch_game(&game_path, &login_server)?;

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
    m.add("__version__", "0.2.0")?;
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
    Ok(())
}
