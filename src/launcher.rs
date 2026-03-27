use crate::errors::VaultError;
use std::collections::HashSet;
use std::ffi::c_void;
use std::path::Path;
use std::process::Command;
use std::thread;
use std::time::{Duration, Instant};
use windows::Win32::Foundation::{BOOL, HWND, LPARAM};
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, GetClassNameW, GetWindowThreadProcessId, IsWindow,
};

const WIZARD_CLASS: &str = "Wizard Graphical Client";

/// Convert an isize handle to HWND (0.58 uses *mut c_void).
fn hwnd_from_isize(h: isize) -> HWND {
    HWND(h as *mut c_void)
}

/// Enumerate all open Wizard101 window handles.
pub fn get_wizard_handles() -> Vec<isize> {
    let mut handles: Vec<isize> = Vec::new();

    unsafe extern "system" fn enum_callback(hwnd: HWND, lparam: LPARAM) -> BOOL {
        let handles = &mut *(lparam.0 as *mut Vec<isize>);
        let mut class_buf = [0u16; 64];
        let len = GetClassNameW(hwnd, &mut class_buf);
        if len > 0 {
            let class_name = String::from_utf16_lossy(&class_buf[..len as usize]);
            if class_name == WIZARD_CLASS {
                handles.push(hwnd.0 as isize);
            }
        }
        BOOL(1) // continue enumeration
    }

    unsafe {
        let _ = EnumWindows(
            Some(enum_callback),
            LPARAM(&mut handles as *mut Vec<isize> as isize),
        );
    }

    handles
}

/// Launch the Wizard101 game process.
pub fn launch_game(game_path: &str) -> Result<(), VaultError> {
    let bin_dir = Path::new(game_path).join("Bin");
    let exe = bin_dir.join("WizardGraphicalClient.exe");

    if !exe.exists() {
        return Err(VaultError::LaunchFailed(format!(
            "Executable not found: {}",
            exe.display()
        )));
    }

    Command::new(&exe)
        .arg("-L")
        .arg("login.us.wizard101.com")
        .arg("12000")
        .current_dir(&bin_dir)
        .spawn()
        .map_err(|e| VaultError::LaunchFailed(e.to_string()))?;

    Ok(())
}

/// Wait for a new Wizard101 window to appear that wasn't in `before_handles`.
/// Returns the new window handle, or error on timeout.
pub fn wait_for_new_handle(
    before_handles: &HashSet<isize>,
    timeout_secs: u64,
) -> Result<isize, VaultError> {
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);

    while Instant::now() < deadline {
        let current = get_wizard_handles();
        for h in &current {
            if !before_handles.contains(h) {
                return Ok(*h);
            }
        }
        thread::sleep(Duration::from_millis(500));
    }

    Err(VaultError::LaunchTimeout(
        "No new wizard window detected".to_string(),
    ))
}

/// Disable or enable a window (prevents user input during login).
pub fn enable_window(hwnd: isize, enable: bool) {
    #[link(name = "user32")]
    extern "system" {
        fn EnableWindow(hwnd: *mut c_void, enable: i32) -> i32;
    }
    unsafe {
        EnableWindow(hwnd as *mut c_void, if enable { 1 } else { 0 });
    }
}

/// Check if a window handle is still valid.
pub fn is_window_valid(hwnd: isize) -> bool {
    unsafe { IsWindow(hwnd_from_isize(hwnd)).as_bool() }
}

/// Kill the process that owns a given window handle.
pub fn kill_process_by_handle(hwnd: isize) -> Result<bool, VaultError> {
    let mut pid: u32 = 0;
    unsafe {
        GetWindowThreadProcessId(hwnd_from_isize(hwnd), Some(&mut pid));
    }

    if pid == 0 {
        return Ok(false);
    }

    use windows::Win32::System::Threading::{OpenProcess, TerminateProcess, PROCESS_TERMINATE};

    unsafe {
        let process = OpenProcess(PROCESS_TERMINATE, false, pid)
            .map_err(|e| VaultError::WindowsApi(e.to_string()))?;
        let result = TerminateProcess(process, 1);
        let _ = windows::Win32::Foundation::CloseHandle(process);
        Ok(result.is_ok())
    }
}
