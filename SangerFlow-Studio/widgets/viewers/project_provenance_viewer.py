"""Read-only Project QC & Provenance workspace viewer."""

from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.alignment_dataset import AlignmentDataset
from core.lineage import RecordRef
from core.project import Project
from core.sequence_dataset import SequenceDataset
from services.project_provenance_summary import (
    NO_RECORD,
    ProjectProvenanceSummary,
    build_project_provenance_summary,
)
from services.project_workspace import workspace_for_bundle
from widgets.viewers.base_viewer import BaseViewer


class ProjectProvenanceViewer(BaseViewer):
    """One compact, read-only snapshot of persisted Project QC/provenance."""

    def __init__(self, project: Project, context: object) -> None:
        super().__init__(
            viewer_title="Project QC & Provenance",
            viewer_kind="project-provenance",
            source_object_id=project.project_id,
        )
        self._context = context
        self._project = project
        self._summary: ProjectProvenanceSummary | None = None
        self._record_refs: tuple[RecordRef, ...] = ()
        self._build_ui()
        self._refresh(project)
        state = getattr(context, "app_state", None)
        signal = getattr(state, "project_changed", None)
        if signal is not None:
            signal.connect(self._on_project_changed)

    @property
    def summary(self) -> ProjectProvenanceSummary:
        assert self._summary is not None
        return self._summary

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._overview = QWidget(self)
        self._overview_form = QFormLayout(self._overview)
        layout.addWidget(self._overview)

        splitter = QSplitter(self)
        lineage_box = QWidget(splitter)
        lineage_layout = QVBoxLayout(lineage_box)
        lineage_layout.addWidget(QLabel("Dataset Lineage", lineage_box))
        self._lineage_table = QTableWidget(0, 6, lineage_box)
        self._lineage_table.setHorizontalHeaderLabels(("Dataset", "Type", "Revision", "State", "Operation", "Parent / Source"))
        self._lineage_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._lineage_table.setAlternatingRowColors(True)
        lineage_layout.addWidget(self._lineage_table)
        splitter.addWidget(lineage_box)

        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Per-record Provenance", right))
        pickers = QHBoxLayout()
        self._dataset_picker = QComboBox(right)
        self._record_picker = QComboBox(right)
        pickers.addWidget(self._dataset_picker)
        pickers.addWidget(self._record_picker)
        right_layout.addLayout(pickers)
        self._provenance_tree = QTreeWidget(right)
        self._provenance_tree.setHeaderLabels(("Record / Dataset", "Source Batch", "Source file", "AB1 source", "Review / pairing"))
        right_layout.addWidget(self._provenance_tree)
        splitter.addWidget(right)
        splitter.setSizes((650, 620))
        layout.addWidget(splitter, 1)

        bottom = QSplitter(self)
        identification_box = QWidget(bottom)
        identification_layout = QVBoxLayout(identification_box)
        identification_layout.addWidget(QLabel("Identification / BLAST", identification_box))
        self._identification_table = QTableWidget(0, 10, identification_box)
        self._identification_table.setHorizontalHeaderLabels(("Dataset", "Record", "Scientific Name", "Best Hit", "Identity", "Query Coverage", "Accession", "Result ID", "Reference", "Payload"))
        self._identification_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._identification_table.setAlternatingRowColors(True)
        identification_layout.addWidget(self._identification_table)
        bottom.addWidget(identification_box)

        alignment_box = QWidget(bottom)
        alignment_layout = QVBoxLayout(alignment_box)
        alignment_layout.addWidget(QLabel("Alignment Preparation", alignment_box))
        self._alignment_table = QTableWidget(0, 9, alignment_box)
        self._alignment_table.setHorizontalHeaderLabels(("Alignment", "Rows", "Length", "Parent", "Revision", "State", "Markers", "Excluded", "Deleted / Edited"))
        self._alignment_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._alignment_table.setAlternatingRowColors(True)
        alignment_layout.addWidget(self._alignment_table)
        bottom.addWidget(alignment_box)
        bottom.setSizes((650, 620))
        layout.addWidget(bottom, 1)

        self._dataset_picker.currentIndexChanged.connect(self._populate_record_picker)
        self._record_picker.currentIndexChanged.connect(self._populate_provenance)

    @Slot(object)
    def _on_project_changed(self, project: object) -> None:
        if isinstance(project, Project):
            self._refresh(project)

    def _refresh(self, project: Project) -> None:
        self._project = project
        state = self._context.app_state
        repository = getattr(state, "current_repository", None)
        workspace = workspace_for_bundle(getattr(state, "current_bundle_path", None))
        self._summary = build_project_provenance_summary(
            project,
            result_repository=repository,
            workspace_root=workspace.root if workspace is not None else None,
        )
        overview = self.summary.overview
        while self._overview_form.rowCount():
            self._overview_form.removeRow(0)
        fields = (
            ("Project", overview.project_name),
            ("Dataset entries", str(overview.dataset_count)),
            ("SequenceDatasets", str(overview.sequence_dataset_count)),
            ("AlignmentDatasets", str(overview.alignment_dataset_count)),
            ("Analysis Results", str(overview.analysis_result_count)),
            ("CURRENT / SUPERSEDED / ARCHIVED", f"{overview.current_count} / {overview.superseded_count} / {overview.archived_count}"),
        )
        for label, value in fields:
            self._overview_form.addRow(label + ":", QLabel(value, self._overview))
        self._populate_lineage()
        self._populate_identifications()
        self._populate_alignments()
        self._populate_dataset_picker()

    def _populate_lineage(self) -> None:
        rows = self.summary.lineage
        self._lineage_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (row.display_name, row.dataset_type, f"r{row.revision}", row.state, row.operation, row.sources)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setToolTip(row.dataset_id)
                self._lineage_table.setItem(row_index, column, item)
        self._lineage_table.resizeColumnsToContents()

    def _populate_identifications(self) -> None:
        rows = self.summary.identifications
        self._identification_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                row.dataset_id,
                row.record_id,
                row.scientific_name,
                row.best_hit,
                row.identity,
                row.query_coverage,
                row.accession,
                row.result_id,
                row.result_reference_state,
                row.payload_state,
            )
            for column, value in enumerate(values):
                self._identification_table.setItem(row_index, column, QTableWidgetItem(value))
        self._identification_table.resizeColumnsToContents()

    def _populate_alignments(self) -> None:
        rows = self.summary.alignments
        self._alignment_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (row.display_name, str(row.sequence_count), str(row.alignment_length), row.parent_dataset_id, f"r{row.revision}", row.state, row.marker_regions, row.excluded_columns, f"{row.deleted_columns} / {row.edited_positions}")
            for column, value in enumerate(values):
                self._alignment_table.setItem(row_index, column, QTableWidgetItem(value))
        self._alignment_table.resizeColumnsToContents()

    def _populate_dataset_picker(self) -> None:
        previous = self._dataset_picker.currentData()
        self._dataset_picker.blockSignals(True)
        self._dataset_picker.clear()
        for entry in self._project.dataset_entries:
            dataset = entry.dataset
            dataset_id = dataset.alignment_id if isinstance(dataset, AlignmentDataset) else dataset.dataset_id
            kind = "Alignment" if isinstance(dataset, AlignmentDataset) else "Sequence"
            self._dataset_picker.addItem(f"{entry.display_name} — {kind} r{entry.revision_number}", dataset_id)
        if previous is not None:
            index = self._dataset_picker.findData(previous)
            if index >= 0:
                self._dataset_picker.setCurrentIndex(index)
        self._dataset_picker.blockSignals(False)
        self._populate_record_picker()

    def _populate_record_picker(self) -> None:
        dataset_id = self._dataset_picker.currentData()
        self._record_picker.blockSignals(True)
        self._record_picker.clear()
        self._record_refs = tuple(
            ref for ref in self.summary.provenance_nodes
            if ref.dataset_id == dataset_id
        )
        for ref in self._record_refs:
            self._record_picker.addItem(ref.sequence_id, ref)
        self._record_picker.blockSignals(False)
        self._populate_provenance()

    def _populate_provenance(self) -> None:
        self._provenance_tree.clear()
        ref = self._record_picker.currentData()
        if not isinstance(ref, RecordRef):
            self._provenance_tree.addTopLevelItem(QTreeWidgetItem((NO_RECORD, "", "", "")))
            return
        self._add_provenance_node(ref, None, set())
        self._provenance_tree.expandAll()
        self._provenance_tree.resizeColumnToContents(0)

    def _add_provenance_node(
        self,
        ref: RecordRef,
        parent: QTreeWidgetItem | None,
        seen: set[RecordRef],
    ) -> None:
        """Render direct RecordRef sources as a tree without inventing edges."""

        node = self.summary.provenance_nodes.get(ref)
        if node is None:
            item = QTreeWidgetItem((f"{ref.sequence_id}  [{ref.dataset_id}]", NO_RECORD, NO_RECORD, "Unavailable", "Not recorded"))
            if parent is None:
                self._provenance_tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            return
        name = f"{node.record_name}  [{node.record_ref.dataset_id}]"
        item = QTreeWidgetItem((name, node.source_batch or NO_RECORD, node.source_filename or NO_RECORD, node.ab1_source_state, node.review_pairing_state))
        if parent is None:
            self._provenance_tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        if ref in seen:
            item.addChild(QTreeWidgetItem(("Circular provenance reference", "Not recorded", "Not recorded", "Unavailable", "Not recorded")))
            return
        next_seen = set(seen)
        next_seen.add(ref)
        for source in node.direct_sources:
            self._add_provenance_node(source, item, next_seen)

    def close_viewer(self) -> bool:
        state = getattr(self._context, "app_state", None)
        signal = getattr(state, "project_changed", None)
        if signal is not None:
            try:
                signal.disconnect(self._on_project_changed)
            except (RuntimeError, TypeError):
                pass
        return True


def create_project_provenance_viewer(context: object, project: object) -> ProjectProvenanceViewer:
    if not isinstance(project, Project):
        raise ValueError("Project QC & Provenance requires a Project")
    return ProjectProvenanceViewer(project, context)
