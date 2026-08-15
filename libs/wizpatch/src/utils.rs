use std::sync::OnceLock;

use crate::errors::WizPatchError;

/// Lookup table for the standard reflected IEEE CRC-32 polynomial.
fn crc32_table() -> &'static [u32; 256] {
    static TABLE: OnceLock<[u32; 256]> = OnceLock::new();
    TABLE.get_or_init(|| {
        let mut table = [0u32; 256];
        let mut i = 0;
        while i < 256 {
            let mut c = i as u32;
            let mut k = 0;
            while k < 8 {
                c = if c & 1 != 0 { 0xEDB8_8320 ^ (c >> 1) } else { c >> 1 };
                k += 1;
            }
            table[i] = c;
            i += 1;
        }
        table
    })
}

/// KingsIsle's CRC-32, as found in the patch file list. It uses the standard
/// reflected IEEE polynomial table but with an initial value of 0 and **no**
/// final XOR — unlike the ubiquitous zlib CRC-32, which conditions with
/// `0xFFFFFFFF` on both ends. Computing the file list's value with plain zlib
/// CRC-32 mismatches every file, so we must use this variant to decide whether
/// a local file is up to date.
///
/// Streamable: seed `crc` with `0` and fold chunk by chunk.
pub fn ki_crc32_update(mut crc: u32, bytes: &[u8]) -> u32 {
    let table = crc32_table();
    for &b in bytes {
        crc = (crc >> 8) ^ table[((crc ^ b as u32) & 0xff) as usize];
    }
    crc
}

/// Extracts the revision identifier from a patch URL.
///
/// Patch URLs contain `WizPatcher/<revision>/...`; this returns `<revision>`.
pub fn revision_from_url(url: &str) -> Result<String, WizPatchError> {
    let marker = "WizPatcher/";
    let start = url
        .find(marker)
        .ok_or_else(|| WizPatchError::NoRevision(url.to_string()))?
        + marker.len();
    let rest = &url[start..];
    let end = rest.find('/').unwrap_or(rest.len());
    Ok(rest[..end].to_string())
}

/// Strips a leading platform-prefix segment (`Windows`, `MacOS`, `Steam`) from a
/// record's `SrcFileName` so it can be joined with the local game directory.
/// Mirrors MilkLauncher's `fix_src_path`.
pub fn fix_src_path(path: &str) -> &str {
    let mut parts = path.splitn(2, '/');
    let first = parts.next().unwrap_or("");
    let rest = parts.next();
    let lower = first.to_ascii_lowercase();
    if matches!(lower.as_str(), "windows" | "macos" | "steam") {
        rest.unwrap_or(first)
    } else {
        path
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ki_crc32_check_vector() {
        // KingsIsle's variant (init 0, no final XOR) over the canonical
        // "123456789" check string. NOT the zlib value (which is 0xCBF43926).
        assert_eq!(ki_crc32_update(0, b"123456789"), 771_566_984);
        // Empty input folds to the seed unchanged.
        assert_eq!(ki_crc32_update(0, b""), 0);
        // Chunked folding matches a single pass.
        let one = ki_crc32_update(0, b"123456789");
        let split = ki_crc32_update(ki_crc32_update(0, b"1234"), b"56789");
        assert_eq!(one, split);
    }

    #[test]
    fn extracts_revision() {
        let url = "http://example.com/WizPatcher/V_r777777.WizardDev/Live/_FileList.bin";
        assert_eq!(revision_from_url(url).unwrap(), "V_r777777.WizardDev");
    }
}
