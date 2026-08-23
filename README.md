# SangerFlow

SangerFlow Studio is a desktop application for Sanger sequencing workflows:
AB1 import, chromatogram and quality review, F/R consensus review, sequence
editing, MAFFT alignment, NCBI BLAST, metadata-aware project records, and
FASTA/NEXUS/PHYLIP/PopART export.

## v1.0 supported surface

- **Official GUI:** SangerFlow Studio, built with PySide6/Qt.
- **Identification:** NCBI BLAST (online and official-website/XML-import
  workflows) is supported.
- **BOLD online identification:** not supported in v1.0.
- **Tkinter GUI:** legacy and unsupported.  It remains in the repository for
  historical/reference use only and is not part of the v1.0 release workflow.

## Run SangerFlow Studio

For a packaged macOS build, open `SangerFlow Studio.app` in Finder.

For source development:

```bash
cd SangerFlow-Studio
source ../.venv/bin/activate
PYTHONPATH=.. python -m app.main
```

SangerFlow Studio requires PySide6 and the Python dependencies declared in
`pyproject.toml`.  Alignment additionally requires a separately installed
[MAFFT](https://mafft.cbrc.jp/alignment/software/) executable.  NCBI BLAST
requires network access.

## Typical Studio workflow

```text
AB1 folder / sequence file
→ Project Dataset
→ Chromatogram or Sequence Editor
→ F/R Consensus Review or MAFFT Alignment
→ NCBI BLAST / metadata filtering
→ derived Dataset and export
```

Projects preserve datasets, revisions, provenance, and analysis results. Keep
backups of research data and review all quality, consensus, and identification
decisions before drawing biological conclusions.

## Documentation

- [Current Status](docs/CURRENT_STATUS.md) — v1.0 support boundary and test tiers.
- [Workflow](docs/Workflow.md) — Studio user workflow and requirements.
- [BLAST status](docs/BLAST_CURRENT_STATUS.md) — NCBI BLAST support notes.
- [Architecture](docs/Architecture.md) — code and data-flow architecture.
- [Development Rules](docs/DEVELOPMENT_RULES.md) — contribution safeguards.

Older documents that describe the Tkinter interface are retained as legacy
design/reference material; they are not v1.0 user instructions.
