"""Fetching and filtering for the approved bot registry repo (Deimos-Wizard101/bots).

All functions here are synchronous (requests-based) and meant to be called via
asyncio.to_thread from the backend so the GUI never blocks on network I/O.
"""

import re
from urllib.parse import quote, urlencode

import requests

registry_repo: str = 'Deimos-Wizard101/bots'
registry_branch: str = 'main'
registry_raw_base: str = f'https://raw.githubusercontent.com/{registry_repo}/{registry_branch}'

# Routing marker the bot runner uses to dispatch expertmode bots (see Deimos.py
# ExecuteBot). It must be the very first line of an expertmode bot's text.
expertmode_marker: str = '###deimos_expertmode'

# Conservative cap on a GitHub "new file" prefill URL. Past this, browsers/servers
# may reject the request, so the caller should fall back to a clipboard paste.
publish_url_max_length: int = 8000

_request_timeout: float = 10.0
_clients_constraint_pattern = re.compile(r'^(==|!=|>=|<=|>|<)\s*(\d+)$')
_clients_constraint_ops = {
    '==': lambda count, value: count == value,
    '!=': lambda count, value: count != value,
    '>=': lambda count, value: count >= value,
    '<=': lambda count, value: count <= value,
    '>': lambda count, value: count > value,
    '<': lambda count, value: count < value,
}


def clients_compatible(constraint, client_count: int) -> bool:
    """Evaluate an optional `@clients` constraint (e.g. '== 4', '>= 1') against the
    current client count. Missing or malformed constraints count as compatible."""
    if not constraint or not isinstance(constraint, str):
        return True
    match = _clients_constraint_pattern.match(constraint.strip())
    if not match:
        return True
    op, value = match.group(1), int(match.group(2))
    return _clients_constraint_ops[op](client_count, value)


def _get_registry_json(url: str):
    """GET a registry JSON file. A zone with no bots has no registry.json, so 404 returns None."""
    resp = requests.get(url, timeout=_request_timeout)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _zone_registry_url(zone: str) -> str:
    return f'{registry_raw_base}/bots/{quote(zone, safe="/")}/registry.json'


def _is_general(bot: dict) -> bool:
    return str(bot.get('world') or bot.get('zone') or '').split('/')[0] == 'General'


def search_compatible_bots(zone: str, client_count) -> list[dict]:
    """Return bots for the given zone plus all General bots, filtered by client count.

    Zone bots sort before General ones and entries are deduped by path. General
    entries come from each General zone's registry.json (rich, with descriptions),
    falling back to the slim index.json entries if a per-zone fetch fails.

    Pass ``client_count=None`` to skip the ``@clients`` filter entirely and return
    every compatible bot regardless of team size.
    """
    candidates = []
    zone_data = _get_registry_json(_zone_registry_url(zone)) if zone else None
    if zone_data:
        candidates.extend(zone_data.get('bots', []))

    index = _get_registry_json(f'{registry_raw_base}/index.json') or {}
    general_zones = sorted(z for z in index.get('zones', {}) if str(z).split('/')[0] == 'General')
    for general_zone in general_zones:
        if general_zone == zone:
            continue
        try:
            general_data = _get_registry_json(_zone_registry_url(general_zone))
        except requests.RequestException:
            general_data = None
        if general_data:
            candidates.extend(general_data.get('bots', []))
        else:
            candidates.extend(b for b in index.get('bots', []) if b.get('zone') == general_zone)

    seen_paths = set()
    results = []
    for bot in candidates:
        path = bot.get('path')
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        if client_count is not None and not clients_compatible(bot.get('clients'), client_count):
            continue
        bot = dict(bot)
        bot['is_general'] = _is_general(bot)
        results.append(bot)
    results.sort(key=lambda b: b['is_general'])
    return results


def fetch_bot_text(path: str) -> str:
    """Download a bot's .txt content given its repo-relative path from the registry."""
    resp = requests.get(f'{registry_raw_base}/{quote(path, safe="/")}', timeout=_request_timeout)
    resp.raise_for_status()
    # raw.githubusercontent serves UTF-8 but often without a charset header, which
    # makes requests fall back to ISO-8859-1 and mangle non-ASCII text.
    resp.encoding = 'utf-8'
    return resp.text


# Metadata header fields, in the order they are emitted into a published bot.
metadata_field_order = ('name', 'zone', 'author', 'format', 'clients', 'description')
_metadata_line_pattern = re.compile(r'^#\s*@(\w+)\s*:\s*(.*)$')


def is_valid_clients_constraint(constraint: str) -> bool:
    """True if `constraint` is empty (= no constraint) or a well-formed comparison."""
    constraint = (constraint or '').strip()
    return not constraint or bool(_clients_constraint_pattern.match(constraint))


def infer_bot_format(text: str) -> str:
    """Return 'expertmode' if the text leads with the expertmode marker, else 'bot'."""
    return 'expertmode' if text.lstrip().startswith(expertmode_marker) else 'bot'


def split_bot_metadata(text: str) -> tuple[dict, str]:
    """Separate a bot's leading metadata header from its executable body.

    Parses the contiguous block of `# @field: value` comment lines at the top
    (including the expertmode marker and multi-line `@description` continuations),
    stopping at the first blank line or non-comment line. Returns (metadata, body).
    """
    lines = text.splitlines()
    idx = 0
    metadata: dict = {}

    if idx < len(lines) and lines[idx].strip().startswith(expertmode_marker):
        metadata['format'] = 'expertmode'
        idx += 1

    description_lines: list[str] = []
    in_description = False
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped.startswith('#'):
            break  # blank line or body statement ends the header
        match = _metadata_line_pattern.match(stripped)
        if match:
            field, value = match.group(1).lower(), match.group(2).strip()
            if field == 'description':
                in_description = True
                description_lines = [value]
            else:
                in_description = False
                metadata[field] = value
        elif in_description:
            description_lines.append(stripped.lstrip('#').strip())
        else:
            break  # a plain comment that isn't part of the header — body begins
        idx += 1

    if description_lines:
        metadata['description'] = '\n'.join(description_lines).strip()

    body_lines = lines[idx:]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    return metadata, '\n'.join(body_lines)


def build_bot_text(metadata: dict, body: str) -> str:
    """Assemble full bot text: optional expertmode marker, metadata header, then body.

    `clients` and `description` are omitted when blank; a multi-line description is
    emitted as a `# @description:` line followed by `# ` continuation lines.
    """
    fmt = (metadata.get('format') or 'bot').strip() or 'bot'
    header: list[str] = []
    if fmt == 'expertmode':
        header.append(expertmode_marker)
    header.append(f"# @name: {(metadata.get('name') or '').strip()}")
    header.append(f"# @zone: {(metadata.get('zone') or '').strip()}")
    header.append(f"# @author: {(metadata.get('author') or '').strip()}")
    header.append(f"# @format: {fmt}")
    clients = (metadata.get('clients') or '').strip()
    if clients:
        header.append(f"# @clients: {clients}")
    description = (metadata.get('description') or '').strip()
    if description:
        desc_lines = description.splitlines()
        header.append(f"# @description: {desc_lines[0]}")
        for extra in desc_lines[1:]:
            header.append(f"# {extra}")

    body = body.strip('\n')
    header_text = '\n'.join(header)
    return f"{header_text}\n\n{body}\n" if body else f"{header_text}\n"


def sanitize_bot_filename(name: str) -> str:
    """Turn a bot name into a safe `<Name>.txt` filename for the registry repo."""
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', (name or '').strip()).strip('_.')
    if not base:
        base = 'bot'
    if not base.lower().endswith('.txt'):
        base += '.txt'
    return base


def bot_repo_path(zone: str, name: str) -> str:
    """Repo-relative path a published bot should live at, e.g. bots/<zone>/<Name>.txt."""
    zone = (zone or '').strip().strip('/')
    return f"bots/{zone}/{sanitize_bot_filename(name)}"


def build_publish_url(zone: str, name: str, content: str) -> str:
    """GitHub 'new file' URL that prefills path + content so the user can propose it
    as a pull request (GitHub auto-forks for users without write access)."""
    path = bot_repo_path(zone, name)
    query = urlencode({'filename': path, 'value': content})
    return f"https://github.com/{registry_repo}/new/{registry_branch}?{query}"


def build_publish_fallback_url(zone: str, name: str) -> str:
    """GitHub 'new file' URL with only the path prefilled (no content), for when the
    full prefill URL would be too long — pair with copying the content to clipboard."""
    path = bot_repo_path(zone, name)
    query = urlencode({'filename': path})
    return f"https://github.com/{registry_repo}/new/{registry_branch}?{query}"
