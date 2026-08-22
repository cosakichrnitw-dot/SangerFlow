"""Reusable custom-painted Mesquite-style sequence grid for Studio viewers."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QAbstractScrollArea, QLineEdit, QMenu
from widgets.font_utils import fixed_width_font


SEQUENCE_GRID_CELL_WIDTH = 18
SEQUENCE_GRID_ROW_HEIGHT = 22
SEQUENCE_GRID_LABEL_WIDTH = 150
SEQUENCE_GRID_RULER_HEIGHT = 42
SEQUENCE_GRID_FONT_SIZE = 10


@dataclass(frozen=True)
class SequenceGridPalette:
    """Shared Mesquite-style colors copied from the Tkinter viewers."""

    base_backgrounds: dict[str, QColor]
    text_color: QColor = field(default_factory=lambda: QColor("#111111"))
    gap_text_color: QColor = field(default_factory=lambda: QColor("#555555"))
    default_background: QColor = field(default_factory=lambda: QColor("white"))
    gap_background: QColor = field(default_factory=lambda: QColor("#D9D9D9"))
    ambiguous_background: QColor = field(default_factory=lambda: QColor("#B7B7B7"))
    edited_background: QColor = field(default_factory=lambda: QColor("#DCEEFF"))
    selection_outline: QColor = field(default_factory=lambda: QColor("#1F4E79"))
    grid_outline: QColor = field(default_factory=lambda: QColor("#B8B8B8"))
    ruler_background: QColor = field(default_factory=lambda: QColor("#FFFFFF"))
    label_background: QColor = field(default_factory=lambda: QColor("#F8F8F8"))
    excluded_overlay: QColor = field(default_factory=lambda: QColor(120, 120, 120, 75))


DEFAULT_SEQUENCE_GRID_PALETTE = SequenceGridPalette(
    base_backgrounds={
        "A": QColor("#E06666"),
        "C": QColor("#7BC67B"),
        "G": QColor("#F6E15A"),
        "T": QColor("#6FA8DC"),
        "N": QColor("#B7B7B7"),
        "-": QColor("#D9D9D9"),
    }
)

SEQUENCE_GRID_EDITED_BACKGROUND = DEFAULT_SEQUENCE_GRID_PALETTE.edited_background
SEQUENCE_GRID_SELECTION_OUTLINE = DEFAULT_SEQUENCE_GRID_PALETTE.selection_outline


@dataclass(frozen=True)
class SequenceGridRow:
    """One visible sequence row in a generic sequence grid."""

    row_id: str
    label: str
    sequence: str
    editable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.row_id, str) or not self.row_id:
            raise ValueError("row_id must be a non-empty string")
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("label must be a non-empty string")
        if not isinstance(self.sequence, str):
            raise ValueError("sequence must be a string")
        object.__setattr__(self, "sequence", self.sequence.upper())


@dataclass(frozen=True)
class SequenceGridSelection:
    """Shared, rectangle-based selection state for sequence-like grids."""

    mode: str = "none"
    active_row: int | None = None
    active_column: int | None = None
    anchor_row: int | None = None
    anchor_column: int | None = None
    first_row: int | None = None
    last_row: int | None = None
    first_column: int | None = None
    last_column: int | None = None

    @property
    def is_empty(self) -> bool:
        return (
            self.first_row is None
            or self.last_row is None
            or self.first_column is None
            or self.last_column is None
        )

    @property
    def is_single_cell(self) -> bool:
        return (
            not self.is_empty
            and self.first_row == self.last_row
            and self.first_column == self.last_column
        )

    @property
    def row_count(self) -> int:
        if self.is_empty:
            return 0
        return int(self.last_row - self.first_row + 1)

    @property
    def column_count(self) -> int:
        if self.is_empty:
            return 0
        return int(self.last_column - self.first_column + 1)

    @property
    def cell_count(self) -> int:
        return self.row_count * self.column_count


class SequenceGridWidget(QAbstractScrollArea):
    """Virtualized, custom-painted grid for sequence/alignment editing."""

    cell_selected = Signal(str, int, str)
    column_selected = Signal(int)
    selection_changed = Signal(object)
    cell_edited = Signal(str, int, str)
    paste_requested = Signal()
    undo_requested = Signal()
    redo_requested = Signal()

    def __init__(self, parent=None, *, palette: SequenceGridPalette | None = None) -> None:
        super().__init__(parent)
        self._rows: tuple[SequenceGridRow, ...] = ()
        self._edited_cells: set[tuple[str, int]] = set()
        self._editable_row_ids: set[str] = set()
        self._excluded_columns: set[int] = set()
        self._selected_row = -1
        self._selected_column = -1
        self._selected_row_indices: set[int] = set()
        self._selection = SequenceGridSelection()
        self._drag_mode: str | None = None
        self._last_drag_position: QPointF | None = None
        self._column_count = 0
        self._palette = palette or DEFAULT_SEQUENCE_GRID_PALETTE
        self._context_menu_handler = None
        self._inline_rename_handler = None
        self._inline_editor: QLineEdit | None = None
        self._inline_editor_row_id: str | None = None
        self._font = fixed_width_font(SEQUENCE_GRID_FONT_SIZE, QFont.Weight.Bold)
        self.setObjectName("sequenceGridWidget")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.horizontalScrollBar().valueChanged.connect(lambda _value: self.viewport().update())
        self.verticalScrollBar().valueChanged.connect(lambda _value: self.viewport().update())
        self._auto_scroll_timer = QTimer(self)
        self._auto_scroll_timer.setInterval(35)
        self._auto_scroll_timer.timeout.connect(self._auto_scroll_drag_selection)

    @property
    def rows(self) -> tuple[SequenceGridRow, ...]:
        return self._rows

    @property
    def edited_cells(self) -> frozenset[tuple[str, int]]:
        return frozenset(self._edited_cells)

    @property
    def cell_width(self) -> int:
        return SEQUENCE_GRID_CELL_WIDTH

    @property
    def row_height(self) -> int:
        return SEQUENCE_GRID_ROW_HEIGHT

    @property
    def label_width(self) -> int:
        return SEQUENCE_GRID_LABEL_WIDTH

    @property
    def ruler_height(self) -> int:
        return SEQUENCE_GRID_RULER_HEIGHT

    @property
    def column_count(self) -> int:
        return self._column_count

    @property
    def selection(self) -> SequenceGridSelection:
        return self._selection

    @property
    def excluded_columns(self) -> frozenset[int]:
        return frozenset(self._excluded_columns)

    def row_label(self, row_index: int) -> str:
        return self._rows[row_index].label

    def cell_base(self, row_index: int, column_index: int) -> str | None:
        """Return a real base, or ``None`` for a non-existent ragged cell.

        ``None`` is deliberately different from ``\"-\"``.  The latter is a
        biological/alignment gap and must remain visible and editable; the
        former only exists in an unaligned display projection whose rows have
        different lengths.
        """
        row = self._rows[row_index]
        return row.sequence[column_index] if 0 <= column_index < len(row.sequence) else None

    def is_existing_cell(self, row_index: int, column_index: int) -> bool:
        return (
            0 <= row_index < len(self._rows)
            and 0 <= column_index < len(self._rows[row_index].sequence)
        )

    def cell_background(self, row_id: str, column_index: int) -> QColor:
        row_index = self._row_index(row_id)
        if row_index is None:
            raise KeyError(row_id)
        base = self.cell_base(row_index, column_index)
        if (row_id, column_index) in self._edited_cells:
            return self._palette.edited_background
        return self._base_background(base) if base is not None else self._palette.default_background

    def set_rows(
        self,
        rows: tuple[SequenceGridRow, ...],
        *,
        edited_cells: set[tuple[str, int]] | None = None,
        preserve_selection: bool = True,
    ) -> None:
        # A caller which removes rows (for example a pending alignment row
        # deletion) must be able to rebuild from durable row IDs without
        # carrying display-index selection state into the new model.
        selected_row_ids = (
            {
                self._rows[index].row_id
                for index in self._selected_row_indices
                if 0 <= index < len(self._rows)
            }
            if preserve_selection
            else set()
        )
        was_row_selection = preserve_selection and self._selection.mode == "row"
        self._rows = tuple(rows)
        self._editable_row_ids = {row.row_id for row in self._rows if row.editable}
        self._edited_cells = set(edited_cells or set())
        self._column_count = max((len(row.sequence) for row in self._rows), default=0)
        if not preserve_selection:
            self._selected_row = -1
            self._selected_column = -1
            self._selected_row_indices.clear()
            self._set_selection(SequenceGridSelection(mode="none"), emit=False)
        else:
            self._selected_row = 0 if self._rows and self._selected_row < 0 else min(self._selected_row, len(self._rows) - 1)
            self._selected_column = 0 if self._column_count and self._selected_column < 0 else min(self._selected_column, self._column_count - 1)
            if self._rows and self._selected_row >= 0:
                self._selected_column = min(
                    self._selected_column,
                    max(0, len(self._rows[self._selected_row].sequence) - 1),
                )
        # A grid rebuild can remove or hide rows.  Selection coordinates are
        # display indices, never durable row references, so discard a stale
        # rectangle before any caller can read it.
        self._selected_row_indices = {
            index for index, row in enumerate(self._rows)
            if was_row_selection and row.row_id in selected_row_ids
        }
        if not self._selection_is_valid() or (
            self._selection.is_single_cell
            and not self.is_existing_cell(
                int(self._selection.first_row), int(self._selection.first_column)
            )
        ):
            self._selection = SequenceGridSelection(mode="none")
            self._selected_row_indices.clear()
        if preserve_selection and self._rows and self._column_count and self._selection.is_empty:
            self._set_selection(
                SequenceGridSelection(
                    mode="cell",
                    active_row=self._selected_row,
                    active_column=self._selected_column,
                    anchor_row=self._selected_row,
                    anchor_column=self._selected_column,
                    first_row=self._selected_row,
                    last_row=self._selected_row,
                    first_column=self._selected_column,
                    last_column=self._selected_column,
                ),
                emit=False,
            )
        self._update_scroll_ranges()
        self.viewport().update()

    def set_excluded_columns(self, columns: object) -> None:
        self._excluded_columns = {
            int(column)
            for column in columns
            if 0 <= int(column) < self._column_count
        }
        self.viewport().update()

    def select_cell(self, row_id: str, column_index: int, *, emit: bool = True) -> bool:
        row_index = self._row_index(row_id)
        if row_index is None or not self.is_existing_cell(row_index, column_index):
            return False
        self._selected_row = row_index
        self._selected_column = int(column_index)
        self._set_selection(
            self._selection_for_rectangle(
                row_index,
                int(column_index),
                row_index,
                int(column_index),
                mode="cell",
                anchor_row=row_index,
                anchor_column=int(column_index),
                active_row=row_index,
                active_column=int(column_index),
            ),
            emit=emit,
        )
        self._ensure_cell_visible()
        if emit:
            self._emit_current_cell()
        self.viewport().update()
        return True

    def select_column(self, column_index: int) -> None:
        if not 0 <= column_index < self._column_count:
            return
        self.select_column_range(column_index, column_index)
        self._ensure_cell_visible()

    def select_column_range(self, first_column: int, last_column: int) -> None:
        if not self._rows or not self._column_count:
            return
        first_column = max(0, min(int(first_column), self._column_count - 1))
        last_column = max(0, min(int(last_column), self._column_count - 1))
        active_column = last_column
        self._selected_row = 0 if self._selected_row < 0 else self._selected_row
        self._selected_column = active_column
        self._set_selection(
            self._selection_for_rectangle(
                0,
                first_column,
                len(self._rows) - 1,
                last_column,
                mode="column",
                anchor_row=0,
                anchor_column=first_column,
                active_row=self._selected_row,
                active_column=active_column,
            )
        )
        self.column_selected.emit(active_column)
        self.viewport().update()

    def select_row(self, row_id: str) -> bool:
        row_index = self._row_index(row_id)
        if row_index is None:
            return False
        self.select_row_range(row_index, row_index)
        return True

    def select_row_range(self, first_row: int, last_row: int) -> None:
        if not self._rows or not self._column_count:
            return
        first_row = max(0, min(int(first_row), len(self._rows) - 1))
        last_row = max(0, min(int(last_row), len(self._rows) - 1))
        active_row = last_row
        self._selected_row_indices = set(range(min(first_row, last_row), max(first_row, last_row) + 1))
        self._selected_row = active_row
        self._selected_column = 0 if self._selected_column < 0 else self._selected_column
        self._set_selection(
            self._selection_for_rectangle(
                first_row,
                0,
                last_row,
                self._column_count - 1,
                mode="row",
                anchor_row=first_row,
                anchor_column=0,
                active_row=active_row,
                active_column=self._selected_column,
            )
        )
        if self._selection.is_single_cell:
            self._emit_current_cell()
        self.viewport().update()

    def toggle_row_selection(self, row_index: int) -> None:
        """Add/remove one taxon row without turning it into a cell selection."""

        if not self._rows or not self._column_count or not 0 <= int(row_index) < len(self._rows):
            return
        row_index = int(row_index)
        if self._selection.mode != "row":
            self._selected_row_indices.clear()
        if row_index in self._selected_row_indices:
            self._selected_row_indices.remove(row_index)
        else:
            self._selected_row_indices.add(row_index)
        if not self._selected_row_indices:
            self.clear_selection()
            return
        selected = sorted(self._selected_row_indices)
        self._selected_row = row_index
        self._selected_column = 0 if self._selected_column < 0 else self._selected_column
        self._set_selection(
            self._selection_for_rectangle(
                selected[0], 0, selected[-1], self._column_count - 1,
                mode="row", anchor_row=selected[0], anchor_column=0,
                active_row=row_index, active_column=self._selected_column,
            )
        )
        self._ensure_cell_visible()
        self.viewport().update()

    def select_rectangle(
        self,
        first_row: int,
        first_column: int,
        last_row: int,
        last_column: int,
        *,
        mode: str = "rectangle",
    ) -> None:
        if not self._rows or not self._column_count:
            return
        # A direct click on ragged display padding must not manufacture a
        # biological selection.  Multi-row rectangles remain display ranges,
        # but ``selected_cells`` filters their non-existent coordinates.
        if first_row == last_row and first_column == last_column and not self.is_existing_cell(first_row, first_column):
            self.clear_selection()
            return
        selection = self._selection_for_rectangle(
            first_row,
            first_column,
            last_row,
            last_column,
            mode=mode,
            anchor_row=first_row,
            anchor_column=first_column,
            active_row=last_row,
            active_column=last_column,
        )
        self._selected_row = selection.active_row if selection.active_row is not None else -1
        self._selected_column = selection.active_column if selection.active_column is not None else -1
        self._set_selection(selection)
        self._ensure_cell_visible()
        if selection.is_single_cell:
            self._emit_current_cell()
        self.viewport().update()

    def clear_selection(self) -> None:
        self._selected_row = -1
        self._selected_column = -1
        self._selected_row_indices.clear()
        self._set_selection(SequenceGridSelection(mode="none"))
        self.viewport().update()

    def set_context_menu_handler(self, handler: object | None) -> None:
        """Install an optional viewer-owned contextual action builder."""

        self._context_menu_handler = handler if callable(handler) else None

    def set_inline_rename_handler(self, handler: object | None) -> None:
        """Install a revision-aware row-label commit callback owned by a viewer."""

        self._inline_rename_handler = handler if callable(handler) else None

    def selected_rows(self) -> tuple[str, ...]:
        if not self._selection_is_valid():
            return ()
        if self._selection.mode == "row":
            return tuple(self._rows[index].row_id for index in sorted(self._selected_row_indices))
        return tuple(
            self._rows[index].row_id
            for index in range(self._selection.first_row, self._selection.last_row + 1)
        )

    def selected_columns(self) -> tuple[int, ...]:
        if not self._selection_is_valid():
            return ()
        return tuple(range(self._selection.first_column, self._selection.last_column + 1))

    def selected_cells(self) -> tuple[tuple[str, int], ...]:
        if not self._selection_is_valid():
            return ()
        cells: list[tuple[str, int]] = []
        row_indices = (
            sorted(self._selected_row_indices)
            if self._selection.mode == "row"
            else range(self._selection.first_row, self._selection.last_row + 1)
        )
        for row_index in row_indices:
            row_id = self._rows[row_index].row_id
            for column in range(self._selection.first_column, self._selection.last_column + 1):
                if self.is_existing_cell(row_index, column):
                    cells.append((row_id, column))
        return tuple(cells)

    def selection_bounds(self) -> tuple[int, int, int, int] | None:
        if not self._selection_is_valid():
            return None
        return (
            self._selection.first_row,
            self._selection.last_row,
            self._selection.first_column,
            self._selection.last_column,
        )

    def selection_status_text(self) -> str:
        if not self._selection_is_valid():
            return "No selection"
        if self._selection.is_single_cell:
            row = self._rows[self._selection.first_row]
            base = self.cell_base(self._selection.first_row, self._selection.first_column)
            if base is None:
                return "No biological position selected"
            return f"1 cell selected | Row: {row.label} | Position: {self._selection.first_column + 1} | Base: {base}"
        if self._selection.mode == "column":
            columns = self.selected_columns()
            excluded_count = len(set(columns) & self._excluded_columns)
            suffix = f" — {excluded_count} excluded" if excluded_count else ""
            if len(columns) == 1:
                return f"Column {columns[0] + 1} | {self._selection.row_count} sequences selected{suffix}"
            return (
                f"Columns {columns[0] + 1}–{columns[-1] + 1} | "
                f"{self._selection.row_count} sequences selected{suffix}"
            )
        if self._selection.mode == "row":
            rows = self.selected_rows()
            if len(rows) == 1:
                return f"{self._rows[self._selection.first_row].label} | {self._selection.column_count} sites selected"
            return f"Selected: {len(rows)} rows × {self._selection.column_count} columns | {len(rows) * self._selection.column_count} cells"
        return (
            f"Selected: {self._selection.row_count} rows × {self._selection.column_count} columns | "
            f"Columns {self._selection.first_column + 1}–{self._selection.last_column + 1} | "
            f"{self._selection.cell_count} cells"
        )

    def selected_text(self) -> str:
        if not self._selection_is_valid():
            return ""
        lines = []
        row_indices = (
            sorted(self._selected_row_indices)
            if self._selection.mode == "row"
            else range(self._selection.first_row, self._selection.last_row + 1)
        )
        for row_index in row_indices:
            row = self._rows[row_index]
            lines.append(
                "".join(
                    row.sequence[column] if column < len(row.sequence) else ""
                    for column in range(self._selection.first_column, self._selection.last_column + 1)
                )
            )
        return "\n".join(lines)

    def selected_fasta_text(self) -> str:
        if not self._selection_is_valid():
            return ""
        entries = []
        row_indices = (
            sorted(self._selected_row_indices)
            if self._selection.mode == "row"
            else range(self._selection.first_row, self._selection.last_row + 1)
        )
        for row_index in row_indices:
            row = self._rows[row_index]
            sequence = "".join(
                row.sequence[column] if column < len(row.sequence) else ""
                for column in range(self._selection.first_column, self._selection.last_column + 1)
            )
            entries.append(f">{row.label}\n{sequence}")
        return "\n".join(entries) + ("\n" if entries else "")

    def copy_selection_to_clipboard(self) -> str:
        text = self.selected_text()
        QApplication.clipboard().setText(text)
        return text

    def set_cell_base(
        self,
        row_id: str,
        column_index: int,
        base: str,
        *,
        edited: bool | None = None,
    ) -> bool:
        row_index = self._row_index(row_id)
        if row_index is None or not self.is_existing_cell(row_index, column_index):
            return False
        base = _coerce_base(base)
        row = self._rows[row_index]
        sequence = list(row.sequence)
        sequence[column_index] = base
        rows = list(self._rows)
        rows[row_index] = SequenceGridRow(
            row_id=row.row_id,
            label=row.label,
            sequence="".join(sequence),
            editable=row.editable,
        )
        self._rows = tuple(rows)
        if edited is True:
            self._edited_cells.add((row_id, column_index))
        elif edited is False:
            self._edited_cells.discard((row_id, column_index))
        self.viewport().update(self._cell_viewport_rect(row_index, column_index))
        return True

    def edit_current_cell(self, base: str) -> bool:
        if not self._selection.is_single_cell:
            return False
        if self._selected_row < 0 or self._selected_column < 0:
            return False
        row = self._rows[self._selected_row]
        if row.row_id not in self._editable_row_ids or not self.is_existing_cell(self._selected_row, self._selected_column):
            return False
        self.cell_edited.emit(row.row_id, self._selected_column, _coerce_base(base))
        return True

    def current_cell(self) -> tuple[str, int, str] | None:
        if (
            self._selected_row < 0
            or self._selected_column < 0
            or self._selected_row >= len(self._rows)
        ):
            return None
        row = self._rows[self._selected_row]
        if not self.is_existing_cell(self._selected_row, self._selected_column):
            return None
        base = row.sequence[self._selected_column]
        return row.row_id, self._selected_column, base

    def visible_range(self) -> tuple[int, int, int, int]:
        """Return inclusive/exclusive visible row and column ranges."""

        x_offset = self.horizontalScrollBar().value()
        y_offset = self.verticalScrollBar().value()
        width = max(1, self.viewport().width() - SEQUENCE_GRID_LABEL_WIDTH)
        height = max(1, self.viewport().height() - SEQUENCE_GRID_RULER_HEIGHT)
        first_col = max(0, x_offset // SEQUENCE_GRID_CELL_WIDTH)
        last_col = min(
            self._column_count,
            (x_offset + width) // SEQUENCE_GRID_CELL_WIDTH + 2,
        )
        first_row = max(0, y_offset // SEQUENCE_GRID_ROW_HEIGHT)
        last_row = min(
            len(self._rows),
            (y_offset + height) // SEQUENCE_GRID_ROW_HEIGHT + 2,
        )
        return first_row, last_row, first_col, last_col

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._update_scroll_ranges()
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self.viewport())
        painter.setFont(self._font)
        painter.fillRect(self.viewport().rect(), self._palette.default_background)
        self._paint_headers(painter)
        self._paint_cells(painter)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        position = event.position()
        if position.y() < SEQUENCE_GRID_RULER_HEIGHT and position.x() >= SEQUENCE_GRID_LABEL_WIDTH:
            column = int((position.x() - SEQUENCE_GRID_LABEL_WIDTH + self.horizontalScrollBar().value()) // SEQUENCE_GRID_CELL_WIDTH)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and not self._selection.is_empty:
                anchor = self._selection.anchor_column
                self.select_column_range(anchor if anchor is not None else column, column)
            else:
                self.select_column(column)
            self._drag_mode = "column"
            event.accept()
            return
        if position.x() < SEQUENCE_GRID_LABEL_WIDTH and position.y() >= SEQUENCE_GRID_RULER_HEIGHT:
            row = int((position.y() - SEQUENCE_GRID_RULER_HEIGHT + self.verticalScrollBar().value()) // SEQUENCE_GRID_ROW_HEIGHT)
            if 0 <= row < len(self._rows):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and not self._selection.is_empty:
                    anchor = self._selection.anchor_row
                    self.select_row_range(anchor if anchor is not None else row, row)
                elif event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
                    self.toggle_row_selection(row)
                else:
                    self.select_row_range(row, row)
                self._drag_mode = "row"
                event.accept()
                return
        if position.x() < SEQUENCE_GRID_LABEL_WIDTH or position.y() < SEQUENCE_GRID_RULER_HEIGHT:
            super().mousePressEvent(event)
            return
        row = int((position.y() - SEQUENCE_GRID_RULER_HEIGHT + self.verticalScrollBar().value()) // SEQUENCE_GRID_ROW_HEIGHT)
        column = int((position.x() - SEQUENCE_GRID_LABEL_WIDTH + self.horizontalScrollBar().value()) // SEQUENCE_GRID_CELL_WIDTH)
        if 0 <= row < len(self._rows) and 0 <= column < self._column_count:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and not self._selection.is_empty:
                anchor_row = self._selection.anchor_row if self._selection.anchor_row is not None else row
                anchor_column = self._selection.anchor_column if self._selection.anchor_column is not None else column
                self.select_rectangle(anchor_row, anchor_column, row, column)
            else:
                self.select_rectangle(row, column, row, column, mode="cell")
            self._drag_mode = "cell"
            if self._selection.is_single_cell:
                self._emit_current_cell()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._drag_mode is None:
            super().mouseMoveEvent(event)
            return
        position = event.position()
        self._last_drag_position = position
        self._update_auto_scroll_timer()
        row = int((position.y() - SEQUENCE_GRID_RULER_HEIGHT + self.verticalScrollBar().value()) // SEQUENCE_GRID_ROW_HEIGHT)
        column = int((position.x() - SEQUENCE_GRID_LABEL_WIDTH + self.horizontalScrollBar().value()) // SEQUENCE_GRID_CELL_WIDTH)
        row = max(0, min(row, len(self._rows) - 1)) if self._rows else -1
        column = max(0, min(column, self._column_count - 1)) if self._column_count else -1
        if row < 0 or column < 0:
            return
        anchor_row = self._selection.anchor_row if self._selection.anchor_row is not None else row
        anchor_column = self._selection.anchor_column if self._selection.anchor_column is not None else column
        if self._drag_mode == "column":
            self.select_column_range(anchor_column, column)
        elif self._drag_mode == "row":
            self.select_row_range(anchor_row, row)
        else:
            self.select_rectangle(anchor_row, anchor_column, row, column)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._drag_mode = None
        self._last_drag_position = None
        self._auto_scroll_timer.stop()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._inline_rename_handler is not None
            and event.position().x() < SEQUENCE_GRID_LABEL_WIDTH
            and event.position().y() >= SEQUENCE_GRID_RULER_HEIGHT
        ):
            row = int((event.position().y() - SEQUENCE_GRID_RULER_HEIGHT + self.verticalScrollBar().value()) // SEQUENCE_GRID_ROW_HEIGHT)
            if 0 <= row < len(self._rows):
                self._begin_inline_rename(row)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is self._inline_editor and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._finish_inline_rename(commit=False)
                return True
        return super().eventFilter(watched, event)

    def _begin_inline_rename(self, row: int) -> None:
        self.select_row_range(row, row)
        self._finish_inline_rename(commit=False)
        record = self._rows[row]
        editor = QLineEdit(record.label, self.viewport())
        editor.setObjectName("sequenceGridInlineRowRename")
        editor.setGeometry(2, SEQUENCE_GRID_RULER_HEIGHT + row * SEQUENCE_GRID_ROW_HEIGHT - self.verticalScrollBar().value(), SEQUENCE_GRID_LABEL_WIDTH - 4, SEQUENCE_GRID_ROW_HEIGHT)
        editor.installEventFilter(self)
        editor.editingFinished.connect(self._commit_inline_rename)
        self._inline_editor = editor
        self._inline_editor_row_id = record.row_id
        editor.show()
        editor.selectAll()
        editor.setFocus()

    def _commit_inline_rename(self) -> None:
        self._finish_inline_rename(commit=True)

    def _finish_inline_rename(self, *, commit: bool) -> None:
        editor = self._inline_editor
        row_id = self._inline_editor_row_id
        self._inline_editor = None
        self._inline_editor_row_id = None
        if editor is None:
            return
        value = editor.text()
        editor.removeEventFilter(self)
        editor.hide()
        editor.deleteLater()
        if commit and row_id is not None and callable(self._inline_rename_handler):
            self._inline_rename_handler(row_id, value)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        # QContextMenuEvent deliberately exposes QPoint APIs (pos/globalPos),
        # not the floating-point position() API of QMouseEvent.  Mapping its
        # global logical coordinate back to the viewport keeps hit testing
        # correct for scrollbars, macOS Ctrl/secondary click and Retina DPR.
        position = QPointF(self.viewport().mapFromGlobal(event.globalPos()))
        self._select_context_target(position)
        if self._context_menu_handler is not None:
            self._context_menu_handler(self._selection, event.globalPos())
            event.accept()
            return
        self._show_default_context_menu(event.globalPos())
        event.accept()

    def _select_context_target(self, position: QPointF) -> None:
        """Select only when the context target is outside the current selection.

        A contextual action on a rectangular/multi-row selection must keep
        operating on that selection.  This mirrors native editors: a
        secondary-click *inside* the selected area opens its menu, while a
        click elsewhere changes the target first.
        """

        if position.x() < SEQUENCE_GRID_LABEL_WIDTH and position.y() < SEQUENCE_GRID_RULER_HEIGHT:
            self.clear_selection()
            return
        if position.y() < SEQUENCE_GRID_RULER_HEIGHT and position.x() >= SEQUENCE_GRID_LABEL_WIDTH:
            column = int((position.x() - SEQUENCE_GRID_LABEL_WIDTH + self.horizontalScrollBar().value()) // SEQUENCE_GRID_CELL_WIDTH)
            if (
                self._selection_is_valid()
                and self._selection.mode == "column"
                and self._selection.first_column <= column <= self._selection.last_column
            ):
                return
            self.select_column(column)
            return
        if position.x() < SEQUENCE_GRID_LABEL_WIDTH and position.y() >= SEQUENCE_GRID_RULER_HEIGHT:
            row = int((position.y() - SEQUENCE_GRID_RULER_HEIGHT + self.verticalScrollBar().value()) // SEQUENCE_GRID_ROW_HEIGHT)
            if 0 <= row < len(self._rows):
                if (
                    self._selection_is_valid()
                    and (self._selection.mode == "row" or self._selection.first_row != self._selection.last_row)
                    and self._selection.first_row <= row <= self._selection.last_row
                ):
                    return
                if row not in self._selected_row_indices or self._selection.mode != "row":
                    self.select_row_range(row, row)
            else:
                self.clear_selection()
            return
        row = int((position.y() - SEQUENCE_GRID_RULER_HEIGHT + self.verticalScrollBar().value()) // SEQUENCE_GRID_ROW_HEIGHT)
        column = int((position.x() - SEQUENCE_GRID_LABEL_WIDTH + self.horizontalScrollBar().value()) // SEQUENCE_GRID_CELL_WIDTH)
        if 0 <= row < len(self._rows) and 0 <= column < self._column_count:
            if (
                self._selection_is_valid()
                and self._selection.first_row <= row <= self._selection.last_row
                and self._selection.first_column <= column <= self._selection.last_column
            ):
                return
            self.select_rectangle(row, column, row, column, mode="cell")
        else:
            self.clear_selection()

    def _selection_is_valid(self) -> bool:
        selection = self._selection
        if selection.is_empty:
            return False
        valid = (
            selection.first_row is not None
            and selection.last_row is not None
            and selection.first_column is not None
            and selection.last_column is not None
            and 0 <= selection.first_row <= selection.last_row < len(self._rows)
            and 0 <= selection.first_column <= selection.last_column < self._column_count
        )
        if selection.mode == "row":
            return valid and bool(self._selected_row_indices) and all(
                0 <= index < len(self._rows) for index in self._selected_row_indices
            )
        return valid

    def _show_default_context_menu(self, global_position: object) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        copy_action.setEnabled(not self._selection.is_empty)
        chosen_action = menu.exec(global_position)
        if chosen_action == copy_action:
            self.copy_selection_to_clipboard()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        key = event.key()
        modifiers = event.modifiers()
        if (modifiers & Qt.KeyboardModifier.ControlModifier) or (
            modifiers & Qt.KeyboardModifier.MetaModifier
        ):
            if key == Qt.Key.Key_Z:
                if modifiers & Qt.KeyboardModifier.ShiftModifier:
                    self.redo_requested.emit()
                else:
                    self.undo_requested.emit()
                event.accept()
                return
            if key == Qt.Key.Key_C:
                self.copy_selection_to_clipboard()
                event.accept()
                return
            if key == Qt.Key.Key_V:
                self.paste_requested.emit()
                event.accept()
                return
            if key == Qt.Key.Key_A:
                self.select_rectangle(0, 0, len(self._rows) - 1, self._column_count - 1, mode="all")
                event.accept()
                return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._move_selection(key, extend=bool(modifiers & Qt.KeyboardModifier.ShiftModifier))
            event.accept()
            return
        if key == Qt.Key.Key_Home:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                self._extend_selection_to(self._selected_row, 0)
            else:
                self._selected_column = 0
                self.select_rectangle(self._selected_row, 0, self._selected_row, 0, mode="cell")
            self._ensure_cell_visible()
            event.accept()
            return
        if key == Qt.Key.Key_End:
            end_column = max(0, len(self._rows[self._selected_row].sequence) - 1) if self._selected_row >= 0 else 0
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                self._extend_selection_to(self._selected_row, end_column)
            else:
                self._selected_column = end_column
                self.select_rectangle(self._selected_row, end_column, self._selected_row, end_column, mode="cell")
            self._ensure_cell_visible()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.clear_selection()
            event.accept()
            return
        text = event.text().upper()
        if text in {"A", "C", "G", "T", "N", "-"} and self.edit_current_cell(text):
            event.accept()
            return
        super().keyPressEvent(event)

    def _paint_headers(self, painter: QPainter) -> None:
        viewport = self.viewport().rect()
        painter.fillRect(0, 0, viewport.width(), SEQUENCE_GRID_RULER_HEIGHT, self._palette.ruler_background)
        painter.fillRect(0, 0, SEQUENCE_GRID_LABEL_WIDTH, viewport.height(), self._palette.label_background)
        painter.setPen(QPen(self._palette.grid_outline))
        painter.drawLine(SEQUENCE_GRID_LABEL_WIDTH - 1, 0, SEQUENCE_GRID_LABEL_WIDTH - 1, viewport.height())
        painter.drawLine(0, SEQUENCE_GRID_RULER_HEIGHT - 1, viewport.width(), SEQUENCE_GRID_RULER_HEIGHT - 1)

        first_row, last_row, first_col, last_col = self.visible_range()
        y_offset = self.verticalScrollBar().value()
        for row_index in range(first_row, last_row):
            row = self._rows[row_index]
            y = SEQUENCE_GRID_RULER_HEIGHT + row_index * SEQUENCE_GRID_ROW_HEIGHT - y_offset
            if self._selection_covers_row(row_index):
                painter.fillRect(
                    QRect(0, y, SEQUENCE_GRID_LABEL_WIDTH, SEQUENCE_GRID_ROW_HEIGHT),
                    QColor(31, 78, 121, 35),
                )
            painter.setPen(QPen(QColor("#222222")))
            painter.drawText(
                QRect(4, y, SEQUENCE_GRID_LABEL_WIDTH - 8, SEQUENCE_GRID_ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                row.label,
            )
        x_offset = self.horizontalScrollBar().value()
        for column in range(first_col, last_col):
            x = SEQUENCE_GRID_LABEL_WIDTH + column * SEQUENCE_GRID_CELL_WIDTH - x_offset
            position = column + 1
            if self._selection_covers_column(column):
                painter.fillRect(
                    QRect(x, 0, SEQUENCE_GRID_CELL_WIDTH, SEQUENCE_GRID_RULER_HEIGHT),
                    QColor(31, 78, 121, 35),
                )
            if column in self._excluded_columns:
                painter.fillRect(
                    QRect(x, 0, SEQUENCE_GRID_CELL_WIDTH, SEQUENCE_GRID_RULER_HEIGHT),
                    self._palette.excluded_overlay,
                )
            painter.setPen(QPen(QColor("#666666")))
            if position == 1 or position % 10 == 0:
                painter.drawText(
                    QRect(x - 10, 2, SEQUENCE_GRID_CELL_WIDTH + 20, 16),
                    Qt.AlignmentFlag.AlignCenter,
                    str(position),
                )
                painter.drawLine(x + SEQUENCE_GRID_CELL_WIDTH // 2, 22, x + SEQUENCE_GRID_CELL_WIDTH // 2, 32)
            elif position % 5 == 0:
                painter.drawLine(x + SEQUENCE_GRID_CELL_WIDTH // 2, 26, x + SEQUENCE_GRID_CELL_WIDTH // 2, 32)

    def _paint_cells(self, painter: QPainter) -> None:
        first_row, last_row, first_col, last_col = self.visible_range()
        x_offset = self.horizontalScrollBar().value()
        y_offset = self.verticalScrollBar().value()
        for row_index in range(first_row, last_row):
            row = self._rows[row_index]
            y = SEQUENCE_GRID_RULER_HEIGHT + row_index * SEQUENCE_GRID_ROW_HEIGHT - y_offset
            for column in range(first_col, last_col):
                base = row.sequence[column] if column < len(row.sequence) else None
                x = SEQUENCE_GRID_LABEL_WIDTH + column * SEQUENCE_GRID_CELL_WIDTH - x_offset
                rect = QRect(x, y, SEQUENCE_GRID_CELL_WIDTH, SEQUENCE_GRID_ROW_HEIGHT)
                self._paint_cell(painter, rect, row.row_id, column, base)

    def _paint_cell(self, painter: QPainter, rect: QRect, row_id: str, column: int, base: str | None) -> None:
        if base is None:
            # A ragged, out-of-range cell is display padding, never a gap.
            painter.fillRect(rect, self._palette.default_background)
            painter.setPen(QPen(self._palette.grid_outline))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            return
        background = self._base_background(base)
        if (row_id, column) in self._edited_cells:
            background = self._palette.edited_background
        painter.fillRect(rect, background)
        painter.setPen(QPen(self._palette.grid_outline))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setPen(QPen(self._palette.gap_text_color if base == "-" else self._palette.text_color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, base)
        row_index = self._row_index(row_id)
        if row_index is not None and self._selection_contains(row_index, column):
            painter.fillRect(rect.adjusted(2, 2, -2, -2), QColor(31, 78, 121, 45))
            painter.setPen(QPen(self._palette.selection_outline, 1))
            painter.drawRect(rect.adjusted(1, 1, -2, -2))
        if column in self._excluded_columns:
            painter.fillRect(rect.adjusted(1, 1, -1, -1), self._palette.excluded_overlay)
            painter.setPen(QPen(QColor(90, 90, 90, 120), 1))
            painter.drawLine(rect.topLeft(), rect.bottomRight())
        if (
            self._selected_column == column
            and 0 <= self._selected_row < len(self._rows)
            and self._rows[self._selected_row].row_id == row_id
        ):
            painter.setPen(QPen(self._palette.selection_outline, 2))
            painter.drawRect(rect.adjusted(2, 2, -3, -3))

    def _move_selection(self, key: int, *, extend: bool = False) -> None:
        if not self._rows or not self._column_count:
            return
        if self._selected_row < 0:
            self._selected_row = 0
        if self._selected_column < 0:
            self._selected_column = 0
        if key == Qt.Key.Key_Left:
            self._selected_column = max(0, self._selected_column - 1)
        elif key == Qt.Key.Key_Right:
            self._selected_column = min(self._column_count - 1, self._selected_column + 1)
        elif key == Qt.Key.Key_Up:
            self._selected_row = max(0, self._selected_row - 1)
        elif key == Qt.Key.Key_Down:
            self._selected_row = min(len(self._rows) - 1, self._selected_row + 1)
        # Never leave keyboard focus on synthetic ragged padding.  Moving
        # vertically clamps into the target row; horizontal movement stops at
        # its last actual sequence coordinate.
        self._selected_column = min(
            self._selected_column,
            max(0, len(self._rows[self._selected_row].sequence) - 1),
        )
        if extend:
            self._extend_selection_to(self._selected_row, self._selected_column)
        else:
            self.select_rectangle(self._selected_row, self._selected_column, self._selected_row, self._selected_column, mode="cell")
        self._ensure_cell_visible()
        self._emit_current_cell()
        self.viewport().update()

    def _emit_current_cell(self) -> None:
        value = self.current_cell()
        if value is not None:
            self.cell_selected.emit(*value)

    def _ensure_cell_visible(self) -> None:
        if self._selected_column >= 0:
            x = self._selected_column * SEQUENCE_GRID_CELL_WIDTH
            x_scroll = self.horizontalScrollBar()
            visible_width = max(1, self.viewport().width() - SEQUENCE_GRID_LABEL_WIDTH)
            if x < x_scroll.value():
                x_scroll.setValue(x)
            elif x + SEQUENCE_GRID_CELL_WIDTH > x_scroll.value() + visible_width:
                x_scroll.setValue(x + SEQUENCE_GRID_CELL_WIDTH - visible_width)
        if self._selected_row >= 0:
            y = self._selected_row * SEQUENCE_GRID_ROW_HEIGHT
            y_scroll = self.verticalScrollBar()
            visible_height = max(1, self.viewport().height() - SEQUENCE_GRID_RULER_HEIGHT)
            if y < y_scroll.value():
                y_scroll.setValue(y)
            elif y + SEQUENCE_GRID_ROW_HEIGHT > y_scroll.value() + visible_height:
                y_scroll.setValue(y + SEQUENCE_GRID_ROW_HEIGHT - visible_height)

    def _update_scroll_ranges(self) -> None:
        total_width = self._column_count * SEQUENCE_GRID_CELL_WIDTH
        total_height = len(self._rows) * SEQUENCE_GRID_ROW_HEIGHT
        self.horizontalScrollBar().setRange(
            0,
            max(0, total_width - max(1, self.viewport().width() - SEQUENCE_GRID_LABEL_WIDTH)),
        )
        self.horizontalScrollBar().setPageStep(max(1, self.viewport().width() - SEQUENCE_GRID_LABEL_WIDTH))
        self.horizontalScrollBar().setSingleStep(SEQUENCE_GRID_CELL_WIDTH)
        self.verticalScrollBar().setRange(
            0,
            max(0, total_height - max(1, self.viewport().height() - SEQUENCE_GRID_RULER_HEIGHT)),
        )
        self.verticalScrollBar().setPageStep(max(1, self.viewport().height() - SEQUENCE_GRID_RULER_HEIGHT))
        self.verticalScrollBar().setSingleStep(SEQUENCE_GRID_ROW_HEIGHT)

    def _cell_viewport_rect(self, row_index: int, column_index: int) -> QRect:
        x = SEQUENCE_GRID_LABEL_WIDTH + column_index * SEQUENCE_GRID_CELL_WIDTH - self.horizontalScrollBar().value()
        y = SEQUENCE_GRID_RULER_HEIGHT + row_index * SEQUENCE_GRID_ROW_HEIGHT - self.verticalScrollBar().value()
        return QRect(x, y, SEQUENCE_GRID_CELL_WIDTH, SEQUENCE_GRID_ROW_HEIGHT)

    def _row_index(self, row_id: str) -> int | None:
        for index, row in enumerate(self._rows):
            if row.row_id == row_id:
                return index
        return None

    def _selection_for_rectangle(
        self,
        first_row: int,
        first_column: int,
        last_row: int,
        last_column: int,
        *,
        mode: str,
        anchor_row: int,
        anchor_column: int,
        active_row: int,
        active_column: int,
    ) -> SequenceGridSelection:
        if not self._rows or not self._column_count:
            return SequenceGridSelection(mode="none")
        first_row = max(0, min(int(first_row), len(self._rows) - 1))
        last_row = max(0, min(int(last_row), len(self._rows) - 1))
        first_column = max(0, min(int(first_column), self._column_count - 1))
        last_column = max(0, min(int(last_column), self._column_count - 1))
        active_row = max(0, min(int(active_row), len(self._rows) - 1))
        active_column = max(0, min(int(active_column), self._column_count - 1))
        anchor_row = max(0, min(int(anchor_row), len(self._rows) - 1))
        anchor_column = max(0, min(int(anchor_column), self._column_count - 1))
        return SequenceGridSelection(
            mode=mode,
            active_row=active_row,
            active_column=active_column,
            anchor_row=anchor_row,
            anchor_column=anchor_column,
            first_row=min(first_row, last_row),
            last_row=max(first_row, last_row),
            first_column=min(first_column, last_column),
            last_column=max(first_column, last_column),
        )

    def _set_selection(self, selection: SequenceGridSelection, *, emit: bool = True) -> None:
        self._selection = selection
        if selection.mode != "row":
            self._selected_row_indices.clear()
        if selection.active_row is not None:
            self._selected_row = selection.active_row
        if selection.active_column is not None:
            self._selected_column = selection.active_column
        if emit:
            self.selection_changed.emit(selection)

    def _extend_selection_to(self, row: int, column: int) -> None:
        if self._selection.is_empty:
            self.select_rectangle(row, column, row, column, mode="cell")
            return
        anchor_row = self._selection.anchor_row if self._selection.anchor_row is not None else row
        anchor_column = self._selection.anchor_column if self._selection.anchor_column is not None else column
        self.select_rectangle(anchor_row, anchor_column, row, column)

    def _selection_contains(self, row: int, column: int) -> bool:
        if self._selection.mode == "row":
            return row in self._selected_row_indices
        return (
            not self._selection.is_empty
            and self._selection.first_row <= row <= self._selection.last_row
            and self._selection.first_column <= column <= self._selection.last_column
        )

    def _selection_covers_row(self, row: int) -> bool:
        if self._selection.mode == "row":
            return row in self._selected_row_indices
        return (
            not self._selection.is_empty
            and self._selection.first_row <= row <= self._selection.last_row
            and self._selection.first_column == 0
            and self._selection.last_column == self._column_count - 1
        )

    def _selection_covers_column(self, column: int) -> bool:
        return (
            not self._selection.is_empty
            and self._selection.first_column <= column <= self._selection.last_column
            and self._selection.first_row == 0
            and self._selection.last_row == len(self._rows) - 1
        )

    def _update_auto_scroll_timer(self) -> None:
        if self._last_drag_position is None:
            self._auto_scroll_timer.stop()
            return
        margin = 24
        rect = self.viewport().rect()
        position = self._last_drag_position
        should_scroll = (
            position.x() < margin
            or position.x() > rect.width() - margin
            or position.y() < margin
            or position.y() > rect.height() - margin
        )
        if should_scroll and not self._auto_scroll_timer.isActive():
            self._auto_scroll_timer.start()
        elif not should_scroll:
            self._auto_scroll_timer.stop()

    def _auto_scroll_drag_selection(self) -> None:
        if self._drag_mode is None or self._last_drag_position is None:
            self._auto_scroll_timer.stop()
            return
        margin = 24
        step_x = SEQUENCE_GRID_CELL_WIDTH * 3
        step_y = SEQUENCE_GRID_ROW_HEIGHT * 2
        rect = self.viewport().rect()
        position = self._last_drag_position
        h_scroll = self.horizontalScrollBar()
        v_scroll = self.verticalScrollBar()
        if position.x() < margin:
            h_scroll.setValue(h_scroll.value() - step_x)
        elif position.x() > rect.width() - margin:
            h_scroll.setValue(h_scroll.value() + step_x)
        if position.y() < margin:
            v_scroll.setValue(v_scroll.value() - step_y)
        elif position.y() > rect.height() - margin:
            v_scroll.setValue(v_scroll.value() + step_y)
        row = int((position.y() - SEQUENCE_GRID_RULER_HEIGHT + v_scroll.value()) // SEQUENCE_GRID_ROW_HEIGHT)
        column = int((position.x() - SEQUENCE_GRID_LABEL_WIDTH + h_scroll.value()) // SEQUENCE_GRID_CELL_WIDTH)
        row = max(0, min(row, len(self._rows) - 1)) if self._rows else -1
        column = max(0, min(column, self._column_count - 1)) if self._column_count else -1
        if row < 0 or column < 0:
            return
        anchor_row = self._selection.anchor_row if self._selection.anchor_row is not None else row
        anchor_column = self._selection.anchor_column if self._selection.anchor_column is not None else column
        if self._drag_mode == "column":
            self.select_column_range(anchor_column, column)
        elif self._drag_mode == "row":
            self.select_row_range(anchor_row, row)
        else:
            self.select_rectangle(anchor_row, anchor_column, row, column)

    def _base_background(self, base: str) -> QColor:
        return self._palette.base_backgrounds.get(
            base.upper(),
            self._palette.ambiguous_background,
        )


def _coerce_base(base: str) -> str:
    value = str(base).upper()
    # SequenceGrid is shared by AlignmentDataset editors.  The immutable
    # model accepts the full DNA/IUPAC alphabet, so paste/edit rendering must
    # not reject valid symbols merely because they have no special palette.
    if value not in set("ACGTNRYSWKMBDHV-"):
        raise ValueError("base must be a DNA/IUPAC symbol or gap")
    return value
