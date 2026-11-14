# Linux backend

Pieces for running Deimos/wizwalker as **native Linux Python** against a
Proton-hosted Wizard101 client, instead of under Wine. The game stays under
Proton; everything else runs native and reaches the game through `/proc` and
X11.

## Parts

- **`pymem/`** — a drop-in replacement for the Windows-only `pymem`, backed by
  the `zhol` native extension (`/proc/<pid>/mem`). Implements exactly the
  surface wizwalker's `MemoryReader` uses: `Pymem.open_process_from_id`,
  `read_bytes`/`write_bytes`/`allocate`, and the module functions
  `memory.virtual_query`, `memory.read_bytes`, `process.module_from_name`, plus
  the `ressources.structure` constants. Put this directory first on `sys.path`
  so `import pymem` resolves here.
- **`window_input.py`** — per-window geometry, focus, and key injection via
  `xdotool` (the clients are XWayland windows). The Linux analogue of
  wizwalker's HWND + PostMessage path.
- **`instances.py`** — find clients by pid from `/proc` (no HWND enumeration).

## zhol extension

`pymem/` imports `zhol`, the native extension built from the `zhol` crate
(`~/Documents/rust-projects/zhol`, `unix-expansion` branch) with its `python`
feature:

```sh
cd ~/Documents/rust-projects/zhol
cargo build --release --features python
cp target/release/libzhol.so <on your PYTHONPATH>/zhol.so
```

`zhol.Process` provides read/write/module/query/pattern_scan/allocate over
`/proc`, reaching the game inside the Wine process. Writes land on read-only and
executable pages (kernel `FOLL_FORCE`, no ptrace), which is what hook
installation needs. Allocation carves a code cave from the module's section
padding; for Wizard101's packed `.text`, register wizwalker's autobot region as
the cave with `Process.register_cave(addr, size)`.

## Status

Verified against a live client: module resolution, region-walking pattern scan
(wizwalker's autobot pattern, found in 0.06 s), reads, writes, cave allocation,
window geometry/focus, and key injection. Remaining integration: make wizwalker
importable on Linux (its `constants.py`/`utils.py` use `ctypes.windll`), route
`timed_send_key` through `window_input`, and make `Client` pid/x-window based.
