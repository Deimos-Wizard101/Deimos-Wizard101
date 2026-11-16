fn main() {
    // On macOS a pyo3 extension module (cdylib) must link with
    // `-undefined dynamic_lookup`: the `_Py*` symbols resolve at load time via the
    // hosting interpreter, not at link time. Applies only to the cdylib; the CLI
    // bin and rlib are unaffected. No-op on Linux/Windows.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rustc-cdylib-link-arg=-undefined");
        println!("cargo:rustc-cdylib-link-arg=dynamic_lookup");
    }
}
