use crate::credential_store;
use crate::errors::VaultError;
use crate::metadata;
use aes::Aes128;
use base64::{engine::general_purpose::URL_SAFE, Engine};
use cbc::cipher::{block_padding::Pkcs7, BlockDecryptMut, KeyIvInit};
use hmac::{Hmac, Mac};
use sha2::Sha256;
use std::collections::HashMap;
use std::fs;
use std::path::Path;
use windows::Win32::Foundation::HLOCAL;
use windows::Win32::Security::Cryptography::{CryptUnprotectData, CRYPT_INTEGER_BLOB};

type Aes128CbcDec = cbc::Decryptor<Aes128>;
type HmacSha256 = Hmac<Sha256>;

/// Decrypt DPAPI-protected data (used for the legacy vault key).
fn dpapi_decrypt(protected: &[u8]) -> Result<Vec<u8>, VaultError> {
    let mut in_blob = CRYPT_INTEGER_BLOB {
        cbData: protected.len() as u32,
        pbData: protected.as_ptr() as *mut u8,
    };
    let mut out_blob = CRYPT_INTEGER_BLOB {
        cbData: 0,
        pbData: std::ptr::null_mut(),
    };

    unsafe {
        CryptUnprotectData(
            &mut in_blob,
            None,
            None,
            None,
            None,
            0,
            &mut out_blob,
        )
        .map_err(|e| VaultError::LegacyDpapi(e.to_string()))?;

        let data =
            std::slice::from_raw_parts(out_blob.pbData, out_blob.cbData as usize).to_vec();

        // Free the output buffer allocated by CryptUnprotectData
        let _ = windows::Win32::Foundation::LocalFree(HLOCAL(out_blob.pbData as *mut _));

        Ok(data)
    }
}

/// Decrypt a Fernet token using pure-Rust crypto.
///
/// Fernet spec: <https://github.com/fernet/spec/blob/master/Spec.md>
/// Key = URL-safe base64 of 32 bytes (16 signing + 16 encryption)
/// Token = URL-safe base64 of: version(1) || timestamp(8) || IV(16) || ciphertext(N) || HMAC(32)
fn fernet_decrypt(key_b64: &str, token_b64: &str) -> Result<Vec<u8>, VaultError> {
    let key_bytes = URL_SAFE
        .decode(key_b64.trim())
        .map_err(|e| VaultError::LegacyFernet(format!("Invalid Fernet key base64: {e}")))?;

    if key_bytes.len() != 32 {
        return Err(VaultError::LegacyFernet(format!(
            "Fernet key must be 32 bytes, got {}",
            key_bytes.len()
        )));
    }

    let signing_key = &key_bytes[..16];
    let encryption_key = &key_bytes[16..];

    let token_bytes = URL_SAFE
        .decode(token_b64.trim())
        .map_err(|e| VaultError::LegacyFernet(format!("Invalid Fernet token base64: {e}")))?;

    // Minimum: version(1) + timestamp(8) + IV(16) + at least 1 block(16) + HMAC(32) = 73
    if token_bytes.len() < 73 {
        return Err(VaultError::LegacyFernet("Token too short".to_string()));
    }

    let version = token_bytes[0];
    if version != 0x80 {
        return Err(VaultError::LegacyFernet(format!(
            "Unsupported Fernet version: {version:#x}"
        )));
    }

    let hmac_offset = token_bytes.len() - 32;
    let payload = &token_bytes[..hmac_offset];
    let expected_hmac = &token_bytes[hmac_offset..];

    // Verify HMAC-SHA256
    let mut mac = HmacSha256::new_from_slice(signing_key)
        .map_err(|e| VaultError::LegacyFernet(format!("HMAC init failed: {e}")))?;
    mac.update(payload);
    mac.verify_slice(expected_hmac)
        .map_err(|_| VaultError::LegacyFernet("HMAC verification failed".to_string()))?;

    // Extract IV and ciphertext
    let iv = &token_bytes[9..25];
    let ciphertext = &token_bytes[25..hmac_offset];

    // Decrypt AES-128-CBC with PKCS7 padding
    let mut buf = ciphertext.to_vec();
    let decryptor = Aes128CbcDec::new(encryption_key.into(), iv.into());
    let plaintext = decryptor
        .decrypt_padded_mut::<Pkcs7>(&mut buf)
        .map_err(|e| VaultError::LegacyFernet(format!("AES decryption failed: {e}")))?;
    let result = plaintext.to_vec();

    Ok(result)
}

/// Import accounts from the legacy Fernet+DPAPI vault into Windows Credential Manager.
///
/// `vault_path` — path to `accounts.vault`
/// `key_path`   — path to `accounts.key`
///
/// Returns the number of accounts successfully imported.
pub fn import_legacy_vault(vault_path: &str, key_path: &str) -> Result<u32, VaultError> {
    let vault_path = Path::new(vault_path);
    let key_path = Path::new(key_path);

    if !vault_path.exists() {
        return Err(VaultError::LegacyParse(format!(
            "Vault file not found: {}",
            vault_path.display()
        )));
    }
    if !key_path.exists() {
        return Err(VaultError::LegacyParse(format!(
            "Key file not found: {}",
            key_path.display()
        )));
    }

    // Step 1: Read and decrypt the DPAPI-protected Fernet key
    let protected_key = fs::read(key_path)
        .map_err(|e| VaultError::LegacyParse(format!("Failed to read key file: {e}")))?;

    let raw_key = dpapi_decrypt(&protected_key)?;
    let key_str = std::str::from_utf8(&raw_key)
        .map_err(|e| VaultError::LegacyFernet(format!("Key is not valid UTF-8: {e}")))?;

    // Step 2: Read the encrypted vault
    let encrypted = fs::read(vault_path)
        .map_err(|e| VaultError::LegacyParse(format!("Failed to read vault file: {e}")))?;

    let token_str = std::str::from_utf8(&encrypted)
        .map_err(|e| VaultError::LegacyFernet(format!("Vault token is not valid UTF-8: {e}")))?;

    // Step 3: Decrypt with Fernet (pure-Rust implementation)
    let decrypted = fernet_decrypt(key_str, token_str)?;

    // Step 4: Parse JSON — format is {"nickname": {"username": "...", "password": "...", "player_gid": "..."}, ...}
    let accounts: HashMap<String, HashMap<String, String>> = serde_json::from_slice(&decrypted)
        .map_err(|e| VaultError::LegacyParse(format!("Failed to parse vault JSON: {e}")))?;

    // Step 5: Write each account to Credential Manager + metadata
    let mut count: u32 = 0;
    for (nickname, data) in &accounts {
        let username = match data.get("username") {
            Some(u) => u,
            None => continue,
        };
        let password = match data.get("password") {
            Some(p) => p,
            None => continue,
        };

        if let Err(e) = credential_store::write_credential(nickname, username, password) {
            eprintln!("Warning: failed to import '{nickname}': {e}");
            continue;
        }

        metadata::ensure_nickname(nickname)?;

        // Migrate GID if present
        if let Some(gid_str) = data.get("player_gid") {
            if let Ok(gid) = gid_str.parse::<u64>() {
                metadata::update_gid(nickname, gid)?;
            }
        }

        count += 1;
    }

    Ok(count)
}
