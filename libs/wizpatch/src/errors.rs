use thiserror::Error;

#[derive(Debug, Error)]
pub enum WizPatchError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("HTTP error: {0}")]
    Http(String),

    #[error("Patch server returned malformed data: {0}")]
    Protocol(String),

    #[error("XML parse error: {0}")]
    Xml(String),

    #[error("Revision string not found in URL: {0}")]
    NoRevision(String),

    #[error("UTF-8 decoding error: {0}")]
    Utf8(#[from] std::string::FromUtf8Error),
}

impl From<quick_xml::Error> for WizPatchError {
    fn from(err: quick_xml::Error) -> Self {
        WizPatchError::Xml(err.to_string())
    }
}
