#!/usr/bin/env bash
# Manage the Deimos account vault on Linux (add / list / delete).
#
#   scripts/linux/accounts.sh add <nickname>     prompt for username + password
#   scripts/linux/accounts.sh list
#   scripts/linux/accounts.sh delete <nickname>
#
# Accounts live in the Windows Credential Manager that Wine emulates inside the
# Proton prefix (not a Linux keyring). The native "add account" button in the
# Deimos GUI cannot work under Wine -- it opens a Win32 credential dialog Wine
# does not implement -- so add accounts here instead.
#
# These changes are flushed to the prefix on disk, but a RUNNING Deimos loaded
# its copy of the registry when its wineserver started and will not see them
# until it restarts. Add accounts before launching Deimos, or restart it after.
set -euo pipefail
source "$(dirname "$0")/env.sh"

if [ ! -f "$WIN_PYTHON" ]; then
    echo "no Windows Python at $WIN_PYTHON; run scripts/linux/setup.sh" >&2
    exit 1
fi

cmd="${1:-}"
case "$cmd" in
    add|list|delete) ;;
    *) sed -n '2,/^$/p' "$0" | cut -c3-; exit 1 ;;
esac

# The Deimos-running check must see host processes, so do it before the sandbox
# re-exec (bwrap gives the sandbox its own PID namespace).
if [ -z "${DEIMOS_IN_SANDBOX:-}" ] && pgrep -f 'bootstrap\.py' >/dev/null 2>&1; then
    echo "note: Deimos is running; restart it afterwards so it picks up this change." >&2
fi

# Proton's launcher is #!/usr/bin/env python3, absent on NixOS outside the FHS
# environment steam-run provides -- so run the whole thing inside one sandbox.
enter_sandbox "$@"

helper="$(winpath "$REPO/scripts/linux/account_tool.py")"
run_helper() {  # args -> account_tool.py; stdin forwarded; Proton/Wine boot noise dropped
    proton_run "$WIN_PYTHON" -I "$helper" "$@" \
        2> >(grep -v -i -E 'freetype|^or equal|^http|fsync:|esync:|^Proton:' >&2 || true)
}

case "$cmd" in
    add)
        nick="${2:?usage: accounts.sh add <nickname>}"
        read -r -p "Wizard101 username for '$nick': " username
        read -r -s -p "Wizard101 password for '$nick': " password
        echo
        printf '%s\n%s\n' "$username" "$password" | run_helper add "$nick"
        ;;
    list)
        run_helper list
        ;;
    delete)
        nick="${2:?usage: accounts.sh delete <nickname>}"
        run_helper delete "$nick"
        ;;
esac
