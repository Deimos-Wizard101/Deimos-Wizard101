"""Splits Combat editor text into per-client sections. Stdlib only, so it can be imported without game hooks."""
import re
from typing import Dict, List, Tuple


def scan_combat_configs(input_data: str, fallback_clients: int = 1, line_seperator: str = "\n") -> Tuple[Dict[int, str], Dict[int, int], bool]:
    '''
    Splits raw file content into per-client combat configs. This is the scan behind
    delegate_combat_configs; it also reports where each config starts.

    Returns (configs, first_lines, explicit): configs maps client index to its text,
    first_lines maps client index to the 1-based line its text starts on, and explicit
    is False when no ###pX header was found and the whole file goes to every client.
    '''

    config_lines = input_data.split(line_seperator)
    client_configs: Dict[int, str] = {}
    first_lines: Dict[int, int] = {}

    #Match number in "###pX", where X is a number. This determines the client index. This also strips all whitespace.
    pattern = re.compile(r'###\s*p\s*(\d+)')
    client_to_match = -1
    local_configs: List[str] = []
    local_first_line = 1

    for i, line in enumerate(config_lines):
        client_match = re.search(pattern, line)
        if client_match is not None:
            if client_to_match != -1:
                client_configs[client_to_match] = line_seperator.join(local_configs)
                first_lines[client_to_match] = local_first_line
            client_to_match = int(client_match.group(1)) - 1
            local_first_line = i + 2
            local_configs.clear()
            continue

        local_configs.append(line)

    #If no client was ever specified, just assign entire config to all clients
    if client_to_match == -1:
        for i in range(fallback_clients):
            client_configs[i] = line_seperator.join(config_lines)
            first_lines[i] = 1

    else:
        client_configs[client_to_match] = line_seperator.join(local_configs)
        first_lines[client_to_match] = local_first_line

    return client_configs, first_lines, client_to_match != -1
