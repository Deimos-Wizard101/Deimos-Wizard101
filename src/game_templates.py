# object templates and lang text from Root.wad, for quest targets.
# TemplateManifest.xml maps template ids to files, Locale/<locale>/<file>.lang has the text for lang keys.
# loaded the first time it's needed, if anything is missing (katsuba, type dump, game files) we just get nothing

import os
import threading
from pathlib import Path

from loguru import logger

_LOCK = threading.Lock()
_STATE: dict = {}  # filled in once loaded, "failed" if it couldn't load
_LANG: dict[str, dict[str, str]] = {}  # lang file -> key -> text


def _load() -> bool:
    with _LOCK:
        if "failed" in _STATE:
            return False
        if "others" in _STATE:
            return True
        try:
            from katsuba.op import STATEFUL_FLAGS, Serializer, SerializerOptions, TypeList
            from katsuba.wad import Archive
            from wizwalker.utils import get_wiz_install

            from src.typedump import ensure_type_dump

            types = ensure_type_dump(allow_live_dump=False)
            if types is None:
                raise RuntimeError("no type dump")
            type_list = TypeList.open(str(types))
            root = Archive.mmap(str(Path(get_wiz_install()) / "Data" / "GameData" / "Root.wad"))
            plain = SerializerOptions()
            plain.shallow = False
            plain.skip_unknown_types = True
            manifest = root.deserialize("TemplateManifest.xml", Serializer(plain, type_list))
            others = {}
            for loc in manifest["m_serializedTemplates"]:
                name = loc["m_filename"]
                name = name.decode("utf-8", "replace") if isinstance(name, bytes) else str(name)
                if not name.startswith("Spells/"):
                    others[int(loc["m_id"])] = name
            stateful = SerializerOptions()
            stateful.shallow = False
            stateful.skip_unknown_types = True
            stateful.flags |= STATEFUL_FLAGS
            _STATE.update(root=root, serializer=Serializer(stateful, type_list), type_list=type_list, others=others)
            logger.debug(f"[quest] template index: {len(others)} object templates")
            return True
        except Exception as e:
            _STATE["failed"] = True
            logger.debug(f"[quest] object templates unavailable: {e}")
            return False


def preload():
    # builds the template index, takes a few seconds so run it off the event loop
    _load()


def object_name(template_id: int) -> str:
    # template file name of an object (like "DS_StoneRose"), empty if unknown
    if not template_id or not _load():
        return ""
    others = _STATE["others"]
    path = others.get(template_id) or others.get(template_id & 0xFFFFFFFF)
    return os.path.splitext(path.rsplit("/", 1)[-1])[0] if path else ""


def lang_text(key: str, locale: str = "en-US") -> str:
    # text for a lang key like "WizardMobs_00001697" (WizardMobs.lang, entry 00001697), empty if unknown.
    # the file is a header line then key / comment / text lines
    if not key or "_" not in key or not _load():
        return ""
    file, _, entry = key.rpartition("_")
    table = _LANG.get(file)
    if table is None:
        table = {}
        try:
            raw = bytes(_STATE["root"][f"Locale/{locale}/{file}.lang"])
            lines = raw.decode("utf-16").split("\r\n")
            table = dict(zip(lines[1::3], lines[3::3]))
        except Exception as e:
            logger.debug(f"[quest] lang file {file} unavailable: {e}")
        _LANG[file] = table
    return table.get(entry, "")


def _deserialize(path: str):
    # a template from Root.wad, or from a zone wad for "|Khrysalis|WorldData|..." paths
    if path.startswith("|"):
        _, world, folder, inner = path.split("|", 3)
        archives = _STATE.setdefault("archives", {})
        name = f"{world}-{folder}.wad"
        if name not in archives:
            from katsuba.wad import Archive
            from wizwalker.utils import get_wiz_install

            archives[name] = Archive.mmap(str(Path(get_wiz_install()) / "Data" / "GameData" / name))
        return archives[name].deserialize(inner, _STATE["serializer"])
    return _STATE["root"].deserialize(path, _STATE["serializer"])


def _text(value) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value or "")


def _class_name(obj) -> str:
    try:
        return _text(_STATE["type_list"].name_for(obj.type_hash)).replace("class ", "")
    except Exception:
        return ""
