# the client's type dump from wiztype, cached per client version in %APPDATA%/Deimos/types/<version>.json.
# entity collision and the quest data reader use it to read game files with katsuba

import os
from pathlib import Path
from typing import Optional

from loguru import logger


def client_version(revision: str) -> str:
    """The client-version component of a revision string, e.g.
    ``r803238.Wizard_1_610`` -> ``Wizard_1_610``.

    The property/type tree is compiled into the client executable and only changes on a
    client-version bump — every ``r80xxxx.Wizard_1_610`` *build* (a content patch) shares one
    tree. So this, not the build number, is the correct key for the type-list cache: it lets one
    dump serve every build of a version instead of forcing a fresh (and, when wiztype's signature
    is stale for the new build, hanging) re-pull on each content patch. Falls back to the whole
    string if there's no ``build.version`` split."""
    return revision.split(".", 1)[1] if "." in revision else revision


def typelist_cache_path(key: str) -> Path:
    # where the type dump for a client version (like Wizard_1_610) is stored, next to the Deimos settings
    appdata = os.environ.get("APPDATA", "")
    base = Path(appdata) / "Deimos" if appdata else Path(os.getcwd())
    return base / "types" / (key.replace(".", "_") + ".json")


def typelist_is_loadable(path: Path) -> bool:
    """Cheap validity probe: the cached dump exists, is non-empty, and katsuba can
    open it. Catches a corrupt/half-written cache so we re-dump instead of choking."""
    try:
        from katsuba.op import TypeList

        return path.exists() and path.stat().st_size > 0 and bool(TypeList.open(str(path)))
    except Exception:
        return False


def dump_type_list(revision: str, path: Path) -> None:
    """Pull a fresh type dump from the running client and write it to ``path`` (atomic).

    Requires a live WizardGraphicalClient. Raises with an actionable message when
    wiztype can't read the client's type tree — that means the client was patched
    and wiztype's memory signature is stale, which a re-dump cannot fix.
    """
    import wiztype

    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        f"[typedump] pulling a fresh type dump for revision {revision} "
        f"from the running client via wiztype (one-time, ~10-30s)"
    )
    try:
        tree = wiztype.get_type_tree()
    except Exception as e:
        raise RuntimeError(
            f"wiztype could not read the client's type tree "
            f"({type(e).__name__}: {e}); the client was likely patched and wiztype's "
            f"memory signature is stale — upgrade wiztype "
            f"(`uv lock --upgrade-package wiztype && uv sync`)"
        ) from e
    tmp = path.with_suffix(".tmp")
    wiztype.JsonTypeDumperV1(tree).dump(tmp, indent=None)
    tmp.replace(path)
    logger.info(
        f"[typedump] type list cached at {path} "
        f"({path.stat().st_size // (1024 * 1024)} MB)"
    )


def cached_type_lists(version: Optional[str]) -> list[Path]:
    # cached dumps, newest first. only the ones for that client version if one is given
    d = typelist_cache_path(version or "_").parent
    try:
        files = [
            p
            for p in d.glob("*.json")
            if (version is None or p.stem == version or p.stem.endswith("_" + version))
            and typelist_is_loadable(p)
        ]
    except Exception:
        return []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def read_revision() -> Optional[str]:
    # revision string of the installed client from Bin/revision.dat, or None
    try:
        from wizwalker.utils import get_wiz_install

        return (Path(get_wiz_install()) / "Bin" / "revision.dat").read_text().strip()
    except Exception:
        return None


def ensure_type_dump(allow_live_dump: bool = True) -> Optional[Path]:
    # path to a type dump for the installed client: a cached one, else a new one from the running client, else None
    revision = read_revision()
    if revision is None:
        return None
    version = client_version(revision)
    cached = cached_type_lists(version)
    if cached:
        return cached[0]
    if not allow_live_dump:
        return None
    path = typelist_cache_path(version)
    try:
        dump_type_list(revision, path)
    except Exception as e:
        logger.warning(f"[typedump] live type dump failed: {e}")
        return None
    return path if typelist_is_loadable(path) else None
