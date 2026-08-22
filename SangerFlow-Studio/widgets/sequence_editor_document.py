"""Studio-only editable projection for SequenceDataset and AlignmentDataset.

This module deliberately owns no scientific model.  It records staged UI
edits against immutable datasets and uses durable record/column identities so
the controller can create the next immutable revision on save.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.alignment_dataset import AlignmentDataset
from core.sequence_dataset import SequenceDataset
from widgets.alignment_edit_operations import (
    BaseEditOperation,
    BulkBaseEditOperation,
    DeleteRowsOperation,
    PasteBlockOperation,
    RenameOperation,
)


class SequenceEditorMode(str, Enum):
    UNALIGNED = "UNALIGNED"
    ALIGNED = "ALIGNED"


@dataclass(frozen=True)
class SequenceEditorRow:
    row_id: str
    label: str
    original_sequence: str


class SequenceEditorDocument:
    """Small, in-memory edit projection shared by sequence editor modes."""

    def __init__(self, dataset: SequenceDataset | AlignmentDataset, *, mode: SequenceEditorMode) -> None:
        self.dataset = dataset
        self.mode = mode
        if mode is SequenceEditorMode.UNALIGNED and not isinstance(dataset, SequenceDataset):
            raise ValueError("Unaligned editor requires a SequenceDataset")
        if mode is SequenceEditorMode.ALIGNED and not isinstance(dataset, AlignmentDataset):
            raise ValueError("Aligned editor requires an AlignmentDataset")
        values = (
            tuple((record.sequence_id, record.sequence) for record in dataset.records)
            if isinstance(dataset, SequenceDataset)
            else tuple((record.record_id, record.aligned_sequence) for record in dataset.records)
        )
        self.rows = tuple(SequenceEditorRow(row_id, row_id, sequence) for row_id, sequence in values)
        self._original = {row_id: sequence for row_id, sequence in values}
        self._current = {row_id: list(sequence) for row_id, sequence in values}
        self._labels = {row_id: row_id for row_id, _ in values}
        self._hidden_row_ids: set[str] = set()
        self._deleted_row_ids: set[str] = set()
        self._undo_stack: list[object] = []
        self._redo_stack: list[object] = []

    @property
    def is_dirty(self) -> bool:
        return bool(self._undo_stack)

    @property
    def deleted_row_ids(self) -> frozenset[str]:
        return frozenset(self._deleted_row_ids)

    @property
    def hidden_row_ids(self) -> frozenset[str]:
        return frozenset(self._hidden_row_ids)

    @property
    def maximum_display_length(self) -> int:
        return max((len(value) for value in self._current.values()), default=0)

    def sequence(self, row_id: str) -> str:
        return "".join(self._current[row_id])

    def original_sequence(self, row_id: str) -> str:
        return self._original[row_id]

    def label(self, row_id: str) -> str:
        return self._labels[row_id]

    def existing_coordinate(self, row_id: str, column: int) -> bool:
        return row_id in self._current and 0 <= int(column) < len(self._current[row_id])

    def visible_row_ids(self) -> tuple[str, ...]:
        return tuple(row.row_id for row in self.rows if row.row_id not in self._hidden_row_ids and row.row_id not in self._deleted_row_ids)

    def set_hidden(self, row_ids: tuple[str, ...] | list[str] | set[str], *, hidden: bool = True) -> None:
        valid = set(row_ids) & set(self._current)
        if hidden:
            self._hidden_row_ids.update(valid)
        else:
            self._hidden_row_ids.difference_update(valid)

    def show_all_rows(self) -> None:
        self._hidden_row_ids.clear()

    def set_base(self, row_id: str, column: int, base: str) -> bool:
        if not self.existing_coordinate(row_id, column):
            return False
        current = self._current[row_id][column]
        if current == base:
            return False
        self._push(BaseEditOperation(((row_id, column, current, base),)))
        return True

    def apply_paste(self, changes: tuple[tuple[str, int, str, str], ...]) -> bool:
        if not changes:
            return False
        if any(not self.existing_coordinate(row_id, column) for row_id, column, _, _ in changes):
            return False
        self._push(PasteBlockOperation(changes))
        return True

    def rename(self, row_id: str, label: str) -> bool:
        label = str(label).strip()
        if (
            not label
            or row_id not in self._labels
            or self._labels[row_id] == label
            or label in {value for key, value in self._labels.items() if key != row_id}
        ):
            return False
        self._push(RenameOperation(row_id, self._labels[row_id], label))
        return True

    def delete_rows(self, row_ids: tuple[str, ...] | list[str]) -> bool:
        requested = frozenset(row_ids) & set(self._current)
        after = frozenset(set(self._deleted_row_ids) | set(requested))
        if after == frozenset(self._deleted_row_ids):
            return False
        self._push(DeleteRowsOperation(frozenset(self._deleted_row_ids), after))
        return True

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        operation = self._undo_stack.pop()
        operation.revert(self)
        self._redo_stack.append(operation)
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        operation = self._redo_stack.pop()
        operation.apply(self)
        self._undo_stack.append(operation)
        return True

    def _push(self, operation: object) -> None:
        operation.apply(self)
        self._undo_stack.append(operation)
        self._redo_stack.clear()

    # PendingEditTarget adapter methods used by typed operations.
    def _apply_base_changes(self, changes: object, *, use_new: bool = True) -> None:
        for row_id, column, previous, current in changes:  # type: ignore[union-attr]
            self._current[row_id][column] = current if use_new else previous

    def _set_deleted_row_ids(self, row_ids: frozenset[str]) -> None:
        self._deleted_row_ids = set(row_ids)

    def _set_excluded_column_ids(self, _column_ids: frozenset[int]) -> None:
        raise RuntimeError("column operations are unavailable in unaligned mode")

    def _set_row_label(self, record_id: str, label: str) -> None:
        self._labels[record_id] = label

    def _apply_delete_columns(self, _column_ids: tuple[int, ...]) -> None:
        raise RuntimeError("column operations are unavailable in unaligned mode")

    def _revert_delete_columns(self, _column_ids: tuple[int, ...], _removed: object) -> None:
        raise RuntimeError("column operations are unavailable in unaligned mode")
