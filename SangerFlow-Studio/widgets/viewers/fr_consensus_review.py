"""Studio Forward/Reverse consensus review workflow viewers.

These viewers are GUI orchestration only.  Pair detection, assembly,
consensus-v2.1, review evidence, and reviewed-consensus derivation are all
delegated to existing SangerFlow core modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QCheckBox,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from core.assembly_view_builders import (
    build_forward_assembly_view,
    build_reverse_assembly_view,
)
from app.icon_registry import studio_icon
from core.consensus_review_session import ConsensusReviewSession
from core.consensus_v2_1 import ConsensusV21Scoring, build_pair_consensus_v2_1
from core.human_review import DecisionType, HumanReviewDecision
from core.lineage import RecordProvenance, RecordRef
from core.pair_alignment import align_pair
from core.reviewed_consensus import build_reviewed_consensus
from core.reverse_complement import build_reverse_complement_view
from core.samples import (
    PairingStatus,
    Sample,
    SampleClassification,
    classify_reads_by_filename,
)
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from core.trimming import trim_sequence
from widgets.sequence_grid import SequenceGridRow, SequenceGridWidget
from widgets.alignment_edit_operations import (
    BaseEditOperation,
    BulkBaseEditOperation,
    DeleteRowsOperation,
)
from widgets.viewers.pair_consensus_chromatogram import PairConsensusChromatogramPanel
from widgets.viewers.multiple_consensus_alignment import TemporaryConsensusAlignment
from widgets.viewers.single_consensus_view_model import (
    SingleConsensusViewModel,
    build_single_consensus_view_model,
)
from widgets.viewers.consensus_decision_presentation import (
    decision_reason_label,
    decision_source_label,
)
from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.viewer_actions import ViewerAction


_SUPPORTED_REVIEW_BASES = ("A", "C", "G", "T", "N", "-")


def _is_conflict_column(column: object) -> bool:
    """Return whether existing consensus evidence marks a review conflict.

    This is presentation-only navigation over the status/evidence produced by
    the existing consensus-v2.1 workflow; it does not make a new conflict
    determination.
    """

    status = str(getattr(column, "status", "")).casefold()
    evidence = getattr(column, "review_evidence", None)
    return (
        "conflict" in status
        or getattr(evidence, "decision_reason", None) == "UNRESOLVED_CONFLICT"
    )


@dataclass(frozen=True)
class ConsensusSampleRow:
    """One filename-classified sample row shown by the Studio manager."""

    sample: Sample
    sample_id: str
    forward_filename: str
    reverse_filename: str
    status: str
    consensus_length: int | None = None
    conflict_count: int | None = None
    unresolved_count: int | None = None
    view_model: SingleConsensusViewModel | None = None
    source_record_provenance: RecordProvenance | None = None
    pairing_resolution: str = "AUTO_CLEAR_PAIR"
    pairing_resolution_origin: str | None = None
    error: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.sample.is_clear_pair and self.view_model is not None and self.error is None


def build_consensus_sample_rows(
    reads: object,
    *,
    scoring: ConsensusV21Scoring | None = None,
    source_dataset: SequenceDataset | None = None,
) -> tuple[ConsensusSampleRow, ...]:
    """Classify reads and build review inputs for clear F/R pairs.

    The returned rows include incomplete and ambiguous filename groups so the
    user can see what will and will not be processed.
    """

    rows: list[ConsensusSampleRow] = []
    for sample in classify_reads_by_filename(reads):
        forward_name = getattr(sample.forward_read, "filename", "—") if sample.forward_read else "—"
        reverse_name = getattr(sample.reverse_read, "filename", "—") if sample.reverse_read else "—"
        if not sample.is_clear_pair:
            rows.append(
                ConsensusSampleRow(
                    sample=sample,
                    sample_id=sample.sample_id,
                    forward_filename=forward_name,
                    reverse_filename=reverse_name,
                    status=_status_label(sample),
                    error="; ".join(sample.reasons) if sample.reasons else None,
                )
            )
            continue
        try:
            view_model = build_fr_single_consensus_view_model(sample, scoring=scoring)
        except Exception as error:  # GUI-facing row; exact core error shown in table
            rows.append(
                ConsensusSampleRow(
                    sample=sample,
                    sample_id=sample.sample_id,
                    forward_filename=forward_name,
                    reverse_filename=reverse_name,
                    status="Assembly / consensus error",
                    error=str(error),
                )
            )
            continue
        unresolved_count = view_model.consensus_sequence.count("N")
        conflict_count = sum(
            1
            for column in view_model.columns
            if "conflict" in column.status.casefold()
            or column.review_evidence.decision_reason == "UNRESOLVED_CONFLICT"
        )
        rows.append(
            ConsensusSampleRow(
                sample=sample,
                sample_id=sample.sample_id,
                forward_filename=forward_name,
                reverse_filename=reverse_name,
                status="Ready",
                consensus_length=len(view_model.consensus_sequence),
                conflict_count=conflict_count,
                unresolved_count=unresolved_count,
                view_model=view_model,
                source_record_provenance=pair_record_provenance(
                    sample, source_dataset
                ),
            )
        )
    return tuple(rows)


def pair_record_provenance(
    sample: Sample,
    source_dataset: SequenceDataset | None,
) -> RecordProvenance | None:
    """Resolve a clear pair to direct source records without filename matching.

    ``SangerRead`` object identity is the only bridge used here.  A filename is
    presentation data and must never decide which source record supplied a
    reviewed consensus.
    """

    if source_dataset is None:
        return None
    if not sample.is_clear_pair:
        return None
    forward_read = sample.forward_read
    reverse_read = sample.reverse_read
    if forward_read is None or reverse_read is None:
        return None

    records_by_source_identity: dict[int, list[SequenceRecord]] = {}
    for record in source_dataset.records:
        source = record.source_reference
        if source is not None:
            records_by_source_identity.setdefault(id(source), []).append(record)

    resolved: list[RecordRef] = []
    for read in (forward_read, reverse_read):
        matches = records_by_source_identity.get(id(read), ())
        if len(matches) != 1:
            return None
        resolved.append(
            RecordRef(source_dataset.dataset_id, matches[0].sequence_id)
        )
    return RecordProvenance(tuple(resolved))


def _source_record_for_read(
    source_dataset: SequenceDataset,
    read: object,
) -> SequenceRecord:
    """Resolve one source record strictly through its in-memory read object."""

    matches = tuple(
        record
        for record in source_dataset.records
        if record.source_reference is read
    )
    if len(matches) != 1:
        raise ValueError(
            "F/R output cannot resolve one exact source record for the selected read."
        )
    return matches[0]


def _output_orphan_record(
    row: ConsensusSampleRow,
    source_dataset: SequenceDataset,
    direction: str,
    *,
    read: object | None = None,
) -> SequenceRecord:
    """Create one explicit single-read output without mutating its AB1 source."""

    if direction == "FORWARD":
        read = read or row.sample.forward_read
        expected_status = PairingStatus.ORPHAN_FORWARD
    elif direction == "REVERSE":
        read = read or row.sample.reverse_read
        expected_status = PairingStatus.ORPHAN_REVERSE
    else:  # pragma: no cover - internal caller validation
        raise ValueError("orphan output direction must be FORWARD or REVERSE")
    is_explicit_ambiguous_candidate = (
        row.sample.pairing_status is PairingStatus.AMBIGUOUS
        and any(
            candidate is read
            for candidate in (
                row.sample.forward_candidates
                if direction == "FORWARD"
                else row.sample.reverse_candidates
            )
        )
    )
    if read is None or (
        row.sample.pairing_status is not expected_status
        and not is_explicit_ambiguous_candidate
    ):
        raise ValueError("selected row is not the requested orphan direction")
    source_record = _source_record_for_read(source_dataset, read)
    if direction == "REVERSE":
        # The existing validated reverse-complement view supplies assembly
        # orientation while retaining exact source trace coordinates.
        sequence = build_reverse_complement_view(read).sequence
        normalized = True
    else:
        sequence = source_record.sequence
        normalized = False
    return SequenceRecord(
        sequence_id=source_record.sequence_id,
        sequence=sequence,
        description=source_record.description,
        source_reference=read,
        metadata={
            **dict(source_record.metadata),
            "record_origin": f"ORPHAN_{direction}",
            "source_sample_id": row.sample_id,
            "orientation_normalized": normalized,
            "single_read_direction": direction,
            "source_read_filename": read.filename,
        },
        provenance=RecordProvenance(
            (RecordRef(source_dataset.dataset_id, source_record.sequence_id),)
        ),
    )


def _output_reviewed_pair_record(
    row: ConsensusSampleRow,
    reviewed_record: SequenceRecord,
    *,
    resolution_row: ConsensusSampleRow | None = None,
) -> SequenceRecord:
    """Carry a human-reviewed pair record into the mixed final output."""

    if len(reviewed_record.provenance.source_records) != 2:
        raise ValueError("reviewed pair output requires Forward and Reverse RecordProvenance")
    resolution_metadata: dict[str, object] = {}
    if resolution_row is not None and resolution_row.pairing_resolution == "MANUAL":
        refs = resolution_row.source_record_provenance.source_records if resolution_row.source_record_provenance else ()
        resolution_metadata = {
            "pairing_resolution": "MANUAL",
            "pairing_resolution_origin": "USER_SELECTED",
            "source_forward_record_id": refs[0].sequence_id if len(refs) == 2 else "",
            "source_reverse_record_id": refs[1].sequence_id if len(refs) == 2 else "",
        }
    return SequenceRecord(
        sequence_id=reviewed_record.sequence_id,
        sequence=reviewed_record.sequence,
        description=reviewed_record.description,
        source_reference=reviewed_record.source_reference,
        metadata={
            **dict(reviewed_record.metadata),
            "record_origin": "REVIEWED_CONSENSUS",
            "source_sample_id": row.sample_id,
            "orientation_normalized": True,
            **resolution_metadata,
        },
        provenance=reviewed_record.provenance,
    )


def build_fr_single_consensus_view_model(
    sample: Sample, *, scoring: ConsensusV21Scoring | None = None,
) -> SingleConsensusViewModel:
    """Build the existing SingleConsensusViewModel from one clear pair."""

    if not isinstance(sample, Sample) or not sample.is_clear_pair:
        raise ValueError("sample must be a clear Forward/Reverse pair")
    forward_read = sample.forward_read
    reverse_read = sample.reverse_read
    if forward_read is None or reverse_read is None:
        raise ValueError("clear pair is missing a read")
    _ensure_trimmed(forward_read)
    _ensure_trimmed(reverse_read)
    pair_alignment = align_pair(
        build_forward_assembly_view(forward_read),
        build_reverse_assembly_view(reverse_read),
    )
    consensus_result = build_pair_consensus_v2_1(pair_alignment, scoring=scoring)
    return build_single_consensus_view_model(
        sample.sample_id,
        pair_alignment,
        consensus_result,
    )


def build_manual_pair_consensus_row(
    ambiguous_row: ConsensusSampleRow,
    forward_read: object,
    reverse_read: object,
    *,
    source_dataset: SequenceDataset | None,
    scoring: ConsensusV21Scoring | None = None,
) -> ConsensusSampleRow:
    """Build one review row from the two reads explicitly selected by a user.

    This deliberately projects the selected candidates into the existing clear
    pair review input.  It never changes filename classification, PairAlignment,
    or consensus-v2.1; unselected candidates remain on the original row.
    """

    sample = ambiguous_row.sample
    if sample.pairing_status is not PairingStatus.AMBIGUOUS:
        raise ValueError("manual pair resolution is available only for ambiguous samples")
    if not any(candidate is forward_read for candidate in sample.forward_candidates):
        raise ValueError("selected Forward read is not a candidate for this sample")
    if not any(candidate is reverse_read for candidate in sample.reverse_candidates):
        raise ValueError("selected Reverse read is not a candidate for this sample")
    selected_sample = Sample(
        sample_id=sample.sample_id,
        classification=SampleClassification.PAIR,
        pairing_status=PairingStatus.CLEAR_PAIR,
        forward_read=forward_read,
        reverse_read=reverse_read,
        forward_candidates=(forward_read,),
        reverse_candidates=(reverse_read,),
    )
    view_model = build_fr_single_consensus_view_model(selected_sample, scoring=scoring)
    provenance = pair_record_provenance(selected_sample, source_dataset)
    if source_dataset is not None and provenance is None:
        raise ValueError("manual pair resolution cannot resolve exact source RecordRefs")
    unresolved_count = view_model.consensus_sequence.count("N")
    conflict_count = sum(_is_conflict_column(column) for column in view_model.columns)
    return ConsensusSampleRow(
        sample=selected_sample,
        sample_id=sample.sample_id,
        forward_filename=getattr(forward_read, "filename", "—"),
        reverse_filename=getattr(reverse_read, "filename", "—"),
        status="Resolved Pair — review required",
        consensus_length=len(view_model.consensus_sequence),
        conflict_count=conflict_count,
        unresolved_count=unresolved_count,
        view_model=view_model,
        source_record_provenance=provenance,
        pairing_resolution="MANUAL",
        pairing_resolution_origin="USER_SELECTED",
    )


class ResolvePairDialog(QDialog):
    """Minimal, explicit candidate chooser for one ambiguous F/R sample."""

    def __init__(self, row: ConsensusSampleRow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if row.sample.pairing_status is not PairingStatus.AMBIGUOUS:
            raise ValueError("Resolve Pair requires an ambiguous sample")
        self._row = row
        self.resolution: str | None = None
        self.setWindowTitle("Resolve Forward / Reverse Pair")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Sample: {row.sample_id}"))
        layout.addWidget(QLabel("Forward candidates:"))
        self._forward_group = QButtonGroup(self)
        self._forward_buttons: dict[QRadioButton, object] = {}
        for index, read in enumerate(row.sample.forward_candidates):
            button = QRadioButton(getattr(read, "filename", f"Forward {index + 1}"))
            self._forward_group.addButton(button)
            self._forward_buttons[button] = read
            layout.addWidget(button)
        layout.addWidget(QLabel("Reverse candidates:"))
        self._reverse_group = QButtonGroup(self)
        self._reverse_buttons: dict[QRadioButton, object] = {}
        for index, read in enumerate(row.sample.reverse_candidates):
            button = QRadioButton(getattr(read, "filename", f"Reverse {index + 1}"))
            self._reverse_group.addButton(button)
            self._reverse_buttons[button] = read
            layout.addWidget(button)
        if row.sample.unspecified_candidates:
            names = ", ".join(read.filename for read in row.sample.unspecified_candidates)
            layout.addWidget(QLabel(f"Unspecified candidates (not auto-classified): {names}"))
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._resolve_button = self._buttons.addButton("Resolve as Pair", QDialogButtonBox.ButtonRole.AcceptRole)
        self._forward_single_button = self._buttons.addButton("Use as Forward Single", QDialogButtonBox.ButtonRole.ActionRole)
        self._reverse_single_button = self._buttons.addButton("Use as Reverse Single", QDialogButtonBox.ButtonRole.ActionRole)
        self._exclude_button = self._buttons.addButton("Exclude from Output", QDialogButtonBox.ButtonRole.DestructiveRole)
        self._buttons.rejected.connect(self.reject)
        self._resolve_button.clicked.connect(lambda: self._finish("PAIR"))
        self._forward_single_button.clicked.connect(lambda: self._finish("FORWARD_SINGLE"))
        self._reverse_single_button.clicked.connect(lambda: self._finish("REVERSE_SINGLE"))
        self._exclude_button.clicked.connect(lambda: self._finish("EXCLUDE"))
        self._forward_group.buttonToggled.connect(self._update_buttons)
        self._reverse_group.buttonToggled.connect(self._update_buttons)
        layout.addWidget(self._buttons)
        self._update_buttons()

    @property
    def selected_forward(self) -> object | None:
        button = self._forward_group.checkedButton()
        return self._forward_buttons.get(button) if button is not None else None

    @property
    def selected_reverse(self) -> object | None:
        button = self._reverse_group.checkedButton()
        return self._reverse_buttons.get(button) if button is not None else None

    def _update_buttons(self, *_args: object) -> None:
        self._resolve_button.setEnabled(self.selected_forward is not None and self.selected_reverse is not None)
        self._forward_single_button.setEnabled(self.selected_forward is not None)
        self._reverse_single_button.setEnabled(self.selected_reverse is not None)

    def _finish(self, resolution: str) -> None:
        self.resolution = resolution
        self.accept()


class ConsensusReviewManagerViewer(BaseViewer):
    """Lightweight Studio manager for F/R consensus candidates."""

    def __init__(
        self,
        rows: tuple[ConsensusSampleRow, ...],
        *,
        context: object | None = None,
        source_dataset: object | None = None,
        settings_metadata: dict[str, object] | None = None,
    ) -> None:
        self._context = context
        self._source_dataset = source_dataset
        self._settings_metadata = dict(settings_metadata or {})
        self._rows = tuple(rows)
        # Output membership is deliberately independent from table selection
        # and chromatogram visibility.  Orphans require an explicit include.
        self._included_single_directions: dict[str, str] = {}
        self._included_single_reads: dict[str, tuple[str, object]] = {}
        self._reviewed_pair_records: dict[str, SequenceRecord] = {}
        self._manual_pair_rows: dict[str, ConsensusSampleRow] = {}
        self._output_excluded_sample_ids: set[str] = set()
        self._action_provider = ConsensusReviewManagerActionProvider()
        source_id = getattr(source_dataset, "dataset_id", None)
        super().__init__(
            viewer_id=f"fr-consensus-manager-{source_id or id(self)}",
            viewer_title="Consensus Samples",
            viewer_kind="consensus-review-manager",
            source_object_id=source_id,
        )
        self._build_ui()

    @property
    def rows(self) -> tuple[ConsensusSampleRow, ...]:
        return self._rows

    @property
    def ready_rows(self) -> tuple[ConsensusSampleRow, ...]:
        return tuple(row for row in self._rows if row.is_ready)

    @property
    def source_dataset(self) -> object | None:
        return self._source_dataset

    @property
    def settings_metadata(self) -> dict[str, object]:
        return dict(self._settings_metadata)

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "fr_consensus.review_selected",
            "fr_consensus.resolve_pair",
            "fr_consensus.include_forward_single",
            "fr_consensus.include_reverse_single",
            "fr_consensus.exclude_from_output",
            "fr_consensus.create_output_dataset",
        )

    def review_selected(self) -> object | None:
        selected = self._selected_effective_ready_row()
        if selected is None:
            self.status_message_changed.emit("Select one Ready F/R pair to review.")
            return None
        controller = getattr(self._context, "project_controller", None)
        open_method = getattr(controller, "open_single_fr_consensus_review", None)
        if callable(open_method):
            return open_method(
                selected,
                source_dataset=self._source_dataset,
                settings_metadata=self._settings_metadata,
                output_manager=self,
            )
        self.open_related_requested.emit({"action": "REVIEW_CONSENSUS", "row": selected})
        return None

    def resolve_selected_pair(self) -> object | None:
        row = self._selected_row()
        if row is None or row.sample.pairing_status is not PairingStatus.AMBIGUOUS:
            self.status_message_changed.emit("Select an ambiguous sample to resolve its Forward/Reverse pair.")
            return None
        dialog = ResolvePairDialog(row, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        if dialog.resolution == "PAIR":
            try:
                resolved = self.resolve_ambiguous_pair(
                    row, dialog.selected_forward, dialog.selected_reverse
                )
            except ValueError as error:
                self.status_message_changed.emit(str(error))
                return None
            return self._open_resolved_pair_for_review(resolved)
        if dialog.resolution == "FORWARD_SINGLE":
            return self.include_ambiguous_single(row, "FORWARD", dialog.selected_forward)
        if dialog.resolution == "REVERSE_SINGLE":
            return self.include_ambiguous_single(row, "REVERSE", dialog.selected_reverse)
        if dialog.resolution == "EXCLUDE":
            return self.exclude_selected_from_output()
        return None

    def resolve_ambiguous_pair(
        self,
        row: ConsensusSampleRow,
        forward_read: object,
        reverse_read: object,
    ) -> ConsensusSampleRow:
        """Persist one explicit candidate choice in manager state and review it."""

        resolved = build_manual_pair_consensus_row(
            row,
            forward_read,
            reverse_read,
            source_dataset=self._source_dataset if isinstance(self._source_dataset, SequenceDataset) else None,
        )
        self._manual_pair_rows[row.sample_id] = resolved
        self._included_single_directions.pop(row.sample_id, None)
        self._included_single_reads.pop(row.sample_id, None)
        self._output_excluded_sample_ids.discard(row.sample_id)
        self._populate_table()
        self.status_message_changed.emit(f"Manual F/R pair selected: {row.sample_id}. Review is required.")
        return resolved

    def _open_resolved_pair_for_review(self, row: ConsensusSampleRow) -> object | None:
        controller = getattr(self._context, "project_controller", None)
        open_method = getattr(controller, "open_single_fr_consensus_review", None)
        if callable(open_method):
            return open_method(
                row,
                source_dataset=self._source_dataset,
                settings_metadata=self._settings_metadata,
                output_manager=self,
            )
        self.open_related_requested.emit({"action": "REVIEW_CONSENSUS", "row": row})
        return None

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        ready_count = len(self.ready_rows)
        layout.addWidget(
            QLabel(
                f"Consensus Samples — Ready: {ready_count}/{len(self._rows)}"
            )
        )
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            (
                "Sample",
                "Forward read",
                "Reverse read",
                "Status",
                "Consensus length",
                "Conflicts",
                "Unresolved / N",
                "Notes",
            )
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.itemDoubleClicked.connect(lambda _item: self.review_selected())
        self._table.itemSelectionChanged.connect(self._selected_row_changed)
        layout.addWidget(self._table, 1)
        footer = QHBoxLayout()
        self._review_button = QPushButton("Review")
        self._review_button.clicked.connect(self.review_selected)
        self._review_all_button = QPushButton("Review All / Multiple Review")
        self._review_all_button.setEnabled(len(self.ready_rows) >= 2)
        self._review_all_button.setToolTip("Open Multiple Consensus Review for all ready F/R pairs.")
        self._review_all_button.clicked.connect(self.review_all)
        self._resolve_pair_button = QPushButton("Resolve Pair…")
        self._resolve_pair_button.clicked.connect(self.resolve_selected_pair)
        self._include_forward_button = QPushButton("Include as Forward Single")
        self._include_forward_button.clicked.connect(self.include_selected_as_forward_single)
        self._include_reverse_button = QPushButton("Include as Reverse Single")
        self._include_reverse_button.clicked.connect(self.include_selected_as_reverse_single)
        self._exclude_output_button = QPushButton("Exclude from Output")
        self._exclude_output_button.clicked.connect(self.exclude_selected_from_output)
        self._create_output_button = QPushButton("Create Output Dataset…")
        self._create_output_button.clicked.connect(self.create_and_register_output_dataset)
        footer.addWidget(self._review_button)
        footer.addWidget(self._review_all_button)
        footer.addWidget(self._resolve_pair_button)
        footer.addWidget(self._include_forward_button)
        footer.addWidget(self._include_reverse_button)
        footer.addWidget(self._exclude_output_button)
        footer.addWidget(self._create_output_button)
        footer.addStretch(1)
        layout.addLayout(footer)
        self._populate_table()

    def _populate_table(self) -> None:
        self._table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            values = (
                row.sample_id,
                row.forward_filename,
                row.reverse_filename,
                self._display_status(row),
                "—" if row.consensus_length is None else str(row.consensus_length),
                "—" if row.conflict_count is None else str(row.conflict_count),
                "—" if row.unresolved_count is None else str(row.unresolved_count),
                self._display_note(row),
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row.sample_id)
                self._table.setItem(row_index, column_index, item)
        for row_index, row in enumerate(self._rows):
            if row.is_ready:
                self._table.selectRow(row_index)
                break
        self._update_output_controls()

    def _selected_ready_row(self) -> ConsensusSampleRow | None:
        row = self._selected_row()
        return row if row is not None and row.is_ready else None

    def _selected_effective_ready_row(self) -> ConsensusSampleRow | None:
        row = self._selected_row()
        if row is None:
            return None
        return self._manual_pair_rows.get(row.sample_id) or (row if row.is_ready else None)

    def _display_status(self, row: ConsensusSampleRow) -> str:
        if row.sample_id in self._output_excluded_sample_ids:
            return "Excluded"
        if row.sample_id in self._manual_pair_rows:
            return "Resolved Pair — review required"
        if row.sample_id in self._included_single_directions:
            direction = self._included_single_directions[row.sample_id].title()
            return f"Resolved as {direction} Single"
        return row.status

    def _display_note(self, row: ConsensusSampleRow) -> str:
        if row.sample_id in self._manual_pair_rows:
            resolved = self._manual_pair_rows[row.sample_id]
            unused = (
                len(row.sample.forward_candidates) - 1
                + len(row.sample.reverse_candidates) - 1
                + len(row.sample.unspecified_candidates)
            )
            suffix = f"; {unused} unused candidate(s) need attention" if unused else ""
            return f"Manual: {resolved.forward_filename} + {resolved.reverse_filename}{suffix}"
        return row.error or ""

    def _selected_row(self) -> ConsensusSampleRow | None:
        selected_ranges = self._table.selectedRanges()
        if not selected_ranges:
            return None
        row_index = selected_ranges[0].topRow()
        if not 0 <= row_index < len(self._rows):
            return None
        return self._rows[row_index]

    def _selected_row_changed(self) -> None:
        self._update_output_controls()

    @property
    def output_excluded_sample_ids(self) -> frozenset[str]:
        return frozenset(self._output_excluded_sample_ids)

    @property
    def included_single_directions(self) -> dict[str, str]:
        return dict(self._included_single_directions)

    def mark_pair_reviewed(self, sample_id: str, record: SequenceRecord) -> None:
        """Register one human-reviewed pair as an output candidate."""

        if not isinstance(record, SequenceRecord):
            raise ValueError("reviewed pair output must be a SequenceRecord")
        row = next((candidate for candidate in self._rows if candidate.sample_id == sample_id), None)
        if row is None or not (row.is_ready or sample_id in self._manual_pair_rows):
            raise ValueError("only a resolved F/R pair can become a reviewed output candidate")
        self._reviewed_pair_records[sample_id] = record
        self._output_excluded_sample_ids.discard(sample_id)
        self.status_message_changed.emit(f"Reviewed pair ready for output: {sample_id}")

    def include_selected_as_forward_single(self) -> bool:
        return self._include_selected_single(PairingStatus.ORPHAN_FORWARD, "FORWARD")

    def include_selected_as_reverse_single(self) -> bool:
        return self._include_selected_single(PairingStatus.ORPHAN_REVERSE, "REVERSE")

    def _include_selected_single(self, status: PairingStatus, direction: str) -> bool:
        row = self._selected_row()
        if row is None or row.sample.pairing_status is not status:
            self.status_message_changed.emit(
                f"Select a {direction.title()} orphan to include it as a single read."
            )
            return False
        self._included_single_directions[row.sample_id] = direction
        self._included_single_reads.pop(row.sample_id, None)
        self._output_excluded_sample_ids.discard(row.sample_id)
        self.status_message_changed.emit(
            f"Included as {direction.title()} single: {row.sample_id}"
        )
        return True

    def include_ambiguous_single(
        self, row: ConsensusSampleRow, direction: str, read: object | None
    ) -> bool:
        """Explicitly route one selected ambiguous candidate through Pass 3B output."""

        candidates = (
            row.sample.forward_candidates if direction == "FORWARD" else row.sample.reverse_candidates
        )
        if row.sample.pairing_status is not PairingStatus.AMBIGUOUS or not any(candidate is read for candidate in candidates):
            raise ValueError(f"selected {direction.title()} read is not an ambiguous-pair candidate")
        self._manual_pair_rows.pop(row.sample_id, None)
        self._reviewed_pair_records.pop(row.sample_id, None)
        self._included_single_directions[row.sample_id] = direction
        self._included_single_reads[row.sample_id] = (direction, read)
        self._output_excluded_sample_ids.discard(row.sample_id)
        self._populate_table()
        self.status_message_changed.emit(f"Included selected candidate as {direction.title()} single: {row.sample_id}")
        return True

    def exclude_selected_from_output(self) -> bool:
        row = self._selected_row()
        if row is None:
            return False
        self._included_single_directions.pop(row.sample_id, None)
        self._included_single_reads.pop(row.sample_id, None)
        self._manual_pair_rows.pop(row.sample_id, None)
        self._reviewed_pair_records.pop(row.sample_id, None)
        self._output_excluded_sample_ids.add(row.sample_id)
        self.status_message_changed.emit(f"Excluded from output: {row.sample_id}")
        return True

    def output_summary(self) -> dict[str, int]:
        forward = sum(direction == "FORWARD" for direction in self._included_single_directions.values())
        reverse = sum(direction == "REVERSE" for direction in self._included_single_directions.values())
        needs_attention = sum(self._row_needs_attention(row) for row in self._rows)
        return {
            "reviewed_consensus": len(self._reviewed_pair_records),
            "forward_singles": forward,
            "reverse_singles": reverse,
            "excluded": len(self._output_excluded_sample_ids),
            "needs_attention": needs_attention,
            "manual_pairs": len(self._manual_pair_rows),
        }

    def _row_needs_attention(self, row: ConsensusSampleRow) -> bool:
        if row.sample_id in self._output_excluded_sample_ids:
            return False
        if row.sample_id in self._manual_pair_rows:
            return bool(
                len(row.sample.forward_candidates) > 1
                or len(row.sample.reverse_candidates) > 1
                or row.sample.unspecified_candidates
            )
        return row.sample.pairing_status in (PairingStatus.AMBIGUOUS, PairingStatus.SINGLE_UNSPECIFIED)

    def build_output_records(self) -> tuple[SequenceRecord, ...]:
        """Build final output records from explicit pair/orphan choices only."""

        if not isinstance(self._source_dataset, SequenceDataset):
            raise ValueError("F/R output requires a registered source SequenceDataset.")
        records: list[SequenceRecord] = []
        for row in self._rows:
            if row.sample_id in self._output_excluded_sample_ids:
                continue
            reviewed = self._reviewed_pair_records.get(row.sample_id)
            if reviewed is not None:
                records.append(
                    _output_reviewed_pair_record(
                        row,
                        reviewed,
                        resolution_row=self._manual_pair_rows.get(row.sample_id),
                    )
                )
                continue
            direction = self._included_single_directions.get(row.sample_id)
            if direction == "FORWARD":
                read = self._included_single_reads.get(row.sample_id, (None, None))[1]
                records.append(_output_orphan_record(row, self._source_dataset, direction, read=read))
            elif direction == "REVERSE":
                read = self._included_single_reads.get(row.sample_id, (None, None))[1]
                records.append(_output_orphan_record(row, self._source_dataset, direction, read=read))
        sequence_ids = tuple(record.sequence_id for record in records)
        collisions = tuple(sorted({value for value in sequence_ids if sequence_ids.count(value) > 1}))
        if collisions:
            raise ValueError("F/R output record ID collision: " + ", ".join(collisions))
        return tuple(records)

    def create_and_register_output_dataset(self) -> SequenceDataset | None:
        summary = self.output_summary()
        if summary["needs_attention"]:
            response = QMessageBox.question(
                self,
                "Create F/R Output Dataset",
                "Unresolved pairing rows will not be included:\n\n"
                f"Reviewed Consensus: {summary['reviewed_consensus']}\n"
                f"  Manually resolved pairs: {summary['manual_pairs']}\n"
                f"Forward Singles: {summary['forward_singles']}\n"
                f"Reverse Singles: {summary['reverse_singles']}\n"
                f"Excluded: {summary['excluded']}\n"
                f"Needs Attention: {summary['needs_attention']}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if response != QMessageBox.StandardButton.Yes:
                return None
        controller = getattr(self._context, "project_controller", None)
        create_method = getattr(controller, "create_fr_output_dataset_from_manager", None)
        if not callable(create_method):
            self.status_message_changed.emit("F/R output registration is not configured.")
            return None
        try:
            dataset = create_method(self)
        except ValueError as error:
            self.status_message_changed.emit(str(error))
            return None
        self.status_message_changed.emit(f"F/R Output Dataset created: {dataset.dataset_id}")
        return dataset

    def _update_output_controls(self) -> None:
        row = self._selected_row()
        status = row.sample.pairing_status if row is not None else None
        self._include_forward_button.setEnabled(status is PairingStatus.ORPHAN_FORWARD)
        self._include_reverse_button.setEnabled(status is PairingStatus.ORPHAN_REVERSE)
        self._resolve_pair_button.setEnabled(status is PairingStatus.AMBIGUOUS)
        self._exclude_output_button.setEnabled(row is not None)

    def review_all(self) -> object | None:
        ready_rows = self.ready_rows
        if len(ready_rows) < 2:
            self.status_message_changed.emit("Multiple Review requires at least two Ready F/R pairs.")
            return None
        controller = getattr(self._context, "project_controller", None)
        open_method = getattr(controller, "open_multiple_fr_consensus_review", None)
        if callable(open_method):
            return open_method(ready_rows, source_dataset=self._source_dataset)
        self.open_related_requested.emit(
            {"action": "REVIEW_ALL_CONSENSUS", "rows": ready_rows}
        )
        return None


class SingleConsensusReviewViewer(BaseViewer):
    """Studio F/R single consensus review using existing core review models."""

    def __init__(
        self,
        row: ConsensusSampleRow,
        *,
        context: object | None = None,
        source_dataset: object | None = None,
        settings_metadata: dict[str, object] | None = None,
        output_manager: object | None = None,
    ) -> None:
        if not isinstance(row, ConsensusSampleRow) or row.view_model is None:
            raise ValueError("SingleConsensusReviewViewer requires a ready consensus row")
        self._row = row
        self._view_model = row.view_model
        self._context = context
        self._source_dataset = source_dataset
        self._source_record_provenance = (
            row.source_record_provenance
            or pair_record_provenance(
                row.sample,
                source_dataset if isinstance(source_dataset, SequenceDataset) else None,
            )
        )
        self._settings_metadata = dict(settings_metadata or {})
        self._output_manager = output_manager
        self._reviewed_bases = list(self._view_model.consensus_sequence)
        self._selected_position = 0
        self._conflict_positions = tuple(
            index
            for index, column in enumerate(self._view_model.columns)
            if _is_conflict_column(column)
        )
        self._undo_stack: list[tuple[str, object]] = []
        self._redo_stack: list[tuple[str, object]] = []
        self._action_provider = SingleConsensusReviewActionProvider()
        source_id = getattr(source_dataset, "dataset_id", None)
        super().__init__(
            viewer_id=f"single-consensus-review-{source_id or 'reads'}-{row.sample_id}",
            viewer_title=f"Consensus Review: {row.sample_id}",
            viewer_kind="single-consensus-review",
            source_object_id=source_id,
        )
        self._build_ui()

    @property
    def sample_id(self) -> str:
        return self._view_model.sample_identifier

    @property
    def original_consensus(self) -> str:
        return self._view_model.consensus_sequence

    @property
    def reviewed_consensus(self) -> str:
        return "".join(self._reviewed_bases)

    @property
    def selected_position(self) -> int:
        return self._selected_position

    @property
    def source_dataset(self) -> object | None:
        return self._source_dataset

    @property
    def source_record_provenance(self) -> RecordProvenance | None:
        return self._source_record_provenance

    @property
    def output_manager(self) -> object | None:
        return self._output_manager

    @property
    def settings_metadata(self) -> dict[str, object]:
        return dict(self._settings_metadata)

    @property
    def has_pending_scientific_changes(self) -> bool:
        return bool(self._undo_stack)

    @property
    def is_dirty(self) -> bool:
        return self.has_pending_scientific_changes

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "single_consensus.accept",
            "single_consensus.jump_forward",
            "single_consensus.jump_reverse",
            "single_consensus.previous_conflict",
            "single_consensus.next_conflict",
            "single_consensus.undo",
            "single_consensus.redo",
            "single_consensus.set_selection_gap",
            "single_consensus.set_selection_n",
            "single_consensus.create_dataset",
        )

    @property
    def selected_evidence(self):
        return self._view_model.columns[self._selected_position].review_evidence

    def select_position(self, position: int) -> None:
        if not 0 <= int(position) < len(self._view_model.columns):
            return
        self._selected_position = int(position)
        self._grid.select_cell("reviewed", self._selected_position)
        self._pair_chromatogram.select_column(self._selected_position, emit=False)
        self._update_detail()

    @property
    def conflict_positions(self) -> tuple[int, ...]:
        """Zero-based PairAlignment columns requiring F/R conflict review."""

        return self._conflict_positions

    def next_conflict(self) -> bool:
        return self._select_relative_conflict(1)

    def previous_conflict(self) -> bool:
        return self._select_relative_conflict(-1)

    def _select_relative_conflict(self, direction: int) -> bool:
        if not self._conflict_positions:
            self.status_message_changed.emit("This F/R pair has no conflict columns.")
            return False
        if direction > 0:
            target = next(
                (position for position in self._conflict_positions if position > self._selected_position),
                self._conflict_positions[0],
            )
        else:
            target = next(
                (position for position in reversed(self._conflict_positions) if position < self._selected_position),
                self._conflict_positions[-1],
            )
        self.select_position(target)
        return True

    def set_selected_base(self, base: str) -> bool:
        return self.set_base(self._selected_position, base)

    def set_base(self, position: int, base: str) -> bool:
        base = str(base).upper()
        if base not in _SUPPORTED_REVIEW_BASES:
            raise ValueError("base must be A/C/G/T/N/-")
        if not 0 <= int(position) < len(self._reviewed_bases):
            return False
        position = int(position)
        previous = self._reviewed_bases[position]
        if previous == base:
            return False
        change = (position, previous, base)
        self._apply_base_changes((change,))
        self._undo_stack.append(("bases", (change,)))
        self._redo_stack.clear()
        self.select_position(position)
        return True

    def set_selection_to_gap(self) -> bool:
        return self.set_selection_to_base("-")

    def set_selection_to_n(self) -> bool:
        return self.set_selection_to_base("N")

    def request_set_selection_to_gap(self) -> bool:
        return self._request_bulk_selection_edit("-")

    def request_set_selection_to_n(self) -> bool:
        return self._request_bulk_selection_edit("N")

    def set_selection_to_base(self, base: str) -> bool:
        base = str(base).upper()
        if base not in _SUPPORTED_REVIEW_BASES:
            raise ValueError("base must be A/C/G/T/N/-")
        changes = []
        for row_id, position in self._grid.selected_cells():
            if row_id != "reviewed":
                continue
            if not 0 <= position < len(self._reviewed_bases):
                continue
            previous = self._reviewed_bases[position]
            if previous != base:
                changes.append((position, previous, base))
        if not changes:
            return False
        self._apply_base_changes(changes)
        self._undo_stack.append(("bases", tuple(changes)))
        self._redo_stack.clear()
        last_position = changes[-1][0]
        self.select_position(last_position)
        return True

    def _request_bulk_selection_edit(self, base: str) -> bool:
        editable_changes = [
            position
            for row_id, position in self._grid.selected_cells()
            if row_id == "reviewed"
            and 0 <= position < len(self._reviewed_bases)
            and self._reviewed_bases[position] != base
        ]
        if len(editable_changes) > 1:
            response = QMessageBox.question(
                self,
                "Edit Reviewed Consensus",
                f"Set {len(editable_changes)} selected reviewed consensus cells to {base}?",
            )
            if response != QMessageBox.StandardButton.Yes:
                return False
        return self.set_selection_to_base(base)

    def accept_selected(self) -> bool:
        original = self.original_consensus[self._selected_position]
        return self.set_base(self._selected_position, original)

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        operation, payload = self._undo_stack.pop()
        if operation == "bases":
            self._apply_base_changes(payload, use_new=False)
            self.select_position(payload[-1][0])
        self._redo_stack.append((operation, payload))
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        operation, payload = self._redo_stack.pop()
        if operation == "bases":
            self._apply_base_changes(payload, use_new=True)
            self.select_position(payload[-1][0])
        self._undo_stack.append((operation, payload))
        return True

    def create_reviewed_consensus(self):
        session = ConsensusReviewSession(
            sample_id=self.sample_id,
            candidate_reference=self._view_model,
        )
        for position, original in enumerate(self.original_consensus):
            reviewed = self._reviewed_bases[position]
            if reviewed == original:
                decision_type = DecisionType.ACCEPT
                reviewed_base = original
            elif reviewed == "N":
                decision_type = DecisionType.AMBIGUOUS
                reviewed_base = reviewed
            else:
                decision_type = DecisionType.CHANGE
                reviewed_base = reviewed
            session.add_decision(
                HumanReviewDecision(
                    sample_id=self.sample_id,
                    consensus_position=position,
                    original_base=original,
                    reviewed_base=reviewed_base,
                    decision_type=decision_type,
                    reason="Studio F/R Consensus Review",
                    evidence_reference=self._view_model.columns[position].review_evidence,
                    reviewer="SangerFlow-Studio",
                    timestamp=datetime.now(timezone.utc),
                )
            )
        return build_reviewed_consensus(
            self.sample_id,
            self.original_consensus,
            session,
        )

    def create_and_register_reviewed_dataset(self):
        controller = getattr(self._context, "project_controller", None)
        register_method = getattr(controller, "register_fr_reviewed_consensus_from_viewer", None)
        if not callable(register_method):
            self.status_message_changed.emit("Project registration is not configured.")
            return None
        dataset = register_method(self)
        self.status_message_changed.emit(f"Reviewed Consensus Dataset created: {dataset.dataset_id}")
        return dataset

    def close_viewer(self) -> bool:
        intent = self.prepare_close()
        return intent is not None and self.commit_close(intent)

    def prepare_close(self) -> str | None:
        """Collect a single F/R review close choice without changing it."""

        if not self.has_pending_scientific_changes:
            return "close"
        choice = QMessageBox.warning(
            self,
            "Unsaved Consensus Review Edits",
            "This review has pending scientific edits.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return None
        return "save" if choice == QMessageBox.StandardButton.Save else "discard"

    def commit_close(self, intent: object) -> bool:
        if intent == "save":
            return self.create_and_register_reviewed_dataset() is not None
        return True

    def jump_to_forward_trace(self) -> bool:
        return self._emit_trace_jump(self.selected_evidence.forward_jump_target, "Forward")

    def jump_to_reverse_trace(self) -> bool:
        return self._emit_trace_jump(self.selected_evidence.reverse_jump_target, "Reverse")

    def _emit_trace_jump(self, target: object | None, label: str) -> bool:
        if target is None:
            self.status_message_changed.emit(
                f"{label} trace evidence is not available for this position."
            )
            return False
        self.open_related_requested.emit(
            {
                "action": "TRACE_JUMP",
                "viewer": self,
                "sample_id": self.sample_id,
                "read_id": getattr(target, "read_identifier", None),
                "raw_trace_position": getattr(target, "raw_trace_position", None),
            }
        )
        self.status_message_changed.emit(
            f"{label} trace jump requested: "
            f"{getattr(target, 'read_identifier', '—')} @ "
            f"{getattr(target, 'raw_trace_position', '—')}"
        )
        return True

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f"Sample: {self.sample_id}    "
                f"Forward: {self._row.forward_filename}    Reverse: {self._row.reverse_filename}"
            )
        )
        self._detail_label = QLabel()
        self._detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._detail_label)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self._grid = SequenceGridWidget()
        self._grid.setObjectName("singleConsensusReviewSequenceGrid")
        self._grid.cell_selected.connect(self._grid_cell_selected)
        self._grid.cell_edited.connect(self._grid_cell_edited)
        self._grid.undo_requested.connect(self.undo)
        self._grid.redo_requested.connect(self.redo)
        self._grid.selection_changed.connect(self._grid_selection_changed)
        self._table = self._grid
        splitter.addWidget(self._grid)
        forward_read = self._row.sample.forward_read
        reverse_read = self._row.sample.reverse_read
        if forward_read is None or reverse_read is None:
            raise ValueError("ready consensus row is missing its Forward or Reverse read")
        self._pair_chromatogram = PairConsensusChromatogramPanel(
            forward_read,
            reverse_read,
            self._view_model.columns,
        )
        self._pair_chromatogram.setObjectName("singleConsensusPairChromatograms")
        self._pair_chromatogram.column_selected.connect(self._pair_chromatogram_column_selected)
        splitter.addWidget(self._pair_chromatogram)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        edit_buttons = QHBoxLayout()
        jump_forward_button = QPushButton("Jump Forward")
        jump_forward_button.setIcon(studio_icon("next"))
        jump_forward_button.clicked.connect(self.jump_to_forward_trace)
        jump_reverse_button = QPushButton("Jump Reverse")
        jump_reverse_button.setIcon(studio_icon("previous"))
        jump_reverse_button.clicked.connect(self.jump_to_reverse_trace)
        previous_conflict_button = QPushButton("Previous Conflict")
        previous_conflict_button.setIcon(studio_icon("previous"))
        previous_conflict_button.clicked.connect(self.previous_conflict)
        next_conflict_button = QPushButton("Next Conflict")
        next_conflict_button.setIcon(studio_icon("next"))
        next_conflict_button.clicked.connect(self.next_conflict)
        accept_button = QPushButton("Accept Auto")
        accept_button.setIcon(studio_icon("accept"))
        accept_button.clicked.connect(self.accept_selected)
        undo_button = QPushButton("Undo")
        undo_button.setIcon(studio_icon("undo"))
        undo_button.clicked.connect(self.undo)
        redo_button = QPushButton("Redo")
        redo_button.setIcon(studio_icon("redo"))
        redo_button.clicked.connect(self.redo)
        create_button = QPushButton("Create Reviewed Consensus")
        create_button.setIcon(studio_icon("create_dataset"))
        create_button.clicked.connect(self.create_and_register_reviewed_dataset)
        edit_buttons.addWidget(jump_forward_button)
        edit_buttons.addWidget(jump_reverse_button)
        edit_buttons.addWidget(previous_conflict_button)
        edit_buttons.addWidget(next_conflict_button)
        edit_buttons.addWidget(accept_button)
        edit_buttons.addWidget(undo_button)
        edit_buttons.addWidget(redo_button)
        edit_buttons.addWidget(create_button)
        edit_buttons.addStretch(1)
        layout.addLayout(edit_buttons)
        self._populate_grid()
        self.select_position(0)

    def _populate_grid(self) -> None:
        self._grid.set_rows(
            (
                SequenceGridRow(
                    "forward",
                    "Forward",
                    _side_sequence(self._view_model, "forward_base"),
                ),
                SequenceGridRow(
                    "reverse",
                    "Reverse",
                    _side_sequence(self._view_model, "reverse_base"),
                ),
                SequenceGridRow(
                    "auto",
                    "Auto Consensus",
                    self.original_consensus,
                ),
                SequenceGridRow(
                    "reviewed",
                    "Reviewed Consensus",
                    self.reviewed_consensus,
                    editable=True,
                ),
            ),
            edited_cells=self._edited_cells(),
        )

    def _refresh_grid_cell(self, position: int) -> None:
        self._grid.set_cell_base(
            "reviewed",
            position,
            self._reviewed_bases[position],
            edited=self._reviewed_bases[position] != self.original_consensus[position],
        )

    def _apply_base_changes(
        self,
        changes: object,
        *,
        use_new: bool = True,
    ) -> None:
        for position, previous, current in changes:
            self._reviewed_bases[position] = current if use_new else previous
            self._refresh_grid_cell(position)

    def _edited_cells(self) -> set[tuple[str, int]]:
        return {
            ("reviewed", position)
            for position, base in enumerate(self._reviewed_bases)
            if base != self.original_consensus[position]
        }

    def _grid_cell_selected(self, row_id: str, column_index: int, base: str) -> None:
        if not 0 <= column_index < len(self._view_model.columns):
            return
        self._selected_position = column_index
        self._pair_chromatogram.select_column(column_index, emit=False)
        self._update_detail()

    def _pair_chromatogram_column_selected(self, column_index: int) -> None:
        """Reverse-sync a chromatogram click to the common PairAlignment cell."""

        self.select_position(column_index)

    def _grid_cell_edited(self, row_id: str, column_index: int, base: str) -> None:
        if row_id != "reviewed":
            return
        self.set_base(column_index, base)

    def _grid_selection_changed(self, _selection: object) -> None:
        if self._grid.selection.is_single_cell:
            return
        self._detail_label.setText(
            f"{self._grid.selection_status_text()}\nMultiple positions selected."
        )

    def _update_detail(self) -> None:
        column = self._view_model.columns[self._selected_position]
        evidence = column.review_evidence
        reviewed_base = self._reviewed_bases[self._selected_position]
        automatic_base = evidence.consensus_base
        review_state = "Manual change" if reviewed_base != automatic_base else "Not changed"
        self._detail_label.setText(
            "Selected consensus position: "
            f"{self._selected_position + 1}\n"
            f"Automatic decision: {automatic_base}    "
            f"Evidence source: {decision_source_label(column.selected_source)}\n"
            f"Automatic reason: {decision_reason_label(getattr(evidence, 'decision_reason', None))}\n"
            f"Reviewed base: {reviewed_base} ({review_state})\n"
            "Forward evidence: "
            f"base={_format_optional(evidence.forward_base)} "
            f"Q={_format_quality(evidence.forward_quality)} "
            f"raw={_format_optional(evidence.forward_raw_index)} "
            f"trim={_format_optional(evidence.forward_trimmed_index)} "
            f"trace={_format_optional(evidence.forward_raw_trace_position)}\n"
            "Reverse evidence: "
            f"base={_format_optional(evidence.reverse_base)} "
            f"Q={_format_quality(evidence.reverse_quality)} "
            f"raw={_format_optional(evidence.reverse_raw_index)} "
            f"trim={_format_optional(evidence.reverse_trimmed_index)} "
            f"trace={_format_optional(evidence.reverse_raw_trace_position)}"
        )


class MultipleConsensusReviewViewer(BaseViewer):
    """Mesquite-style multi-sample reviewed-consensus editor."""

    def __init__(
        self,
        rows: tuple[ConsensusSampleRow, ...],
        *,
        context: object | None = None,
        source_dataset: object | None = None,
    ) -> None:
        ready_rows = tuple(row for row in rows if row.is_ready and row.view_model is not None)
        if len(ready_rows) < 2:
            raise ValueError("MultipleConsensusReviewViewer requires at least two ready rows")
        self._rows = ready_rows
        self._context = context
        self._source_dataset = source_dataset
        self._source_record_provenance_by_sample = {
            row.sample_id: (
                row.source_record_provenance
                or pair_record_provenance(
                    row.sample,
                    source_dataset if isinstance(source_dataset, SequenceDataset) else None,
                )
            )
            for row in self._rows
        }
        self._reviewed_sequences = {
            row.sample_id: list(row.view_model.consensus_sequence)
            for row in self._rows
        }
        self._selected_sample_id = self._rows[0].sample_id
        self._selected_position = 0
        self._selected_mafft_column: int | None = None
        self._temporary_alignment: TemporaryConsensusAlignment | None = None
        self._sample_visibility: dict[str, QCheckBox] = {}
        # Display visibility and output inclusion deliberately have separate
        # state: hiding evidence must never silently remove a sample from a
        # reviewed-consensus Dataset.
        self._hidden_sample_ids: set[str] = set()
        self._deleted_sample_ids: set[str] = set()
        self._output_excluded_sample_ids: set[str] = set()
        self._undo_stack: list[object] = []
        self._redo_stack: list[object] = []
        self._variable_sites = self._compute_variable_sites()
        self._action_provider = MultipleConsensusReviewActionProvider()
        source_id = getattr(source_dataset, "dataset_id", None)
        super().__init__(
            viewer_id=f"multiple-consensus-review-{source_id or id(self)}",
            viewer_title="Multiple Consensus Review",
            viewer_kind="multiple-consensus-review",
            source_object_id=source_id,
        )
        self._build_ui()

    @property
    def rows(self) -> tuple[ConsensusSampleRow, ...]:
        return self._rows

    @property
    def source_dataset(self) -> object | None:
        return self._source_dataset

    @property
    def variable_sites(self) -> tuple[int, ...]:
        return self._variable_sites

    @property
    def reviewed_sequences(self) -> dict[str, str]:
        return {
            sample_id: "".join(bases)
            for sample_id, bases in self._reviewed_sequences.items()
        }

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "multiple_consensus.previous_variable_site",
            "multiple_consensus.next_variable_site",
            "multiple_consensus.undo",
            "multiple_consensus.redo",
            "multiple_consensus.set_selection_gap",
            "multiple_consensus.set_selection_n",
            "multiple_consensus.align_selected",
            "multiple_consensus.previous_conflict",
            "multiple_consensus.next_conflict",
            "multiple_consensus.create_dataset",
            "multiple_consensus.hide_rows",
            "multiple_consensus.show_all_rows",
            "multiple_consensus.delete_rows",
            "multiple_consensus.exclude_rows_from_output",
            "multiple_consensus.include_all_output_rows",
            "multiple_consensus.paste",
        )

    def select_cell(self, sample_id: str, position: int) -> bool:
        if sample_id not in self._reviewed_sequences:
            return False
        if not 0 <= int(position) < len(self._reviewed_sequences[sample_id]):
            return False
        self._selected_sample_id = sample_id
        self._selected_position = int(position)
        if self._temporary_alignment is not None:
            column = self._temporary_alignment.row_for(sample_id).column_for_consensus_position(
                self._selected_position
            )
            if column is None:
                return False
            self._selected_mafft_column = column
            self._grid.select_cell(sample_id, column)
        else:
            self._selected_mafft_column = None
            self._grid.select_cell(sample_id, self._selected_position)
        self._sync_pair_chromatogram()
        self._update_detail()
        return True

    @property
    def temporary_alignment(self) -> TemporaryConsensusAlignment | None:
        return self._temporary_alignment

    def selected_alignment_sample_ids(self) -> tuple[str, ...]:
        return tuple(
            row.sample_id
            for row in self._rows
            if self._sample_visibility[row.sample_id].isChecked()
        )

    @property
    def hidden_sample_ids(self) -> frozenset[str]:
        return frozenset(self._hidden_sample_ids)

    @property
    def output_excluded_sample_ids(self) -> frozenset[str]:
        return frozenset(self._output_excluded_sample_ids)

    @property
    def pending_deleted_row_ids(self) -> frozenset[str]:
        return frozenset(self._deleted_sample_ids)

    @property
    def has_pending_scientific_changes(self) -> bool:
        return bool(self._undo_stack)

    @property
    def transient_consensus_sequences(self) -> dict[str, str]:
        """Current sequences, excluding pending-deleted samples but not hidden ones."""

        return {
            sample_id: "".join(sequence)
            for sample_id, sequence in self._reviewed_sequences.items()
            if sample_id not in self._deleted_sample_ids
        }

    def hide_selected_rows(self) -> bool:
        sample_ids = set(self._grid.selected_rows())
        if not sample_ids:
            return False
        self._hidden_sample_ids.update(sample_ids)
        self._populate_grid()
        self._select_first_visible_sample()
        self.status_message_changed.emit(f"Hidden samples: {len(sample_ids)}")
        return True

    def delete_selected_rows(self) -> bool:
        """Stage a scientific/output deletion distinct from viewer-only Hide."""

        sample_ids = set(self._grid.selected_rows())
        remaining = {
            row.sample_id for row in self._rows
            if row.sample_id not in self._deleted_sample_ids and row.sample_id not in sample_ids
        }
        if not sample_ids or not remaining:
            return False
        before = frozenset(self._deleted_sample_ids)
        after = frozenset(self._deleted_sample_ids | sample_ids)
        operation = DeleteRowsOperation(before, after)
        operation.apply(self)
        self._undo_stack.append(operation)
        self._redo_stack.clear()
        self.status_message_changed.emit(
            f"Unsaved changes • {len(self._deleted_sample_ids)} sample(s) deleted from next output."
        )
        return True

    def show_all_rows(self) -> None:
        self._hidden_sample_ids.clear()
        self._populate_grid()
        self._select_first_visible_sample()
        self.status_message_changed.emit("All consensus samples shown.")

    def exclude_selected_rows_from_output(self) -> bool:
        sample_ids = set(self._grid.selected_rows())
        if not sample_ids:
            return False
        self._output_excluded_sample_ids.update(sample_ids)
        self.status_message_changed.emit(f"Excluded from next output: {len(sample_ids)} sample(s).")
        return True

    def include_all_output_rows(self) -> None:
        self._output_excluded_sample_ids.clear()
        self.status_message_changed.emit("All consensus samples included in next output.")

    def alignment_input_sequences(self) -> dict[str, str]:
        """Return current reviewed sequences for the explicitly selected samples."""

        selected = self.selected_alignment_sample_ids()
        if len(selected) < 2:
            raise ValueError("Select at least two consensus samples to align.")
        sequences = {sample_id: self._reviewed_sequences[sample_id] for sample_id in selected}
        gap_samples = tuple(sample_id for sample_id, sequence in sequences.items() if "-" in sequence)
        if gap_samples:
            raise ValueError(
                "Temporary MAFFT alignment cannot use reviewed consensus containing gaps: "
                + ", ".join(gap_samples)
            )
        return {sample_id: "".join(sequence) for sample_id, sequence in sequences.items()}

    def set_temporary_alignment(self, aligned_dataset: SequenceDataset) -> None:
        """Replace the complete session-only mapping after MAFFT succeeds."""

        source_sequences = self.alignment_input_sequences()
        alignment = TemporaryConsensusAlignment.from_mafft_dataset(
            aligned_dataset,
            source_sequences,
        )
        self._temporary_alignment = alignment
        self._selected_mafft_column = None
        self._populate_grid()
        first_sample = next(iter(alignment.rows))
        self.select_cell(first_sample, 0)
        self.status_message_changed.emit(
            f"Temporary MAFFT alignment ready: {len(alignment.rows)} samples, {alignment.length} columns."
        )

    def request_align_selected(self) -> object | None:
        controller = getattr(self._context, "project_controller", None)
        align_method = getattr(controller, "align_multiple_consensus_review", None)
        if not callable(align_method):
            self.status_message_changed.emit("Temporary MAFFT alignment is not configured.")
            return None
        try:
            return align_method(self)
        except Exception as error:
            self.status_message_changed.emit(str(error))
            return None

    def set_selected_base(self, base: str) -> bool:
        return self.set_base(self._selected_sample_id, self._selected_position, base)

    def set_base(self, sample_id: str, position: int, base: str) -> bool:
        base = str(base).upper()
        if base not in _SUPPORTED_REVIEW_BASES:
            raise ValueError("base must be A/C/G/T/N/-")
        if self._temporary_alignment is not None and base == "-":
            raise ValueError(
                "Gap edits are unavailable while a temporary MAFFT alignment is active; re-align after structural edits."
            )
        if sample_id not in self._reviewed_sequences:
            return False
        position = int(position)
        sequence = self._reviewed_sequences[sample_id]
        if not 0 <= position < len(sequence):
            return False
        previous = sequence[position]
        if previous == base:
            return False
        change = (sample_id, position, previous, base)
        self._apply_base_changes((change,))
        self._undo_stack.append(BaseEditOperation((change,)))
        self._redo_stack.clear()
        self.select_cell(sample_id, position)
        return True

    def set_selection_to_gap(self) -> bool:
        return self.set_selection_to_base("-")

    def set_selection_to_n(self) -> bool:
        return self.set_selection_to_base("N")

    def request_set_selection_to_gap(self) -> bool:
        return self._request_bulk_selection_edit("-")

    def request_set_selection_to_n(self) -> bool:
        return self._request_bulk_selection_edit("N")

    def set_selection_to_base(self, base: str) -> bool:
        base = str(base).upper()
        if base not in _SUPPORTED_REVIEW_BASES:
            raise ValueError("base must be A/C/G/T/N/-")
        changes = []
        for sample_id, position in self._grid.selected_cells():
            if sample_id not in self._reviewed_sequences:
                continue
            sequence = self._reviewed_sequences[sample_id]
            if not 0 <= position < len(sequence):
                continue
            previous = sequence[position]
            if previous != base:
                changes.append((sample_id, position, previous, base))
        if not changes:
            return False
        self._apply_base_changes(changes)
        operation_type = BaseEditOperation if len(changes) == 1 else BulkBaseEditOperation
        self._undo_stack.append(operation_type(tuple(changes)))
        self._redo_stack.clear()
        sample_id, position, _previous, _current = changes[-1]
        self.select_cell(sample_id, position)
        return True

    def paste_selection(self, text: str | None = None) -> bool:
        """Apply a strict, in-bounds substitution matrix as one operation."""

        text = QApplication.clipboard().text() if text is None else str(text)
        lines = [
            line.strip().upper()
            for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if line.strip()
        ]
        if not lines or any(any(base not in _SUPPORTED_REVIEW_BASES for base in line) for line in lines):
            self.status_message_changed.emit("Paste accepts only A/C/G/T/N/- symbols.")
            return False
        bounds = self._grid.selection_bounds()
        if bounds is None:
            self.status_message_changed.emit("Select a consensus cell rectangle before pasting.")
            return False
        first_row, last_row, first_column, last_column = bounds
        target_rows = list(range(first_row, last_row + 1))
        target_columns = list(range(first_column, last_column + 1))
        exact_shape = (
            len(target_rows) == len(lines)
            and all(len(line) == len(target_columns) for line in lines)
        )
        if not exact_shape:
            if len(target_rows) != 1 or len(target_columns) != 1 or len({len(line) for line in lines}) != 1:
                self.status_message_changed.emit(
                    f"Paste shape mismatch. Expected: {len(target_rows)} × {len(target_columns)}; "
                    f"Clipboard: {len(lines)} × {max(len(line) for line in lines)}."
                )
                return False
            target_rows = list(range(first_row, first_row + len(lines)))
            target_columns = list(range(first_column, first_column + len(lines[0])))
            if target_rows[-1] >= len(self._grid.rows) or target_columns[-1] >= self._grid.column_count:
                self.status_message_changed.emit("Paste would extend the alignment; only substitution paste is allowed.")
                return False
        changes = []
        for row_offset, grid_row in enumerate(target_rows):
            sample_id = self._grid.rows[grid_row].row_id
            for column_offset, grid_column in enumerate(target_columns):
                position = grid_column
                if self._temporary_alignment is not None:
                    position = self._temporary_alignment.row_for(sample_id).consensus_position_for_column(grid_column)
                    if position is None or lines[row_offset][column_offset] == "-":
                        self.status_message_changed.emit(
                            "Paste cannot modify structural MAFFT gap columns; re-align after structural edits."
                        )
                        return False
                previous = self._reviewed_sequences[sample_id][position]
                current = lines[row_offset][column_offset]
                if previous != current:
                    changes.append((sample_id, position, previous, current))
        if not changes:
            return False
        if len(changes) > 1 and QMessageBox.question(
            self, "Paste Reviewed Consensus", f"Paste {len(changes)} base substitutions?"
        ) != QMessageBox.StandardButton.Yes:
            return False
        operation = BulkBaseEditOperation(tuple(changes))
        operation.apply(self)
        self._undo_stack.append(operation)
        self._redo_stack.clear()
        return True

    def _request_bulk_selection_edit(self, base: str) -> bool:
        editable_changes = [
            (sample_id, position)
            for sample_id, position in self._grid.selected_cells()
            if sample_id in self._reviewed_sequences
            and 0 <= position < len(self._reviewed_sequences[sample_id])
            and self._reviewed_sequences[sample_id][position] != base
        ]
        if len(editable_changes) > 1:
            response = QMessageBox.question(
                self,
                "Edit Reviewed Consensus",
                f"Set {len(editable_changes)} selected reviewed consensus cells to {base}?",
            )
            if response != QMessageBox.StandardButton.Yes:
                return False
        return self.set_selection_to_base(base)

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        operation = self._undo_stack.pop()
        operation.revert(self)
        changes = getattr(operation, "changes", ())
        if changes:
            sample_id, position, _previous, _current = changes[-1]
            self.select_cell(sample_id, position)
        self._redo_stack.append(operation)
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        operation = self._redo_stack.pop()
        operation.apply(self)
        changes = getattr(operation, "changes", ())
        if changes:
            sample_id, position, _previous, _current = changes[-1]
            self.select_cell(sample_id, position)
        self._undo_stack.append(operation)
        return True

    def next_variable_site(self) -> bool:
        return self._move_variable_site(1)

    def previous_variable_site(self) -> bool:
        return self._move_variable_site(-1)

    def create_reviewed_consensus_dataset(
        self,
        *,
        dataset_id: str,
        name: str,
        metadata: dict[str, object] | None = None,
    ) -> SequenceDataset:
        records = tuple(
            SequenceRecord(
                sequence_id=row.sample_id,
                sequence="".join(self._reviewed_sequences[row.sample_id]),
                source_reference=row.view_model,
                metadata={
                    "source": "Multiple Consensus Review",
                    "sample_id": row.sample_id,
                    "original_consensus": row.view_model.consensus_sequence,
                    "reviewed_consensus": "".join(self._reviewed_sequences[row.sample_id]),
                    "changed_positions": tuple(
                        index
                        for index, base in enumerate(self._reviewed_sequences[row.sample_id])
                        if base != row.view_model.consensus_sequence[index]
                    ),
                },
                provenance=(
                    self._source_record_provenance_by_sample[row.sample_id]
                    or RecordProvenance()
                ),
            )
            for row in self._rows
            if row.sample_id not in self._output_excluded_sample_ids
            and row.sample_id not in self._deleted_sample_ids
        )
        return SequenceDataset(
            dataset_id=dataset_id,
            name=name,
            source_type=SourceType.REVIEWED_CONSENSUS,
            records=records,
            metadata={
                "source": "Multiple Consensus Review",
                "reviewed": True,
                "consensus_method": "consensus-v2.1 + human_review",
                "original_read_count": len(self._rows) * 2,
                "sample_count": len(records),
                "variable_sites": self._variable_sites,
                "pending_deleted_rows": tuple(sorted(self._deleted_sample_ids)),
                "output_excluded_rows": tuple(sorted(self._output_excluded_sample_ids)),
                **(metadata or {}),
            },
        )

    def create_and_register_reviewed_dataset(self) -> SequenceDataset | None:
        controller = getattr(self._context, "project_controller", None)
        register_method = getattr(
            controller,
            "register_multiple_fr_reviewed_consensus_from_viewer",
            None,
        )
        if not callable(register_method):
            self.status_message_changed.emit("Project registration is not configured.")
            return None
        dataset = register_method(self)
        self.status_message_changed.emit(
            f"Multiple Reviewed Consensus Dataset created: {dataset.dataset_id}"
        )
        return dataset

    def close_viewer(self) -> bool:
        """Never lose pending reviewed-consensus or staged-row edits silently."""

        intent = self.prepare_close()
        return intent is not None and self.commit_close(intent)

    def prepare_close(self) -> str | None:
        """Ask for a review-close intent without changing review state."""

        if not self.has_pending_scientific_changes:
            return "close"
        choice = QMessageBox.warning(
            self,
            "Unsaved Consensus Review Edits",
            "This review has pending scientific edits.",
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
        """Apply an already-confirmed review close intent."""

        if intent == "save":
            return self.create_and_register_reviewed_dataset() is not None
        return True

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._summary_label = QLabel()
        layout.addWidget(self._summary_label)
        sample_controls = QHBoxLayout()
        alignment_samples_label = QLabel("Samples for temporary alignment:")
        alignment_samples_label.setToolTip(
            "Choose which reviewed samples are included in the temporary alignment preview. "
            "This does not change review status or reviewed-dataset output."
        )
        sample_controls.addWidget(alignment_samples_label)
        for row in self._rows:
            checkbox = QCheckBox(row.sample_id)
            checkbox.setChecked(True)
            self._sample_visibility[row.sample_id] = checkbox
            sample_controls.addWidget(checkbox)
        # Temporary MAFFT editing is intentionally not exposed here.  Save
        # reviewed consensus first, then use Sequence Editor — Unaligned →
        # Align… to create a formal AlignmentDataset with Project lineage.
        sample_controls.addStretch(1)
        layout.addLayout(sample_controls)
        self._detail_label = QLabel()
        self._detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._detail_label)
        self._grid = SequenceGridWidget()
        self._grid.setObjectName("multipleConsensusReviewSequenceGrid")
        self._grid.cell_selected.connect(self._grid_cell_selected)
        self._grid.cell_edited.connect(self._grid_cell_edited)
        self._grid.undo_requested.connect(self.undo)
        self._grid.redo_requested.connect(self.redo)
        self._grid.paste_requested.connect(self.paste_selection)
        self._grid.selection_changed.connect(self._grid_selection_changed)
        self._grid.set_context_menu_handler(self._show_grid_context_menu)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._grid)
        selected_row = self._row_for_sample(self._selected_sample_id)
        forward_read = selected_row.sample.forward_read
        reverse_read = selected_row.sample.reverse_read
        if forward_read is None or reverse_read is None:
            raise ValueError("ready consensus row is missing its Forward or Reverse read")
        self._pair_chromatogram = PairConsensusChromatogramPanel(
            forward_read,
            reverse_read,
            selected_row.view_model.columns,
        )
        self._pair_chromatogram.setObjectName("multipleConsensusPairChromatograms")
        self._pair_chromatogram.column_selected.connect(self._pair_chromatogram_column_selected)
        splitter.addWidget(self._pair_chromatogram)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        buttons = QHBoxLayout()
        previous_button = QPushButton("Previous Variable Site")
        previous_button.setIcon(studio_icon("previous"))
        previous_button.clicked.connect(self.previous_variable_site)
        next_button = QPushButton("Next Variable Site")
        next_button.setIcon(studio_icon("next"))
        next_button.clicked.connect(self.next_variable_site)
        previous_conflict_button = QPushButton("Previous Conflict")
        previous_conflict_button.setIcon(studio_icon("previous"))
        previous_conflict_button.clicked.connect(self.previous_conflict)
        next_conflict_button = QPushButton("Next Conflict")
        next_conflict_button.setIcon(studio_icon("next"))
        next_conflict_button.clicked.connect(self.next_conflict)
        create_button = QPushButton("Create Reviewed Consensus Dataset")
        create_button.setIcon(studio_icon("create_dataset"))
        create_button.clicked.connect(self.create_and_register_reviewed_dataset)
        buttons.addWidget(previous_button)
        buttons.addWidget(next_button)
        buttons.addWidget(previous_conflict_button)
        buttons.addWidget(next_conflict_button)
        undo_button = QPushButton("Undo")
        undo_button.setIcon(studio_icon("undo"))
        undo_button.clicked.connect(self.undo)
        redo_button = QPushButton("Redo")
        redo_button.setIcon(studio_icon("redo"))
        redo_button.clicked.connect(self.redo)
        buttons.addWidget(undo_button)
        buttons.addWidget(redo_button)
        buttons.addWidget(create_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._populate_grid()
        self.select_cell(self._selected_sample_id, 0)

    def _populate_grid(self) -> None:
        alignment = self._temporary_alignment
        self._grid.set_rows(
            tuple(
                SequenceGridRow(
                    row.sample_id,
                    row.sample_id,
                    (
                        alignment.row_for(row.sample_id).aligned_sequence
                        if alignment is not None and row.sample_id in alignment.rows
                        else "".join(self._reviewed_sequences[row.sample_id])
                    ),
                    editable=True,
                )
                for row in self._rows
                if row.sample_id not in self._hidden_sample_ids
                and row.sample_id not in self._deleted_sample_ids
                and (alignment is None or row.sample_id in alignment.rows)
            ),
            edited_cells=(self._aligned_edited_cells() if alignment is not None else self._edited_cells()),
        )
        self._summary_label.setText(
            f"Samples: {len(self._rows)}    "
            f"Pending deleted: {len(self._deleted_sample_ids)}    "
            f"Output excluded: {len(self._output_excluded_sample_ids)}    "
            f"{'MAFFT alignment' if alignment is not None else 'Consensus'} length: {self._grid.column_count}    "
            f"Variable sites: {len(self._variable_sites)}"
        )

    def _select_first_visible_sample(self) -> None:
        visible = tuple(row for row in self._rows if row.sample_id not in self._hidden_sample_ids)
        if visible:
            self.select_cell(visible[0].sample_id, 0)

    def _show_grid_context_menu(self, selection: object, global_position: object) -> None:
        menu = QMenu(self)
        mode = getattr(selection, "mode", "none")
        if mode == "row":
            hide = menu.addAction("Hide Sample(s)")
            hide.triggered.connect(self.hide_selected_rows)
            delete = menu.addAction("Delete Sample(s) from Next Output")
            delete.triggered.connect(self.delete_selected_rows)
            output = menu.addAction("Exclude from Reviewed Dataset Output")
            output.triggered.connect(self.exclude_selected_rows_from_output)
            menu.addSeparator()
            show_all = menu.addAction("Show All Samples")
            show_all.triggered.connect(self.show_all_rows)
            include_all = menu.addAction("Include All in Output")
            include_all.triggered.connect(self.include_all_output_rows)
        elif mode != "none":
            copy = menu.addAction("Copy")
            copy.triggered.connect(self._grid.copy_selection_to_clipboard)
            paste = menu.addAction("Paste (Substitution Only)")
            paste.triggered.connect(self.paste_selection)
            bases = menu.addMenu("Set Base")
            for base, label in (("A", "A"), ("C", "C"), ("G", "G"), ("T", "T"), ("N", "N"), ("-", "Gap")):
                action = bases.addAction(label)
                action.triggered.connect(lambda _checked=False, value=base: self._request_bulk_selection_edit(value))
            menu.addSeparator()
            undo = menu.addAction("Undo")
            undo.triggered.connect(self.undo)
            redo = menu.addAction("Redo")
            redo.triggered.connect(self.redo)
        if menu.actions():
            menu.exec(global_position)

    def _refresh_grid_cell(self, sample_id: str, position: int) -> None:
        original = self._original_sequence(sample_id)
        grid_column = position
        if self._temporary_alignment is not None:
            mapped_column = self._temporary_alignment.row_for(sample_id).column_for_consensus_position(position)
            if mapped_column is None:
                return
            grid_column = mapped_column
        self._grid.set_cell_base(
            sample_id,
            grid_column,
            self._reviewed_sequences[sample_id][position],
            edited=self._reviewed_sequences[sample_id][position] != original[position],
        )

    def _apply_base_changes(
        self,
        changes: object,
        *,
        use_new: bool = True,
    ) -> None:
        for sample_id, position, previous, current in changes:
            self._reviewed_sequences[sample_id][position] = current if use_new else previous
            self._refresh_grid_cell(sample_id, position)

    def _set_deleted_row_ids(self, row_ids: frozenset[str]) -> None:
        self._deleted_sample_ids = set(row_ids)
        self._selected_mafft_column = None
        self._populate_grid()
        self._select_first_visible_sample()

    def _edited_cells(self) -> set[tuple[str, int]]:
        edited: set[tuple[str, int]] = set()
        for row in self._rows:
            reviewed = self._reviewed_sequences[row.sample_id]
            original = row.view_model.consensus_sequence
            edited.update(
                (row.sample_id, position)
                for position, base in enumerate(reviewed)
                if base != original[position]
            )
        return edited

    def _aligned_edited_cells(self) -> set[tuple[str, int]]:
        if self._temporary_alignment is None:
            return self._edited_cells()
        edited: set[tuple[str, int]] = set()
        for sample_id, row in self._temporary_alignment.rows.items():
            original = self._original_sequence(sample_id)
            reviewed = self._reviewed_sequences[sample_id]
            for column, position in enumerate(row.consensus_positions):
                if position is not None and reviewed[position] != original[position]:
                    edited.add((sample_id, column))
        return edited

    def _row_for_sample(self, sample_id: str) -> ConsensusSampleRow:
        for row in self._rows:
            if row.sample_id == sample_id:
                return row
        raise KeyError(sample_id)

    def _sync_pair_chromatogram(self) -> None:
        row = self._row_for_sample(self._selected_sample_id)
        forward_read = row.sample.forward_read
        reverse_read = row.sample.reverse_read
        if forward_read is None or reverse_read is None:
            self._pair_chromatogram.clear_selection()
            return
        self._pair_chromatogram.set_evidence_source(
            forward_read,
            reverse_read,
            row.view_model.columns,
        )
        self._pair_chromatogram.select_column(self._selected_position, emit=False)

    def _pair_chromatogram_column_selected(self, pair_column: int) -> None:
        """Map an existing PairAlignment column back to its MAFFT display cell."""

        sample_id = self._selected_sample_id
        if self._temporary_alignment is not None:
            mafft_column = self._temporary_alignment.row_for(sample_id).column_for_consensus_position(
                pair_column
            )
            if mafft_column is None:
                return
            self._selected_mafft_column = mafft_column
            self._selected_position = pair_column
            self._grid.select_cell(sample_id, mafft_column)
        else:
            self._selected_position = pair_column
            self._grid.select_cell(sample_id, pair_column)
        self._update_detail()

    def _grid_cell_selected(self, row_id: str, column_index: int, base: str) -> None:
        self._selected_sample_id = row_id
        if self._temporary_alignment is not None:
            self._selected_mafft_column = column_index
            position = self._temporary_alignment.row_for(row_id).consensus_position_for_column(column_index)
            if position is None:
                self._pair_chromatogram.clear_selection()
                self._update_detail()
                return
            self._selected_position = position
        else:
            self._selected_mafft_column = None
            self._selected_position = column_index
        self._sync_pair_chromatogram()
        self._update_detail()

    def _grid_cell_edited(self, row_id: str, column_index: int, base: str) -> None:
        position = column_index
        if self._temporary_alignment is not None:
            position = self._temporary_alignment.row_for(row_id).consensus_position_for_column(column_index)
            if position is None or base == "-":
                self.status_message_changed.emit(
                    "MAFFT gap columns are structural and cannot be edited; re-align after structural edits.")
                self._populate_grid()
                return
        self.set_base(row_id, position, base)
        if self._temporary_alignment is not None:
            self._populate_grid()
            self.select_cell(row_id, position)

    def _grid_selection_changed(self, _selection: object) -> None:
        if self._grid.selection.is_single_cell:
            return
        self._detail_label.setText(
            f"{self._grid.selection_status_text()}\nMultiple positions selected."
        )

    def _update_detail(self) -> None:
        if self._temporary_alignment is not None and self._selected_mafft_column is not None:
            position = self._temporary_alignment.row_for(self._selected_sample_id).consensus_position_for_column(
                self._selected_mafft_column
            )
            if position is None:
                self._detail_label.setText(
                    f"Selected sample: {self._selected_sample_id}    "
                    f"Alignment column: {self._selected_mafft_column + 1}    "
                    "Consensus position: —    Forward trace: —    Reverse trace: —    Base: GAP"
                )
                return
        reviewed = self._reviewed_sequences[self._selected_sample_id]
        base = reviewed[self._selected_position]
        column = self._row_for_sample(self._selected_sample_id).view_model.columns[self._selected_position]
        evidence = column.review_evidence
        review_state = "Manual change" if base != evidence.consensus_base else "Not changed"
        self._detail_label.setText(
            f"Selected sample: {self._selected_sample_id}    "
            f"Alignment column: {(self._selected_mafft_column + 1) if self._selected_mafft_column is not None else self._selected_position + 1}    "
            f"Consensus position: {self._selected_position + 1}\n"
            f"Automatic decision: {evidence.consensus_base}    "
            f"Evidence source: {decision_source_label(column.selected_source)}\n"
            f"Automatic reason: {decision_reason_label(getattr(evidence, 'decision_reason', None))}\n"
            f"Reviewed base: {base} ({review_state})\n"
            f"Forward evidence: {_format_optional(evidence.forward_base)}, Q{_format_quality(evidence.forward_quality)}    "
            f"Reverse evidence: {_format_optional(evidence.reverse_base)}, Q{_format_quality(evidence.reverse_quality)}"
        )

    def _move_variable_site(self, direction: int) -> bool:
        if not self._variable_sites:
            return False
        current = self._selected_position
        if direction > 0:
            candidates = [site for site in self._variable_sites if site > current]
            target = candidates[0] if candidates else self._variable_sites[0]
        else:
            candidates = [site for site in self._variable_sites if site < current]
            target = candidates[-1] if candidates else self._variable_sites[-1]
        return self.select_cell(self._selected_sample_id, target)

    def _conflict_positions(self, sample_id: str) -> tuple[int, ...]:
        return tuple(
            index
            for index, column in enumerate(self._row_for_sample(sample_id).view_model.columns)
            if _is_conflict_column(column)
        )

    def next_conflict(self) -> bool:
        return self._move_conflict(1)

    def previous_conflict(self) -> bool:
        return self._move_conflict(-1)

    def _move_conflict(self, direction: int) -> bool:
        conflicts = self._conflict_positions(self._selected_sample_id)
        if not conflicts:
            return False
        current = self._selected_position
        candidates = [position for position in conflicts if (position > current if direction > 0 else position < current)]
        target = (candidates[0] if direction > 0 else candidates[-1]) if candidates else (
            conflicts[0] if direction > 0 else conflicts[-1]
        )
        return self.select_cell(self._selected_sample_id, target)

    def _compute_variable_sites(self) -> tuple[int, ...]:
        max_length = max(
            (len(row.view_model.consensus_sequence) for row in self._rows),
            default=0,
        )
        variable_sites = []
        for position in range(max_length):
            bases = {
                row.view_model.consensus_sequence[position]
                for row in self._rows
                if position < len(row.view_model.consensus_sequence)
            }
            if len(bases) > 1:
                variable_sites.append(position)
        return tuple(variable_sites)

    def _original_sequence(self, sample_id: str) -> str:
        for row in self._rows:
            if row.sample_id == sample_id:
                return row.view_model.consensus_sequence
        raise KeyError(sample_id)


class ConsensusReviewManagerActionProvider:
    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        return (
            ViewerAction(
                action_id="fr_consensus.review_selected",
                label="Review",
                tooltip="Open Single Consensus Review for the selected clear F/R pair",
                callback=getattr(viewer, "review_selected"),
                enabled=bool(getattr(viewer, "ready_rows", ())),
            ),
            ViewerAction(
                action_id="fr_consensus.review_all",
                label="Review All",
                tooltip="Open Multiple Consensus Review for all ready F/R pairs",
                callback=getattr(viewer, "review_all"),
                enabled=len(getattr(viewer, "ready_rows", ())) >= 2,
            ),
            ViewerAction(
                action_id="fr_consensus.resolve_pair",
                label="Resolve Pair…",
                tooltip="Explicitly select one Forward and one Reverse candidate",
                callback=getattr(viewer, "resolve_selected_pair"),
            ),
            ViewerAction(
                action_id="fr_consensus.include_forward_single",
                label="Include as Forward Single",
                tooltip="Explicitly include the selected Forward orphan in the next output Dataset",
                callback=getattr(viewer, "include_selected_as_forward_single"),
            ),
            ViewerAction(
                action_id="fr_consensus.include_reverse_single",
                label="Include as Reverse Single",
                tooltip="Explicitly include the selected Reverse orphan in assembly orientation",
                callback=getattr(viewer, "include_selected_as_reverse_single"),
            ),
            ViewerAction(
                action_id="fr_consensus.exclude_from_output",
                label="Exclude from Output",
                callback=getattr(viewer, "exclude_selected_from_output"),
            ),
            ViewerAction(
                action_id="fr_consensus.create_output_dataset",
                label="Create Output Dataset…",
                callback=getattr(viewer, "create_and_register_output_dataset"),
            ),
        )


class SingleConsensusReviewActionProvider:
    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        return (
            ViewerAction(
                action_id="single_consensus.accept",
                label="Accept Auto",
                callback=getattr(viewer, "accept_selected"),
            ),
            ViewerAction(
                action_id="single_consensus.jump_forward",
                label="Jump Forward",
                tooltip="Request a jump to the Forward read trace evidence",
                callback=getattr(viewer, "jump_to_forward_trace"),
            ),
            ViewerAction(
                action_id="single_consensus.jump_reverse",
                label="Jump Reverse",
                tooltip="Request a jump to the Reverse read trace evidence",
                callback=getattr(viewer, "jump_to_reverse_trace"),
            ),
            ViewerAction(
                action_id="single_consensus.previous_conflict",
                label="Previous Conflict",
                tooltip="Select the previous PairAlignment conflict column",
                callback=getattr(viewer, "previous_conflict"),
                enabled=bool(getattr(viewer, "conflict_positions", ())),
            ),
            ViewerAction(
                action_id="single_consensus.next_conflict",
                label="Next Conflict",
                tooltip="Select the next PairAlignment conflict column",
                callback=getattr(viewer, "next_conflict"),
                enabled=bool(getattr(viewer, "conflict_positions", ())),
            ),
            ViewerAction(
                action_id="single_consensus.undo",
                label="Undo",
                callback=getattr(viewer, "undo"),
            ),
            ViewerAction(
                action_id="single_consensus.redo",
                label="Redo",
                callback=getattr(viewer, "redo"),
            ),
            ViewerAction(
                action_id="single_consensus.set_selection_gap",
                label="Set Selection to Gap",
                tooltip="Set reviewed consensus selection to gap as one undoable operation",
                callback=getattr(viewer, "request_set_selection_to_gap"),
            ),
            ViewerAction(
                action_id="single_consensus.set_selection_n",
                label="Set Selection to N",
                tooltip="Set reviewed consensus selection to N as one undoable operation",
                callback=getattr(viewer, "request_set_selection_to_n"),
            ),
            ViewerAction(
                action_id="single_consensus.create_dataset",
                label="Create Reviewed Consensus",
                callback=getattr(viewer, "create_and_register_reviewed_dataset"),
            ),
        )


class MultipleConsensusReviewActionProvider:
    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        return (
            ViewerAction(
                action_id="multiple_consensus.hide_rows",
                label="Hide Selected Samples",
                tooltip="Hide selected samples in this viewer only",
                callback=getattr(viewer, "hide_selected_rows"),
            ),
            ViewerAction(
                action_id="multiple_consensus.show_all_rows",
                label="Show All Samples",
                callback=getattr(viewer, "show_all_rows"),
            ),
            ViewerAction(
                action_id="multiple_consensus.delete_rows",
                label="Delete Selected Samples",
                tooltip="Stage selected samples for removal from the next reviewed Dataset output",
                callback=getattr(viewer, "delete_selected_rows"),
            ),
            ViewerAction(
                action_id="multiple_consensus.exclude_rows_from_output",
                label="Exclude Selected from Output",
                tooltip="Exclude selected samples only from the next reviewed Dataset output",
                callback=getattr(viewer, "exclude_selected_rows_from_output"),
            ),
            ViewerAction(
                action_id="multiple_consensus.include_all_output_rows",
                label="Include All in Output",
                callback=getattr(viewer, "include_all_output_rows"),
            ),
            ViewerAction(
                action_id="multiple_consensus.paste",
                label="Paste",
                tooltip="Paste substitutions without extending the reviewed consensus alignment",
                callback=getattr(viewer, "paste_selection"),
            ),
            ViewerAction(
                action_id="multiple_consensus.previous_variable_site",
                label="Previous Variable Site",
                callback=getattr(viewer, "previous_variable_site"),
                enabled=bool(getattr(viewer, "variable_sites", ())),
            ),
            ViewerAction(
                action_id="multiple_consensus.next_variable_site",
                label="Next Variable Site",
                callback=getattr(viewer, "next_variable_site"),
                enabled=bool(getattr(viewer, "variable_sites", ())),
            ),
            ViewerAction(
                action_id="multiple_consensus.previous_conflict",
                label="Previous Conflict",
                callback=getattr(viewer, "previous_conflict"),
            ),
            ViewerAction(
                action_id="multiple_consensus.next_conflict",
                label="Next Conflict",
                callback=getattr(viewer, "next_conflict"),
            ),
            ViewerAction(
                action_id="multiple_consensus.undo",
                label="Undo",
                callback=getattr(viewer, "undo"),
            ),
            ViewerAction(
                action_id="multiple_consensus.redo",
                label="Redo",
                callback=getattr(viewer, "redo"),
            ),
            ViewerAction(
                action_id="multiple_consensus.set_selection_gap",
                label="Set Selection to Gap",
                tooltip="Set selected reviewed consensus cells to gap as one undoable operation",
                callback=getattr(viewer, "request_set_selection_to_gap"),
            ),
            ViewerAction(
                action_id="multiple_consensus.set_selection_n",
                label="Set Selection to N",
                tooltip="Set selected reviewed consensus cells to N as one undoable operation",
                callback=getattr(viewer, "request_set_selection_to_n"),
            ),
            ViewerAction(
                action_id="multiple_consensus.create_dataset",
                label="Create Reviewed Consensus Dataset",
                callback=getattr(viewer, "create_and_register_reviewed_dataset"),
            ),
        )


def _status_label(sample: Sample) -> str:
    if sample.pairing_status is PairingStatus.CLEAR_PAIR:
        return "Ready"
    if sample.pairing_status is PairingStatus.ORPHAN_FORWARD:
        return "Incomplete — Forward only"
    if sample.pairing_status is PairingStatus.ORPHAN_REVERSE:
        return "Incomplete — Reverse only"
    if sample.pairing_status is PairingStatus.SINGLE_UNSPECIFIED:
        return "Incomplete — direction unknown"
    return "Ambiguous"


def _ensure_trimmed(read: object) -> None:
    if not getattr(read, "trimmed_sequence", ""):
        trim_sequence(read)


def _format_optional(value: object | None) -> str:
    return "—" if value is None else str(value)


def _format_quality(value: object | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return str(value)


def _side_sequence(view_model: SingleConsensusViewModel, attribute: str) -> str:
    bases = []
    for column in view_model.columns:
        evidence = column.review_evidence
        base = getattr(evidence, attribute)
        bases.append("-" if base is None else str(base).upper())
    return "".join(bases)
