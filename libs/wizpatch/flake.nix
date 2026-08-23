{
  description = "wizpatch — a fast parallel Wizard101 patcher and downloader";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        inherit (pkgs) lib;

        wizpatch = pkgs.rustPlatform.buildRustPackage {
          pname = "wizpatch";
          version = "0.1.0";

          # Only the files the build actually needs — keeps the local game
          # install (./wizard101) and ./target out of the Nix store.
          src = lib.fileset.toSource {
            root = ./.;
            fileset = lib.fileset.unions [
              ./Cargo.toml
              ./Cargo.lock
              ./src
            ];
          };

          cargoLock.lockFile = ./Cargo.lock;

          # The `wizpatch` binary target is gated behind the `cli` feature; the
          # library builds without it.
          buildFeatures = [ "cli" ];
          cargoTestFlags = [ "--features" "cli" ];

          # rustls + ring give us pure-Rust TLS, so there's no OpenSSL or macOS
          # Security framework to wire up. Darwin's linker still wants libiconv.
          buildInputs = lib.optionals pkgs.stdenv.isDarwin [ pkgs.libiconv ];

          meta = {
            description = "Fast parallel patcher/downloader for Wizard101 game files";
            homepage = "https://github.com/Deimos-Wizard101/wizpatch";
            license = lib.licenses.gpl3Plus;
            mainProgram = "wizpatch";
            platforms = lib.platforms.unix;
          };
        };
      in
      {
        packages.default = wizpatch;
        packages.wizpatch = wizpatch;

        apps.default = {
          type = "app";
          program = lib.getExe wizpatch;
        };

        devShells.default = pkgs.mkShell {
          inputsFrom = [ wizpatch ];
          packages = with pkgs; [
            cargo
            rustc
            clippy
            rustfmt
            rust-analyzer
          ];
          RUST_SRC_PATH = "${pkgs.rustPlatform.rustLibSrc}";
        };

        formatter = pkgs.nixpkgs-fmt;
      }
    );
}
