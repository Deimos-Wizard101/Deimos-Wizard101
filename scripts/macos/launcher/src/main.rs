//! Signed macOS launcher for Deimos.
//!
//! On macOS a process can only `task_for_pid` another process (what zhol needs to
//! read/hook the Wine-hosted game) if the process's MAIN executable is code-signed
//! with `com.apple.security.cs.debugger`. A signed copy of the framework `python3`
//! does not work: the venv/framework launch path re-execs into the unsigned
//! framework binary, so the entitlement isn't on the image the kernel checks.
//!
//! This launcher embeds libpython and runs the target script in-process, so the
//! main image IS this signed binary — the entitlement stays effective and no
//! re-exec happens. Build with `build.sh` (which also ad-hoc signs it with the
//! entitlement); see README.md.
//!
//!     deimos-launcher <script.py> [args...]
//!
//! `sys.path` is seeded from the `PYTHONPATH` env var (colon-separated), exactly as
//! the normal interpreter would, so point it at the venv site-packages plus the
//! Deimos dirs (src/linux_backend, libs/wizwalker, libs/wizsprinter) and the dir
//! holding zhol.so — the same PYTHONPATH used to run Deimos directly.

use std::process::ExitCode;

use pyo3::prelude::*;
use pyo3::types::{PyList, PyString};

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: deimos-launcher <script.py> [args...]");
        return ExitCode::from(2);
    }
    let script = args[1].clone();
    let script_args = args[2..].to_vec();

    pyo3::prepare_freethreaded_python();
    let code = Python::with_gil(|py| -> ExitCode {
        let run = (|| -> PyResult<()> {
            let sys = py.import_bound("sys")?;
            let sys_path = sys.getattr("path")?.downcast_into::<PyList>().unwrap();

            // Prepend PYTHONPATH entries (venv site-packages, Deimos dirs, zhol dir).
            if let Ok(pp) = std::env::var("PYTHONPATH") {
                for (i, entry) in pp.split(':').filter(|s| !s.is_empty()).enumerate() {
                    sys_path.insert(i, PyString::new_bound(py, entry))?;
                }
            }
            // The script's own directory at sys.path[0], exactly as `python
            // script.py` does — so a script can `import` its sibling packages
            // (e.g. Deimos.py importing `src`).
            if let Some(dir) = std::path::Path::new(&script).parent() {
                if let Some(d) = dir.to_str() {
                    let d = if d.is_empty() { "." } else { d };
                    sys_path.insert(0, PyString::new_bound(py, d))?;
                }
            }

            // Point child processes (subprocess[sys.executable], multiprocessing
            // spawn) at the real framework python, not this launcher binary — else
            // `sys.executable -c ...` treats "-c" as a script path. Children don't
            // need the debugger entitlement.
            let fix_exe = r#"
import os, sys
for _c in (getattr(sys, '_base_executable', None),
           os.path.join(sys.base_prefix, 'bin', 'python3.13'),
           os.path.join(sys.base_prefix, 'bin', 'python3')):
    if _c and os.path.exists(_c) and 'deimos-launcher' not in _c:
        sys.executable = _c
        try:
            import multiprocessing
            multiprocessing.set_executable(_c)
        except Exception:
            pass
        break
"#;
            let _ = py.run_bound(fix_exe, None, None);

            // sys.argv = [script, args...], as a normal `python script.py ...` run.
            let argv = PyList::empty_bound(py);
            argv.append(PyString::new_bound(py, &script))?;
            for a in &script_args {
                argv.append(PyString::new_bound(py, a))?;
            }
            sys.setattr("argv", argv)?;

            // Run the script as __main__ (so `if __name__ == "__main__":` fires).
            let runpy = py.import_bound("runpy")?;
            let kwargs = pyo3::types::PyDict::new_bound(py);
            kwargs.set_item("run_name", "__main__")?;
            runpy.call_method("run_path", (PyString::new_bound(py, &script),), Some(&kwargs))?;
            Ok(())
        })();

        if let Err(e) = &run {
            e.print(py);
        }
        // Flush: Python's stdout/stderr are block-buffered when not a tty (piped or
        // redirected), so without this all script output is lost on a clean exit.
        if let Ok(sys) = py.import_bound("sys") {
            for name in ["stdout", "stderr"] {
                if let Ok(stream) = sys.getattr(name) {
                    let _ = stream.call_method0("flush");
                }
            }
        }
        if run.is_ok() {
            ExitCode::SUCCESS
        } else {
            ExitCode::FAILURE
        }
    });

    // Finalize so atexit handlers run and C-level buffers flush before exit.
    unsafe {
        pyo3::ffi::Py_FinalizeEx();
    }
    code
}
