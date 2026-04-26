use std::collections::HashSet;
use std::process;

use wizlaunch::{credential_store, credui, launcher, login, metadata};

const DEFAULT_LOGIN_SERVER: &str = "login.us.wizard101.com:12000";

fn usage() {
    eprintln!(
        "wizlaunch — Wizard101 account manager & launcher\n\
         \n\
         Usage:\n\
         \n\
         Account management:\n\
         \n\
           wizlaunch list                          List saved accounts\n\
           wizlaunch add <nickname>                Add account (opens credential dialog)\n\
           wizlaunch delete <nickname>             Remove account\n\
         \n\
         Launching:\n\
         \n\
           wizlaunch launch <nick> [nicks...] [options]\n\
         \n\
         Options:\n\
         \n\
           --path <game_path>                     Path to Wizard101 install\n\
           --server <host:port>                   Login server (default: {DEFAULT_LOGIN_SERVER})\n\
           --timeout <secs>                       Window detection timeout (default: 30)"
    );
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();

    if args.is_empty() {
        usage();
        process::exit(1);
    }

    let result = match args[0].as_str() {
        "list" => cmd_list(),
        "add" => cmd_add(&args[1..]),
        "delete" => cmd_delete(&args[1..]),
        "launch" => cmd_launch(&args[1..]),
        "-h" | "--help" | "help" => {
            usage();
            Ok(())
        }
        other => {
            eprintln!("Unknown command: {other}");
            usage();
            process::exit(1);
        }
    };

    if let Err(e) = result {
        eprintln!("Error: {e}");
        process::exit(1);
    }
}

fn cmd_list() -> Result<(), Box<dyn std::error::Error>> {
    let cred_nicks = credential_store::list_credential_nicknames()?;
    let ordered = metadata::get_ordered_nicknames(&cred_nicks)?;
    if ordered.is_empty() {
        println!("No saved accounts.");
    } else {
        for (i, nick) in ordered.iter().enumerate() {
            println!("  {}. {nick}", i + 1);
        }
    }
    Ok(())
}

fn cmd_add(args: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let nickname = args.first().ok_or("Usage: wizlaunch add <nickname>")?;
    let (username, password) = credui::prompt_credentials(
        "wizlaunch — Save Account",
        &format!("Enter credentials for '{nickname}'"),
    )?;
    credential_store::write_credential(nickname, &username, &password)?;
    metadata::ensure_nickname(nickname)?;
    println!("Account '{nickname}' saved.");
    Ok(())
}

fn cmd_delete(args: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let nickname = args.first().ok_or("Usage: wizlaunch delete <nickname>")?;
    credential_store::delete_credential(nickname)?;
    metadata::remove_nickname(nickname)?;
    println!("Account '{nickname}' deleted.");
    Ok(())
}

fn cmd_launch(args: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let mut nicknames: Vec<String> = Vec::new();
    let mut game_path: Option<String> = None;
    let mut login_server = DEFAULT_LOGIN_SERVER.to_string();
    let mut timeout_secs: u64 = 30;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--path" => {
                i += 1;
                game_path = Some(args.get(i).ok_or("--path requires a value")?.clone());
            }
            "--server" => {
                i += 1;
                login_server = args.get(i).ok_or("--server requires a value")?.clone();
            }
            "--timeout" => {
                i += 1;
                timeout_secs = args
                    .get(i)
                    .ok_or("--timeout requires a value")?
                    .parse()
                    .map_err(|_| "invalid timeout")?;
            }
            nick => nicknames.push(nick.to_string()),
        }
        i += 1;
    }

    if nicknames.is_empty() {
        return Err("Usage: wizlaunch launch <nick> [nicks...] [--path <path>] [--server <host:port>]".into());
    }

    let game_path = game_path.unwrap_or_else(|| detect_game_path());

    let mut known: HashSet<isize> = launcher::get_wizard_handles().into_iter().collect();

    for nickname in &nicknames {
        println!("Launching '{nickname}'...");
        launcher::launch_game(&game_path, &login_server)?;

        match launcher::wait_for_new_handle(&known, timeout_secs) {
            Ok(handle) => {
                known.insert(handle);
                launcher::enable_window(handle, false);
                std::thread::sleep(std::time::Duration::from_secs(2));

                let (username, password) = credential_store::read_credential(nickname)?;
                login::login_to_instance(handle, &username, &password)?;

                launcher::enable_window(handle, true);
                println!("  Logged in '{nickname}' (handle {handle}).");
            }
            Err(e) => {
                eprintln!("  Failed to detect window for '{nickname}': {e}");
            }
        }
    }

    Ok(())
}

fn detect_game_path() -> String {
    let steam = r"C:\Program Files (x86)\Steam\steamapps\common\Wizard101";
    let default = r"C:\ProgramData\KingsIsle Entertainment\Wizard101";
    if std::path::Path::new(steam).is_dir() {
        steam.to_string()
    } else {
        default.to_string()
    }
}
