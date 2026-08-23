# SangerFlow v1.0 current status

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

## Normal launch

Use the packaged Studio application when available. For source development:

```bash
cd SangerFlow-Studio
source ../.venv/bin/activate
PYTHONPATH=.. python -m app.main
```

Do not use `python -m gui.app` as a v1.0 user workflow; that starts the legacy
Tkinter interface.

## Test tiers

| Tier | Purpose | v1.0 release gate |
|---|---|---|
| Core/headless | Scientific models, workflow, persistence, import/export | Yes |
| Studio Qt | PySide6 GUI in offscreen mode plus platform smoke checks | Yes |
| `legacy_tk` | Native Tkinter widget tests | No; opt-in only |
| BOLD internal | BOLD result/filter/parser compatibility | Kept, but does not imply v1.0 online BOLD support |

The CI marker `legacy_tk` separates native Tk widget tests from the normal
headless release gate. A native Tk run remains available to maintain the
legacy implementation without making it a v1.0 release requirement.

## External dependencies

- MAFFT must be installed separately for alignment.
- NCBI BLAST requires network access and compliance with NCBI usage guidance.
- The macOS packaged application is distributed separately from source builds;
  packaging does not bundle research data or project files.

## Legacy documentation

Documents whose primary subject is `gui/`, `python -m gui.app`, or Tkinter
windows should be treated as legacy/reference documentation. Candidates for a
future `docs/legacy/` move include older GUI-specific documents and historical
status reports; they are retained in place during v1.0 to avoid breaking links.
