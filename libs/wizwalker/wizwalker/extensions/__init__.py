import os as _os
import sys as _sys

# Allow wizsprinter (and other extensions) installed as separate packages
# to overlay into this namespace by finding wizwalker/extensions/ dirs
# across all sys.path entries.
_pname = _os.path.join("wizwalker", "extensions")
for _dir in _sys.path:
    _subdir = _os.path.join(_dir, _pname)
    if _os.path.isdir(_subdir) and _subdir not in __path__:
        __path__.append(_subdir)
