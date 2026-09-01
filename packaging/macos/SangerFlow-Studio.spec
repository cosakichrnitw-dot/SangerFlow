# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the local SangerFlow Studio macOS v1.0 bundle."""

from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules

REPOSITORY_ROOT = Path(SPECPATH).resolve().parents[1]
STUDIO_ROOT = REPOSITORY_ROOT / "SangerFlow-Studio"
HOOKS_ROOT = REPOSITORY_ROOT / "packaging" / "macos" / "hooks"
LEGAL_ROOT = REPOSITORY_ROOT / "packaging" / "macos" / "legal"


def _distribution_notice_files(distribution_name: str) -> list[tuple[str, str]]:
    """Collect installed metadata and license files for a shipped package."""
    try:
        installed = distribution(distribution_name)
    except PackageNotFoundError:
        return []

    files: list[tuple[str, str]] = []
    destination = f"Legal/third-party/{distribution_name}"
    for relative_path in installed.files or ():
        name = relative_path.name.lower()
        if name == "metadata" or "license" in name or "copying" in name or "notice" in name:
            source = Path(installed.locate_file(relative_path))
            if source.is_file():
                files.append((str(source), destination))
    return files

datas = [
    (str(REPOSITORY_ROOT / "config"), "config"),
    (str(STUDIO_ROOT / "resources"), "SangerFlow-Studio/resources"),
    (str(REPOSITORY_ROOT / "LICENSE"), "Legal"),
    (str(REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md"), "Legal"),
    (str(REPOSITORY_ROOT / "PROJECT_ASSETS_NOTICE.md"), "Legal"),
    (str(LEGAL_ROOT / "GPL-3.0.txt"), "Legal/Qt"),
    (str(LEGAL_ROOT / "LGPL-3.0.txt"), "Legal/Qt"),
]

python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    datas.append((str(python_license), "Legal/Python"))

for package_name in (
    "PySide6",
    "PySide6_Essentials",
    "PySide6_Addons",
    "shiboken6",
    "biopython",
    "numpy",
    "openpyxl",
    "et_xmlfile",
    "certifi",
    "pyqtgraph",
    "colorama",
    "pyinstaller",
):
    datas.extend(_distribution_notice_files(package_name))

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
