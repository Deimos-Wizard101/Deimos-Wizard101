#!/usr/bin/env bash
# Run Deimos from source under Proton, optionally launching game clients first.
#
#   scripts/linux/run.sh [--clients N] [--server host:port] [--shell]
#
#   --clients N   start N WizardGraphicalClient.exe instances in the prefix
#                 before Deimos (log in manually, or from Deimos' Launcher tab)
#   --server      login server, default login.us.wizard101.com:12000
#   --shell       drop into a shell inside the sandbox instead of starting
#                 Deimos; `proton_run` and `winpath` are available there
#
# Deimos' own log goes to logs/ in the repo as usual; its stdout/stderr
# (tracebacks included) goes to $DEIMOS_LINUX_HOME/logs/deimos-stdout.log.
# Run scripts/linux/setup.sh first.
set -euo pipefail
source "$(dirname "$0")/env.sh"

orig_args=("$@")
clients=0
server="login.us.wizard101.com:12000"
shell=0
while [ $# -gt 0 ]; do
    case "$1" in
        --clients) clients="$2"; shift ;;
        --server) server="$2"; shift ;;
        --shell) shell=1 ;;
        *) sed -n '2,/^$/p' "$0" | cut -c3-; exit 1 ;;
    esac
    shift
done

if [ ! -f "$WIN_PYTHON" ]; then
    echo "no Windows Python at $WIN_PYTHON; run scripts/linux/setup.sh" >&2
    exit 1
fi

enter_sandbox "${orig_args[@]}"
mkdir -p "$LOG_DIR"

if [ "$clients" -gt 0 ]; then
    exe="$GAME_PATH/Bin/WizardGraphicalClient.exe"
    if [ ! -f "$exe" ]; then
        echo "game client not found at $exe; set WIZLAUNCH_GAME_PATH" >&2
        exit 1
    fi
    for ((i = 0; i < clients; i++)); do
        (cd "$GAME_PATH/Bin" && proton_run "$exe" -L "${server%:*}" "${server##*:}" &)
    done
fi

# Command channel for scripts/linux/exec.sh: anything written to the fifo runs
# in this sandbox, so test scripts and extra clients share the wineserver.
fifo="$DEIMOS_LINUX_HOME/sandbox.cmd"
rm -f "$fifo"
mkfifo "$fifo"
export -f proton_run winpath
export WIN_PYTHON REPO LOG_DIR GAME_PATH
(
    while read -r line < "$fifo"; do
        [ -n "$line" ] && bash -c "$line" &
    done
) &
listener=$!
trap 'kill "$listener" 2>/dev/null; rm -f "$fifo"' EXIT

if [ "$shell" = 1 ]; then
    cd "$REPO"
    bash
    exit
fi

cd "$REPO"
export DEIMOS_STDOUT_LOG="$(winpath "$LOG_DIR/deimos-stdout.log")"
"$PROTON" run "${WIN_PYTHON%python.exe}pythonw.exe" -X utf8 "$(winpath scripts/linux/bootstrap.py)"
