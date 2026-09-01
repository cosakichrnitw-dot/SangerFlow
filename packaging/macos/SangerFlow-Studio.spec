# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the local SangerFlow Studio macOS v1.0 bundle."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

REPOSITORY_ROOT = Path(SPECPATH).resolve().parents[1]
STUDIO_ROOT = REPOSITORY_ROOT / "SangerFlow-Studio"
HOOKS_ROOT = REPOSITORY_ROOT / "packaging" / "macos" / "hooks"

datas = [
    (str(REPOSITORY_ROOT / "config"), "config"),
    (str(STUDIO_ROOT / "resources"), "SangerFlow-Studio/resources"),
]

hiddenimports = [
    *collect_submodules("widgets"),
    "certifi",
    "openpyxl",
    "openpyxl.cell._writer",
    "openpyxl.worksheet._writer",
]

a = Analysis(
    [str(STUDIO_ROOT / "studio_entry.py")],
    pathex=[str(REPOSITORY_ROOT), str(STUDIO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(HOOKS_ROOT)],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "gui"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SangerFlow Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    a.binaries,
    a.datas,
    name="SangerFlow Studio.app",
    icon=None,
    bundle_identifier="org.sangerflow.studio",
    info_plist={
        "CFBundleDisplayName": "SangerFlow Studio",
        "CFBundleName": "SangerFlow Studio",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
    },
)
