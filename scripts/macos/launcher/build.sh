#!/usr/bin/env bash
# Build and ad-hoc code-sign the macOS Deimos launcher.
#
# The signature carries com.apple.security.cs.debugger so the launcher (which IS
# the interpreter host — it embeds libpython) can task_for_pid the Wine game.
# Ad-hoc (`-s -`), no hardened runtime, so library validation does not block the
# third-party dylibs the app loads; this matches what makes the zhol Rust examples
# work on this machine.
set -euo pipefail
cd "$(dirname "$0")"

# pyo3 needs a Python to link against; the one you run Deimos with (3.13).
export PYO3_PYTHON="${PYO3_PYTHON:-python3.13}"

cargo build --release
BIN="target/release/deimos-launcher"

codesign --force --sign - --entitlements launcher.entitlements "$BIN"
echo "--- signature ---"
codesign -dv --entitlements :- "$BIN" 2>&1 | grep -iE "debugger|library-validation|Signature" || true
echo
echo "built + signed: $(pwd)/$BIN"
echo "run e.g.:  PYTHONPATH=... $BIN ../attach_test.py"
