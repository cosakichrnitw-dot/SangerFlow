# Tkinter to SangerFlow-Studio Migration Inventory

This document records the current migration state from the existing Tkinter GUI
to the PySide6 SangerFlow-Studio shell.  The Tkinter implementation is treated
as the source of truth for existing GUI workflow behavior.

## Source files audited

- `gui/main_window.py`
- `gui/button_bar.py`
- `gui/sample_panel.py`
- `gui/chromatogram_canvas.py`
- `gui/chromatogram_read.py`
- `gui/quality_panel.py`
- `gui/blast_dialog.py`
- `gui/alignment_window.py`
- `gui/alignment_chromatogram_canvas.py`
- `gui/alignment_sequence_window.py`
- `gui/alignment_canvas.py`
- `gui/consensus_review_entry.py`
- `gui/consensus_review_manager.py`
- `gui/consensus_viewer.py`
- `gui/multiple_consensus_viewer.py`
- `gui/fasta_import_dialog.py`
- `gui/project_dataset_manager.py`

## Feature inventory

| Feature | Tkinter implementation | Current Studio implementation | Migration status | Missing behavior |
|---|---|---|---|---|
| Open AB1 file | `MainWindow.open_file()` → `load_ab1_file()` → `ChromatogramCanvas.load_data()` | Not yet exposed in Studio menu | Not migrated | Single-file dialog and tab creation |
| Open AB1 folder | `MainWindow.open_folder()` → `load_ab1_folder()` → `ChromatogramCanvas.load_reads()` | `ProjectController.open_ab1_folder()` opens `ChromatogramViewer` | Migrated | Project registration remains separate |
| Multiple read chromatogram display | `ChromatogramCanvas` rows | `ChromatogramViewer` single raw-coordinate canvas | Migrated | Further performance tuning may be needed for very large batches |
| Raw trace display | `ChromatogramRead.draw()` | `ChromatogramRenderCache` + `ChromatogramCanvasWidget` | Migrated | QGraphicsScene/tile cache intentionally deferred |
| Raw sequence display | `ChromatogramRead.draw_sequence()` | Base items drawn from raw sequence/base positions | Migrated | None known |
| Quality overlay | `ChromatogramRead` quality drawing | Cached quality path overlay | Migrated | Threshold coloring not separated into its own layer |
| Trim overlay | `show_trim_region` on raw trace | `Show Trim Region` action on raw trace | Migrated | Trim execution/reset GUI not yet exposed in Studio |
| Horizontal trace-coordinate scroll | Tk canvas `xview` | Studio scrollbar + wheel delta over raw trace coordinate width | Migrated | Native inertial feel may still differ from Tkinter |
| Trackpad / Shift horizontal scroll | `mouse_scroll()` with Shift handling | `ChromatogramCanvasWidget.wheelEvent()` | Migrated | macOS hardware verification still recommended |
| Middle/Shift drag pan | `pan_start()` / `pan_move()` | Middle-button and Shift-left pan in `ChromatogramCanvasWidget` | Migrated | Fine-grained pan acceleration not tuned |
| Command/Ctrl wheel X zoom | `mouse_scroll()` command branch | Ctrl-wheel uses existing `set_x_scale()` path | Migrated | macOS Command modifier mapping should be hardware-verified |
| X Scale | APE-style vertical scrollbar | Studio right-side X slider | Migrated | Visual control is Qt slider, not native scrollbar |
| Y Scale | Row/trace lane scaling | Studio Y slider changes row height and row contents | Migrated | None known |
| Sample visibility | `SamplePanel` checkboxes | Compact Studio Sample Panel checkboxes | Migrated | Panel-level vertical scrolling not yet implemented |
| Sample All / None / Invert | `SamplePanel.select_all/clear_all/invert_selection` | Same controls on Studio Sample Panel | Migrated | None known |
| Selected base inspector | `ChromatogramCanvas._show_base_coordinates()` | `SelectedBasePanel` | Migrated | None known |
| Manual base editing | No clear Tkinter implementation found in audited files | Not added | Intentionally not migrated | Existing behavior appears inspection-only |
| Quality report | `QualityPanel` table: length, HQ%, Q20, Q30, threshold selection | `QualityReportViewer` table and HQ threshold selection | Partially migrated | Export selected FASTA, save/load selection, Align Selected still need full Studio workflows |
| Quality apply to viewer | `QualityPanel.apply_to_viewer()` | Not yet connected from `QualityReportViewer` | Partial | Needs context callback to update active `ChromatogramViewer` visibility |
| Quality selected FASTA export | `QualityPanel.export_fasta()` | Not yet exposed | Not migrated | Should use Studio export framework |
| Quality selection save/load | `core.selection.save_selection/load_selection` | Not yet exposed | Not migrated | Needs Studio dialog/action |
| Align selected from QualityPanel | `QualityPanel.align_selected()` → MAFFT | Not yet exposed from quality report | Not migrated | Should route to Alignment Chromatogram Viewer / AlignmentDataset workflow |
| FASTA alignment open | `MainWindow.open_alignment()` → `align_fasta()` → `AlignmentSequenceWindow` | Dataset import and DatasetViewer exist; direct FASTA alignment menu not yet exposed | Partial | Studio file menu import/open action |
| FASTA alignment display | `AlignmentCanvas` | DatasetViewer can display `AlignmentDataset`; dedicated alignment sequence viewer not yet migrated | Partial | Position ruler/colored base grid viewer |
| Align chromatograms | `MainWindow.align_chromatograms()` → `align_reads()` → `AlignmentWindow` | `AlignmentChromatogramViewer` using existing `align_reads()` and mapper | Partially migrated | Full chromatogram waveform rows under alignment bases are not yet drawn |
| Alignment column → trace mapping | `alignment_to_trace_positions()` | `AlignmentChromatogramViewer.alignment_column_to_trace_position()` | Migrated | None known |
| Alignment click callback | `AlignmentWindow.alignment_clicked()` → Main Viewer jump | Studio selection signal emits selected mapping | Partial | Direct jump back to active ChromatogramViewer needs controller-level wiring |
| Alignment consensus export | `AlignmentWindow.export_consensus()` | `AlignmentChromatogramViewer` emits export request | Partial | File dialog/export handling not yet attached |
| BLAST dialog | `BlastDialog` target/database/top hits/export | New BLAST workflow/result/viewer exists outside Studio; Chromatogram action emits request | Partial | Studio BLAST settings dialog and real app callback are not wired |
| Consensus Review entry | `MainWindow.open_consensus_review_manager()` | Studio action emits consensus request only | Partial | Full Consensus Review Manager tab/window not yet connected |
| Single Consensus Review | `SingleConsensusReviewWindow` | Not migrated to PySide6 | Not migrated | Needs Viewer Framework implementation |
| Multiple Consensus Alignment Review | `MultipleConsensusAlignmentWindow` | Not migrated to PySide6 | Not migrated | Alignment Editor exists in Tkinter only |
| Project Dataset Manager | Tkinter `ProjectDatasetManagerWindow` | Studio ProjectExplorer + DatasetViewer | Migrated conceptually | Dataset Manager-specific buttons are not all mirrored |
| FASTA Import Dialog | Tkinter dialog exists | Not yet exposed in Studio menu | Not migrated | Needs ProjectController action |

## Intentional non-migrations

- Manual base editing was not added to Studio because audited Tkinter Main Viewer
  code provides base inspection, not a stable manual base edit workflow.
- Tkinter widgets themselves were not copied.  Studio keeps the existing
  `MainWindow` / `AppState` / `ProjectController` / `BaseViewer` /
  `TabManager` / `ActionManager` architecture.

## Current researcher workflow in Studio

1. Open a Project Bundle, or open an AB1 folder directly.
2. Inspect raw chromatogram rows in `ChromatogramViewer`.
3. Toggle read visibility with the compact Sample Panel.
4. Inspect base, quality, raw index, trim index, raw trace position, and trim
   trace position by clicking bases.
5. Toggle trim overlay.
6. Open Quality Report from a chromatogram or AB1-backed dataset.
7. Open MAFFT Chromatogram Alignment from a chromatogram or AB1-backed dataset.
8. Continue BLAST, Consensus, and Export through currently exposed connection
   points while full PySide6 viewers are migrated.

## Migration count

Current Tkinter feature migration status:

- Migrated: 15
- Partially migrated: 9
- Not migrated: 6
- Intentionally not migrated: 1

Tkinter feature migration rate: 15 / 31 fully migrated.

## v1.0 GUI work remaining

Priority A:

- Single AB1 file open in Studio.
- Full Alignment Chromatogram waveform drawing under aligned bases.
- Controller-level jump from Alignment Chromatogram selection back to
  ChromatogramViewer raw trace coordinate.
- Studio FASTA/alignment import menu actions.
- Studio export action handlers for consensus/alignment/quality outputs.

Priority B:

- Quality Report apply-to-viewer, selected FASTA export, save/load selection.
- BLAST settings dialog wired to new BLAST Workflow / ResultRepository.
- Consensus Review Manager PySide6 integration.

Priority C:

- Single Consensus Review and Multiple Consensus Alignment Review PySide6
  migrations.
- Dedicated alignment sequence grid viewer with position ruler and base colors.
- Hardware-level tuning for macOS trackpad inertial scrolling.
