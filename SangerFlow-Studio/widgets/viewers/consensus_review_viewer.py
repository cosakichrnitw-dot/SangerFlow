"""Studio-native consensus review viewer for AlignmentDataset values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QLabel,
)

from core.alignment_dataset import AlignmentDataset
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from export.sequence_export import (
    export_dataset_to_fasta,
    export_dataset_to_nexus,
    export_dataset_to_phylip,
)
from widgets.font_utils import fixed_width_font
from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.viewer_actions import ViewerAction


VALID_REVIEW_BASES = frozenset("ACGTN-")
POSITION_ROW = 0
ORIGINAL_ROW = 1
REVIEWED_ROW = 2


@dataclass(frozen=True)
class ConsensusChange:
    """One auditable consensus edit in 1-based alignment coordinates."""

    position: int
    original_base: str
    reviewed_base: str
    changed_at: str

    def as_metadata(self) -> dict[str, object]:
        return {
            "position": self.position,
            "original_base": self.original_base,
            "reviewed_base": self.reviewed_base,
            "changed_at": self.changed_at,
        }


class ConsensusReviewViewer(BaseViewer):
    """Edit reviewed consensus while preserving original consensus and history."""

    def __init__(
        self,
        alignment_dataset: AlignmentDataset,
        *,
        context: object | None = None,
    ) -> None:
        if not isinstance(alignment_dataset, AlignmentDataset):
            raise ValueError("ConsensusReviewViewer requires an AlignmentDataset")
        self._alignment_dataset = alignment_dataset
        self._context = context
        self._original_consensus = _consensus_from_alignment(alignment_dataset)
        self._reviewed_consensus = list(self._original_consensus)
        self._changes_by_position: dict[int, ConsensusChange] = {}
        self._undo_stack: list[tuple[int, str, str]] = []
        self._redo_stack: list[tuple[int, str, str]] = []
        self._action_provider = ConsensusReviewActionProvider()
        super().__init__(
            viewer_id=f"consensus-review-{_safe_identifier(alignment_dataset.alignment_id)}",
            viewer_title=f"Consensus Review: {alignment_dataset.name}",
            viewer_kind="consensus-review",
            source_object_id=alignment_dataset.alignment_id,
        )
        self._build_ui()

    @property
    def alignment_dataset(self) -> AlignmentDataset:
        return self._alignment_dataset

    @property
    def original_consensus(self) -> str:
        return self._original_consensus

    @property
    def reviewed_consensus(self) -> str:
        return "".join(self._reviewed_consensus)

    @property
    def change_log(self) -> tuple[ConsensusChange, ...]:
        return tuple(
            self._changes_by_position[position]
            for position in sorted(self._changes_by_position)
        )

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "consensus_review.undo",
            "consensus_review.redo",
            "consensus_review.create_dataset",
            "consensus_review.export",
        )

    def select_position(self, position: int) -> None:
        if position < 1 or position > len(self._reviewed_consensus):
            return
        self._table.setCurrentCell(REVIEWED_ROW, position - 1)
        self._update_status(position)

    def edit_selected_base(self, base: str) -> bool:
        item = self._table.currentItem()
        if item is None:
            return False
        return self.edit_base(item.column() + 1, base)

    def edit_base(self, position: int, base: str) -> bool:
        base = base.upper()
        if base not in VALID_REVIEW_BASES:
            return False
        if position < 1 or position > len(self._reviewed_consensus):
            return False
        index = position - 1
        previous = self._reviewed_consensus[index]
        if previous == base:
            return False
        self._apply_edit(position, base, record_undo=True)
        self._redo_stack.clear()
        return True

    def undo(self) -> None:
        if not self._undo_stack:
            return
        position, old_base, new_base = self._undo_stack.pop()
        self._redo_stack.append((position, old_base, new_base))
        self._apply_edit(position, old_base, record_undo=False)

    def redo(self) -> None:
        if not self._redo_stack:
            return
        position, old_base, new_base = self._redo_stack.pop()
        self._undo_stack.append((position, old_base, new_base))
        self._apply_edit(position, new_base, record_undo=False)

    def create_reviewed_dataset(self) -> SequenceDataset:
        dataset_id = f"{self._alignment_dataset.alignment_id}_reviewed_consensus"
        name = f"{self._alignment_dataset.name} reviewed consensus"
        return build_reviewed_consensus_dataset(
            self._alignment_dataset,
            dataset_id=dataset_id,
            name=name,
            original_consensus=self.original_consensus,
            reviewed_consensus=self.reviewed_consensus,
            change_log=self.change_log,
        )

    def create_and_register_reviewed_dataset(self) -> SequenceDataset | None:
        controller = getattr(self._context, "project_controller", None)
        if controller is None:
            return self.create_reviewed_dataset()
        create = getattr(controller, "register_reviewed_consensus_from_viewer", None)
        if not callable(create):
            return self.create_reviewed_dataset()
        return create(self)

    def export_reviewed_dataset(self) -> None:
        dataset = self.create_reviewed_dataset()
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Reviewed Consensus",
            self._default_export_path(f"{dataset.dataset_id}.fasta"),
            "FASTA (*.fasta *.fa);;NEXUS (*.nex *.nexus);;PHYLIP (*.phy *.phylip)",
        )
        if not filepath:
            return
        try:
            suffix = Path(filepath).suffix.lower()
            if "NEXUS" in selected_filter or suffix in {".nex", ".nexus"}:
                export_dataset_to_nexus(dataset, filepath, metadata=dataset.metadata)
            elif "PHYLIP" in selected_filter or suffix in {".phy", ".phylip"}:
                export_dataset_to_phylip(dataset, filepath)
            else:
                export_dataset_to_fasta(dataset, filepath)
        except Exception as error:
            QMessageBox.critical(self, "Could not export reviewed consensus", str(error))

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

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        key = event.key()
        text = event.text().upper()
        if event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            if key == Qt.Key.Key_Z:
                self.undo()
                return
            if key == Qt.Key.Key_Y:
                self.redo()
                return
        if text in VALID_REVIEW_BASES:
            self.edit_selected_base(text)
            return
        super().keyPressEvent(event)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._summary = QLabel(
            f"Alignment: {self._alignment_dataset.name}    "
            f"Length: {self._alignment_dataset.length}    "
            f"Records: {self._alignment_dataset.sequence_count}"
        )
        layout.addWidget(self._summary)
        self._status = QLabel("Select a reviewed consensus base, then type A/C/G/T/N/-.")
        layout.addWidget(self._status)
        self._table = QTableWidget()
        self._table.setObjectName("consensusReviewTable")
        self._table.setRowCount(3)
        self._table.setColumnCount(len(self._original_consensus))
        self._table.setVerticalHeaderLabels(
            ("Alignment Position", "Original Consensus", "Reviewed Consensus")
        )
        self._table.horizontalHeader().hide()
        self._table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.cellClicked.connect(self._cell_clicked)
        layout.addWidget(self._table, 1)
        self._populate_table()

    def _populate_table(self) -> None:
        font = fixed_width_font(10, QFont.Weight.Bold)
        small_font = fixed_width_font(8)
        for column, base in enumerate(self._original_consensus):
            position = column + 1
            position_item = QTableWidgetItem(str(position))
            position_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            position_item.setFont(small_font)
            position_item.setFlags(position_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(POSITION_ROW, column, position_item)

            original_item = _base_item(base, font)
            original_item.setFlags(original_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(ORIGINAL_ROW, column, original_item)

            reviewed_item = _base_item(base, font)
            reviewed_item.setFlags(reviewed_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(REVIEWED_ROW, column, reviewed_item)
            self._table.setColumnWidth(column, 22)
        for row in range(3):
            self._table.setRowHeight(row, 24)

    def _cell_clicked(self, row: int, column: int) -> None:
        if column < 0:
            return
        self._table.setCurrentCell(REVIEWED_ROW, column)
        self._update_status(column + 1)

    def _apply_edit(self, position: int, base: str, *, record_undo: bool) -> None:
        index = position - 1
        previous = self._reviewed_consensus[index]
        self._reviewed_consensus[index] = base
        if record_undo:
            self._undo_stack.append((position, previous, base))
        original = self._original_consensus[index]
        if base == original:
            self._changes_by_position.pop(position, None)
        else:
            self._changes_by_position[position] = ConsensusChange(
                position=position,
                original_base=original,
                reviewed_base=base,
                changed_at=datetime.now(timezone.utc).isoformat(),
            )
        self._refresh_reviewed_cell(position)
        self._table.setCurrentCell(REVIEWED_ROW, index)
        self._update_status(position)

    def _refresh_reviewed_cell(self, position: int) -> None:
        index = position - 1
        item = self._table.item(REVIEWED_ROW, index)
        if item is None:
            return
        base = self._reviewed_consensus[index]
        item.setText(base)
        item.setForeground(_base_color(base))
        if base != self._original_consensus[index]:
            item.setBackground(QColor("#FFD966"))
        else:
            item.setBackground(QColor("white"))

    def _update_status(self, position: int) -> None:
        index = position - 1
        self._status.setText(
            f"Position {position}: {self._original_consensus[index]} → {self._reviewed_consensus[index]}    "
            f"Changes: {len(self._changes_by_position)}"
        )


class ConsensusReviewActionProvider:
    """Toolbar actions for Studio consensus editing."""

    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        return (
            ViewerAction(
                action_id="consensus_review.undo",
                label="Undo",
                tooltip="Undo the last consensus edit",
                callback=getattr(viewer, "undo"),
            ),
            ViewerAction(
                action_id="consensus_review.redo",
                label="Redo",
                tooltip="Redo the last undone consensus edit",
                callback=getattr(viewer, "redo"),
            ),
            ViewerAction(
                action_id="consensus_review.create_dataset",
                label="Create Reviewed Consensus",
                tooltip="Create a Reviewed Consensus Dataset and add it to the Project",
                callback=getattr(viewer, "create_and_register_reviewed_dataset"),
            ),
            ViewerAction(
                action_id="consensus_review.export",
                label="Export",
                tooltip="Export reviewed consensus as FASTA, NEXUS, or PHYLIP",
                callback=getattr(viewer, "export_reviewed_dataset"),
            ),
        )


def build_reviewed_consensus_dataset(
    alignment_dataset: AlignmentDataset,
    *,
    dataset_id: str,
    name: str,
    original_consensus: str,
    reviewed_consensus: str,
    change_log: tuple[ConsensusChange, ...],
) -> SequenceDataset:
    """Create the persisted ReviewedConsensus Dataset representation."""

    metadata = {
        "source": "Reviewed Consensus",
        "reviewed": True,
        "consensus_method": "Studio Consensus Review",
        "original_read_count": alignment_dataset.sequence_count,
        "parent_dataset_id": alignment_dataset.alignment_id,
        "parent_alignment_id": alignment_dataset.alignment_id,
        "original_consensus": original_consensus,
        "reviewed_consensus": reviewed_consensus,
        "change_log": [change.as_metadata() for change in change_log],
        "applied_decision_count": len(change_log),
    }
    record = SequenceRecord(
        sequence_id=dataset_id,
        sequence=reviewed_consensus,
        description="Reviewed consensus generated by SangerFlow-Studio",
        metadata={
            "source": "Reviewed Consensus",
            "reviewed": True,
            "original_consensus": original_consensus,
            "change_log": [change.as_metadata() for change in change_log],
        },
    )
    return SequenceDataset(
        dataset_id=dataset_id,
        name=name,
        source_type=SourceType.REVIEWED_CONSENSUS,
        records=(record,),
        metadata=metadata,
    )


def create_consensus_review_viewer(context: object, dataset: object) -> ConsensusReviewViewer:
    return ConsensusReviewViewer(dataset, context=context)


def _consensus_from_alignment(dataset: AlignmentDataset) -> str:
    consensus: list[str] = []
    for column in range(dataset.length):
        counts: dict[str, int] = {}
        for record in dataset.records:
            base = record.aligned_sequence[column]
            if base == "-":
                continue
            counts[base] = counts.get(base, 0) + 1
        if not counts:
            consensus.append("-")
        else:
            consensus.append(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0])
    return "".join(consensus)


def _base_item(base: str, font: QFont) -> QTableWidgetItem:
    item = QTableWidgetItem(base)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setFont(font)
    item.setForeground(_base_color(base))
    return item


def _base_color(base: str) -> QColor:
    colors = {
        "A": QColor("green"),
        "T": QColor("red"),
        "G": QColor("black"),
        "C": QColor("blue"),
        "N": QColor("#555555"),
        "-": QColor("#777777"),
    }
    return colors.get(base.upper(), QColor("#555555"))


def _safe_identifier(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in str(value)
    )
