# deimos-updater

A tiny native self-update helper for [Deimos-Wizard101](https://github.com/Deimos-Wizard101/Deimos-Wizard101).

A running PyInstaller one-file `Deimos.exe` holds a lock on its own image and
therefore cannot overwrite itself. Deimos embeds this helper, extracts it at
update time, spawns it detached, and exits. The helper then:

1. Waits for the parent Deimos process (by PID) to fully exit.
2. Copies the freshly downloaded executable over the old one, retrying to ride
   out lingering file locks (common under Wine/Proton).
3. Optionally relaunches the updated executable.

All steps are logged to `%APPDATA%/Deimos/update/updater.log` so failures (e.g.
a read-only install directory) are diagnosable rather than silent.

## Usage

```
deimos-updater --pid <parent_pid> --new <downloaded.exe> --target <Deimos.exe> [--relaunch] [--log <path>]
```

| Flag | Description |
|------|-------------|
| `--pid` | PID of the parent process to wait on before swapping. |
| `--new` | Path to the freshly downloaded replacement executable. |
| `--target` | Path to the executable to overwrite (the running `Deimos.exe`). |
| `--relaunch` | If present, launch `--target` after a successful swap. |
| `--log` | Override the log file path (defaults to `%APPDATA%/Deimos/update/updater.log`). |

Exit codes: `0` success · `2` missing args · `3` payload missing · `4` swap failed.

## Build

```
cargo build --release
```

Produces `target/release/deimos-updater.exe`.

## License

GPL-3.0-only.
