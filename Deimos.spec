# -*- mode: python ; coding: utf-8 -*-

import os
import re
import subprocess
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Always rebuild the native helpers so local builds pick up Rust source changes
# (cargo is incremental, so this is cheap when nothing changed). A missing cargo
# is non-fatal — the os.path.exists guards below then omit the helper from the
# bundle. A cargo *failure* is not silently swallowed: without the warning below
# a stale target/release/*.exe from an earlier build gets bundled instead, which
# is how a moved manifest path went unnoticed until CI caught it.
#
#   libs/updater  -> deimos-updater.exe, the self-update helper
#   libs/wizpatch -> wizpatch.exe, the "verify/patch before launch" patcher
#                    (its default features include the `cli` bin target)
for _crate in ("updater", "wizpatch"):
    _manifest = os.path.join("libs", _crate, "Cargo.toml")
    if not os.path.exists(_manifest):
        print(f"WARNING: {_manifest} not found; skipping {_crate} build.")
        continue
    try:
        _r = subprocess.run(
            ["cargo", "build", "--release", "--manifest-path", _manifest],
            check=False,
        )
        if _r.returncode != 0:
            print(f"WARNING: cargo build failed for {_crate} (exit {_r.returncode}); "
                  "any binary bundled below is stale.")
    except FileNotFoundError:
        print(f"WARNING: cargo not found; skipping {_crate} build.")

# wizsprinter installs into the wizwalker.extensions namespace at runtime via a
# sys.path scan in wizwalker/extensions/__init__.py. PyInstaller's static
# analysis can't see that, so collect submodules and data files explicitly.
hiddenimports = (
    collect_submodules('wizwalker')
    + collect_submodules('wizwalker.extensions.wizsprinter')
    + collect_submodules('wizwalker.extensions.wizsprinter.combat_backends')
    + collect_submodules('wizsprinter')
    + collect_submodules('lark')
    + ['wizlaunch']
)

datas = [
    ('Deimos-logo.ico', '.'),
    ('Deimos-logo.png', '.'),
    ('locale', 'locale'),
    # The katsuba TypeList is no longer shipped: it's generated on demand by wiztype
    # from the running client and cached per-revision under %APPDATA%/Deimos/types/.
]
datas += collect_data_files('wizwalker.extensions.wizsprinter')
datas += collect_data_files('wizwalker.extensions.wizsprinter.combat_backends')
# Also collect .py sources as data. The data files above force
# wizwalker/extensions/wizsprinter/ to exist on disk, which would shadow the
# PYZ-archived submodules (Python treats the on-disk dir as a namespace
# package and only searches __path__ for submodules). Putting the .py files
# on disk too keeps imports working.
datas += collect_data_files(
    'wizwalker.extensions.wizsprinter',
    include_py_files=True,
)
datas += collect_data_files(
    'wizwalker.extensions.wizsprinter.combat_backends',
    include_py_files=True,
)

# Embed the native self-update helper (built from libs/updater via `cargo build
# --release`). If it hasn't been built, the bundle still works — Deimos just
# falls back to telling the user to update manually.
_updater_exe = os.path.join('libs', 'updater', 'target', 'release', 'deimos-updater.exe')
if os.path.exists(_updater_exe):
    datas += [(_updater_exe, '.')]
else:
    print(f"WARNING: {_updater_exe} not found; self-updater will be unavailable in this build.")

# Embed the wizpatch game-file patcher (built from libs/wizpatch). If it's
# missing, the bundle still works — the "verify/patch before launch" option
# simply no-ops with a warning.
_wizpatch_exe = os.path.join('libs', 'wizpatch', 'target', 'release', 'wizpatch.exe')
if os.path.exists(_wizpatch_exe):
    datas += [(_wizpatch_exe, '.')]
else:
    print(f"WARNING: {_wizpatch_exe} not found; game-file patching will be unavailable in this build.")


# The Windows version resource is derived from tool_version rather than read
# straight from version_info.txt. The release workflows rewrite tool_version in
# Deimos.py but never touch that file, so it had drifted: 3.14.0 builds shipped
# reporting 3.10.0.0 under Properties -> Details. version_info.txt stays the
# template for everything else (company, description, copyright); only the
# version fields are substituted, into a generated copy, so a build never
# modifies a tracked file.
def _render_version_info():
    template = 'version_info.txt'
    try:
        source = open('Deimos.py', encoding='utf-8').read()
        match = re.search(
            r"^tool_version:\s*str\s*=\s*['\"]([^'\"]+)['\"]", source, re.MULTILINE
        )
        if not match:
            print("WARNING: could not read tool_version from Deimos.py; "
                  f"using {template} unchanged.")
            return template

        version = match.group(1)
        # PE version fields are numeric only, so a pre-release suffix
        # (3.14.0-beta.1) contributes its release core alone.
        core = version.split('-', 1)[0]
        numbers = [int(p) if p.isdigit() else 0 for p in core.split('.')]
        numbers = (numbers + [0, 0, 0, 0])[:4]
        dotted = '.'.join(str(n) for n in numbers)
        tup = '({})'.format(', '.join(str(n) for n in numbers))

        text = open(template, encoding='utf-8').read()
        # Lambda replacements: the substituted text is data, not a regex
        # template, so backslashes and group refs in it stay literal.
        text = re.sub(r'filevers=\([^)]*\)', lambda m: f'filevers={tup}', text)
        text = re.sub(r'prodvers=\([^)]*\)', lambda m: f'prodvers={tup}', text)
        for field in ('FileVersion', 'ProductVersion'):
            text = re.sub(
                r"(StringStruct\(u'" + field + r"',\s*u')[^']*(')",
                lambda m: m.group(1) + dotted + m.group(2),
                text,
            )

        out_dir = os.path.join('build', 'Deimos')
        os.makedirs(out_dir, exist_ok=True)
        rendered = os.path.join(out_dir, 'version_info.generated.txt')
        with open(rendered, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Version resource: tool_version {version} -> {dotted}")
        return rendered
    except OSError as e:
        print(f"WARNING: could not render version resource ({e}); "
              f"using {template} unchanged.")
        return template


_version_file = _render_version_info()

a = Analysis(
    ['Deimos.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Deimos',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='Deimos-logo.ico',
    version=_version_file,
    manifest='app.manifest',
)
