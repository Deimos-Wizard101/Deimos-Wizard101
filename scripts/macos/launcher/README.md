# Deimos macOS launcher

A tiny signed native host that **embeds libpython** and runs a Python script
in-process. It exists to solve one macOS-specific problem:

To read/hook another process, zhol calls `task_for_pid`, which the kernel only
permits if the **main executable** of the calling process is code-signed with
`com.apple.security.cs.debugger`. A signed *copy* of the framework `python3`
doesn't work — the venv/framework launch path re-execs into the unsigned framework
binary (`sys._base_executable`), so the entitlement isn't on the image the kernel
checks. This launcher **is** the interpreter (no re-exec), so the entitlement
stays effective.

(The game's own Wine loader must separately carry `get-task-allow`; see
`libs/wizwalker/wizwalker/_macos.py` for that side.)

## Build + sign

    cd scripts/macos/launcher
    PYO3_PYTHON=python3.13 ./build.sh

Produces and ad-hoc-signs `target/release/deimos-launcher` with the entitlement
(`launcher.entitlements`). Requires Rust (cargo) and a Python 3.13 that pyo3 can
link against.

## Run

Set `PYTHONPATH` exactly as you would to run Deimos directly — the venv
site-packages plus the native-backend dirs and the folder holding `zhol.so`:

    export PYTHONPATH="<venv>/lib/python3.13/site-packages:\
    $PWD/../../../src/linux_backend:$PWD/../../../libs/wizwalker:\
    $PWD/../../../libs/wizsprinter:<dir-with-zhol.so>"

    # Prove attach works:
    ./target/release/deimos-launcher ../macos_attach_test.py

    # Run the app the same way (once PyQt6 etc. are in the venv):
    ./target/release/deimos-launcher ../../../Deimos.py

If libpython isn't found at runtime, point `DYLD_LIBRARY_PATH` or `PYTHONHOME` at
the framework (the `allow-dyld-environment-variables` entitlement permits this),
e.g. `PYTHONHOME=/opt/homebrew/Frameworks/Python.framework/Versions/3.13`.

## Notes

- Ad-hoc signed, **no** hardened runtime: library validation is therefore not
  enforced, so the many third-party dylibs (zhol.so, PyQt6, numpy, …) load. The
  `cs.disable-library-validation` entitlement is included belt-and-suspenders in
  case a hardened-runtime signature is used later.
- This is the macOS equivalent of `scripts/linux/run_native.sh`.
