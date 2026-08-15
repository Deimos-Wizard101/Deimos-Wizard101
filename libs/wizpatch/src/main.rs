use std::path::PathBuf;
use std::process;

use wizpatch::{patch, Country, Game, Mode, PatchOptions, Platform, WizPatchError};

fn usage() {
    eprintln!(
        "wizpatch — Wizard101 patcher\n\
         \n\
         Usage: wizpatch <command> [globs...] [options]\n\
         \n\
         Commands:\n\
         \n\
           patch                    CRC-check local files and download the\n\
                                    missing/changed ones (the default workflow)\n\
           download                 Force-download files, ignoring local CRC\n\
                                    (use to repair/refetch)\n\
           search                   Print file-list entries matching the globs;\n\
                                    download nothing\n\
         \n\
         Globs (positional, repeatable) select which files a command acts on.\n\
         A pattern with no wildcard is a case-insensitive substring match; one\n\
         with '*' or '?' is a glob where '*' spans '/'. With no glob, patch and\n\
         download act on the whole file list. search requires at least one.\n\
         \n\
         Examples:\n\
           wizpatch patch\n\
           wizpatch download 'Data/GameData/*.wad'\n\
           wizpatch search Root.wad\n\
         \n\
         Options:\n\
         \n\
           --path <DIR>             Game install directory\n\
                                    (auto-detected on macOS/Windows; required on Linux)\n\
           --platform <p>           windows|mac|steam\n\
                                    (default: mac on macOS, windows elsewhere)\n\
           --country <us|eu>        Patch server region (default: us)\n\
           --revision <STR>         Pin a specific revision\n\
                                    (e.g. V_r800683.Wizard_1_610)\n\
           --no-download-missing    Patch only files already present locally\n\
                                    (patch mode only)\n\
           --jobs <N>               Max parallel large-file downloads (default: 8)\n\
           --small-jobs <N>         Parallel small-file downloads (default: 64)\n\
           -v, --verbose            Print per-file completions and controller stats\n\
           -h, --help               Print this help"
    );
}

fn default_platform() -> Platform {
    if cfg!(target_os = "macos") {
        Platform::MacOs
    } else {
        Platform::Windows
    }
}

fn default_game_path(platform: Platform) -> Option<PathBuf> {
    let candidates: Vec<PathBuf> = if cfg!(target_os = "macos") {
        vec![PathBuf::from("/Applications/Wizard101")]
    } else if cfg!(target_os = "windows") {
        let non_steam = PathBuf::from(r"C:\ProgramData\KingsIsle Entertainment\Wizard101");
        let steam = PathBuf::from(r"C:\Program Files (x86)\Steam\steamapps\common\Wizard101");
        match platform {
            Platform::Steam => vec![steam, non_steam],
            _ => vec![non_steam, steam],
        }
    } else {
        return None;
    };
    candidates.into_iter().find(|p| p.is_dir())
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if let Err(e) = smol::block_on(run(args)) {
        eprintln!("Error: {e}");
        process::exit(1);
    }
}

async fn run(args: Vec<String>) -> Result<(), WizPatchError> {
    // First token is the command (or a help flag).
    let mut i = 0;
    let mode = match args.first().map(String::as_str) {
        Some("patch") => Mode::Patch,
        Some("download") => Mode::Download,
        Some("search") => Mode::Search,
        Some("-h") | Some("--help") | Some("help") | None => {
            usage();
            return Ok(());
        }
        Some(other) => {
            eprintln!("Unknown command: {other}");
            usage();
            process::exit(1);
        }
    };
    i += 1;

    let mut download_missing = true;
    let mut country = Country::Us;
    let mut revision: Option<String> = None;
    let mut game_path: Option<PathBuf> = None;
    let mut platform: Option<Platform> = None;
    let mut jobs: usize = 8;
    let mut small_jobs: usize = 64;
    let mut verbose = false;
    let mut globs: Vec<String> = Vec::new();

    while i < args.len() {
        match args[i].as_str() {
            "--download-missing" => download_missing = true,
            "--no-download-missing" => download_missing = false,
            "--country" => {
                i += 1;
                country = match args.get(i).map(String::as_str) {
                    Some("us") => Country::Us,
                    Some("eu") => Country::Eu,
                    other => {
                        return Err(WizPatchError::Protocol(format!(
                            "unknown country: {other:?}"
                        )));
                    }
                };
            }
            "--platform" => {
                i += 1;
                platform = Some(match args.get(i).map(String::as_str) {
                    Some("windows") => Platform::Windows,
                    Some("mac") | Some("macos") => Platform::MacOs,
                    Some("steam") => Platform::Steam,
                    other => {
                        return Err(WizPatchError::Protocol(format!(
                            "unknown platform: {other:?}"
                        )));
                    }
                });
            }
            "--revision" => {
                i += 1;
                revision = Some(
                    args.get(i)
                        .ok_or_else(|| {
                            WizPatchError::Protocol("--revision needs a value".into())
                        })?
                        .clone(),
                );
            }
            "--path" => {
                i += 1;
                game_path = Some(PathBuf::from(args.get(i).ok_or_else(|| {
                    WizPatchError::Protocol("--path needs a value".into())
                })?));
            }
            "--jobs" => {
                i += 1;
                jobs = args
                    .get(i)
                    .and_then(|s| s.parse().ok())
                    .filter(|&n: &usize| n >= 1)
                    .ok_or_else(|| {
                        WizPatchError::Protocol("--jobs needs a positive integer".into())
                    })?;
            }
            "--small-jobs" => {
                i += 1;
                small_jobs = args
                    .get(i)
                    .and_then(|s| s.parse().ok())
                    .filter(|&n: &usize| n >= 1)
                    .ok_or_else(|| {
                        WizPatchError::Protocol("--small-jobs needs a positive integer".into())
                    })?;
            }
            "-v" | "--verbose" => verbose = true,
            "-h" | "--help" | "help" => {
                usage();
                return Ok(());
            }
            other if other.starts_with('-') => {
                eprintln!("Unknown argument: {other}");
                usage();
                process::exit(1);
            }
            // A bare token is a glob/substring selector.
            other => globs.push(other.to_string()),
        }
        i += 1;
    }

    if mode == Mode::Search && globs.is_empty() {
        eprintln!("Error: `search` needs at least one glob/substring to match.");
        usage();
        process::exit(1);
    }

    let platform = platform.unwrap_or_else(default_platform);

    // Search and download never read local files, so a real install path is
    // not strictly required — but patch (and the path-join for downloads) need
    // somewhere to write. Auto-detect as before.
    let game_path = match game_path {
        Some(p) => p,
        None => match default_game_path(platform) {
            Some(p) => {
                println!("Auto-detected install: {}", p.display());
                p
            }
            None if mode == Mode::Search => PathBuf::new(),
            None => {
                eprintln!(
                    "Error: could not auto-detect a Wizard101 install on this OS — pass --path <DIR>."
                );
                process::exit(1);
            }
        },
    };

    let opts = PatchOptions {
        game: Game::Wizard101,
        platform,
        country,
        revision,
        mode,
        globs,
        download_missing,
        game_path,
        jobs,
        small_jobs,
        verbose,
    };

    let stats = patch(&opts).await?;
    match mode {
        Mode::Search => {} // run_search already printed everything
        _ => println!(
            "\nDone. {} downloaded, {} up-to-date, {} skipped (missing), {} failed (of {} records).",
            stats.downloaded,
            stats.up_to_date,
            stats.skipped_missing,
            stats.failed,
            stats.total
        ),
    }
    Ok(())
}
