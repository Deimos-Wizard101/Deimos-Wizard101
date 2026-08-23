//! Thin port of `UpdateNotifier.get_file_list_records` for Wizard101's XML
//! file list. The full update/diff/DB machinery is intentionally omitted —
//! MilkLauncher does not use it for Wizard101 patching.

use crate::dml::{parse_records_from_xml, Field, Record};
use crate::errors::WizPatchError;
use crate::webdriver::get_url_data;

#[derive(Debug, Clone)]
pub struct FileRecord {
    pub src_file_name: String,
    pub crc: u64,
    pub size: u64,
    pub extra: Record,
}

impl FileRecord {
    pub fn from_record(rec: Record) -> Option<Self> {
        let src_file_name = rec.get("SrcFileName")?.as_str()?.to_string();
        let crc = rec.get("CRC")?.as_i64()? as u64;
        let size = rec.get("Size")?.as_i64()? as u64;
        Some(Self {
            src_file_name,
            crc,
            size,
            extra: rec,
        })
    }
}

/// Fetches the XML file list and returns one `FileRecord` per `<RECORD>`.
pub async fn get_file_list_records(file_list_url: &str) -> Result<Vec<FileRecord>, WizPatchError> {
    // Python's UpdateNotifier swaps `.bin` for `.xml` on Wizard101.
    let xml_url = file_list_url.replace(".bin", ".xml");
    let data = get_url_data(&xml_url, None).await?;
    let parsed = parse_records_from_xml(&data)?;
    let records = parsed.get("records").cloned().unwrap_or_default();

    Ok(records
        .into_iter()
        .filter_map(FileRecord::from_record)
        .collect())
}

impl Field {
    pub fn into_string(self) -> Option<String> {
        match self {
            Field::Text(s) => Some(s),
            Field::Int(i) => Some(i.to_string()),
        }
    }
}
