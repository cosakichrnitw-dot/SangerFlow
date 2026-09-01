# SangerFlow v1.0 current status

## Release state

SangerFlow is in the v1.0 release-preparation / feature-freeze phase. The
official researcher-facing GUI is **SangerFlow Studio (PySide6/Qt)**.

## Support boundary

| Item | v1.0 status |
|---|---|
| Official desktop GUI | **SangerFlow Studio (PySide6/Qt)** |
| AB1 import, chromatogram review, QC and trimming | Supported in Studio |
| F/R consensus review and reviewed-consensus output | Supported in Studio |
| Sequence Editor and MAFFT alignment | Supported in Studio; MAFFT is an external dependency |
| Project/Dataset revisions, provenance, metadata and Project Records | Supported in Studio |
| NCBI BLAST | Supported in Studio (online and website/XML import workflows) |
| Export | Supported Studio formats include FASTA, NEXUS, PHYLIP, PopART and applicable result exports |
| BOLD online identification | **Not supported in v1.0** |
| Tkinter GUI (`gui/`) | **Legacy / unsupported** |

The legacy Tkinter code and BOLD models, parsers, exporters, and tests remain
in the repository for compatibility, historical reference, and possible future
work. They are not part of the v1.0 researcher-facing release surface.

## Source launch

For source development:

```bash
cd SangerFlow-Studio
source ../.venv/bin/activate
PYTHONPATH=.. python -m app.main
```

Do not use `python -m gui.app` as a v1.0 user workflow; that starts the legacy
Tkinter interface.

## Test tiers

| Tier | Purpose | Public v1.0 release gate |
|---|---|---|
| Core/headless | Scientific models, workflow, persistence, import/export | Yes |
| Studio Qt | PySide6 GUI in offscreen mode plus platform smoke checks | Yes |
| `legacy_tk` | Native Tkinter widget tests | No; opt-in only |
| `private_validation` | Local validation requiring non-public research data | No; opt-in only |
| BOLD internal | BOLD result/filter/parser compatibility | Kept, but does not imply v1.0 online BOLD support |

The CI marker `legacy_tk` separates native Tk widget tests from the normal
headless release gate. `private_validation` keeps local, non-public validation
outside a clean public clone. Neither tier should be required to release v1.0.

## External dependencies

- MAFFT must be installed separately for alignment.
- NCBI BLAST requires network access and compliance with NCBI usage guidance.
- No public signed/notarized macOS application has been released yet. The
  maintained packaging recipe does not bundle research data, project files, or
  MAFFT.

## Legacy documentation

Documents whose primary subject is `gui/`, `python -m gui.app`, Tkinter, or a
historical design proposal are reference material rather than current v1.0 user
documentation. Current user instructions are linked from the repository README.
