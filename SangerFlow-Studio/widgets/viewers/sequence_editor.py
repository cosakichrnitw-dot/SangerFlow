"""Unaligned Sequence Editor backed by the Studio-only editor document."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from core.models import SangerRead
from core.project import RevisionState
from core.sequence_dataset import SequenceDataset, SourceType
from export.sequence_export import export_dataset_to_fasta, export_dataset_to_nexus, export_dataset_to_phylip
from app.selection import SelectionKind, StudioSelection
from app.icon_registry import studio_icon
from widgets.sequence_editor_document import SequenceEditorDocument, SequenceEditorMode
from widgets.sequence_grid import SequenceGridRow, SequenceGridWidget
from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.viewer_actions import ViewerAction


_EDITABLE_SYMBOLS = frozenset("ACGTNRYSWKMBDHV-")


class SequenceEditor(BaseViewer):
    """Mesquite-like editor for one immutable, unaligned SequenceDataset revision."""

    def __init__(self, dataset: SequenceDataset, *, context: object | None = None) -> None:
        if not isinstance(dataset, SequenceDataset):
            raise ValueError("Sequence Editor — Unaligned requires a SequenceDataset")
        self._dataset = dataset
        self._context = context
        self._document = SequenceEditorDocument(dataset, mode=SequenceEditorMode.UNALIGNED)
        self._selected: tuple[str, int] | None = None
        super().__init__(
            viewer_id=f"sequence-editor-unaligned-{dataset.dataset_id}",
            viewer_title=f"Sequence Editor — Unaligned: {dataset.name}",
            viewer_kind="sequence-editor-unaligned",
            source_object_id=dataset.dataset_id,
        )
        self._build_ui()

    @property
    def dataset(self) -> SequenceDataset:
        return self._dataset

    @property
    def document(self) -> SequenceEditorDocument:
        return self._document

    @property
    def is_dirty(self) -> bool:
        return self._document.is_dirty

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (_SequenceEditorActionProvider(self._context),)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return tuple(action.action_id for action in self.action_providers[0].actions_for(self))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        self._status = QLabel("Select a base to edit or review source evidence.")
        layout.addWidget(self._summary)
        layout.addWidget(self._status)
        self._grid = SequenceGridWidget(self)
        self._grid.setObjectName("unalignedSequenceEditorGrid")
        self._grid.cell_selected.connect(self._cell_selected)
        self._grid.cell_edited.connect(self._cell_edited)
        self._grid.undo_requested.connect(self.undo)
        self._grid.redo_requested.connect(self.redo)
        self._grid.paste_requested.connect(self.paste_selection)
        self._grid.set_context_menu_handler(self._show_context_menu)
        self._grid.set_inline_rename_handler(self._commit_inline_row_rename)
        layout.addWidget(self._grid, 1)
        self.refresh()

    def refresh(self) -> None:
        rows = tuple(
            SequenceGridRow(
                row_id=row_id,
                label=self._document.label(row_id),
                sequence=self._document.sequence(row_id),
                editable=True,
            )
            for row_id in self._document.visible_row_ids()
        )
        edited = {
            (row.row_id, position)
            for row in self._document.rows
            if row.row_id not in self._document.deleted_row_ids
            for position, base in enumerate(self._document.sequence(row.row_id))
            if base != self._document.original_sequence(row.row_id)[position]
        }
        self._grid.set_rows(rows, edited_cells=edited)
        pending = []
        if self._document.is_dirty:
            pending.append("Unsaved scientific changes")
        if self._document.deleted_row_ids:
            pending.append(f"{len(self._document.deleted_row_ids)} pending deletion")
        if self._document.hidden_row_ids:
            pending.append(f"{len(self._document.hidden_row_ids)} temporarily hidden")
        suffix = " • " + " • ".join(pending) if pending else ""
        self._summary.setText(f"{len(rows)} sequences • Unaligned{suffix}")
        self._is_dirty = self._document.is_dirty

    def _cell_selected(self, row_id: str, column: int, base: str) -> None:
        self._selected = (row_id, column)
        self._status.setText(self.evidence_status(row_id, column, base))
        self.selection_changed.emit(
            StudioSelection(
                kind=SelectionKind.SEQUENCE_RECORD,
                object_id=row_id,
                payload={"record_id": row_id, "column": column, "base": base},
                source_viewer_id=self.viewer_id,
            )
        )

    def _cell_edited(self, row_id: str, column: int, base: str) -> None:
        self.set_base(row_id, column, base)

    def set_base(self, row_id: str, column: int, base: str) -> bool:
        base = str(base).upper()
        if base not in _EDITABLE_SYMBOLS:
            return False
        if self._editability_error() is not None:
            self._status.setText(self._editability_error() or "Editing unavailable")
            return False
        changed = self._document.set_base(row_id, column, base)
        if changed:
            self.refresh()
            self._grid.select_cell(row_id, column, emit=False)
        return changed

    def rename_selected_row(self, name: str | None = None) -> bool:
        row_ids = self._grid.selected_rows()
        if len(row_ids) != 1:
            return False
        if name is None:
            name, accepted = QInputDialog.getText(self, "Rename Row", "Record name:", text=self._document.label(row_ids[0]))
            if not accepted:
                return False
        changed = self._document.rename(row_ids[0], name)
        if changed:
            self.refresh()
        return changed

    def hide_selected_rows(self) -> bool:
        row_ids = self._grid.selected_rows()
        if not row_ids:
            return False
        self._document.set_hidden(row_ids)
        self.refresh()
        return True

    def _commit_inline_row_rename(self, row_id: str, name: str) -> bool:
        """Use the existing staged document rename operation for inline edits."""

        self._grid.select_row(row_id)
        changed = self.rename_selected_row(name)
        if not changed:
            self._status.setText("Row name must be non-empty and unique.")
        return changed

    def show_all_rows(self) -> None:
        self._document.show_all_rows()
        self.refresh()

    def delete_selected_rows(self) -> bool:
        if self._editability_error() is not None:
            return False
        changed = self._document.delete_rows(self._grid.selected_rows())
        if changed:
            self.refresh()
        return changed

    def undo(self) -> bool:
        changed = self._document.undo()
        if changed:
            self.refresh()
        return changed

    def redo(self) -> bool:
        changed = self._document.redo()
        if changed:
            self.refresh()
        return changed

    def copy_selection(self) -> str:
        return self._grid.copy_selection_to_clipboard()

    def paste_selection(self, text: str | None = None) -> bool:
        if self._editability_error() is not None or self._grid.selection.is_empty:
            return False
        if text is None:
            text = QApplication.clipboard().text()
        lines = [line.strip().upper() for line in str(text).splitlines()]
        if not lines or any(not line or set(line) - _EDITABLE_SYMBOLS for line in lines):
            self._status.setText("Paste requires DNA/IUPAC symbols only.")
            return False
        selected_rows = self._grid.selected_rows()
        first = self._grid.selection.first_column
        if first is None or len(lines) not in {1, len(selected_rows)}:
            self._status.setText("Paste shape does not match the selected rows.")
            return False
        changes = []
        for index, row_id in enumerate(selected_rows):
            line = lines[0] if len(lines) == 1 else lines[index]
            if not all(self._document.existing_coordinate(row_id, first + offset) for offset in range(len(line))):
                self._status.setText("Paste cannot extend a sequence or fill non-existent cells.")
                return False
            for offset, base in enumerate(line):
                previous = self._document.sequence(row_id)[first + offset]
                if previous != base:
                    changes.append((row_id, first + offset, previous, base))
        if not self._document.apply_paste(tuple(changes)):
            return False
        self.refresh()
        return True

    def evidence_status(self, row_id: str, column: int, current_base: str | None = None) -> str:
        record = self._dataset.get_record(row_id)
        current = current_base or self._document.sequence(row_id)[column]
        original = record.sequence[column]
        source = record.source_reference
        if not isinstance(source, SangerRead):
            return f"Sample: {row_id} • Position: {column + 1} • Current base: {current} • Source evidence unavailable"
        quality = tuple(getattr(source, "quality", ()) or ())
        raw_positions = tuple(getattr(source, "base_positions", ()) or ())
        quality_value = quality[column] if column < len(quality) else None
        trace = raw_positions[column] if column < len(raw_positions) else None
        detail = f"Original evidence base: {original}"
        if quality_value is not None:
            detail += f" • Original quality: Q{quality_value}"
        if trace is not None:
            detail += f" • Raw trace: {trace}"
        return f"Sample: {row_id} • Position: {column + 1} • Current base: {current} • {detail}"

    def review_source_evidence(self) -> bool:
        if self._selected is None:
            return False
        row_id, column = self._selected
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "open_source_chromatogram_for_sequence_editor", None)
        if not callable(method):
            self._status.setText("Source evidence review is unavailable.")
            return False
        return bool(method(self, row_id, column))

    def align_sequences(self) -> object | None:
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "align_sequence_dataset_from_editor", None)
        if not callable(method):
            self._status.setText("Alignment workflow is unavailable.")
            return None
        try:
            return method(self)
        except ValueError as error:
            # QAction callbacks must present ordinary workflow validation in
            # the editor, never leak an exception into Qt's event dispatcher.
            self._status.setText(str(error))
            QMessageBox.warning(self, "Align Sequences", str(error))
            return None

    def save_edited_revision(self) -> object | None:
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "register_edited_sequence_dataset_from_viewer", None)
        if not callable(method):
            self._status.setText("Project revision saving is unavailable.")
            return None
        try:
            return method(self)
        except ValueError as error:
            self._status.setText(str(error))
            QMessageBox.warning(self, "Save Edited Sequences", str(error))
            return None

    def request_export_fasta(self) -> str | None:
        return self._request_export(
            "Export Dataset as FASTA",
            ".fasta",
            "FASTA files (*.fasta *.fas *.fa *.fna);;All files (*)",
            export_dataset_to_fasta,
        )

    def request_export_nexus(self) -> str | None:
        return self._request_export(
            "Export Dataset as NEXUS",
            ".nex",
            "NEXUS files (*.nex *.nexus);;All files (*)",
            lambda dataset, filepath: export_dataset_to_nexus(
                dataset, filepath, metadata=dataset.metadata
            ),
        )

    def request_export_phylip(self) -> str | None:
        return self._request_export(
            "Export Dataset as PHYLIP",
            ".phy",
            "PHYLIP files (*.phy *.phylip);;All files (*)",
            export_dataset_to_phylip,
        )

    def _request_export(
        self,
        title: str,
        suffix: str,
        name_filter: str,
        exporter: object,
    ) -> str | None:
        """Export the current saved Dataset through the existing exporters.

        A dirty document represents a pending immutable revision.  Requiring a
        revision save first prevents an export label from silently exporting a
        different sequence state than the editor displays.
        """

        if self.is_dirty:
            self._status.setText("Save edited sequences before exporting this Dataset.")
            return None
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            title,
            f"{self._dataset.dataset_id}{suffix}",
            name_filter,
        )
        if not filepath:
            return None
        if not filepath.lower().endswith(suffix):
            filepath += suffix
        try:
            exporter(self._dataset, filepath)  # type: ignore[misc]
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, title, str(error))
            return None
        self.status_message_changed.emit(f"Exported: {filepath}")
        return filepath

    def create_edited_sequence_dataset(self, *, dataset_id: str, name: str, metadata: dict[str, object] | None = None) -> SequenceDataset:
        from core.lineage import RecordProvenance, RecordRef
        records = tuple(
            type(record)(
                sequence_id=self._document.label(record.sequence_id),
                sequence=self._document.sequence(record.sequence_id),
                description=record.description,
                source_reference=record.source_reference,
                metadata=record.metadata,
                provenance=RecordProvenance((RecordRef(self._dataset.dataset_id, record.sequence_id),)),
            )
            for record in self._dataset.records
            if record.sequence_id not in self._document.deleted_row_ids
        )
        return SequenceDataset(
            dataset_id=dataset_id, name=name, source_type=self._dataset.source_type,
            records=records,
            metadata={**dict(self._dataset.metadata), "source_dataset_id": self._dataset.dataset_id, "derived_from": "SEQUENCE_EDIT", **(metadata or {})},
        )

    def _editability_error(self) -> str | None:
        state = getattr(self._context, "app_state", None)
        project = getattr(state, "current_project", None)
        if project is None:
            return None
        try:
            entry = project.get_entry(self._dataset.dataset_id)
        except (KeyError, ValueError):
            return None
        if entry.revision_state is RevisionState.ARCHIVED:
            return "This Dataset is archived. Restore it before editing."
        if not project.is_current_revision(self._dataset.dataset_id):
            return "This Dataset revision is no longer current. Open the current revision."
        return None

    def _show_context_menu(self, selection: object, global_position: object) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        mode = getattr(selection, "mode", "none")
        if mode == "row":
            count = len(self._grid.selected_rows())
            rename = menu.addAction(studio_icon("rename"), "Rename Row…")
            rename.setEnabled(count == 1)
            rename.setToolTip("Rename one record in the next saved Dataset revision")
            rename.triggered.connect(self.rename_selected_row)
            hide = menu.addAction(studio_icon("hide"), f"Hide {count} Selected Row{'s' if count != 1 else ''} (Viewer Only)")
            hide.setToolTip("Temporarily hide these rows in this viewer. The Dataset is unchanged.")
            hide.triggered.connect(self.hide_selected_rows)
            delete = menu.addAction(studio_icon("delete"), f"Delete {count} Row{'s' if count != 1 else ''} from Next Revision…")
            delete.setToolTip("Mark these rows for removal only when a new Dataset revision is saved.")
            delete.triggered.connect(self.delete_selected_rows)
            menu.addAction(studio_icon("show"), "Show All Rows", self.show_all_rows)
        elif mode != "none":
            menu.addAction(studio_icon("copy"), "Copy", self.copy_selection)
            menu.addAction(studio_icon("paste"), "Paste (Within Existing Coordinates)", self.paste_selection)
            bases = menu.addMenu("Set Base")
            for base, label in (("A", "A"), ("C", "C"), ("G", "G"), ("T", "T"), ("N", "N")):
                action = bases.addAction(label)
                action.setToolTip(f"Set the selected existing sequence coordinates to {label}")
                action.triggered.connect(lambda _checked=False, value=base: self._set_selected_bases(value))
            menu.addAction(studio_icon("evidence"), "Review Source Evidence…", self.review_source_evidence)
        menu.exec(global_position)

    def _set_selected_bases(self, base: str) -> bool:
        """Apply one requested base to the current rectangular selection."""

        changed = False
        for row_id, column in self._grid.selected_cells():
            changed = self.set_base(row_id, column, base) or changed
        return changed

    def close_viewer(self) -> bool:
        if not self.is_dirty:
            return True
        choice = QMessageBox.question(self, "Unsaved Sequence Edits", "Save edited Dataset revision before closing?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if choice is QMessageBox.StandardButton.Cancel:
            return False
        if choice is QMessageBox.StandardButton.Save:
            return self.save_edited_revision() is not None
        return True


class _SequenceEditorActionProvider:
    def __init__(self, context: object | None) -> None:
        self._context = context

    def actions_for(self, viewer: SequenceEditor) -> tuple[ViewerAction, ...]:
        editable = viewer._editability_error() is None
        controller = getattr(self._context, "project_controller", None)
        selected_record = None
        if viewer._selected is not None:
            try:
                selected_record = viewer.dataset.get_record(viewer._selected[0])
            except KeyError:
                selected_record = None
        reviewed_evidence_available = (
            viewer.dataset.source_type is SourceType.REVIEWED_CONSENSUS
            and bool(
                viewer.dataset.metadata.get("parent_dataset_id")
                or viewer.dataset.metadata.get("source_dataset_id")
            )
            and bool(viewer.dataset.metadata.get("source_sample_id"))
        )
        evidence_available = (
            selected_record is not None
            and (
                isinstance(selected_record.source_reference, SangerRead)
                or reviewed_evidence_available
            )
            and callable(
                getattr(controller, "open_source_chromatogram_for_sequence_editor", None)
            )
        )
        alignment_available = callable(
            getattr(controller, "align_sequence_dataset_from_editor", None)
        )
        export_available = not viewer.is_dirty
        return (
            ViewerAction("sequence_editor.save", "Save Edited Sequences", viewer.save_edited_revision, "Create the next immutable SequenceDataset revision", enabled=editable and viewer.is_dirty, toolbar=True, menu_group="Dataset", priority=100),
            ViewerAction("sequence_editor.undo", "Undo", viewer.undo, "Undo latest sequence edit", toolbar=True, menu_group="Edit", priority=90),
            ViewerAction("sequence_editor.redo", "Redo", viewer.redo, "Redo latest sequence edit", toolbar=True, menu_group="Edit", priority=89),
            ViewerAction("sequence_editor.copy", "Copy", viewer.copy_selection, "Copy selected bases", menu_group="Edit", context_scope="cell"),
            ViewerAction("sequence_editor.paste", "Paste", viewer.paste_selection, "Paste only into existing sequence coordinates", enabled=editable, menu_group="Edit", context_scope="cell"),
            ViewerAction("sequence_editor.rename_row", "Rename Row", viewer.rename_selected_row, "Rename a record in the next revision", enabled=editable, menu_group="Edit", context_scope="row"),
            ViewerAction("sequence_editor.hide_rows", "Hide Rows", viewer.hide_selected_rows, "Temporarily hide selected rows", menu_group="Edit", context_scope="row"),
            ViewerAction("sequence_editor.show_all_rows", "Show All Rows", viewer.show_all_rows, "Restore temporarily hidden rows", menu_group="Edit", context_scope="row"),
            ViewerAction("sequence_editor.delete_rows", "Delete Rows", viewer.delete_selected_rows, "Remove selected rows in the next revision", enabled=editable, menu_group="Edit", context_scope="row"),
            ViewerAction("sequence_editor.review_evidence", "Review Source Evidence…", viewer.review_source_evidence, "Open source chromatogram evidence for the selected base", enabled=evidence_available, toolbar=True, menu_group="Dataset", priority=70),
            ViewerAction("sequence_editor.align", "Align…", viewer.align_sequences, "Create a new AlignmentDataset with MAFFT", enabled=editable and alignment_available, toolbar=True, menu_group="Align", priority=80),
            ViewerAction("sequence_editor.export_fasta", "Export Dataset as FASTA", viewer.request_export_fasta, "Export the current saved SequenceDataset as FASTA", enabled=export_available, menu_group="Export"),
            ViewerAction("sequence_editor.export_nexus", "Export Dataset as NEXUS", viewer.request_export_nexus, "Export the current saved SequenceDataset as NEXUS", enabled=export_available, menu_group="Export"),
            ViewerAction("sequence_editor.export_phylip", "Export Dataset as PHYLIP", viewer.request_export_phylip, "Export the current saved SequenceDataset as PHYLIP", enabled=export_available, menu_group="Export"),
        )


def create_sequence_editor(context: object, dataset: object) -> SequenceEditor:
    return SequenceEditor(dataset, context=context)
