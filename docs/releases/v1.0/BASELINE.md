# SangerFlow v1.0 baseline

This document records the v1.0.0 regression baseline before v1.1 development.
It does not extend the v1.0 support boundary or replace the release notes.

- Release tag: `v1.0.0`
- Tag target commit: `f8abf9b5cbf21c4e15171372abdc3617a12ed530`
- Official GUI: SangerFlow Studio (PySide6/Qt)
- Not part of the v1.0 supported workflow: the legacy Tkinter GUI and BOLD
  online identification.

Use this as a manual regression checklist when a v1.1 change could affect an
existing workflow. Automated coverage is summarized in
[`../v1.1/TEST_AUDIT.md`](../v1.1/TEST_AUDIT.md).

## Project lifecycle

- [ ] Create a Project.
- [ ] Open an existing Project.
- [ ] Save a Project.
- [ ] Close a Project, including the Save / Discard / Cancel path for dirty
  editors.
- [ ] Reopen a saved Project and confirm its persisted state.
- [ ] Confirm archive and restore behavior.
- [ ] Confirm that Project Summary Graph nodes and relationships are
  consistent with the Project.

## AB1 and chromatogram review

- [ ] Import one AB1 file.
- [ ] Import an AB1 folder containing multiple reads.
- [ ] Display chromatograms and read labels.
- [ ] Inspect quality information.
- [ ] Apply and inspect trimming.
- [ ] Toggle and inspect the trim-region display.
- [ ] Make and save a manual sequence/base edit through the supported editor
  workflow.

## Forward/reverse workflow

- [ ] Automatically classify clear Forward/Reverse pairs.
- [ ] Confirm reverse-complement orientation is handled correctly.
- [ ] Confirm orphan reads remain available and are never silently discarded.
- [ ] Create a pair alignment.
- [ ] Generate a consensus candidate.
- [ ] Open Single Consensus Review.
- [ ] Confirm Forward and Reverse chromatograms remain available as review
  evidence.
- [ ] Record manual consensus decisions or edits and create reviewed output.
- [ ] Open Multiple Consensus Review where applicable.

## Data model and traceability

- [ ] Import and persist metadata.
- [ ] Create and inspect immutable Dataset revisions.
- [ ] Create a derived Dataset.
- [ ] Confirm parent/source relationships remain visible.
- [ ] Confirm provenance and history remain available after save and reopen.

## Alignment

- [ ] Invoke MAFFT after confirming the external executable is available.
- [ ] Create an alignment.
- [ ] Open Alignment Viewer.
- [ ] Edit an alignment through Alignment Editor.
- [ ] Save and reopen the edited alignment revision.

## Identification

- [ ] Submit an NCBI BLAST query when network access is available.
- [ ] Parse or import BLAST results.
- [ ] Filter BLAST results.
- [ ] Export BLAST results.

## Export and reports

- [ ] Export FASTA.
- [ ] Export Excel where the selected workflow supports it.
- [ ] Open the Quality Report.
- [ ] Verify other applicable sequence exports, including NEXUS, PHYLIP, and
  PopART NEXUS.

## Scope reminder

This checklist records v1.0 behavior. It does not claim Windows support or
BOLD online integration. MAFFT and NCBI BLAST remain external dependencies.
