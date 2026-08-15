# wizpatch

A fast, parallel patcher and downloader for Wizard101 game files.

## Install

### Nix (Linux & macOS)

With flakes enabled, run it without installing:

```sh
nix run github:Deimos-Wizard101/wizpatch -- patch
```

Install it into your profile:

```sh
nix profile install github:Deimos-Wizard101/wizpatch
```

Or add it to a flake / NixOS / home-manager config via the `packages.<system>.default`
output. A dev shell with the full Rust toolchain is available with `nix develop`.

### Homebrew (macOS)

```sh
brew install --HEAD Deimos-Wizard101/wizpatch/wizpatch
```

(Once a tagged release exists, `brew install Deimos-Wizard101/wizpatch/wizpatch`
will build from that release instead of `main`.)

### Cargo / from source (Linux, macOS, Windows)

Requires a Rust toolchain. The CLI lives behind the `cli` feature:

```sh
cargo install --git https://github.com/Deimos-Wizard101/wizpatch --features cli
```

or, from a local checkout:

```sh
cargo install --path . --features cli
```

## Usage

```
wizpatch <command> [globs...] [options]
```

Commands:

- `patch` — CRC-check local files and download the missing/changed ones.
- `download` — force-download files, ignoring local CRC (repair/refetch).
- `search` — print file-list entries matching the globs; download nothing.

Run `wizpatch --help` for the full option list.

## License

GPL-3.0-or-later.
