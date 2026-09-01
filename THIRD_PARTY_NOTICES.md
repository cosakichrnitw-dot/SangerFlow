# Third-party notices

SangerFlow source code is distributed under the MIT License. The components
listed below remain subject to their own licenses. This document is a concise
release inventory, not a replacement for the full license text or notices
distributed by an upstream project.

| Component | Role in SangerFlow | Distribution role | Upstream license / notice |
|---|---|---|---|
| [Python](https://www.python.org/) | Runtime | Python 3.12.10 is bundled in the macOS application | [PSF License Agreement](https://docs.python.org/3/license.html); the corresponding text is bundled as `Contents/Resources/Legal/Python-PSF-LICENSE.txt` |
| [PySide6 / Qt](https://doc.qt.io/qtforpython-6/) | Studio GUI and Qt runtime | Bundled in a macOS app build | Qt for Python community licensing is available under LGPLv3/GPLv3; see the [Qt licensing page](https://www.qt.io/licensing/open-source-lgpl-obligations). A release bundle must retain the applicable Qt/PySide notices. |
| [Biopython](https://biopython.org/) | Sequence and AB1-related functionality | Python dependency | [Biopython License Agreement](https://biopython.org/DIST/LICENSE) |
| [NumPy](https://numpy.org/) | Numerical processing | Python dependency | [BSD 3-Clause](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| [openpyxl](https://openpyxl.readthedocs.io/) | XLSX import/export | Python dependency | [MIT License](https://foss.heptapod.net/openpyxl/openpyxl/-/blob/branch/3.1/LICENCE.rst) |
| [certifi](https://github.com/certifi/python-certifi) | CA certificate bundle for HTTPS | Python dependency | [MPL-2.0](https://github.com/certifi/python-certifi/blob/master/LICENSE) |
| [pyqtgraph](https://www.pyqtgraph.org/) | Qt plotting support | Python dependency | [MIT License](https://github.com/pyqtgraph/pyqtgraph/blob/master/LICENSE.txt) |
| [colorama](https://github.com/tartley/colorama) | Console-color compatibility | Python dependency | [BSD 3-Clause](https://github.com/tartley/colorama/blob/master/LICENSE.txt) |
| [PyInstaller](https://pyinstaller.org/) | macOS application build tooling | Build-time only; its bootloader is included in a generated app | [GPL-2.0-or-later with the PyInstaller bootloader exception](https://pyinstaller.org/en/stable/license.html) |
| [MAFFT](https://mafft.cbrc.jp/alignment/software/) | External alignment executable | Not bundled; separately installed by the user | Upstream source distributions identify the no-extension source package as BSD. |

NCBI BLAST is an external network service, not a bundled Python dependency.
Users who submit queries through SangerFlow are responsible for complying with
NCBI service guidance and terms.

Before distributing a packaged application, verify the exact bundled versions
and include every license text and notice required by the chosen dependency
artifacts. In particular, binary Qt/PySide6 and numerical packages can carry
additional upstream notices beyond this summary. The maintained macOS build
recipe copies this notice inventory, the installed distribution metadata and
available license files for shipped Python packages, the bundled Python 3.12.10
PSF License text as `Python-PSF-LICENSE.txt`, and
the GNU GPLv3/LGPLv3 texts into `Contents/Resources/Legal/`.
