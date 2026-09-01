"""Mesquite-style high-density alignment table viewer."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QLabel, QMenu, QMessageBox, QPushButton, QVBoxLayout

from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.project import RevisionState
from core.alignment_mapper import alignment_to_trace_positions
from core.models import SangerRead
from app.icon_registry import studio_icon
from export.sequence_export import (
    export_alignment_to_fasta,
    export_alignment_to_nexus,
    export_alignment_to_phylip,
)
from export.partition_export import create_partition_definition
from widgets.sequence_grid import (
    SEQUENCE_GRID_CELL_WIDTH,
    SEQUENCE_GRID_LABEL_WIDTH,
    SEQUENCE_GRID_ROW_HEIGHT,
    SequenceGridRow,
    SequenceGridWidget,
)
from widgets.alignment_edit_operations import (
    BaseEditOperation,
    BulkBaseEditOperation,
    DeleteColumnsOperation,
    DeleteRowsOperation,
    ExcludeColumnsOperation,
    RenameOperation,
)
from widgets.viewers.alignment_chromatogram_viewer import AlignmentChromatogramViewer
from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.viewer_actions import ViewerAction


ALIGNMENT_NAME_COLUMN_WIDTH = SEQUENCE_GRID_LABEL_WIDTH
ALIGNMENT_BASE_COLUMN_WIDTH = SEQUENCE_GRID_CELL_WIDTH
ALIGNMENT_ROW_HEIGHT = SEQUENCE_GRID_ROW_HEIGHT
ALIGNMENT_NAME_FONT_SIZE = 9
ALIGNMENT_BASE_FONT_SIZE = 9
_EDITABLE_ALIGNMENT_SYMBOLS = frozenset("ACGTNRYSWKMBDHV-")


class AlignmentViewer(BaseViewer):
    """Display an AlignmentDataset without chromatogram waveforms."""

    def __init__(
        self,
        alignment_dataset: AlignmentDataset,
        *,
        context: object | None = None,
    ) -> None:
        if not isinstance(alignment_dataset, AlignmentDataset):
            raise ValueError("AlignmentViewer requires an AlignmentDataset")
        self._dataset = alignment_dataset
        self._context = context
        self._edited_sequences = {
            record.record_id: list(record.aligned_sequence)
            for record in alignment_dataset.records
        }
        self._record_labels = {record.record_id: record.record_id for record in alignment_dataset.records}
        # Stable original IDs survive structural deletion; UI indices are only
        # projections of this ordered list and are never stored in operations.
        self._column_ids = list(range(alignment_dataset.length))
        self._deleted_column_ids: set[int] = set()
        self._hidden_row_ids: set[str] = set()
        self._deleted_row_ids: set[str] = set()
        self._excluded_column_ids = set(int(column) for column in alignment_dataset.metadata.get("excluded_columns", ()))
        self._undo_stack: list[object] = []
        self._redo_stack: list[object] = []
        self._selected_cell: tuple[str, int] | None = None
        self._selected_column: int | None = None
        self._action_provider = AlignmentViewerActionProvider(context)
        super().__init__(
            viewer_id=f"alignment-viewer-{_safe_identifier(alignment_dataset.alignment_id)}",
            viewer_title=f"Sequence Editor — Aligned: {alignment_dataset.name}",
            viewer_kind="alignment",
            source_object_id=alignment_dataset.alignment_id,
        )
        self._build_ui()

    @property
    def dataset(self) -> AlignmentDataset:
        return self._dataset

    @property
    def selected_cell(self) -> tuple[str, int] | None:
        return self._selected_cell

    @property
    def selected_column(self) -> int | None:
        return self._selected_column

    @property
    def edited_cells(self) -> frozenset[tuple[str, int]]:
        return frozenset(self._edited_cells())

    @property
    def pending_deleted_row_ids(self) -> frozenset[str]:
        """Rows removed only from the next saved AlignmentDataset revision."""

        return frozenset(self._deleted_row_ids)

    @property
    def pending_deleted_column_ids(self) -> frozenset[int]:
        return frozenset(self._deleted_column_ids)

    @property
    def current_alignment_length(self) -> int:
        return len(self._column_ids)

    @property
    def has_pending_scientific_changes(self) -> bool:
        return bool(self._undo_stack)

    @property
    def is_dirty(self) -> bool:
        """Expose staged alignment edits to generic Studio workflow guards."""

        return self.has_pending_scientific_changes

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "alignment.review_chromatograms",
            "alignment.undo",
            "alignment.redo",
            "alignment.copy_selection",
            "alignment.export_selected_rows_fasta",
            "alignment.export_selection_fasta",
            "alignment.export_fasta",
            "alignment.export_nexus",
            "alignment.export_phylip",
            "alignment.export_iqtree_partitions",
            "alignment.export_raxml_partitions",
            "alignment.export_nexus_charsets",
            "alignment.run_blast",
            "alignment.exclude_columns",
            "alignment.include_columns",
            "alignment.delete_selected_columns",
            "alignment.paste",
            "alignment.hide_rows",
            "alignment.show_all_rows",
            "alignment.rename_selected_row",
            "alignment.delete_selected_rows",
            "alignment.set_selection_gap",
            "alignment.set_selection_n",
            "alignment.set_selection_a",
            "alignment.set_selection_c",
            "alignment.set_selection_g",
            "alignment.set_selection_t",
            "alignment.save_edited_alignment",
        )

    def open_dataset(self, dataset: object) -> None:
        if not isinstance(dataset, AlignmentDataset):
            raise ValueError("AlignmentViewer requires an AlignmentDataset")
        self._dataset = dataset
        self._edited_sequences = {
            record.record_id: list(record.aligned_sequence)
            for record in dataset.records
        }
        self._record_labels = {record.record_id: record.record_id for record in dataset.records}
        self._column_ids = list(range(dataset.length))
        self._deleted_column_ids.clear()
        self._hidden_row_ids.clear()
        self._deleted_row_ids.clear()
        self._excluded_column_ids = set(int(column) for column in dataset.metadata.get("excluded_columns", ()))
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.refresh()

    def select_alignment_cell(self, row_index: int, column_index: int) -> tuple[str, int, str] | None:
        if row_index < 0 or row_index >= len(self._dataset.records):
            return None
        record = self._dataset.records[row_index]
        if column_index < 0 or column_index >= self.current_alignment_length:
            return None
        alignment_column = column_index + 1
        self._selected_cell = (record.record_id, alignment_column)
        self._selected_column = alignment_column
        self._grid.select_cell(record.record_id, column_index, emit=False)
        base = self._edited_sequences[record.record_id][column_index]
        self._status.setText(self._evidence_status(record, column_index, base))
        return record.record_id, alignment_column, self._edited_sequences[record.record_id][column_index]

    def select_column(self, column_index: int) -> None:
        if column_index < 0 or column_index >= self.current_alignment_length:
            return
        self._selected_column = column_index + 1
        self._selected_cell = None
        self._grid.select_cell("__consensus__", column_index, emit=False)
        self._status.setText(f"Column: {column_index + 1}")

    def review_chromatograms(self) -> object | None:
        if self._deleted_column_ids:
            self.status_message_changed.emit(
                "Chromatogram review is unavailable while columns are pending deletion; "
                "save the edited Alignment revision and reopen it first."
            )
            return None
        context = self._context
        tab_manager = getattr(context, "tab_manager", None)
        if tab_manager is None:
            self.open_related_requested.emit(
                {"action": "REVIEW_CHROMATOGRAMS", "viewer": self, "dataset": self._dataset}
            )
            return None
        reads = _reads_from_alignment_dataset(self._dataset, self._context)
        if not reads:
            self.status_message_changed.emit(
                "No SangerRead references are attached to this AlignmentDataset."
            )
            return None
        alignment = tuple(
            _AlignmentRecord(
                str(record.metadata.get("source_filename", record.record_id)),
                record.aligned_sequence,
            )
            for record in self._dataset.records
        )
        viewer = AlignmentChromatogramViewer(
            reads,
            alignment=alignment,
            alignment_dataset=self._dataset,
            context=context,
            source_object_id=self._dataset.alignment_id,
            initial_alignment_column=self._selected_column,
        )
        return tab_manager.open_viewer(
            viewer,
            resource_key=f"alignment-chromatograms:{self._dataset.alignment_id}",
        )

    def run_blast(self) -> object | None:
        self._notify_exclusion_contract("BLAST")
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "run_blast_for_dataset_interactive", None)
        if not callable(method):
            method = getattr(controller, "run_blast_for_dataset", None)
        if not callable(method):
            self.status_message_changed.emit("BLAST workflow is not configured.")
            return None
        try:
            return method(self._dataset, parent_widget=self)
        except TypeError:
            return method(self._dataset)

    def run_bold(self) -> object | None:
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "run_bold_for_dataset_interactive", None)
        if not callable(method):
            method = getattr(controller, "run_bold_for_dataset", None)
        if not callable(method):
            self.status_message_changed.emit("BOLD workflow is not configured.")
            return None
        try:
            return method(self._dataset, parent_widget=self)
        except TypeError:
            return method(self._dataset)

    def set_base(self, record_id: str, column_index: int, base: str) -> bool:
        if record_id not in self._edited_sequences:
            return False
        base = str(base).upper()
        if base not in _EDITABLE_ALIGNMENT_SYMBOLS:
            raise ValueError("base must be a DNA/IUPAC symbol or gap")
        if not 0 <= int(column_index) < self.current_alignment_length:
            return False
        column_index = int(column_index)
        previous = self._edited_sequences[record_id][column_index]
        if previous == base:
            return False
        change = (record_id, column_index, previous, base)
        self._apply_cell_changes((change,))
        self._undo_stack.append(BaseEditOperation((change,)))
        self._redo_stack.clear()
        self.refresh()
        self.select_alignment_cell(self._record_index(record_id), column_index)
        return True

    def set_selection_to_gap(self) -> bool:
        return self.set_selection_to_base("-")

    def set_selection_to_n(self) -> bool:
        return self.set_selection_to_base("N")

    def request_set_selection_to_gap(self) -> bool:
        return self._request_bulk_selection_edit("-")

    def request_set_selection_to_n(self) -> bool:
        return self._request_bulk_selection_edit("N")

    def request_set_selection_to_base(self, base: str) -> bool:
        return self._request_bulk_selection_edit(base)

    def set_selection_to_base(self, base: str) -> bool:
        base = str(base).upper()
        if base not in _EDITABLE_ALIGNMENT_SYMBOLS:
            raise ValueError("base must be a DNA/IUPAC symbol or gap")
        changes = []
        for row_id, column in self._grid.selected_cells():
            if row_id == "__consensus__" or row_id not in self._edited_sequences:
                continue
            previous = self._edited_sequences[row_id][column]
            if previous != base:
                changes.append((row_id, column, previous, base))
        if not changes:
            return False
        self._apply_cell_changes(changes)
        operation_type = BaseEditOperation if len(changes) == 1 else BulkBaseEditOperation
        self._undo_stack.append(operation_type(tuple(changes)))
        self._redo_stack.clear()
        self.refresh()
        self._status.setText(f"Set {len(changes)} selected cells to {base}.")
        return True

    def _request_bulk_selection_edit(self, base: str) -> bool:
        editable_changes = [
            (row_id, column)
            for row_id, column in self._grid.selected_cells()
            if row_id != "__consensus__"
            and row_id in self._edited_sequences
            and self._edited_sequences[row_id][column] != base
        ]
        if len(editable_changes) > 1:
            response = QMessageBox.question(
                self,
                "Edit Selected Alignment Cells",
                f"Set {len(editable_changes)} selected cells to {base}?",
            )
            if response != QMessageBox.StandardButton.Yes:
                return False
        return self.set_selection_to_base(base)

    def exclude_selected_columns(self) -> bool:
        columns = set(self._grid.selected_columns())
        if not columns:
            return False
        column_ids = {self._column_ids[column] for column in columns if 0 <= column < self.current_alignment_length}
        before = frozenset(self._excluded_column_ids)
        after = frozenset(self._excluded_column_ids | column_ids)
        if before == after:
            return False
        self._set_excluded_column_ids(after)
        self._undo_stack.append(ExcludeColumnsOperation(before, after))
        self._redo_stack.clear()
        self._status.setText(self._grid.selection_status_text())
        return True

    def include_selected_columns(self) -> bool:
        columns = set(self._grid.selected_columns())
        if not columns:
            return False
        column_ids = {self._column_ids[column] for column in columns if 0 <= column < self.current_alignment_length}
        before = frozenset(self._excluded_column_ids)
        after = frozenset(self._excluded_column_ids - column_ids)
        if before == after:
            return False
        self._set_excluded_column_ids(after)
        self._undo_stack.append(ExcludeColumnsOperation(before, after))
        self._redo_stack.clear()
        self._status.setText(self._grid.selection_status_text())
        return True

    def delete_selected_columns(self, *, confirm: bool = False) -> bool:
        """Stage structural deletion using stable original column IDs."""

        message = self._alignment_editability_error()
        if message is not None:
            self.status_message_changed.emit(message)
            return False
        columns = tuple(sorted(set(self._grid.selected_columns())))
        if not columns:
            return False
        column_ids = tuple(self._column_ids[column] for column in columns if 0 <= column < self.current_alignment_length)
        if not column_ids or len(column_ids) >= self.current_alignment_length:
            return False
        if confirm:
            answer = QMessageBox.question(
                self,
                "Delete Selected Columns",
                f"Delete {len(column_ids)} column(s) from the next saved Alignment revision?\n"
                "The source AlignmentDataset is not modified.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        removed = {
            record_id: tuple(self._edited_sequences[record_id][index] for index in columns)
            for record_id in self._edited_sequences
        }
        operation = DeleteColumnsOperation(column_ids, removed)
        operation.apply(self)
        self._undo_stack.append(operation)
        self._redo_stack.clear()
        self._selected_cell = None
        self._selected_column = None
        self.refresh(reset_grid_selection=True)
        self._status.setText(f"Unsaved changes • {len(self._deleted_column_ids)} column(s) deleted")
        return True

    def request_delete_selected_columns(self) -> bool:
        return self.delete_selected_columns(confirm=True)

    def paste_selection(self, text: str | None = None) -> bool:
        """Strict substitution-only paste; it never extends an alignment."""

        message = self._alignment_editability_error()
        if message is not None:
            self.status_message_changed.emit(message)
            return False
        from PySide6.QtWidgets import QApplication

        text = QApplication.clipboard().text() if text is None else str(text)
        lines = [line.strip().upper() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
        if not lines:
            self._status.setText("Clipboard contains no bases to paste.")
            return False
        if any(any(base not in _EDITABLE_ALIGNMENT_SYMBOLS for base in line) for line in lines):
            self._status.setText("Paste accepts only DNA/IUPAC symbols or gaps.")
            return False
        bounds = self._grid.selection_bounds()
        if bounds is None:
            self._status.setText("Select an editable cell or rectangle before pasting.")
            return False
        first_row, last_row, first_column, last_column = bounds
        selected_rows = list(range(first_row, last_row + 1))
        selected_columns = list(range(first_column, last_column + 1))
        # One-cell selection is an anchor: the clipboard rectangle must still
        # fit the existing matrix.  Larger selections require exact shape.
        if not (len(selected_rows) == len(lines) and all(len(line) == len(selected_columns) for line in lines)):
            if len(selected_rows) != 1 or len(selected_columns) != 1:
                self._status.setText(
                    f"Paste shape mismatch. Expected: {len(selected_rows)} × {len(selected_columns)}; "
                    f"Clipboard: {len(lines)} × {max(len(line) for line in lines)}."
                )
                return False
            selected_rows = list(range(first_row, first_row + len(lines)))
            selected_columns = list(range(first_column, first_column + len(lines[0])))
            if len({len(line) for line in lines}) != 1 or selected_rows[-1] >= len(self._grid.rows) or selected_columns[-1] >= self.current_alignment_length:
                self._status.setText("Paste would extend the Alignment; only substitution paste is allowed.")
                return False
        changes: list[tuple[str, int, str, str]] = []
        for row_offset, row_index in enumerate(selected_rows):
            row_id = self._grid.rows[row_index].row_id
            if row_id == "__consensus__" or row_id in self._deleted_row_ids:
                self._status.setText("Consensus and deleted rows cannot be edited.")
                return False
            for column_offset, column_index in enumerate(selected_columns):
                previous = self._edited_sequences[row_id][column_index]
                current = lines[row_offset][column_offset]
                if previous != current:
                    changes.append((row_id, column_index, previous, current))
        if not changes:
            return False
        if len(changes) > 1:
            answer = QMessageBox.question(self, "Paste Alignment Bases", f"Paste {len(changes)} base substitutions?")
            if answer != QMessageBox.StandardButton.Yes:
                return False
        operation = BulkBaseEditOperation(tuple(changes))
        operation.apply(self)
        self._undo_stack.append(operation)
        self._redo_stack.clear()
        self.refresh()
        return True

    def hide_selected_rows(self) -> bool:
        row_ids = {row_id for row_id in self._grid.selected_rows() if row_id != "__consensus__"}
        if not row_ids:
            return False
        self._hidden_row_ids.update(row_ids)
        self.refresh()
        self._status.setText(f"Hidden rows: {len(row_ids)}")
        return True

    def show_all_rows(self) -> None:
        self._hidden_row_ids.clear()
        self.refresh()
        self._status.setText("All rows shown.")

    def rename_selected_row(self, new_label: str) -> bool:
        selected = [row_id for row_id in self._grid.selected_rows() if row_id != "__consensus__"]
        if len(selected) != 1:
            return False
        new_label = str(new_label).strip()
        if not new_label:
            raise ValueError("new row label must be non-empty")
        row_id = selected[0]
        existing_labels = {
            label
            for other_id, label in self._record_labels.items()
            if other_id != row_id and other_id not in self._deleted_row_ids
        }
        if new_label in existing_labels:
            raise ValueError("new row label duplicates another visible alignment row")
        previous = self._record_labels.get(row_id, row_id)
        if previous == new_label:
            return False
        self._set_row_label(row_id, new_label)
        self._undo_stack.append(RenameOperation(row_id, previous, new_label))
        self._redo_stack.clear()
        self.refresh()
        self._grid.select_row(row_id)
        return True

    def _commit_inline_row_rename(self, row_id: str, new_label: str) -> bool:
        """Commit inline labels through the existing undoable rename operation."""

        self._grid.select_row(row_id)
        try:
            changed = self.rename_selected_row(new_label)
        except ValueError as error:
            self._status.setText(str(error))
            return False
        if not changed:
            self._status.setText("Row name must be non-empty and unique.")
        return changed

    def delete_selected_rows_from_derived_dataset(self) -> bool:
        return self._delete_rows_from_derived_dataset(self._grid.selected_rows())

    def _delete_rows_from_derived_dataset(self, selected_row_ids: object) -> bool:
        """Stage a row deletion using IDs captured before any modal UI opens."""

        editable_message = self._alignment_editability_error()
        if editable_message is not None:
            self._status.setText(editable_message)
            self.status_message_changed.emit(editable_message)
            return False
        available_ids = {record.record_id for record in self._dataset.records}
        row_ids = {
            str(row_id)
            for row_id in selected_row_ids
            if row_id != "__consensus__" and str(row_id) in available_ids
        }
        remaining = [record.record_id for record in self._dataset.records if record.record_id not in self._deleted_row_ids and record.record_id not in row_ids]
        if not row_ids or not remaining:
            return False
        before = frozenset(self._deleted_row_ids)
        after = frozenset(self._deleted_row_ids | row_ids)
        self._set_deleted_row_ids(after)
        self._undo_stack.append(DeleteRowsOperation(before, after))
        self._redo_stack.clear()
        # A row deletion invalidates all display-index selection coordinates.
        # Rebuild the grid without preserving selection, so a removed row can
        # never be followed by a stale row/cell/context-menu target.
        self._selected_cell = None
        self._selected_column = None
        self.refresh(reset_grid_selection=True)
        message = f"Unsaved changes • {len(self._deleted_row_ids)} row{'s' if len(self._deleted_row_ids) != 1 else ''} deleted"
        self._status.setText(message)
        self.status_message_changed.emit(message)
        return True

    def copy_selection(self) -> str:
        return self._grid.copy_selection_to_clipboard()

    def selection_fasta_text(self) -> str:
        """Return the selected row × column rectangle as aligned FASTA."""

        return self._grid.selected_fasta_text()

    def selected_rows_fasta_text(self) -> str:
        """Return complete selected AlignmentDataset rows as aligned FASTA.

        The SequenceGrid also contains a transient consensus display row.  It
        is intentionally not an AlignmentDataset record and must never become
        part of a selected-row export.
        """

        selected_ids = set(self._grid.selected_rows())
        entries = [
            f">{record.record_id}\n{record.aligned_sequence}"
            for record in self._dataset.records
            if record.record_id in selected_ids
        ]
        return "\n".join(entries) + ("\n" if entries else "")

    def selected_rows_export_summary(self) -> str | None:
        selected_ids = set(self._grid.selected_rows())
        count = sum(record.record_id in selected_ids for record in self._dataset.records)
        if not count:
            return None
        return f"{count} sequence{'s' if count != 1 else ''} selected • Alignment length: {self.current_alignment_length} columns"

    def selected_region_export_summary(self) -> str | None:
        bounds = self._grid.selection_bounds()
        if bounds is None:
            return None
        first_row, last_row, first_column, last_column = bounds
        row_count = last_row - first_row + 1
        region_length = last_column - first_column + 1
        return (
            f"{row_count} sequence{'s' if row_count != 1 else ''} • "
            f"Columns {first_column + 1}–{last_column + 1} • "
            f"Region length: {region_length} columns"
        )

    def export_selected_rows_fasta(self, filepath: str | Path) -> str:
        text = self.selected_rows_fasta_text()
        if not text:
            raise ValueError("Select one or more AlignmentDataset rows before exporting.")
        path = Path(filepath)
        path.write_text(text, encoding="utf-8")
        return text

    def export_selection_fasta(self, filepath: str | Path) -> str:
        text = self.selection_fasta_text()
        if not text:
            raise ValueError("Select an alignment region before exporting.")
        path = Path(filepath)
        path.write_text(text, encoding="utf-8")
        return text

    def request_export_selected_rows_fasta(self) -> str | None:
        if not self._allow_saved_alignment_export("Export Selected Rows as FASTA"):
            return None
        summary = self.selected_rows_export_summary()
        if summary is None:
            self.status_message_changed.emit("Select one or more alignment rows before exporting full rows as FASTA.")
            return None
        self._notify_exclusion_contract("selection export")
        filepath, _selected_filter = QFileDialog.getSaveFileName(
            self,
            f"Export Selected Rows as FASTA — {summary}",
            self._default_export_path(f"{self._dataset.alignment_id}_selected_rows.fasta"),
            "FASTA files (*.fasta *.fa *.fas *.fna);;All files (*)",
        )
        if not filepath:
            return None
        text = self.export_selected_rows_fasta(filepath)
        self.status_message_changed.emit(f"Selected rows exported ({summary}): {filepath}")
        return text

    def request_export_selection_fasta(self) -> str | None:
        """Export the explicit row × column selection as an aligned FASTA region."""

        if not self._allow_saved_alignment_export("Export Selected Region as FASTA"):
            return None
        summary = self.selected_region_export_summary()
        if summary is None:
            self.status_message_changed.emit("Select an alignment region before exporting it as FASTA.")
            return None
        self._notify_exclusion_contract("selection region export")
        filepath, _selected_filter = QFileDialog.getSaveFileName(
            self,
            f"Export Selected Region as FASTA — {summary}",
            self._default_export_path(f"{self._dataset.alignment_id}_selected_region.fasta"),
            "FASTA files (*.fasta *.fa *.fas *.fna);;All files (*)",
        )
        if not filepath:
            return None
        text = self.export_selection_fasta(filepath)
        self.status_message_changed.emit(f"Selected region exported ({summary}): {filepath}")
        return text

    def request_export_alignment_fasta(self) -> str | None:
        return self._request_export_alignment(
            title="Export Alignment as FASTA",
            default_suffix=".fasta",
            name_filter="FASTA files (*.fasta *.fas *.fa *.fna);;All files (*)",
            exporter=export_alignment_to_fasta,
        )

    def request_export_alignment_nexus(self) -> str | None:
        return self._request_export_alignment(
            title="Export Alignment as NEXUS",
            default_suffix=".nex",
            name_filter="NEXUS files (*.nex *.nexus);;All files (*)",
            exporter=lambda dataset, filepath: export_alignment_to_nexus(
                dataset,
                filepath,
                metadata=dataset.metadata,
            ),
        )

    def request_export_alignment_phylip(self) -> str | None:
        return self._request_export_alignment(
            title="Export Alignment as PHYLIP",
            default_suffix=".phy",
            name_filter="PHYLIP files (*.phy *.phylip);;All files (*)",
            exporter=export_alignment_to_phylip,
        )

    def request_export_iqtree_partitions(self) -> str | None:
        return self._request_export_partitions(
            title="Export IQ-TREE Partitions",
            default_suffix=".iqtree.partitions",
            text_getter=lambda definition: definition.iqtree,
        )

    def request_export_raxml_partitions(self) -> str | None:
        return self._request_export_partitions(
            title="Export RAxML Partitions",
            default_suffix=".raxml.partitions",
            text_getter=lambda definition: definition.raxml,
        )

    def request_export_nexus_charsets(self) -> str | None:
        return self._request_export_partitions(
            title="Export NEXUS Charsets",
            default_suffix=".nexus.charsets",
            text_getter=lambda definition: definition.nexus_charset,
        )

    def _request_export_partitions(
        self,
        *,
        title: str,
        default_suffix: str,
        text_getter: object,
    ) -> str | None:
        if not self._allow_saved_alignment_export(title):
            return None
        self._notify_exclusion_contract("partition export")
        try:
            definition = create_partition_definition(self._dataset)
        except Exception as error:
            QMessageBox.warning(self, title, str(error))
            return None
        filepath, _selected_filter = QFileDialog.getSaveFileName(
            self,
            title,
            self._default_export_path(f"{self._dataset.alignment_id}{default_suffix}"),
            "Text files (*.txt);;All files (*)",
        )
        if not filepath:
            return None
        filepath = _ensure_suffix(filepath, default_suffix)
        try:
            Path(filepath).write_text(str(text_getter(definition)) + "\n", encoding="utf-8")  # type: ignore[misc]
        except OSError as error:
            QMessageBox.warning(self, title, str(error))
            return None
        self.status_message_changed.emit(f"Exported: {filepath}")
        return filepath

    def _request_export_alignment(
        self,
        *,
        title: str,
        default_suffix: str,
        name_filter: str,
        exporter: object,
    ) -> str | None:
        if not self._allow_saved_alignment_export(title):
            return None
        self._notify_exclusion_contract("alignment export")
        filepath, _selected_filter = QFileDialog.getSaveFileName(
            self,
            title,
            self._default_export_path(f"{self._dataset.alignment_id}{default_suffix}"),
            name_filter,
        )
        if not filepath:
            return None
        filepath = _ensure_suffix(filepath, default_suffix)
        try:
            exporter(self._dataset, filepath)  # type: ignore[misc]
        except Exception as error:
            QMessageBox.warning(self, title, str(error))
            return None
        self.status_message_changed.emit(f"Exported: {filepath}")
        return filepath

    def _allow_saved_alignment_export(self, title: str) -> bool:
        """Prevent an export from silently using the previous revision.

        The existing exporters intentionally receive the immutable
        ``AlignmentDataset``.  While the editor contains pending edits, that
        object is the prior scientific state, so exporting it would otherwise
        disagree with the visible grid.
        """

        if not self.is_dirty:
            return True
        message = "Save or discard pending alignment edits before exporting."
        self.status_message_changed.emit(message)
        QMessageBox.warning(self, title, message)
        return False

    def _notify_exclusion_contract(self, target: str) -> None:
        """Make the v1.0 retain-and-annotate exclusion default explicit.

        Existing exporters and analysis runners intentionally receive the
        immutable AlignmentDataset and therefore retain every column.  Pending
        exclusions are recorded only when an edited revision is saved; no
        downstream scientific default is silently changed in the editor.
        """

        if self._excluded_column_ids:
            self.status_message_changed.emit(
                f"{target}: excluded columns are retained by the current default; "
                "save to annotate the edited revision."
            )

    def _default_export_path(self, filename: str) -> str:
        controller = getattr(self._context, "project_controller", None)
        directory_getter = getattr(controller, "export_default_directory", None)
        if not callable(directory_getter):
            return filename
        try:
            directory = str(directory_getter() or "")
        except Exception:
            return filename
        return str(Path(directory) / filename) if directory else filename

    def request_rename_selected_row(self) -> bool:
        selected = [row_id for row_id in self._grid.selected_rows() if row_id != "__consensus__"]
        if len(selected) != 1:
            self.status_message_changed.emit("Select exactly one row to rename.")
            return False
        row_id = selected[0]
        current = self._record_labels.get(row_id, row_id)
        new_label, accepted = QInputDialog.getText(
            self,
            "Rename Alignment Row",
            "New row name:",
            text=current,
        )
        if not accepted:
            return False
        try:
            return self.rename_selected_row(new_label)
        except ValueError as exc:
            QMessageBox.warning(self, "Rename Alignment Row", str(exc))
            return False

    def request_delete_selected_rows(self) -> bool:
        # Native modal dialogs may cause a view to lose its transient Qt
        # selection.  Capture durable record IDs first, then use this exact
        # collection after confirmation.
        row_ids = tuple(row_id for row_id in self._grid.selected_rows() if row_id != "__consensus__")
        if not row_ids:
            self.status_message_changed.emit("Select one or more rows to delete from the derived alignment.")
            return False
        editable_message = self._alignment_editability_error()
        if editable_message is not None:
            QMessageBox.warning(self, "Delete Rows", editable_message)
            self.status_message_changed.emit(editable_message)
            return False
        response = QMessageBox.question(
            self,
            "Delete Rows from Derived Alignment",
            "Delete selected rows from the next saved derived AlignmentDataset?\n"
            "The source AlignmentDataset is not modified.",
        )
        if response != QMessageBox.StandardButton.Yes:
            return False
        return self._delete_rows_from_derived_dataset(row_ids)

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        operation = self._undo_stack.pop()
        operation.revert(self)
        self._redo_stack.append(operation)
        self.refresh(reset_grid_selection=isinstance(operation, (DeleteRowsOperation, DeleteColumnsOperation)))
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        operation = self._redo_stack.pop()
        operation.apply(self)
        self._undo_stack.append(operation)
        self.refresh(reset_grid_selection=isinstance(operation, (DeleteRowsOperation, DeleteColumnsOperation)))
        return True

    def create_edited_alignment_dataset(
        self,
        *,
        alignment_id: str,
        name: str,
        metadata: dict[str, object] | None = None,
    ) -> AlignmentDataset:
        records = tuple(
            self._create_edited_record(record)
            for record in self._dataset.records
            if record.record_id not in self._deleted_row_ids
        )
        return AlignmentDataset(
            alignment_id=alignment_id,
            name=name,
            parent_dataset_id=self._dataset.parent_dataset_id,
            records=records,
            marker_regions=() if self._deleted_column_ids else self._dataset.marker_regions,
            metadata={
                **dict(self._dataset.metadata),
                "source_alignment_id": self._dataset.alignment_id,
                "derived_from": "ALIGNMENT_EDITOR",
                "edited_cells": tuple(sorted(self._edited_cells())),
                "excluded_columns": tuple(sorted(self._current_excluded_columns())),
                "renamed_rows": {
                    record_id: label
                    for record_id, label in self._record_labels.items()
                    if label != record_id
                },
                "deleted_rows": tuple(sorted(self._deleted_row_ids)),
                "deleted_columns": tuple(sorted(self._deleted_column_ids)),
                "marker_regions_invalidated_by_deleted_columns": bool(self._deleted_column_ids),
                **(metadata or {}),
            },
        )

    def _create_edited_record(self, record: AlignmentRecord) -> AlignmentRecord:
        """Preserve current-column to original-evidence mapping in metadata.

        Physical column deletion changes the display alignment coordinate but
        must never cause downstream chromatogram review to shift an ungapped
        base onto the next raw AB1 peak.  These values are presentation
        lineage metadata, not a new scientific alignment algorithm.
        """

        record_metadata = dict(record.metadata)
        root_sequence = str(
            record_metadata.get("source_alignment_sequence", record.aligned_sequence)
        )
        inherited_columns = tuple(
            int(value)
            for value in record_metadata.get(
                "source_alignment_columns", tuple(range(len(record.aligned_sequence)))
            )
        )
        if len(inherited_columns) != len(record.aligned_sequence):
            inherited_columns = tuple(range(len(record.aligned_sequence)))
            root_sequence = record.aligned_sequence
        current_source_columns = tuple(
            inherited_columns[column_id]
            for column_id in self._column_ids
            if 0 <= column_id < len(inherited_columns)
        )
        return AlignmentRecord(
            record_id=self._record_labels.get(record.record_id, record.record_id),
            source_record_id=record.source_record_id,
            aligned_sequence="".join(self._edited_sequences[record.record_id]),
            metadata={
                **record_metadata,
                "source_record_id_before_edit": record.record_id,
                "original_aligned_sequence": record.aligned_sequence,
                "source_alignment_sequence": root_sequence,
                "source_alignment_columns": current_source_columns,
                "edited_positions": tuple(
                    position
                    for position, base in enumerate(self._edited_sequences[record.record_id])
                    if base != record.aligned_sequence[self._column_ids[position]]
                ),
            },
        )

    def save_edited_alignment(self) -> AlignmentDataset | None:
        controller = getattr(self._context, "project_controller", None)
        register_method = getattr(controller, "register_edited_alignment_from_viewer", None)
        if not callable(register_method):
            self.status_message_changed.emit("Project registration is not configured.")
            return None
        try:
            dataset = register_method(self)
        except ValueError as error:
            self.status_message_changed.emit(str(error))
            QMessageBox.warning(self, "Save Edited Alignment", str(error))
            return None
        # The immutable revision is now registered.  This viewer becomes a
        # stale read-only view, not a second unsaved editing session.
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.status_message_changed.emit(f"Edited AlignmentDataset created: {dataset.alignment_id}")
        return dataset

    def close_viewer(self) -> bool:
        """Protect pending scientific edits; viewer-only Hide is not dirty."""

        intent = self.prepare_close()
        return intent is not None and self.commit_close(intent)

    def prepare_close(self) -> str | None:
        """Ask for an Alignment close intent without changing the working copy."""

        if not self.has_pending_scientific_changes:
            return "close"
        choice = QMessageBox.warning(
            self,
            "Unsaved Alignment Edits",
            "This Alignment has pending scientific edits.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return None
        if choice == QMessageBox.StandardButton.Save:
            return "save"
        return "discard"

    def commit_close(self, intent: object) -> bool:
        """Apply an already-confirmed Alignment close intent."""

        if intent == "save":
            return self.save_edited_alignment() is not None
        return True

    def refresh(self, *, reset_grid_selection: bool = False) -> None:
        remaining = self._dataset.sequence_count - len(self._deleted_row_ids)
        summary = [
            f"Sequences: {remaining}",
            f"Alignment length: {self.current_alignment_length}",
            (
                "Editing working copy • Unsaved edits"
                if self.is_dirty
                else "Editing working copy • No unsaved edits"
            ),
        ]
        if self._deleted_row_ids:
            count = len(self._deleted_row_ids)
            summary.insert(1, f"Unsaved changes • {count} row{'s' if count != 1 else ''} deleted")
        if self._deleted_column_ids:
            count = len(self._deleted_column_ids)
            summary.insert(1, f"Unsaved changes • {count} column{'s' if count != 1 else ''} deleted")
        if self._undo_stack and not self._deleted_row_ids and not self._deleted_column_ids:
            summary.insert(1, "Unsaved scientific changes")
        if self._hidden_row_ids:
            summary.append(f"{len(self._hidden_row_ids)} temporarily hidden")
        if self._excluded_column_ids:
            summary.append(f"{len(self._excluded_column_ids)} excluded (retained)")
        self._summary.setText("    •    ".join(summary))
        self._manual_edit_legend.setVisible(bool(self._edited_cells()))
        self._save_revision_button.setEnabled(
            self.is_dirty and self._alignment_editability_error() is None
        )
        self._populate_table(reset_grid_selection=reset_grid_selection)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        self._manual_edit_legend = QLabel(
            "Blue cells are manually edited bases in this working copy."
        )
        self._manual_edit_legend.setToolTip(
            "These edits are not written to the source Alignment. Save Changes as New Revision "
            "to create a new immutable Alignment revision."
        )
        self._save_revision_button = QPushButton("Save Changes as New Revision")
        self._save_revision_button.setObjectName("saveChangesAsNewRevisionButton")
        self._save_revision_button.setToolTip(
            "Save this working copy as a new immutable Alignment revision. "
            "The current revision remains preserved."
        )
        self._save_revision_button.clicked.connect(self.save_edited_alignment)
        layout.addWidget(self._summary)
        layout.addWidget(self._manual_edit_legend)
        self._status = QLabel("Select an alignment cell or column.")
        layout.addWidget(self._status)
        layout.addWidget(self._save_revision_button)
        self._grid = SequenceGridWidget()
        self._grid.setObjectName("alignmentViewerSequenceGrid")
        self._grid.cell_selected.connect(self._grid_cell_selected)
        self._grid.column_selected.connect(self._grid_column_selected)
        self._grid.cell_edited.connect(self._grid_cell_edited)
        self._grid.undo_requested.connect(self.undo)
        self._grid.redo_requested.connect(self.redo)
        self._grid.paste_requested.connect(self.paste_selection)
        self._grid.selection_changed.connect(self._grid_selection_changed)
        self._grid.set_context_menu_handler(self._show_grid_context_menu)
        self._grid.set_inline_rename_handler(self._commit_inline_row_rename)
        self._table = self._grid
        layout.addWidget(self._grid, 1)
        self.refresh()

    def show_revision_saved_feedback(self, message: str) -> None:
        """Show Controller-confirmed immutable-revision feedback in the new editor."""

        self._status.setText(str(message))
        self._status.setToolTip(
            "The source Alignment revision remains preserved. Use Save Project to persist "
            "the Project and its new revision to disk."
        )
        self.status_message_changed.emit(str(message))

    def _show_grid_context_menu(self, selection: object, global_position: object) -> None:
        """Expose alignment editing where the selection is made, not in a long toolbar."""

        menu = QMenu(self)
        mode = getattr(selection, "mode", "none")
        if mode == "row":
            selected_count = len(self._selected_editable_row_ids())
            rename = menu.addAction(studio_icon("rename"), "Rename Row…")
            rename.setEnabled(selected_count == 1)
            rename.triggered.connect(self.request_rename_selected_row)
            hide = menu.addAction(studio_icon("hide"), "Hide Selected Rows (Viewer Only)")
            hide.setEnabled(bool(selected_count))
            hide.triggered.connect(self.hide_selected_rows)
            delete = menu.addAction(studio_icon("delete"), "Delete Row(s)…")
            delete.setEnabled(bool(selected_count))
            delete.triggered.connect(self.request_delete_selected_rows)
            copy = menu.addAction(studio_icon("copy"), "Copy Sequence")
            copy.setEnabled(bool(self._grid.selected_rows()))
            copy.triggered.connect(self.copy_selection)
            menu.addSeparator()
            show_all = menu.addAction(studio_icon("show"), "Show All Rows")
            show_all.triggered.connect(self.show_all_rows)
            review = menu.addAction(studio_icon("evidence"), "Review Alignment Chromatograms")
            review.triggered.connect(self.review_chromatograms)
        elif mode == "column":
            exclude = menu.addAction(studio_icon("hide"), "Exclude Selected Column(s)")
            exclude.setEnabled(self._alignment_editability_error() is None)
            exclude.triggered.connect(self.exclude_selected_columns)
            include = menu.addAction(studio_icon("show"), "Include Selected Column(s)")
            include.setEnabled(self._alignment_editability_error() is None)
            include.triggered.connect(self.include_selected_columns)
            delete = menu.addAction(studio_icon("delete"), "Delete Selected Columns…")
            delete.setEnabled(self._alignment_editability_error() is None and self.current_alignment_length > len(self._grid.selected_columns()))
            delete.triggered.connect(self.request_delete_selected_columns)
        elif mode != "none":
            copy = menu.addAction(studio_icon("copy"), "Copy")
            copy.triggered.connect(self.copy_selection)
            paste = menu.addAction(studio_icon("paste"), "Paste (Substitution Only)")
            paste.setEnabled(self._alignment_editability_error() is None)
            paste.triggered.connect(self.paste_selection)
            bases = menu.addMenu("Set Base")
            for base, label in (("A", "A"), ("C", "C"), ("G", "G"), ("T", "T"), ("N", "N"), ("-", "Gap")):
                action = bases.addAction(label)
                action.triggered.connect(lambda _checked=False, value=base: self.request_set_selection_to_base(value))
            menu.addSeparator()
            undo = menu.addAction(studio_icon("undo"), "Undo")
            undo.setEnabled(bool(self._undo_stack))
            undo.triggered.connect(self.undo)
            redo = menu.addAction(studio_icon("redo"), "Redo")
            redo.setEnabled(bool(self._redo_stack))
            redo.triggered.connect(self.redo)
        if menu.actions():
            menu.exec(global_position)

    def _selected_editable_row_ids(self) -> tuple[str, ...]:
        return tuple(
            row_id for row_id in self._grid.selected_rows()
            if row_id != "__consensus__" and row_id in self._edited_sequences
        )

    def _populate_table(self, *, reset_grid_selection: bool = False) -> None:
        rows = (
            SequenceGridRow(
                row_id="__consensus__",
                label="Consensus",
                sequence=self._transient_consensus_sequence(),
            ),
        ) + tuple(
            SequenceGridRow(
                row_id=record.record_id,
                label=self._record_labels.get(record.record_id, record.record_id),
                sequence="".join(self._edited_sequences[record.record_id]),
                editable=True,
            )
            for record in self._dataset.records
            if record.record_id not in self._hidden_row_ids and record.record_id not in self._deleted_row_ids
        )
        self._grid.set_rows(
            rows,
            edited_cells=self._edited_cells(),
            preserve_selection=not reset_grid_selection,
        )
        self._grid.set_excluded_columns(self._current_excluded_columns())

    def _alignment_editability_error(self) -> str | None:
        """Return a user-facing reason an immutable Project revision cannot edit."""

        state = getattr(self._context, "app_state", None)
        project = getattr(state, "current_project", None)
        if project is None:
            return None
        try:
            entry = project.get_entry(self._dataset.alignment_id)
        except (KeyError, ValueError):
            # Standalone/unregistered AlignmentViewer instances remain useful
            # for review and test fixtures; saving still requires a Project.
            return None
        if entry.revision_state is RevisionState.ARCHIVED:
            return "This Alignment is archived. Restore it before editing rows."
        if not project.is_current_revision(self._dataset.alignment_id):
            return "This Alignment revision is no longer current. Open the current revision before editing rows."
        return None

    def _grid_cell_selected(self, row_id: str, column_index: int, base: str) -> None:
        if row_id == "__consensus__":
            self.select_column(column_index)
            return
        row_index = next(
            (
                index
                for index, record in enumerate(self._dataset.records)
                if record.record_id == row_id
            ),
            -1,
        )
        if row_index >= 0:
            self.select_alignment_cell(row_index, column_index)

    def _grid_cell_edited(self, row_id: str, column_index: int, base: str) -> None:
        if row_id == "__consensus__":
            return
        self.set_base(row_id, column_index, base)

    def _grid_selection_changed(self, _selection: object) -> None:
        if self._grid.selection.is_single_cell:
            return
        self._selected_cell = None
        self._selected_column = None
        self._status.setText(self._grid.selection_status_text())

    def _grid_column_selected(self, column_index: int) -> None:
        if column_index < 0 or column_index >= self.current_alignment_length:
            return
        self._selected_column = column_index + 1
        self._selected_cell = None
        self._status.setText(f"Column: {column_index + 1}")

    def _evidence_status(self, record: AlignmentRecord, column_index: int, base: str) -> str:
        """Show evidence only when the existing alignment record retains a SangerRead."""

        prefix = f"Sample: {record.record_id}    Alignment column: {column_index + 1}    Base: {base}"
        source = record.metadata.get("source_reference") if record.metadata else None
        if not isinstance(source, SangerRead):
            source = _source_read_for_alignment_record(self._dataset, record.record_id, self._context)
        if not isinstance(source, SangerRead) or base == "-":
            return prefix
        mapping = alignment_to_trace_positions(record.aligned_sequence, source)
        trace_position = mapping.get(column_index + 1)
        if trace_position is None:
            return prefix
        raw_positions = tuple(getattr(source, "trimmed_base_positions", ()) or ())
        try:
            trimmed_index = raw_positions.index(trace_position)
        except ValueError:
            trimmed_index = None
        raw_index = None
        if trimmed_index is not None:
            raw_index = int(getattr(source, "trim_start", 0) or 0) + trimmed_index
        quality = None
        trimmed_quality = tuple(getattr(source, "trimmed_quality", ()) or ())
        if trimmed_index is not None and trimmed_index < len(trimmed_quality):
            quality = trimmed_quality[trimmed_index]
        details = []
        if quality is not None:
            details.append(f"Quality: Q{quality}")
        if raw_index is not None:
            details.append(f"Raw base: {raw_index + 1}")
        details.append(f"Trace: {trace_position}")
        return prefix + "    " + "    ".join(details)

    def _original_sequence(self, record_id: str) -> str:
        for record in self._dataset.records:
            if record.record_id == record_id:
                return record.aligned_sequence
        raise KeyError(record_id)

    def _record_index(self, record_id: str) -> int:
        for index, record in enumerate(self._dataset.records):
            if record.record_id == record_id:
                return index
        raise KeyError(record_id)

    def _edited_cells(self) -> set[tuple[str, int]]:
        edited: set[tuple[str, int]] = set()
        for record in self._dataset.records:
            current = self._edited_sequences[record.record_id]
            edited.update(
                (record.record_id, position)
                for position, base in enumerate(current)
                if base != record.aligned_sequence[self._column_ids[position]]
            )
        return edited

    def _apply_cell_changes(self, changes: list[tuple[str, int, str, str]] | tuple[tuple[str, int, str, str], ...], *, use_new: bool = True) -> None:
        for record_id, column_index, previous, current in changes:
            value = current if use_new else previous
            self._edited_sequences[record_id][column_index] = value
            self._grid.set_cell_base(
                record_id,
                column_index,
                value,
                edited=value != self._original_sequence(record_id)[self._column_ids[column_index]],
            )

    def _apply_base_changes(self, changes: object, *, use_new: bool = True) -> None:
        """Typed-operation adapter; alignment cells use current editor columns."""

        self._apply_cell_changes(changes, use_new=use_new)

    # PendingEditTarget implementation used by typed editor operations.
    def _set_deleted_row_ids(self, row_ids: frozenset[str]) -> None:
        self._deleted_row_ids = set(row_ids)
        self._selected_cell = None
        self._selected_column = None

    def _set_excluded_column_ids(self, column_ids: frozenset[int]) -> None:
        self._excluded_column_ids = set(column_ids) - self._deleted_column_ids
        self._grid.set_excluded_columns(self._current_excluded_columns())

    def _set_row_label(self, record_id: str, label: str) -> None:
        self._record_labels[record_id] = label

    def _apply_delete_columns(self, column_ids: tuple[int, ...]) -> None:
        indices = sorted((self._column_ids.index(column_id) for column_id in column_ids if column_id in self._column_ids), reverse=True)
        for index in indices:
            for sequence in self._edited_sequences.values():
                sequence.pop(index)
            self._deleted_column_ids.add(self._column_ids.pop(index))
        self._excluded_column_ids.difference_update(column_ids)
        self._selected_cell = None
        self._selected_column = None

    def _revert_delete_columns(self, column_ids: tuple[int, ...], removed: object) -> None:
        values = removed if isinstance(removed, dict) else {}
        for column_id in sorted(column_ids):
            if column_id not in self._deleted_column_ids:
                continue
            index = sum(existing_id < column_id for existing_id in self._column_ids)
            for record_id, sequence in self._edited_sequences.items():
                row_values = values.get(record_id, ())
                offset = tuple(sorted(column_ids)).index(column_id)
                sequence.insert(index, row_values[offset])
            self._column_ids.insert(index, column_id)
            self._deleted_column_ids.remove(column_id)
        self._selected_cell = None
        self._selected_column = None

    def _current_excluded_columns(self) -> set[int]:
        return {
            current_index
            for current_index, column_id in enumerate(self._column_ids)
            if column_id in self._excluded_column_ids
        }

    def _transient_consensus_sequence(self) -> str:
        sequences = (
            "".join(self._edited_sequences[record.record_id])
            for record in self._dataset.records
            if record.record_id not in self._deleted_row_ids
        )
        return _consensus_from_sequences(tuple(sequences))


class AlignmentViewerActionProvider:
    def __init__(self, context: object | None) -> None:
        self._context = context

    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        dataset = getattr(viewer, "_dataset", None)
        context = getattr(viewer, "_context", None)
        has_sanger_reads = bool(
            dataset is not None and _reads_from_alignment_dataset(dataset, context)
        )
        review_available = (
            has_sanger_reads
            and not bool(getattr(viewer, "_deleted_column_ids", ()))
            and getattr(context, "tab_manager", None) is not None
        )
        export_available = not bool(getattr(viewer, "is_dirty", False))
        return (
            ViewerAction(
                action_id="alignment.review_chromatograms",
                label="Review Alignment Chromatograms",
                tooltip="Open alignment-coordinate chromatogram review when Sanger reads are attached",
                callback=getattr(viewer, "review_chromatograms"),
                enabled=review_available,
                toolbar=True,
                menu_group="Align",
                priority=80,
            ),
            ViewerAction(
                action_id="alignment.undo",
                label="Undo",
                tooltip="Undo the latest alignment cell edit",
                callback=getattr(viewer, "undo"),
                toolbar=True,
                menu_group="Edit",
                priority=100,
            ),
            ViewerAction(
                action_id="alignment.redo",
                label="Redo",
                tooltip="Redo the latest alignment cell edit",
                callback=getattr(viewer, "redo"),
                toolbar=True,
                menu_group="Edit",
                priority=99,
            ),
            ViewerAction(
                action_id="alignment.copy_selection",
                label="Copy",
                tooltip="Copy selected alignment cells as plain text",
                callback=getattr(viewer, "copy_selection"),
            ),
            ViewerAction(
                action_id="alignment.export_selected_rows_fasta",
                label="Export Selected Rows as FASTA…",
                tooltip="Export each selected AlignmentDataset row in full; the selected column range is ignored and alignment gaps are retained",
                callback=getattr(viewer, "request_export_selected_rows_fasta"),
                enabled=export_available,
            ),
            ViewerAction(
                action_id="alignment.export_selection_fasta",
                label="Export Selected Region as FASTA…",
                tooltip="Export only the selected row × column region as FASTA; alignment gaps in the selected rectangle are retained",
                callback=getattr(viewer, "request_export_selection_fasta"),
                enabled=export_available,
            ),
            ViewerAction(
                action_id="alignment.export_fasta",
                label="Export Full Alignment as FASTA…",
                tooltip="Export every current alignment row as aligned FASTA, preserving gaps and excluded-column annotations",
                callback=getattr(viewer, "request_export_alignment_fasta"),
                enabled=export_available,
            ),
            ViewerAction(
                action_id="alignment.export_nexus",
                label="Export Full Alignment as NEXUS…",
                tooltip="Export every current alignment row as NEXUS, preserving alignment gaps",
                callback=getattr(viewer, "request_export_alignment_nexus"),
                enabled=export_available,
            ),
            ViewerAction(
                action_id="alignment.export_phylip",
                label="Export Full Alignment as PHYLIP…",
                tooltip="Export every current alignment row as PHYLIP, preserving alignment gaps",
                callback=getattr(viewer, "request_export_alignment_phylip"),
                enabled=export_available,
            ),
            ViewerAction(
                action_id="alignment.export_iqtree_partitions",
                label="Export IQ-TREE Partitions",
                tooltip="Export marker regions as IQ-TREE partition definitions",
                callback=getattr(viewer, "request_export_iqtree_partitions"),
                enabled=export_available,
            ),
            ViewerAction(
                action_id="alignment.export_raxml_partitions",
                label="Export RAxML Partitions",
                tooltip="Export marker regions as RAxML partition definitions",
                callback=getattr(viewer, "request_export_raxml_partitions"),
                enabled=export_available,
            ),
            ViewerAction(
                action_id="alignment.export_nexus_charsets",
                label="Export NEXUS Charsets",
                tooltip="Export marker regions as NEXUS CHARSET declarations",
                callback=getattr(viewer, "request_export_nexus_charsets"),
                enabled=export_available,
            ),
            ViewerAction(
                action_id="alignment.run_blast",
                label="BLAST…",
                tooltip="Choose NCBI Online or the official NCBI Website workflow after removing gaps",
                callback=getattr(viewer, "run_blast"),
                toolbar=True,
                menu_group="Identify",
                priority=70,
            ),
            ViewerAction(
                action_id="alignment.exclude_columns",
                label="Exclude Selected Columns",
                tooltip="Mark selected alignment columns as excluded without deleting them",
                callback=getattr(viewer, "exclude_selected_columns"),
            ),
            ViewerAction(
                action_id="alignment.include_columns",
                label="Include Selected Columns",
                tooltip="Unmark selected alignment columns as excluded",
                callback=getattr(viewer, "include_selected_columns"),
            ),
            ViewerAction(
                action_id="alignment.delete_selected_columns",
                label="Delete Columns",
                tooltip="Delete selected columns in the next saved Alignment revision",
                callback=getattr(viewer, "request_delete_selected_columns"),
                enabled=getattr(viewer, "_alignment_editability_error")() is None,
            ),
            ViewerAction(
                action_id="alignment.paste",
                label="Paste",
                tooltip="Paste A/C/G/T/N/- substitutions without changing alignment length",
                callback=getattr(viewer, "paste_selection"),
                enabled=getattr(viewer, "_alignment_editability_error")() is None,
            ),
            ViewerAction(
                action_id="alignment.hide_rows",
                label="Hide Rows",
                tooltip="Temporarily hide selected rows in this viewer only",
                callback=getattr(viewer, "hide_selected_rows"),
            ),
            ViewerAction(
                action_id="alignment.show_all_rows",
                label="Show All Rows",
                tooltip="Show all hidden rows",
                callback=getattr(viewer, "show_all_rows"),
            ),
            ViewerAction(
                action_id="alignment.rename_selected_row",
                label="Rename Row",
                tooltip="Rename one selected row in the next saved derived AlignmentDataset",
                callback=getattr(viewer, "request_rename_selected_row"),
            ),
            ViewerAction(
                action_id="alignment.delete_selected_rows",
                label="Delete Rows",
                tooltip="Mark selected rows for removal from the next saved AlignmentDataset revision",
                callback=getattr(viewer, "request_delete_selected_rows"),
            ),
            ViewerAction(
                action_id="alignment.set_selection_a",
                label="Set Selection to A",
                tooltip="Set editable selected cells to A as one undoable operation",
                callback=lambda: viewer.request_set_selection_to_base("A"),
            ),
            ViewerAction(
                action_id="alignment.set_selection_c",
                label="Set Selection to C",
                tooltip="Set editable selected cells to C as one undoable operation",
                callback=lambda: viewer.request_set_selection_to_base("C"),
            ),
            ViewerAction(
                action_id="alignment.set_selection_g",
                label="Set Selection to G",
                tooltip="Set editable selected cells to G as one undoable operation",
                callback=lambda: viewer.request_set_selection_to_base("G"),
            ),
            ViewerAction(
                action_id="alignment.set_selection_t",
                label="Set Selection to T",
                tooltip="Set editable selected cells to T as one undoable operation",
                callback=lambda: viewer.request_set_selection_to_base("T"),
            ),
            ViewerAction(
                action_id="alignment.set_selection_gap",
                label="Set Selection to Gap",
                tooltip="Set editable selected cells to gap as one undoable operation",
                callback=getattr(viewer, "request_set_selection_to_gap"),
            ),
            ViewerAction(
                action_id="alignment.set_selection_n",
                label="Set Selection to N",
                tooltip="Set editable selected cells to N as one undoable operation",
                callback=getattr(viewer, "request_set_selection_to_n"),
            ),
            ViewerAction(
                action_id="alignment.save_edited_alignment",
                label="Save Changes as New Revision",
                tooltip="Save edits as a new immutable Alignment revision. The previous revision is preserved.",
                callback=getattr(viewer, "save_edited_alignment"),
                toolbar=True,
                menu_group="Dataset",
                priority=110,
            ),
        )


@dataclass(frozen=True)
class _AlignmentRecord:
    id: str
    seq: str


def create_alignment_viewer(context: object, dataset: object) -> AlignmentViewer:
    return AlignmentViewer(dataset, context=context)


def _consensus_sequence(dataset: AlignmentDataset) -> str:
    return _consensus_from_sequences(tuple(record.aligned_sequence for record in dataset.records))


def _consensus_from_sequences(sequences: tuple[str, ...]) -> str:
    """Display-only consensus for the current editor state.

    Hidden rows are deliberately supplied by callers: viewer-only filtering
    must not alter this calculation; pending deleted rows are omitted.
    """

    if not sequences:
        return ""
    bases: list[str] = []
    for column in range(len(sequences[0])):
        counts = Counter(
            sequence[column]
            for sequence in sequences
            if sequence[column] != "-"
        )
        if not counts:
            bases.append("-")
        else:
            bases.append(counts.most_common(1)[0][0])
    return "".join(bases)


def _reads_from_alignment_dataset(
    dataset: AlignmentDataset,
    context: object | None = None,
) -> tuple[SangerRead, ...]:
    metadata_reads = dataset.metadata.get("source_reads") if dataset.metadata else None
    if metadata_reads:
        reads = tuple(read for read in metadata_reads if isinstance(read, SangerRead))
        if reads:
            return reads
    project = getattr(getattr(context, "app_state", None), "project", None)
    if project is not None:
        try:
            parent_dataset = project.get_dataset(dataset.parent_dataset_id)
        except (AttributeError, KeyError):
            parent_dataset = None
        if parent_dataset is not None:
            by_id = {
                getattr(record, "sequence_id", None): getattr(record, "source_reference", None)
                for record in getattr(parent_dataset, "records", ())
            }
            reads = tuple(
                by_id.get(record.source_record_id)
                for record in dataset.records
                if isinstance(by_id.get(record.source_record_id), SangerRead)
            )
            if reads:
                return reads
    reads: list[SangerRead] = []
    for record in dataset.records:
        source = record.metadata.get("source_reference") if record.metadata else None
        if isinstance(source, SangerRead):
            reads.append(source)
    return tuple(reads)


def _source_read_for_alignment_record(
    dataset: AlignmentDataset,
    record_id: str,
    context: object | None,
) -> SangerRead | None:
    """Resolve an existing attached source read without inventing a mapping."""

    record = next((item for item in dataset.records if item.record_id == record_id), None)
    if record is None:
        return None
    project = getattr(getattr(context, "app_state", None), "project", None)
    if project is not None:
        try:
            parent_dataset = project.get_dataset(dataset.parent_dataset_id)
        except (AttributeError, KeyError):
            parent_dataset = None
        if parent_dataset is not None:
            parent_record = next(
                (
                    item
                    for item in getattr(parent_dataset, "records", ())
                    if getattr(item, "sequence_id", None) == record.source_record_id
                ),
                None,
            )
            source = getattr(parent_record, "source_reference", None)
            if isinstance(source, SangerRead):
                return source
    source = record.metadata.get("source_reference") if record.metadata else None
    if isinstance(source, SangerRead):
        return source
    return None


def _safe_identifier(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in str(value)
    )


def _ensure_suffix(filepath: str, suffix: str) -> str:
    path = Path(filepath)
    if path.suffix:
        return str(path)
    return str(path.with_suffix(suffix))
