# SangerFlow Studio workflow

This is the v1.0 user workflow. The official GUI is **SangerFlow Studio
(PySide6/Qt)**. The Tkinter interface under `gui/` is legacy and unsupported;
it is not a normal launch or release-validation path.

## Requirements

- Python dependencies from `pyproject.toml` for source development, or the
  packaged Studio application.
- MAFFT available on `PATH` (or configured in Tool Settings) for alignment.
- Network access for NCBI BLAST.

## Start Studio from source

```bash
cd SangerFlow-Studio
source ../.venv/bin/activate
PYTHONPATH=.. python -m app.main
```

## Research workflow

1. Create or open a Project.
2. Import an AB1 folder/file or a sequence file.
3. Inspect quality and raw chromatogram evidence in Chromatogram Viewer.
4. For F/R data, use Consensus to classify pairs, explicitly resolve ambiguous
   candidates where necessary, then review and save consensus output.
5. Use Sequence Editor to review or edit sequences; use Align with MAFFT when
   an alignment is required.
6. Use Review Alignment Chromatograms only for read-only evidence inspection.
7. Identify sequences through NCBI BLAST, either online or by importing XML
   downloaded from the official NCBI website.
8. Import metadata, filter Project Records, build derived Datasets, and export
   the required format.
9. Save the Project to preserve revisions and provenance.

## Identification policy

- **NCBI BLAST is supported** in v1.0.
- **BOLD online identification is not supported** in v1.0 and is intentionally
  absent from the ordinary Studio workflow.

## Common checks

| Situation | Check |
|---|---|
| Alignment cannot start | Confirm MAFFT is installed/configured and the input is unaligned. |
| BLAST fails | Check network access, NCBI status, and the submitted sequence. |
| Source evidence unavailable | Confirm the original AB1 source files are still accessible. |
| Project cannot be reopened | Keep the `.sangerflow` bundle and referenced source data available. |

See [CURRENT_STATUS.md](CURRENT_STATUS.md) for release support boundaries and
test tiers. Historical Tkinter instructions are legacy reference material.
