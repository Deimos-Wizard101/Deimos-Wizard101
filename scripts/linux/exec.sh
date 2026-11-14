#!/usr/bin/env bash
# Run a command inside the Wine session started by scripts/linux/run.sh.
#
#   scripts/linux/exec.sh <shell command>
#
# The command runs in the sandbox's bash with env.sh loaded, so `proton_run`,
# `launch_client`, `winpath`, $WIN_PYTHON, $REPO etc. are available. Its output goes wherever
# the command sends it; redirect to a file to read it from the host, e.g.
#
#   scripts/linux/exec.sh 'proton_run "$WIN_PYTHON" "$(winpath test.py)" > "$LOG_DIR/test.out" 2>&1'
set -euo pipefail
source "$(dirname "$0")/env.sh"
fifo="$DEIMOS_LINUX_HOME/sandbox.cmd"
if [ ! -p "$fifo" ]; then
    echo "no live session at $fifo; start scripts/linux/run.sh first" >&2
    exit 1
fi
printf '%s\n' "$*" > "$fifo"
