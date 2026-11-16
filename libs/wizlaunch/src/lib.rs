pub mod errors;
pub mod metadata;

// The credential vault, launcher, in-client login, Steam, and the credential
// dialog are Win32-backed. Off-Windows they compile to stubs (same API) so the
// crate builds and imports on macOS/Linux — Deimos hooks an already-running
// client; those features return clear "not supported on this platform" errors.
#[cfg(windows)]
pub mod credential_store;
#[cfg(not(windows))]
#[path = "credential_store_stub.rs"]
pub mod credential_store;

#[cfg(windows)]
pub mod credui;
#[cfg(not(windows))]
#[path = "credui_stub.rs"]
pub mod credui;

#[cfg(windows)]
pub mod launcher;
#[cfg(not(windows))]
#[path = "launcher_stub.rs"]
pub mod launcher;

#[cfg(windows)]
pub mod login;
#[cfg(not(windows))]
#[path = "login_stub.rs"]
pub mod login;

#[cfg(windows)]
pub mod steam;
#[cfg(not(windows))]
#[path = "steam_stub.rs"]
pub mod steam;

#[cfg(feature = "pyo3")]
mod python;

#[cfg(feature = "pyo3")]
pub use python::*;
