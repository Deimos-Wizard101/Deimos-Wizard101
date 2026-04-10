# PyInstaller runtime hook: extend wizwalker.extensions.__path__ so that
# wizsprinter's namespace extension (bundled as data files) is discoverable.
import os
import sys

if hasattr(sys, "_MEIPASS"):
    import wizwalker.extensions

    _ws_ext = os.path.join(sys._MEIPASS, "_wizsprinter_lib", "wizwalker", "extensions")
    if os.path.isdir(_ws_ext) and _ws_ext not in wizwalker.extensions.__path__:
        wizwalker.extensions.__path__.append(_ws_ext)
