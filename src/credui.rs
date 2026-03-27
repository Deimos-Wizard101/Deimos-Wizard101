use crate::errors::VaultError;
use std::ffi::c_void;
use windows::core::PCWSTR;
use windows::Win32::Foundation::HWND;
use windows::Win32::Security::Credentials::{
    CredUIPromptForWindowsCredentialsW, CredUnPackAuthenticationBufferW, CREDUI_INFOW,
    CRED_PACK_GENERIC_CREDENTIALS, CREDUIWIN_GENERIC,
};
use windows::Win32::System::Com::CoTaskMemFree;

fn to_wide_null(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

/// Open the Windows CredUI dialog and return (username, password).
/// The dialog is OS-owned — Python cannot intercept the credentials.
pub fn prompt_credentials(caption: &str, message: &str) -> Result<(String, String), VaultError> {
    let caption_wide = to_wide_null(caption);
    let message_wide = to_wide_null(message);

    let ui_info = CREDUI_INFOW {
        cbSize: std::mem::size_of::<CREDUI_INFOW>() as u32,
        hwndParent: HWND::default(),
        pszMessageText: PCWSTR(message_wide.as_ptr()),
        pszCaptionText: PCWSTR(caption_wide.as_ptr()),
        hbmBanner: Default::default(),
    };

    let mut auth_package: u32 = 0;
    let mut out_buf: *mut c_void = std::ptr::null_mut();
    let mut out_buf_size: u32 = 0;

    let result = unsafe {
        CredUIPromptForWindowsCredentialsW(
            Some(&ui_info),
            0,
            &mut auth_package,
            None,
            0,
            &mut out_buf,
            &mut out_buf_size,
            None,
            CREDUIWIN_GENERIC,
        )
    };

    // ERROR_CANCELLED = 1223
    if result == 1223 {
        return Err(VaultError::CredUiCancelled);
    }
    if result != 0 {
        return Err(VaultError::CredUiFailed(format!(
            "CredUI returned error code {result}"
        )));
    }

    // Unpack the authentication buffer to get username and password
    let (username, password) = unsafe {
        let result = unpack_auth_buffer(out_buf, out_buf_size)?;
        CoTaskMemFree(Some(out_buf));
        result
    };

    Ok((username, password))
}

unsafe fn unpack_auth_buffer(
    buf: *const c_void,
    buf_size: u32,
) -> Result<(String, String), VaultError> {
    // First call to get required buffer sizes
    let mut user_size: u32 = 0;
    let mut domain_size: u32 = 0;
    let mut pass_size: u32 = 0;

    let _ = CredUnPackAuthenticationBufferW(
        CRED_PACK_GENERIC_CREDENTIALS,
        buf,
        buf_size,
        windows::core::PWSTR::null(),
        &mut user_size,
        windows::core::PWSTR::null(),
        Some(&mut domain_size),
        windows::core::PWSTR::null(),
        &mut pass_size,
    );

    // Allocate buffers
    let mut user_buf: Vec<u16> = vec![0u16; user_size as usize];
    let mut domain_buf: Vec<u16> = vec![0u16; domain_size as usize];
    let mut pass_buf: Vec<u16> = vec![0u16; pass_size as usize];

    CredUnPackAuthenticationBufferW(
        CRED_PACK_GENERIC_CREDENTIALS,
        buf,
        buf_size,
        windows::core::PWSTR(user_buf.as_mut_ptr()),
        &mut user_size,
        windows::core::PWSTR(domain_buf.as_mut_ptr()),
        Some(&mut domain_size),
        windows::core::PWSTR(pass_buf.as_mut_ptr()),
        &mut pass_size,
    )
    .map_err(|e| VaultError::CredUiFailed(format!("CredUnPack failed: {e}")))?;

    // Convert wide strings (trim null terminators)
    let username = String::from_utf16_lossy(&user_buf[..user_size.saturating_sub(1) as usize]);
    let password = String::from_utf16_lossy(&pass_buf[..pass_size.saturating_sub(1) as usize]);

    // Zero out password buffer
    for b in &mut pass_buf {
        *b = 0;
    }

    Ok((username, password))
}
