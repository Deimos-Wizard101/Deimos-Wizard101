use crate::errors::VaultError;
use std::ffi::c_void;
use std::slice;
use windows::core::PWSTR;
use windows::Win32::Foundation::FILETIME;
use windows::Win32::Security::Credentials::{
    CredDeleteW, CredEnumerateW, CredFree, CredReadW, CredWriteW, CREDENTIALW,
    CRED_ENUMERATE_FLAGS, CRED_FLAGS, CRED_PERSIST_LOCAL_MACHINE, CRED_TYPE_GENERIC,
};

pub const TARGET_PREFIX: &str = "Deimos/account/";

fn to_wide_null(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

fn from_wide_ptr(ptr: *const u16) -> String {
    if ptr.is_null() {
        return String::new();
    }
    unsafe {
        let mut len = 0;
        while *ptr.add(len) != 0 {
            len += 1;
        }
        String::from_utf16_lossy(slice::from_raw_parts(ptr, len))
    }
}

pub fn target_name(nickname: &str) -> String {
    format!("{TARGET_PREFIX}{nickname}")
}

pub fn write_credential(
    nickname: &str,
    username: &str,
    password: &str,
) -> Result<(), VaultError> {
    let target = target_name(nickname);
    let mut target_wide = to_wide_null(&target);
    let mut username_wide = to_wide_null(username);
    let password_bytes: Vec<u8> = password.as_bytes().to_vec();

    let cred = CREDENTIALW {
        Flags: CRED_FLAGS(0),
        Type: CRED_TYPE_GENERIC,
        TargetName: PWSTR(target_wide.as_mut_ptr()),
        Comment: PWSTR::null(),
        LastWritten: FILETIME::default(),
        CredentialBlobSize: password_bytes.len() as u32,
        CredentialBlob: password_bytes.as_ptr() as *mut u8,
        Persist: CRED_PERSIST_LOCAL_MACHINE,
        AttributeCount: 0,
        Attributes: std::ptr::null_mut(),
        TargetAlias: PWSTR::null(),
        UserName: PWSTR(username_wide.as_mut_ptr()),
    };

    unsafe { CredWriteW(&cred, 0).map_err(|e| VaultError::CredentialWrite(e.to_string())) }
}

pub fn read_credential(nickname: &str) -> Result<(String, String), VaultError> {
    let target = target_name(nickname);
    let target_wide = to_wide_null(&target);
    let mut cred_ptr: *mut CREDENTIALW = std::ptr::null_mut();

    unsafe {
        CredReadW(
            windows::core::PCWSTR(target_wide.as_ptr()),
            CRED_TYPE_GENERIC,
            0,
            &mut cred_ptr,
        )
        .map_err(|_| VaultError::CredentialNotFound(nickname.to_string()))?;

        let cred = &*cred_ptr;
        let username = from_wide_ptr(cred.UserName.0);
        let password = if cred.CredentialBlobSize > 0 && !cred.CredentialBlob.is_null() {
            let blob =
                slice::from_raw_parts(cred.CredentialBlob, cred.CredentialBlobSize as usize);
            String::from_utf8_lossy(blob).into_owned()
        } else {
            String::new()
        };

        CredFree(cred_ptr as *const c_void);
        Ok((username, password))
    }
}

pub fn delete_credential(nickname: &str) -> Result<(), VaultError> {
    let target = target_name(nickname);
    let target_wide = to_wide_null(&target);

    unsafe {
        CredDeleteW(
            windows::core::PCWSTR(target_wide.as_ptr()),
            CRED_TYPE_GENERIC,
            0,
        )
        .map_err(|e| VaultError::CredentialDelete(e.to_string()))
    }
}

pub fn list_credential_nicknames() -> Result<Vec<String>, VaultError> {
    let filter = format!("{TARGET_PREFIX}*");
    let filter_wide = to_wide_null(&filter);
    let mut count: u32 = 0;
    let mut creds_ptr: *mut *mut CREDENTIALW = std::ptr::null_mut();

    unsafe {
        let result = CredEnumerateW(
            windows::core::PCWSTR(filter_wide.as_ptr()),
            CRED_ENUMERATE_FLAGS(0),
            &mut count,
            &mut creds_ptr,
        );

        if result.is_err() {
            // ERROR_NOT_FOUND (1168) means no credentials match — return empty list
            let err = result.unwrap_err();
            if err.code().0 as u32 == 0x80070490 || err.code().0 == -2147023728 {
                return Ok(Vec::new());
            }
            return Err(VaultError::CredentialEnumerate(err.to_string()));
        }

        let mut nicknames = Vec::with_capacity(count as usize);
        let creds_slice = slice::from_raw_parts(creds_ptr, count as usize);
        for &cred_ptr in creds_slice {
            let cred = &*cred_ptr;
            let full_target = from_wide_ptr(cred.TargetName.0);
            if let Some(nick) = full_target.strip_prefix(TARGET_PREFIX) {
                nicknames.push(nick.to_string());
            }
        }

        CredFree(creds_ptr as *const c_void);
        Ok(nicknames)
    }
}

pub fn has_credential(nickname: &str) -> bool {
    read_credential(nickname).is_ok()
}
