# SangerFlow Studio macOS Beta bundle

This directory contains the PyInstaller recipe for the local macOS Beta
bundle. It packages only the PySide6 Studio application; the legacy Tkinter
GUI is explicitly excluded.

## Build

Keep the packaging environment separate from the development environment.
From the repository root, create (once) and activate a packaging-only virtual
environment outside the working tree:

```bash
python3.12 -m venv "$HOME/.venvs/sangerflow-studio-package"
source "$HOME/.venvs/sangerflow-studio-package/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e . pyinstaller
python -m PyInstaller --noconfirm packaging/macos/SangerFlow-Studio.spec
```

The normal Studio development environment remains `.venv` at the repository
root (which may itself be a link to a developer-managed environment outside
the working tree). Do not install PyInstaller into that environment merely to
produce a bundle.

The result is `dist/SangerFlow Studio.app`.

## Included assets

- Python runtime and required Python packages
- PySide6, Qt frameworks, and Qt platform plugins
- `config/qc_threshold.json`
- `SangerFlow-Studio/resources/icons/*.svg`

Scientific source data, AB1 files, Excel files, projects, and other user data
are not included.

## MAFFT

MAFFT remains an optional external executable. In the packaged app it is
discovered through the existing Tool Settings path or the environment PATH;
it is not copied into the bundle.

For Finder launches, the bundled entry point also checks the customary macOS
install locations `/opt/homebrew/bin` and `/usr/local/bin`. A path selected in
Tool Settings remains the most explicit and portable option.

## Local Beta distribution

The app is not signed or notarized in this phase. Other Macs may show the
standard Gatekeeper warning. A signed/notarized release is a separate task.
