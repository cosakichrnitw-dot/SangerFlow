"""Tests for the reusable Mesquite-style SequenceGridWidget."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from widgets.sequence_grid import (
    SEQUENCE_GRID_CELL_WIDTH,
    SEQUENCE_GRID_EDITED_BACKGROUND,
    SEQUENCE_GRID_LABEL_WIDTH,
    SEQUENCE_GRID_ROW_HEIGHT,
    DEFAULT_SEQUENCE_GRID_PALETTE,
    SequenceGridRow,
    SequenceGridSelection,
    SequenceGridWidget,
)


class SequenceGridWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_renders_rows_with_fixed_labels_gaps_and_base_colors(self) -> None:
        grid = SequenceGridWidget()
        grid.set_rows(
            (
                SequenceGridRow("r1", "Read 1", "ATG-C"),
                SequenceGridRow("r2", "Read 2", "ATGGC"),
            )
        )

        self.assertEqual(grid.label_width, SEQUENCE_GRID_LABEL_WIDTH)
        self.assertEqual(grid.cell_width, SEQUENCE_GRID_CELL_WIDTH)
        self.assertEqual(grid.row_height, SEQUENCE_GRID_ROW_HEIGHT)
        self.assertEqual(grid.row_label(0), "Read 1")
        self.assertEqual(grid.cell_base(0, 3), "-")
        self.assertEqual(
            grid.cell_background("r1", 3).name().upper(),
            DEFAULT_SEQUENCE_GRID_PALETTE.gap_background.name().upper(),
        )

    def test_ragged_padding_is_blank_not_a_biological_gap(self) -> None:
        grid = SequenceGridWidget()
        grid.set_rows(
            (
                SequenceGridRow("long", "Long", "ATG-C", editable=True),
                SequenceGridRow("short", "Short", "ATG", editable=True),
            )
        )

        self.assertEqual(grid.cell_base(0, 3), "-")
        self.assertIsNone(grid.cell_base(1, 3))
        self.assertFalse(grid.is_existing_cell(1, 3))
        self.assertFalse(grid.select_cell("short", 3))
        self.assertFalse(grid.set_cell_base("short", 3, "A"))
        grid.select_rectangle(1, 3, 1, 3)
        self.assertEqual(grid.selected_cells(), ())

    def test_ragged_copy_never_turns_missing_cells_into_gaps(self) -> None:
        grid = SequenceGridWidget()
        grid.set_rows(
            (
                SequenceGridRow("long", "Long", "ATGC"),
                SequenceGridRow("short", "Short", "AT"),
            )
        )
        grid.select_rectangle(0, 1, 1, 3)
        self.assertEqual(grid.selected_text(), "TGC\nT")
        self.assertNotIn("-", grid.selected_text().splitlines()[1])

    def test_selection_and_keyboard_editing_emit_changes(self) -> None:
        grid = SequenceGridWidget()
        edits = []
        grid.cell_edited.connect(lambda row_id, column, base: edits.append((row_id, column, base)))
        grid.set_rows(
            (
                SequenceGridRow("auto", "Auto", "ATGC"),
                SequenceGridRow("reviewed", "Reviewed", "ATGC", editable=True),
            )
        )

        self.assertTrue(grid.select_cell("reviewed", 2))
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_N,
            Qt.KeyboardModifier.NoModifier,
            "n",
        )
        QApplication.sendEvent(grid, event)

        self.assertEqual(edits, [("reviewed", 2, "N")])

    def test_rectangle_row_column_and_bounds_selection(self) -> None:
        grid = SequenceGridWidget()
        grid.set_rows(
            (
                SequenceGridRow("r1", "Read 1", "ATGC"),
                SequenceGridRow("r2", "Read 2", "ATGT"),
                SequenceGridRow("r3", "Read 3", "ATGA"),
            )
        )

        grid.select_rectangle(0, 1, 2, 3)

        self.assertEqual(grid.selection_bounds(), (0, 2, 1, 3))
        self.assertEqual(grid.selected_rows(), ("r1", "r2", "r3"))
        self.assertEqual(grid.selected_columns(), (1, 2, 3))
        self.assertEqual(len(grid.selected_cells()), 9)
        self.assertIn("3 rows × 3 columns", grid.selection_status_text())

        grid.select_row_range(1, 2)
        self.assertEqual(grid.selection_bounds(), (1, 2, 0, 3))
        self.assertIn("2 rows", grid.selection_status_text())

        grid.select_column_range(2, 3)
        self.assertEqual(grid.selection_bounds(), (0, 2, 2, 3))
        self.assertIn("Columns 3–4", grid.selection_status_text())

    def test_cmd_a_escape_shift_arrow_and_multi_edit_protection(self) -> None:
        grid = SequenceGridWidget()
        edits = []
        grid.cell_edited.connect(lambda row_id, column, base: edits.append((row_id, column, base)))
        grid.set_rows(
            (
                SequenceGridRow("r1", "Read 1", "ATGC", editable=True),
                SequenceGridRow("r2", "Read 2", "ATGT", editable=True),
            )
        )
        grid.select_cell("r1", 1)

        shift_right = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Right,
            Qt.KeyboardModifier.ShiftModifier,
        )
        QApplication.sendEvent(grid, shift_right)
        self.assertEqual(grid.selection_bounds(), (0, 0, 1, 2))

        replace = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_N,
            Qt.KeyboardModifier.NoModifier,
            "n",
        )
        QApplication.sendEvent(grid, replace)
        self.assertEqual(edits, [])

        select_all = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.MetaModifier,
            "a",
        )
        QApplication.sendEvent(grid, select_all)
        self.assertEqual(grid.selection_bounds(), (0, 1, 0, 3))

        escape = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(grid, escape)
        self.assertIsNone(grid.selection_bounds())

    def test_selection_survives_scroll(self) -> None:
        grid = SequenceGridWidget()
        grid.resize(300, 140)
        grid.set_rows(
            tuple(
                SequenceGridRow(f"r{index}", f"Read {index}", "A" * 100)
                for index in range(20)
            )
        )
        grid.select_rectangle(3, 10, 5, 12)

        grid.horizontalScrollBar().setValue(200)
        grid.verticalScrollBar().setValue(80)

        self.assertEqual(grid.selection_bounds(), (3, 5, 10, 12))
        self.assertIn(("r4", 11), grid.selected_cells())

    def test_edited_cells_are_highlighted(self) -> None:
        grid = SequenceGridWidget()
        grid.set_rows(
            (SequenceGridRow("reviewed", "Reviewed", "ATGC", editable=True),),
            edited_cells={("reviewed", 1)},
        )

        self.assertEqual(
            grid.cell_background("reviewed", 1).name().upper(),
            SEQUENCE_GRID_EDITED_BACKGROUND.name().upper(),
        )

    def test_visible_range_is_viewport_based(self) -> None:
        grid = SequenceGridWidget()
        grid.resize(260, 120)
        grid.set_rows(
            tuple(
                SequenceGridRow(f"r{index}", f"Read {index}", "A" * 1000)
                for index in range(100)
            )
        )

        first_row, last_row, first_col, last_col = grid.visible_range()
        expected_max_columns = (
            max(1, grid.viewport().width() - grid.label_width) // grid.cell_width
        ) + 3
        expected_max_rows = (
            max(1, grid.viewport().height() - grid.ruler_height) // grid.row_height
        ) + 3

        self.assertLessEqual(last_col - first_col, expected_max_columns)
        self.assertLessEqual(last_row - first_row, expected_max_rows)

    def test_selection_copy_and_fasta_export_text_preserve_order(self) -> None:
        grid = SequenceGridWidget()
        grid.set_rows(
            (
                SequenceGridRow("r1", "Read 1", "ATG-C"),
                SequenceGridRow("r2", "Read 2", "ATGTC"),
            )
        )

        grid.select_rectangle(0, 1, 1, 3)

        self.assertEqual(grid.selected_text(), "TG-\nTGT")
        self.assertEqual(grid.selected_fasta_text(), ">Read 1\nTG-\n>Read 2\nTGT\n")

        copy_event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_C,
            Qt.KeyboardModifier.MetaModifier,
            "c",
        )
        QApplication.sendEvent(grid, copy_event)

        self.assertEqual(QApplication.clipboard().text(), "TG-\nTGT")

    def test_excluded_columns_are_reported_and_visible_as_state(self) -> None:
        grid = SequenceGridWidget()
        grid.set_rows(
            (
                SequenceGridRow("r1", "Read 1", "ATGC"),
                SequenceGridRow("r2", "Read 2", "ATGT"),
            )
        )

        grid.set_excluded_columns({1, 3, 99})
        grid.select_column_range(1, 3)

        self.assertEqual(grid.excluded_columns, frozenset({1, 3}))
        self.assertIn("2 excluded", grid.selection_status_text())

    def test_drag_auto_scroll_timer_uses_viewport_edges(self) -> None:
        grid = SequenceGridWidget()
        grid.resize(220, 120)
        grid.set_rows(
            tuple(
                SequenceGridRow(f"r{index}", f"Read {index}", "A" * 200)
                for index in range(20)
            )
        )

        grid._drag_mode = "cell"
        grid._last_drag_position = QPointF(grid.viewport().width() - 1, grid.viewport().height() - 1)
        grid._update_auto_scroll_timer()

        self.assertTrue(grid._auto_scroll_timer.isActive())

        grid._drag_mode = None
        grid._last_drag_position = None
        grid._update_auto_scroll_timer()

        self.assertFalse(grid._auto_scroll_timer.isActive())

    def test_rows_refresh_discards_stale_selection_indices(self) -> None:
        grid = SequenceGridWidget()
        grid.set_rows(
            (
                SequenceGridRow("r1", "Read 1", "ATGC"),
                SequenceGridRow("r2", "Read 2", "ATGC"),
            )
        )
        grid.set_rows((SequenceGridRow("r1", "Read 1", "ATGC"),))
        # Simulates a queued view refresh observing a pre-filter rectangle.
        grid._selection = SequenceGridSelection(
            mode="row", first_row=1, last_row=1, first_column=0, last_column=3
        )

        self.assertEqual(grid.selected_rows(), ())
        self.assertEqual(grid.selected_cells(), ())
        self.assertEqual(grid.selection_bounds(), None)

    def test_rows_refresh_can_explicitly_clear_display_index_selection(self) -> None:
        grid = SequenceGridWidget()
        grid.set_rows(
            (
                SequenceGridRow("r1", "Read 1", "ATGC"),
                SequenceGridRow("r2", "Read 2", "ATGC"),
                SequenceGridRow("r3", "Read 3", "ATGC"),
            )
        )
        grid.select_row("r2")

        # Pending row deletion rebuilds must not preserve an old display
        # coordinate that could now point to another record.
        grid.set_rows(
            (
                SequenceGridRow("r1", "Read 1", "ATGC"),
                SequenceGridRow("r3", "Read 3", "ATGC"),
            ),
            preserve_selection=False,
        )

        self.assertTrue(grid.selection.is_empty)
        self.assertEqual(grid.selected_rows(), ())
        self.assertEqual(grid.selected_cells(), ())
        self.assertIsNone(grid.current_cell())

    def test_row_header_supports_cmd_multiselect_and_shift_range(self) -> None:
        grid = SequenceGridWidget()
        grid.resize(320, 180)
        grid.set_rows(tuple(SequenceGridRow(f"r{index}", f"Read {index}", "ATGC") for index in range(4)))

        grid.select_row_range(0, 0)
        grid.toggle_row_selection(2)
        self.assertEqual(grid.selected_rows(), ("r0", "r2"))
        grid.select_row_range(0, 3)
        self.assertEqual(grid.selected_rows(), ("r0", "r1", "r2", "r3"))

    def test_row_header_mouse_interaction_selects_rows(self) -> None:
        grid = SequenceGridWidget()
        grid.resize(320, 180)
        grid.set_rows(tuple(SequenceGridRow(f"r{index}", f"Read {index}", "ATGC") for index in range(4)))
        grid.show()
        self.application.processEvents()
        y = grid.ruler_height + grid.row_height // 2
        QTest.mouseClick(grid.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(8, y))
        QTest.mouseClick(
            grid.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier,
            QPoint(8, y + 2 * grid.row_height),
        )
        self.assertEqual(grid.selected_rows(), ("r0", "r2"))
        QTest.mouseClick(
            grid.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ShiftModifier,
            QPoint(8, y + 3 * grid.row_height),
        )
        self.assertEqual(grid.selected_rows(), ("r0", "r1", "r2", "r3"))

    def test_context_menu_target_uses_viewport_coordinates_for_all_regions(self) -> None:
        grid = SequenceGridWidget()
        grid.resize(360, 180)
        grid.show()
        grid.set_rows((SequenceGridRow("r1", "Read 1", "ATGC"), SequenceGridRow("r2", "Read 2", "ATGT")))
        observed = []
        grid.set_context_menu_handler(lambda selection, _global: observed.append(selection.mode))

        def open_menu_at(local: QPoint) -> None:
            event = QContextMenuEvent(
                QContextMenuEvent.Reason.Mouse,
                local,
                grid.viewport().mapToGlobal(local),
            )
            grid.contextMenuEvent(event)

        # Each target is evaluated independently; a deliberate selection is
        # now preserved when the next context click remains inside it.
        for point in (
            QPoint(8, grid.ruler_height + 4),  # row header
            QPoint(grid.label_width + 4, grid.ruler_height + 4),  # cell
            QPoint(grid.label_width + 4, 4),  # column header
            QPoint(4, 4),  # empty corner
        ):
            grid.clear_selection()
            open_menu_at(point)

        self.assertEqual(observed, ["row", "cell", "column", "none"])

    def test_context_click_inside_rectangle_preserves_existing_selection(self) -> None:
        grid = SequenceGridWidget()
        grid.resize(360, 180)
        grid.show()
        grid.set_rows((SequenceGridRow("r1", "Read 1", "ATGC"), SequenceGridRow("r2", "Read 2", "ATGT")))
        grid.select_rectangle(0, 0, 1, 2)

        # A context click in the selected rectangle must not collapse it to
        # one cell before the viewer builds a multi-cell action menu.
        grid._select_context_target(QPointF(grid.label_width + 2 * grid.cell_width, grid.ruler_height + grid.row_height + 4))
        self.assertEqual(grid.selection_bounds(), (0, 1, 0, 2))

        # A target outside the rectangle deliberately starts a new selection.
        grid._select_context_target(QPointF(grid.label_width + 3 * grid.cell_width, grid.ruler_height + 4))
        self.assertEqual(grid.selection_bounds(), (0, 0, 3, 3))

    def test_context_click_on_row_header_inside_rectangle_keeps_multi_row_selection(self) -> None:
        grid = SequenceGridWidget()
        grid.set_rows((SequenceGridRow("r1", "Read 1", "ATGC"), SequenceGridRow("r2", "Read 2", "ATGT")))
        grid.select_rectangle(0, 0, 1, 2)

        grid._select_context_target(QPointF(8, grid.ruler_height + grid.row_height + 4))
        self.assertEqual(grid.selection_bounds(), (0, 1, 0, 2))


if __name__ == "__main__":
    unittest.main()
