import json
import os
import shutil
from pathlib import Path


DEFAULT_THEME = {
    "bg_color": "#1e1e1e",
    "alt_bg": "#2d2d2d",
    "text_color": "#ffffff",
    "button_color": "#4a019e",
    "stroke_color": "#e0e0e0",
    "titlebar_bg": "#1e1e1e",
}

DEFAULT_SETTINGS = {
    # [settings]
    "speed_multiplier": 5.0,
    "use_potions": True,
    "rich_presence": True,
    "drop_logging": True,
    "use_anti_afk": True,
    "buy_potions": True,
    # [gui]
    "on_top": True,
    "locale": "en",
    "font": "Segoe UI",
    "font_size": 9,
    # [sigil]
    "use_team_up": False,
    "client_to_follow": None,
    # [questing]
    "client_to_boost": None,
    "friend_teleport": False,
    "gear_switching_in_solo_zones": False,
    "hitter_client": None,
    # [auto pet]
    "ignore_pet_level_up": False,
    "only_play_dance_game": False,
    # [combat]
    "kill_minions_first": False,
    "automatic_team_based_combat": False,
    "discard_duplicate_cards": True,
    # [launcher]
    "remember_chosen_clients": False,
}

RESTART_REQUIRED_KEYS = {"locale"}

# Maps ini section+key -> DEFAULT_SETTINGS key with type coercion
_INI_SETTINGS_MAP = {
    ("settings", "speed_multiplier"): ("speed_multiplier", float),
    ("settings", "use_potions"): ("use_potions", bool),
    ("settings", "rich_presence"): ("rich_presence", bool),
    ("settings", "drop_logging"): ("drop_logging", bool),
    ("settings", "use_anti_afk"): ("use_anti_afk", bool),
    ("settings", "buy_potions"): ("buy_potions", bool),
    ("gui", "on_top"): ("on_top", bool),
    ("gui", "theme"): ("theme", str),
    ("gui", "text_color"): ("text_color", str),
    ("gui", "button_color"): ("button_color", str),
    ("gui", "locale"): ("locale", str),
    ("gui", "font"): ("font", str),
    ("gui", "font_size"): ("font_size", int),
    ("sigil", "use_team_up"): ("use_team_up", bool),
    ("sigil", "client_to_follow"): ("client_to_follow", str),
    ("questing", "client_to_boost"): ("client_to_boost", str),
    ("questing", "friend_teleport"): ("friend_teleport", bool),
    ("questing", "gear_switching_in_solo_zones"): ("gear_switching_in_solo_zones", bool),
    ("questing", "hitter_client"): ("hitter_client", str),
    ("auto pet", "ignore_pet_level_up"): ("ignore_pet_level_up", bool),
    ("auto pet", "only_play_dance_game"): ("only_play_dance_game", bool),
    ("combat", "kill_minions_first"): ("kill_minions_first", bool),
    ("combat", "automatic_team_based_combat"): ("automatic_team_based_combat", bool),
    ("combat", "discard_duplicate_cards"): ("discard_duplicate_cards", bool),
}


DEFAULT_HOTKEYS = {
    "toggle_speed": {"key": "F5", "modifiers": []},
    "toggle_combat": {"key": "NINE", "modifiers": []},
    "toggle_dialogue": {"key": "F4", "modifiers": []},
    "toggle_dialogue_side_quests": {"key": "F4", "modifiers": ["SHIFT"]},
    "toggle_sigil": {"key": "F2", "modifiers": []},
    "toggle_questing": {"key": "F3", "modifiers": []},
    "toggle_freecam": {"key": "F1", "modifiers": []},
    "freecam_tp": {"key": "F1", "modifiers": ["SHIFT"]},
    "quest_tp": {"key": "F7", "modifiers": []},
    "mass_tp": {"key": "F6", "modifiers": []},
    "xyz_sync": {"key": "F8", "modifiers": []},
    "x_press": {"key": "X", "modifiers": []},
    "friend_tp": {"key": "EIGHT", "modifiers": []},
    "kill_tool": {"key": "F9", "modifiers": []},
    "toggle_auto_pet": None,
    "toggle_auto_potion": None,
}

# Maps ini key names -> action_id
_INI_KEY_MAP = {
    "toggle_speed_multiplier": "toggle_speed",
    "toggle_auto_combat": "toggle_combat",
    "toggle_auto_dialogue": "toggle_dialogue",
    "toggle_auto_sigil": "toggle_sigil",
    "toggle_auto_questing": "toggle_questing",
    "toggle_freecam": "toggle_freecam",
    "quest_teleport": "quest_tp",
    "mass_quest_teleport": "mass_tp",
    "sync_client_locations": "xyz_sync",
    "x_press": "x_press",
    "friend_teleport": "friend_tp",
    "kill_tool": "kill_tool",
}


def _theme_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Deimos" / "default_theme.json"


class DeimosSettings:
    def __init__(self, settings_path: str | None = None):
        if settings_path is None:
            appdata = os.environ.get("APPDATA", "")
            settings_dir = Path(appdata) / "Deimos"
            settings_dir.mkdir(parents=True, exist_ok=True)
            self._path = settings_dir / "settings.json"
        else:
            self._path = Path(settings_path)

        self._data: dict = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}
        if "hotkeys" not in self._data:
            self._data["hotkeys"] = dict(DEFAULT_HOTKEYS)
            self._save()

    def _save(self):
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get_hotkeys(self) -> dict:
        return dict(self._data.get("hotkeys", DEFAULT_HOTKEYS))

    def set_hotkey(self, action_id: str, key: str, modifiers: list[str]):
        self._data.setdefault("hotkeys", {})[action_id] = {
            "key": key,
            "modifiers": modifiers,
        }
        self._save()

    def clear_hotkey(self, action_id: str):
        self._data.setdefault("hotkeys", {})[action_id] = None
        self._save()

    def reset_hotkeys(self):
        self._data["hotkeys"] = dict(DEFAULT_HOTKEYS)
        self._save()

    def get_settings(self) -> dict:
        defaults = dict(DEFAULT_SETTINGS)
        defaults.update(self._data.get("settings", {}))
        return defaults

    def get_setting(self, key):
        return self._data.get("settings", {}).get(key, DEFAULT_SETTINGS.get(key))

    def set_setting(self, key, value):
        self._data.setdefault("settings", {})[key] = value
        self._save()

    def set_settings(self, settings_dict: dict):
        s = self._data.setdefault("settings", {})
        s.update(settings_dict)
        self._save()

    def get_recent_imports(self, category: str) -> list:
        return list(self._data.get("recent_imports", {}).get(category, []))

    def add_recent_import(self, category: str, filepath: str, max_recent: int = 10):
        ri = self._data.setdefault("recent_imports", {})
        recent = ri.setdefault(category, [])
        if filepath in recent:
            recent.remove(filepath)
        recent.insert(0, filepath)
        del recent[max_recent:]
        self._save()

    def get_theme(self) -> dict:
        tp = _theme_path()
        theme = dict(DEFAULT_THEME)
        if tp.exists():
            try:
                data = json.loads(tp.read_text(encoding="utf-8"))
                theme.update(data)
            except (json.JSONDecodeError, OSError):
                pass
        else:
            tp.parent.mkdir(parents=True, exist_ok=True)
            tp.write_text(json.dumps(theme, indent=2), encoding="utf-8")
        return theme

    def set_theme(self, theme_dict: dict):
        tp = _theme_path()
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(json.dumps(theme_dict, indent=2), encoding="utf-8")

    def export_theme(self, filepath: str):
        shutil.copy2(str(_theme_path()), filepath)

    def import_theme(self, filepath: str) -> dict:
        theme = dict(DEFAULT_THEME)
        try:
            data = json.loads(Path(filepath).read_text(encoding="utf-8"))
            theme.update(data)
        except (json.JSONDecodeError, OSError):
            pass
        self.set_theme(theme)
        return theme

    def migrate_theme_from_settings(self):
        """One-time migration: derive theme file from old settings keys."""
        tp = _theme_path()
        if tp.exists():
            return
        s = self._data.get("settings", {})
        old_theme = s.get("theme")
        old_text = s.get("text_color")
        old_btn = s.get("button_color")
        if old_theme is None and old_text is None and old_btn is None:
            return
        t = old_theme.lower() if isinstance(old_theme, str) else "black"
        if t in ("black", "dark"):
            bg = "#1e1e1e"
            alt = "#2d2d2d"
        else:
            bg = "#f0f0f0"
            alt = "#ffffff"
        tc = old_text if isinstance(old_text, str) else "#ffffff"
        bc = old_btn if isinstance(old_btn, str) else "#4a019e"
        sc = tc if tc else ("#e0e0e0" if t in ("black", "dark") else "#333333")
        theme = {
            "bg_color": bg,
            "alt_bg": alt,
            "text_color": tc,
            "button_color": bc,
            "stroke_color": sc,
            "titlebar_bg": bg,
        }
        self.set_theme(theme)
        for k in ("theme", "text_color", "button_color"):
            s.pop(k, None)
        self._save()

    def migrate_settings_from_ini(self, parser):
        """One-time migration of all ini sections into settings.json."""
        if self._data.get("_settings_migrated"):
            return

        migrated = dict(DEFAULT_SETTINGS)
        for (section, ini_key), (settings_key, typ) in _INI_SETTINGS_MAP.items():
            raw = parser.get(section, ini_key, fallback=None)
            if raw is None:
                continue
            if typ is bool:
                migrated[settings_key] = raw.lower() in ("true", "yes", "1", "on")
            elif typ is float:
                try:
                    migrated[settings_key] = float(raw)
                except ValueError:
                    pass
            elif typ is int:
                try:
                    migrated[settings_key] = int(raw)
                except ValueError:
                    pass
            else:
                val = raw.strip()
                migrated[settings_key] = val if val else None

        # Normalize empty strings to None for client fields
        for k in ("client_to_follow", "client_to_boost", "hitter_client"):
            if migrated.get(k) is not None and not migrated[k].strip():
                migrated[k] = None

        self._data["settings"] = migrated
        self._data["_settings_migrated"] = True
        self._save()

    def migrate_from_ini(self, parser):
        """One-time migration from ini [hotkeys] section if settings.json didn't already exist."""
        if self._path.exists() and self._data.get("_migrated"):
            return

        if not parser.has_section("hotkeys"):
            self._data["_migrated"] = True
            self._save()
            return

        hotkeys = dict(DEFAULT_HOTKEYS)
        for ini_key, action_id in _INI_KEY_MAP.items():
            value = parser.get("hotkeys", ini_key, fallback=None)
            if value is not None:
                # The ini stores just the key name (no modifier info)
                # Special case: dialogue also has shift variant
                if action_id == "toggle_dialogue":
                    hotkeys["toggle_dialogue"] = {"key": value, "modifiers": []}
                    hotkeys["toggle_dialogue_side_quests"] = {"key": value, "modifiers": ["SHIFT"]}
                elif action_id == "toggle_freecam":
                    hotkeys["toggle_freecam"] = {"key": value, "modifiers": []}
                    hotkeys["freecam_tp"] = {"key": value, "modifiers": ["SHIFT"]}
                else:
                    hotkeys[action_id] = {"key": value, "modifiers": []}

        self._data["hotkeys"] = hotkeys
        self._data["_migrated"] = True
        self._save()
