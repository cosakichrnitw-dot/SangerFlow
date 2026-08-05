"""GUI-only state for an alignment editor.

This module deliberately has no dependency on MAFFT, consensus, evidence, or
Tk.  It is the common contract to be shared by corner, row, column, and
matrix views while keeping immutable alignment values in ``core``.
"""

from dataclasses import dataclass, field
from enum import Enum


class SelectionKind(str, Enum):
    CELL = "cell"
    RECTANGLE = "rectangle"
    ROW = "row"
    COLUMN = "column"
    ALL = "all"


@dataclass(frozen=True)
class MatrixSelection:
    """Inclusive matrix coordinates, independent of how a view was clicked."""

    kind: SelectionKind
    row_start: int
    row_end: int
    column_start: int
    column_end: int

    def cells(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (row, column)
            for row in range(self.row_start, self.row_end + 1)
            for column in range(self.column_start, self.column_end + 1)
        )


@dataclass
class AlignmentEditorState:
    """Editor overlays only; never modifies the aligned consensus input."""

    row_count: int
    column_count: int
    selection: MatrixSelection | None = None
    excluded_rows: set[int] = field(default_factory=set)
    excluded_columns: set[int] = field(default_factory=set)

    def select_cell(self, row: int, column: int) -> MatrixSelection:
        return self._set(SelectionKind.CELL, row, row, column, column)

    def select_rectangle(self, start: tuple[int, int], end: tuple[int, int]) -> MatrixSelection:
        return self._set(SelectionKind.RECTANGLE, min(start[0], end[0]), max(start[0], end[0]), min(start[1], end[1]), max(start[1], end[1]))

    def select_row(self, row: int) -> MatrixSelection:
        return self._set(SelectionKind.ROW, row, row, 0, self.column_count - 1)

    def select_column(self, column: int) -> MatrixSelection:
        return self._set(SelectionKind.COLUMN, 0, self.row_count - 1, column, column)

    def select_all(self) -> MatrixSelection:
        return self._set(SelectionKind.ALL, 0, self.row_count - 1, 0, self.column_count - 1)

    def _set(self, kind, row_start, row_end, column_start, column_end):
        if not (0 <= row_start <= row_end < self.row_count and 0 <= column_start <= column_end < self.column_count):
            raise ValueError("selection is outside the alignment")
        self.selection = MatrixSelection(kind, row_start, row_end, column_start, column_end)
        return self.selection
