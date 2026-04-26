import os
import sys


def _resource_path(filename: str) -> str:
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return filename


def load_lang(langcode: str) -> callable:
    strings = {}
    path = _resource_path(os.path.join('locale', f'{langcode}.lang'))
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                key, _, value = line.partition('=')
                if _:
                    strings[key.strip()] = value.strip().replace('\\n', '\n')
    except FileNotFoundError:
        pass

    def tl(key: str) -> str:
        return strings.get(key, key)

    return tl
