//! XML file-list parser. MilkLauncher only patches Wizard101, whose file list
//! is served as XML (`.xml`); the binary DML format used by Pirate101 is not
//! ported.

use std::collections::HashMap;

use quick_xml::events::Event;
use quick_xml::Reader;

use crate::errors::WizPatchError;

const IGNORED: &[&str] = &["_TableList", "About"];

#[derive(Debug, Clone)]
pub enum Field {
    Int(i64),
    Text(String),
}

impl Field {
    pub fn as_i64(&self) -> Option<i64> {
        match self {
            Field::Int(v) => Some(*v),
            Field::Text(s) => s.parse().ok(),
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Field::Text(s) => Some(s.as_str()),
            Field::Int(_) => None,
        }
    }
}

pub type Record = HashMap<String, Field>;

/// Parses the XML file list. Matches the Python
/// `parse_records_from_xml`: returns `{"records": [...]}`.
pub fn parse_records_from_xml(data: &[u8]) -> Result<HashMap<String, Vec<Record>>, WizPatchError> {
    let text = std::str::from_utf8(data)
        .map_err(|e| WizPatchError::Xml(format!("invalid utf-8: {e}")))?;
    let mut reader = Reader::from_str(text);
    reader.config_mut().trim_text(true);

    let mut buf = Vec::new();
    let mut records: Vec<Record> = Vec::new();

    let mut depth: usize = 0;
    let mut table_skip_depth: Option<usize> = None;
    let mut current_record: Option<Record> = None;
    let mut current_field: Option<String> = None;

    loop {
        match reader.read_event_into(&mut buf)? {
            Event::Start(e) => {
                depth += 1;
                let name = String::from_utf8(e.name().as_ref().to_vec())?;

                if depth == 2 && IGNORED.contains(&name.as_str()) {
                    table_skip_depth = Some(depth);
                    continue;
                }
                if table_skip_depth.is_some() {
                    continue;
                }

                match depth {
                    3 => current_record = Some(HashMap::new()),
                    4 => current_field = Some(name),
                    _ => {}
                }
            }
            Event::End(_) => {
                if let Some(skip) = table_skip_depth {
                    if depth == skip {
                        table_skip_depth = None;
                    }
                }

                if depth == 3 {
                    if let Some(rec) = current_record.take() {
                        records.push(rec);
                    }
                } else if depth == 4 {
                    current_field = None;
                }
                depth = depth.saturating_sub(1);
            }
            Event::Text(t) => {
                if table_skip_depth.is_some() {
                    continue;
                }
                if let (Some(rec), Some(field)) =
                    (current_record.as_mut(), current_field.as_ref())
                {
                    let raw = t.unescape().map_err(|e| WizPatchError::Xml(e.to_string()))?;
                    let value = if !raw.is_empty() && raw.chars().all(|c| c.is_ascii_digit()) {
                        Field::Int(raw.parse().unwrap_or(0))
                    } else {
                        Field::Text(raw.into_owned())
                    };
                    rec.insert(field.clone(), value);
                }
            }
            Event::Eof => break,
            _ => {}
        }
        buf.clear();
    }

    let mut out = HashMap::new();
    out.insert("records".to_string(), records);
    Ok(out)
}
