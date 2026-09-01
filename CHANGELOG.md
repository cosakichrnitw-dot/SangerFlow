# Changelog

All notable user-facing changes are documented here. SangerFlow follows a
feature-freeze release process before a numbered public release.

## [1.0.0] - 2026-09-01

### Added

- SangerFlow Studio, the official PySide6/Qt desktop interface.
- AB1 import, chromatogram inspection, quality review, and trimming workflows.
- Sequence editing, F/R consensus review, and reviewed-consensus output.
- Metadata import, Project Records filtering, and derived Dataset creation.
- MAFFT alignment, alignment editing, and chromatogram-evidence review.
- NCBI BLAST online and official website/XML-import workflows.
- Immutable Dataset revisions, provenance-aware projects, and project save/reload.
- FASTA, NEXUS, PHYLIP, PopART NEXUS, and applicable result-export workflows.

### Notes

- MAFFT remains an external dependency.
- BOLD online identification and the legacy Tkinter GUI are not supported as
  v1.0 researcher-facing workflows.
