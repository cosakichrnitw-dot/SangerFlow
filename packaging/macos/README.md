# SangerFlow Studio macOS packaging

This directory contains the PyInstaller recipe for a local SangerFlow Studio
v1.0 macOS application. It packages the PySide6 Studio application only; the
legacy Tkinter GUI is explicitly excluded.

## Build environment

Use a packaging-only virtual environment outside the repository. Do not reuse
or modify the normal Studio development environment merely to build an app.

```bash
python3.12 -m venv "$HOME/.venvs/sangerflow-studio-package"
source "$HOME/.venvs/sangerflow-studio-package/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e . pyinstaller
python -m PyInstaller --noconfirm packaging/macos/SangerFlow-Studio.spec
```

From the repository root, build the bundle:

```bash
python -m PyInstaller --noconfirm packaging/macos/SangerFlow-Studio.spec
```

The result is `dist/SangerFlow Studio.app`.

## Included assets

- Python runtime and required Python packages
- PySide6, Qt frameworks, and Qt platform plugins
- `config/qc_threshold.json`
- `SangerFlow-Studio/resources/icons/`
- `Contents/Resources/Legal/`, containing the SangerFlow license, third-party
  notice inventory, installed-package metadata/license files, and the GNU
  GPLv3/LGPLv3 texts used for the Qt/PySide6 community distribution

Scientific source data, AB1 files, Excel files, projects, local settings,
credentials, and other user data are not included.

## MAFFT

MAFFT remains an optional external executable. In the packaged app it is
discovered through the existing Tool Settings path or the environment PATH;
it is not copied into the bundle.

For Finder launches, the bundled entry point also checks the customary macOS
install locations `/opt/homebrew/bin` and `/usr/local/bin`. A path selected in
Tool Settings remains the most explicit and portable option.

## Local verification

After building, check the application version and launch it directly:

```bash
plutil -p "dist/SangerFlow Studio.app/Contents/Info.plist"
"dist/SangerFlow Studio.app/Contents/MacOS/SangerFlow Studio"
```

Verify that the version is `1.0.0`, Studio reaches its main window, and icons
load. For a reproducible delivery artifact, archive the completed app and
record a SHA-256 checksum, for example:

```bash
ditto -c -k --sequesterRsrc --keepParent "dist/SangerFlow Studio.app" "SangerFlow-Studio-1.0.0-macos.zip"
shasum -a 256 "SangerFlow-Studio-1.0.0-macos.zip"
```

## Signing and notarization

Signing, notarization, and public release-asset upload are separate release
steps. Do not claim that a local bundle is signed or notarized unless those
steps have been performed and recorded.
