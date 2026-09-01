"""Checks for Chromatogram Viewer v1 and AB1 folder routing."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins
configure_qt_plugins()
from app.app_state import AppState
from app.action_manager import ActionManager
from app.selection import SelectionKind
from controllers.project_controller import ProjectController
from core.models import SangerRead
from core.project import Project
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from core.trimming import trim_sequence
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QFontMetricsF
from PySide6.QtWidgets import QApplication, QDialog, QGraphicsView, QMainWindow, QToolBar
from app.read_visibility import ReadVisibilityManager
from views.project_view import ProjectView
from widgets.viewers.viewer_context import ViewerContext
from widgets.viewers.chromatogram_viewer import (
    ChromatogramViewer,
    TRACE_HEIGHT,
    TRACE_TOP,
    _centered_text_baseline,
    has_chromatogram_sources,
    reads_from_dataset,
    _read_view,
    _trim_overlay_scene_rects,
)
from widgets.alignment_settings_dialog import AlignmentSettingsDialog
from widgets.viewers.alignment_chromatogram_viewer import (
    ALIGNMENT_TRACE_GAIN,
    BASE_WIDTH,
    NAME_WIDTH,
    ROW_HEIGHT,
    AlignmentChromatogramViewer,
    _alignment_column_x,
    _peak_to_peak_trace_segments,
    _quality_for_trace_position,
    _raw_trace_path,
    _trace_segments,
)
from widgets.viewers.alignment_viewer import AlignmentViewer
from widgets.viewers.sequence_editor import SequenceEditor
from widgets.viewers.quality_report_viewer import QualityReportViewer
from widgets.quality_report_dock import QualityReportDock
from widgets.inspector_panel import InspectorPanel


class ChromatogramViewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = QApplication.instance() or QApplication([])

    def test_alignment_settings_default_and_advanced_metadata_are_reproducible(self) -> None:
        dialog = AlignmentSettingsDialog(dataset_name="AB1 reads", sequence_count=3)
        defaults = dialog.settings()
        self.assertEqual(defaults.strategy, "Auto")
        self.assertTrue(defaults.open_after_completion)
        self.assertIsNone(defaults.gap_opening_penalty)
        dialog._advanced.setChecked(True)
        dialog._strategy.setCurrentText("L-INS-i")
        dialog._gap_opening.setValue(1.7)
        advanced = dialog.settings()
        self.assertEqual(advanced.strategy, "L-INS-i")
        self.assertEqual(advanced.metadata()["alignment_parameters"]["gap_opening_penalty"], 1.7)

    def test_chromatogram_viewer_displays_multiple_reads(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK346_F.ab1", "ATGT"))

        viewer = ChromatogramViewer(reads, title="Chromatograms")

        self.assertEqual(viewer.viewer_kind, "chromatogram")
        self.assertEqual(len(viewer.read_views), 2)
        self.assertIn("Reads: 2", viewer._summary_label.text())
        self.assertEqual(viewer.read_views[0].sequence, "ATGC")
        self.assertGreater(viewer.read_views[0].average_quality, 0)
        self.assertEqual(viewer.read_views[0].trim_start, 0)
        self.assertEqual(viewer.read_views[0].trim_end, 4)
        self.assertEqual(viewer._content_height(), 200)
        self.assertIsInstance(viewer._canvas_widget, QGraphicsView)
        self.assertEqual(len(viewer._canvas_widget.row_items), 2)
        self.assertIn("IK345_F.ab1", viewer._canvas_widget.row_items)
        self.assertEqual(
            viewer._canvas_widget.scene_item_counts(),
            {
                "scene_items": 2,
                "read_items": 2,
                "trace_items": 0,
                "base_items": 0,
                "tick_items": 0,
                "overlay_items": 0,
                "trim_items": 0,
            },
        )
        self.assertFalse(hasattr(viewer, "_sample_panel_widget"))
        self.assertFalse(hasattr(viewer, "_label_widget"))
        self.assertEqual(viewer._read_label_widget.width(), 110)

    def test_read_labels_share_scene_row_geometry_for_small_and_scrollable_read_sets(self) -> None:
        """Labels and traces stay on the same row centers for every read count."""

        for read_count in (1, 2, 4, 10, 24):
            with self.subTest(read_count=read_count):
                reads = tuple(
                    _read_untrimmed(f"read_{index}.ab1", "ATGCATGCATGC")
                    for index in range(read_count)
                )
                viewer = ChromatogramViewer(reads, title="Chromatograms")
                viewer._canvas_widget.setFixedSize(240, 180)
                viewer._read_label_widget.setFixedHeight(180)
                viewer.refresh()
                self.application.processEvents()

                self.assertEqual(
                    viewer._canvas_widget.alignment(),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                )
                self.assertEqual(viewer._content_height(), read_count * viewer._row_height())
                for row_index, read_view in enumerate(viewer.visible_read_views):
                    geometry = viewer._row_geometry(row_index)
                    item = viewer._canvas_widget.row_items[read_view.read_id]
                    self.assertEqual(item.pos().y(), geometry.top())
                    self.assertEqual(viewer._read_label_widget._row_center_y(row_index), geometry.center().y())

                # Horizontal navigation and selection must not alter a label's
                # vertical relationship to its trace row.
                viewer._horizontal_scrollbar.setValue(min(20, viewer._horizontal_scrollbar.maximum()))
                viewer.select_read(reads[-1].filename)
                self.assertEqual(
                    viewer._read_label_widget._row_center_y(read_count - 1),
                    viewer._row_geometry(read_count - 1).center().y(),
                )

                if read_count > 10:
                    y_offset = min(viewer._vertical_scrollbar.maximum(), viewer._row_height() + 7)
                    viewer._vertical_scrollbar.setValue(y_offset)
                    metrics = QFontMetricsF(viewer._read_label_widget.font())
                    center = viewer._read_label_widget._row_center_y(1) - viewer._y_offset
                    baseline = _centered_text_baseline(center, metrics)
                    glyph_center = baseline + (metrics.descent() - metrics.ascent()) / 2
                    self.assertAlmostEqual(glyph_center, center)

                # A resize can change viewport space, but never content rows.
                viewer._canvas_widget.resize(320, 260)
                viewer._update_scroll_ranges()
                for row_index, read_view in enumerate(viewer.visible_read_views):
                    self.assertEqual(
                        viewer._canvas_widget.row_items[read_view.read_id].pos().y(),
                        viewer._row_geometry(row_index).top(),
                    )

    def test_closed_chromatogram_viewers_receive_no_visibility_callback(self) -> None:
        manager = ReadVisibilityManager()
        read = _read("IK345_F.ab1", "ATGC")
        chromatogram = ChromatogramViewer(
            (read,),
            context=ViewerContext(None, None, read_visibility_manager=manager),
        )
        alignment = AlignmentChromatogramViewer(
            (read,),
            alignment=_alignment(((read.filename, read.sequence),)),
            context=ViewerContext(None, None, read_visibility_manager=manager),
        )
        chromatogram_key = chromatogram._visibility_source_key
        alignment_key = alignment._visibility_source_key

        # TabManager invokes close_viewer() before removeTab()/deleteLater().
        # That formal lifecycle must detach both short-lived viewers from the
        # long-lived ReadVisibilityManager.
        chromatogram.close_viewer()
        alignment.close_viewer()
        chromatogram.deleteLater()
        alignment.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        manager.set_visible_ids(chromatogram_key, ())
        manager.set_visible_ids(alignment_key, ())
        self.application.processEvents()

    def test_open_dataset_keeps_all_sanger_reads_visible(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK346_F.ab1", "ATGT"))
        dataset = SequenceDataset(
            dataset_id="ab1-trimmed",
            name="AB1 Trimmed",
            source_type=SourceType.AB1_TRIMMED,
            records=tuple(
                SequenceRecord(
                    sequence_id=read.filename,
                    sequence=read.trimmed_sequence,
                    source_reference=read,
                )
                for read in reads
            ),
        )
        viewer = ChromatogramViewer((), title="Chromatograms")

        viewer.open_dataset(dataset)

        self.assertEqual(tuple(read.read_id for read in viewer.read_views), ("IK345_F.ab1", "IK346_F.ab1"))
        self.assertEqual(tuple(read.read_id for read in viewer.visible_read_views), ("IK345_F.ab1", "IK346_F.ab1"))
        self.assertEqual(viewer._content_height(), 200)
        self.assertEqual(viewer._canvas_widget.scene_item_counts()["scene_items"], 2)

    def test_render_geometry_is_cached_at_load_time(self) -> None:
        viewer = ChromatogramViewer((_read("IK345_F.ab1", "ATGC"),), title="Chromatograms")
        cache = viewer.read_views[0].render_cache

        self.assertEqual(tuple(cache.trace_paths), ("A", "C", "G", "T"))
        self.assertIsNotNone(cache.quality_path)
        self.assertEqual(cache.base_items[0][:3], (0, "A", 5))
        self.assertEqual(cache.base_items[0][3].text(), "A")
        self.assertEqual(cache.tick_items[0][:2], (5, "1"))
        self.assertEqual(cache.tick_items[0][2].text(), "1")

    def test_quality_dock_checkbox_toggles_canvas_visibility_and_compacts_canvas(self) -> None:
        viewer = ChromatogramViewer(
            (_read("IK345_F.ab1", "ATGC"), _read("IK346_F.ab1", "ATGT")),
            title="Chromatograms",
        )
        original_height = viewer._content_height()

        viewer.set_read_visible("IK345_F.ab1", False)
        self.application.processEvents()

        self.assertNotIn("IK345_F.ab1", viewer.visible_read_ids)
        self.assertEqual(tuple(read.read_id for read in viewer.visible_read_views), ("IK346_F.ab1",))
        self.assertEqual(viewer._content_height(), original_height // 2)
        self.assertEqual(viewer.read_views[1].read_id, "IK346_F.ab1")
        selected = viewer.select_base_at(viewer.read_views[1].base_positions[0], 20)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.read_id, "IK346_F.ab1")

        viewer.set_read_visible("IK345_F.ab1", True)
        self.application.processEvents()

        self.assertIn("IK345_F.ab1", viewer.visible_read_ids)
        self.assertEqual(viewer._content_height(), original_height)

    def test_quality_report_dock_is_read_visibility_manager(self) -> None:
        reads = (
            _read("IK345_F.ab1", "ATGC"),
            _read("IK346_F.ab1", "ATGT"),
        )
        manager = ReadVisibilityManager()
        dock = QualityReportDock(visibility_manager=manager)
        viewer = ChromatogramViewer(reads, title="Chromatograms")
        manager.visibility_changed.connect(viewer._visibility_changed)
        manager.initialize_source(viewer._visibility_source_key, tuple(read.filename for read in reads))
        dock.set_reads(viewer.read_views, source_key=viewer._visibility_source_key)

        dock._table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        self.application.processEvents()

        self.assertEqual(tuple(read.read_id for read in viewer.visible_read_views), ("IK346_F.ab1",))
        self.assertEqual(dock.selected_read_ids(), ("IK346_F.ab1",))

    def test_quality_report_dock_displays_q40_and_hq_using_q40_default(self) -> None:
        # C13_FishF1.ab1 Geneious Default Profile comparison: 7,463 / 10,000
        # bases meet Q40, which is 74.63% before one-decimal display rounding.
        c13_quality = [40] * 7463 + [39] * 2537
        viewer = ChromatogramViewer(
            (_read_with_quality("C13_FishF1.ab1", "A" * len(c13_quality), c13_quality),),
            title="Chromatograms",
        )
        dock = QualityReportDock(visibility_manager=ReadVisibilityManager())
        dock.set_reads(viewer.read_views, source_key="c13-fixture")

        self.assertEqual(dock._table.horizontalHeaderItem(2).text(), "Q20%")
        self.assertEqual(dock._table.horizontalHeaderItem(3).text(), "Q30%")
        self.assertEqual(dock._table.horizontalHeaderItem(4).text(), "Q40%")
        self.assertEqual(dock._table.horizontalHeaderItem(5).text(), "HQ%")
        self.assertNotIn("MeanQ", [dock._table.horizontalHeaderItem(i).text() for i in range(7)])
        self.assertEqual(dock._table.item(0, 2).text(), "100.0")
        self.assertEqual(dock._table.item(0, 3).text(), "100.0")
        self.assertEqual(viewer.read_views[0].q40_rate, 74.63)
        self.assertEqual(dock._table.item(0, 4).text(), "74.6")
        self.assertEqual(dock._table.item(0, 5).text(), "74.6")
        self.assertEqual(dock._hq_threshold, 40)

    def test_quality_visibility_is_shared_with_alignment_chromatogram_viewer(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK346_F.ab1", "ATGT"))
        manager = ReadVisibilityManager()
        context = ViewerContext(
            AppState(),
            ProjectController(AppState()),
            read_visibility_manager=manager,
        )
        source_key = "ab1-trimmed"
        chromatogram_viewer = ChromatogramViewer(
            reads,
            title="Chromatograms",
            source_object_id=source_key,
            context=context,
        )
        alignment_viewer = AlignmentChromatogramViewer(
            reads,
            alignment=_alignment((("IK345_F.ab1", "ATGC"), ("IK346_F.ab1", "ATGT"))),
            source_object_id=source_key,
            context=context,
        )

        manager.set_visible(source_key, "IK345_F.ab1", False)
        self.application.processEvents()

        self.assertEqual(tuple(read.read_id for read in chromatogram_viewer.visible_read_views), ("IK346_F.ab1",))
        self.assertEqual(tuple(record.id for record in alignment_viewer._visible_records()), ("IK346_F.ab1",))

    def test_x_and_y_scale_sliders_update_viewer_scale(self) -> None:
        read = _read_untrimmed("IK345_F.ab1", "ATGCATGC")
        viewer = ChromatogramViewer((read,), title="Chromatograms")
        viewer._canvas_widget.setFixedSize(80, 120)
        viewer.refresh()
        original_width = viewer._content_width()
        original_height = viewer._content_height()
        original_row_height = viewer._row_height()

        viewer._scale_panel_widget.x_slider.setValue(200)
        viewer._scale_panel_widget.y_slider.setValue(150)
        self.application.processEvents()

        self.assertEqual(viewer.scale_x, 2.0)
        self.assertEqual(viewer.scale_y, 1.5)
        self.assertGreater(viewer._content_width(), original_width)
        self.assertEqual(viewer._row_height(), int(original_row_height * 1.5))
        self.assertGreater(viewer._content_height(), original_height)
        self.assertIn("QScrollBar:vertical", viewer._scale_panel_widget.x_slider.styleSheet())
        self.assertEqual(viewer._scale_panel_widget.x_slider.width(), 17)
        self.assertEqual(viewer._scale_panel_widget.y_slider.width(), 17)

    def test_scale_slider_drag_defers_scene_and_pixmap_rebuild_until_release(self) -> None:
        read = _read_untrimmed("IK345_F.ab1", "ATGCATGC")
        viewer = ChromatogramViewer((read,), title="Chromatograms")
        viewer.refresh()
        initial = viewer.rebuild_diagnostics()

        viewer._scale_panel_widget.x_slider.setSliderDown(True)
        viewer._scale_panel_widget.x_slider.setValue(120)
        viewer._scale_panel_widget.x_slider.setValue(140)
        viewer._scale_panel_widget.x_slider.setValue(160)
        during_drag = viewer.rebuild_diagnostics()

        self.assertEqual(during_drag, initial)
        self.assertEqual(viewer.scale_x, 1.0)

        viewer._scale_panel_widget.x_slider.setSliderDown(False)
        viewer.commit_pending_scale()
        after_release = viewer.rebuild_diagnostics()

        self.assertEqual(viewer.scale_x, 1.6)
        self.assertEqual(after_release["scene_rebuild_count"], initial["scene_rebuild_count"] + 1)
        self.assertGreater(after_release["pending_tile_jobs"], 0)
        self.assertEqual(after_release["trace_pixmap_rebuild_count"], initial["trace_pixmap_rebuild_count"])

        viewer._canvas_widget.process_pending_trace_tiles_for_tests()
        after_tile_build = viewer.rebuild_diagnostics()

        self.assertEqual(after_tile_build["pending_tile_jobs"], 0)
        self.assertGreater(
            after_tile_build["trace_pixmap_rebuild_count"],
            initial["trace_pixmap_rebuild_count"],
        )

    def test_trace_tile_builds_are_queued_for_visible_rows_only(self) -> None:
        reads = tuple(
            _read_untrimmed(f"IK{345 + index}_F.ab1", "ATGC" * 50)
            for index in range(12)
        )
        viewer = ChromatogramViewer(reads, title="Chromatograms")
        viewer._canvas_widget.setFixedSize(200, 80)
        viewer.refresh()

        diagnostics = viewer.rebuild_diagnostics()

        self.assertGreater(diagnostics["pending_tile_jobs"], 0)
        self.assertLess(diagnostics["pending_tile_jobs"], len(reads) * 2)
        self.assertEqual(diagnostics["trace_pixmap_rebuild_count"], 0)

        viewer._canvas_widget.process_pending_trace_tiles_for_tests()
        after_tile_build = viewer.rebuild_diagnostics()

        self.assertEqual(after_tile_build["pending_tile_jobs"], 0)
        self.assertGreater(after_tile_build["trace_pixmap_rebuild_count"], 0)

    def test_hundred_read_scene_uses_one_item_per_read_and_lazy_tiles(self) -> None:
        """A 100-read workload must not multiply scene items by bases or traces."""

        reads = tuple(
            _read_untrimmed(f"IK{1000 + index}_F.ab1", "ATGC" * 50)
            for index in range(100)
        )
        viewer = ChromatogramViewer(reads, title="100 reads")
        viewer._canvas_widget.setFixedSize(240, 120)
        viewer.refresh()

        counts = viewer._canvas_widget.scene_item_counts()
        diagnostics = viewer.rebuild_diagnostics()
        self.assertEqual(counts["scene_items"], 100)
        self.assertEqual(counts["read_items"], 100)
        self.assertEqual(counts["trace_items"], 0)
        self.assertEqual(counts["base_items"], 0)
        self.assertLess(diagnostics["pending_tile_jobs"], len(reads) * 2)

    def test_chromatogram_viewer_uses_raw_read_values_not_trimmed_values(self) -> None:
        read = _read_untrimmed("IK345_F.ab1", "NATGCN")
        read.trim_start = 1
        read.trim_end = 5
        read.trimmed_sequence = "ATGC"
        read.trimmed_quality = [30, 31, 32, 33]
        read.trimmed_base_positions = [0, 8, 16, 24]
        read.trimmed_traces = {
            "A": [1, 2],
            "C": [1, 2],
            "G": [1, 2],
            "T": [1, 2],
        }

        viewer = ChromatogramViewer((read,), title="Chromatograms")

        self.assertEqual(viewer.read_views[0].sequence, "NATGCN")
        self.assertEqual(viewer.read_views[0].quality, tuple(read.quality))
        self.assertEqual(viewer.read_views[0].base_positions, tuple(read.base_positions))
        self.assertEqual(viewer.read_views[0].trace_length, len(read.traces["A"]))

    def test_trim_overlay_uses_raw_trace_positions_in_scene_coordinates(self) -> None:
        read = _read_untrimmed("IK345_F.ab1", "ATGCATGC")
        read.trim_start = 2
        read.trim_end = 6
        read_view = _read_view(read)

        rects = _trim_overlay_scene_rects(read_view, scale_x=2.0, scale_y=1.5)

        self.assertEqual(len(rects), 2)
        self.assertEqual(rects[0].x(), 0)
        self.assertEqual(rects[0].width(), read.base_positions[2] * 2.0)
        self.assertEqual(rects[1].x(), read.base_positions[6] * 2.0)
        self.assertEqual(rects[0].y(), TRACE_TOP * 1.5)
        self.assertEqual(rects[0].height(), TRACE_HEIGHT / 2 * 1.5)

    def test_trim_overlay_keeps_global_coordinates_across_tile_boundaries(self) -> None:
        read = _read_untrimmed("IK345_F.ab1", "ATGC")
        read.base_positions = [100, 600, 1100, 1600]
        read.traces = {
            "A": [1 for _ in range(1900)],
            "C": [1 for _ in range(1900)],
            "G": [1 for _ in range(1900)],
            "T": [1 for _ in range(1900)],
        }
        read.trim_start = 1
        read.trim_end = 3
        read_view = _read_view(read)

        rects = _trim_overlay_scene_rects(read_view, scale_x=1.0, scale_y=1.0)

        self.assertEqual(len(rects), 1)
        self.assertEqual(rects[0].x(), 0)
        self.assertEqual(rects[0].width(), 600)

    def test_trim_overlay_does_not_apply_dpr_as_an_extra_scale(self) -> None:
        read = _read_untrimmed("IK345_F.ab1", "ATGC")
        read.trim_start = 1
        read.trim_end = 3
        read_view = _read_view(read)

        rects = _trim_overlay_scene_rects(read_view, scale_x=2.0, scale_y=2.0)

        self.assertEqual(rects[0].width(), read.base_positions[1] * 2.0)

    def test_horizontal_scroll_is_based_on_raw_trace_width(self) -> None:
        read = _read_untrimmed("IK345_F.ab1", "ATGCATGCATGC")
        viewer = ChromatogramViewer((read,), title="Chromatograms")
        viewer._canvas_widget.setFixedSize(80, 120)
        viewer.refresh()

        self.assertEqual(viewer._content_width(), len(read.traces["A"]) + 80)
        self.assertGreater(viewer._horizontal_scrollbar.maximum(), 0)
        self.assertEqual(
            viewer._horizontal_scrollbar.maximum(),
            viewer._content_width() - viewer._canvas_widget.width(),
        )
        viewer._horizontal_scrollbar.setValue(25)

        self.assertEqual(viewer._x_offset, 25)
        self.assertFalse(hasattr(viewer._canvas_widget, "scroll_to"))
        self.assertEqual(viewer._horizontal_scrollbar.height(), 12)
        self.assertIn("QScrollBar:horizontal", viewer._horizontal_scrollbar.styleSheet())

    def test_mini_map_is_removed_and_horizontal_scroll_remains_available(self) -> None:
        viewer = ChromatogramViewer((_read_untrimmed("IK345_F.ab1", "ATGCATGCATGC"),), title="Chromatograms")
        viewer._canvas_widget.setFixedSize(80, 120)
        viewer.refresh()

        self.assertFalse(hasattr(viewer, "_mini_map_widget"))
        viewer._horizontal_scrollbar.setValue(viewer._horizontal_scrollbar.maximum() // 2)

        self.assertEqual(
            viewer._horizontal_scrollbar.value(),
            viewer._horizontal_scrollbar.maximum() // 2,
        )

    def test_trackpad_horizontal_scroll_delta_moves_trace_coordinate_viewport(self) -> None:
        viewer = ChromatogramViewer((_read_untrimmed("IK345_F.ab1", "ATGCATGCATGC"),), title="Chromatograms")
        viewer._canvas_widget.setFixedSize(80, 120)
        viewer.refresh()

        viewer._canvas_widget.handle_wheel_delta(-30, 0)

        self.assertEqual(viewer._horizontal_scrollbar.value(), 30)
        self.assertEqual(viewer._x_offset, 30)

    def test_control_wheel_zoom_keeps_existing_x_scale_path(self) -> None:
        viewer = ChromatogramViewer((_read_untrimmed("IK345_F.ab1", "ATGCATGCATGC"),), title="Chromatograms")
        viewer._canvas_widget.setFixedSize(80, 120)
        viewer.refresh()

        viewer._canvas_widget.handle_wheel_delta(-30, 0)
        viewer._canvas_widget.wheelEvent(_wheel_event(vertical_delta=120, control=True))

        self.assertGreater(viewer.scale_x, 1.0)
        self.assertEqual(viewer._x_offset, 30)

    def test_read_selection_emits_sequence_record_selection(self) -> None:
        viewer = ChromatogramViewer((_read("IK345_F.ab1", "ATGC"),), title="Chromatograms")
        selections = []
        viewer.selection_changed.connect(selections.append)

        viewer.select_read("IK345_F.ab1")

        self.assertEqual(viewer.selected_read_id, "IK345_F.ab1")
        self.assertEqual(len(selections), 1)
        self.assertEqual(selections[0].kind, SelectionKind.SEQUENCE_RECORD)
        self.assertEqual(selections[0].object_id, "IK345_F.ab1")

    def test_base_click_selection_updates_selected_base_inspector(self) -> None:
        read = _read("IK345_F.ab1", "ATGC")
        viewer = ChromatogramViewer((read,), title="Chromatograms")

        selected = viewer.select_base_at(read.base_positions[2], 20)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.read_id, "IK345_F.ab1")
        self.assertEqual(selected.base, "G")
        self.assertEqual(selected.raw_index, 2)
        self.assertIn("Base: G", viewer._inspector_panel.text())
        self.assertIn("Length: 4", viewer._inspector_panel.text())
        self.assertIn("Mean Q: 35.0", viewer._inspector_panel.text())
        self.assertIn("Raw index (0-based): 2", viewer._inspector_panel.text())

    def test_read_selection_updates_selected_base_panel_without_base(self) -> None:
        viewer = ChromatogramViewer((_read("IK345_F.ab1", "ATGC"),), title="Chromatograms")

        viewer.select_read("IK345_F.ab1")

        self.assertIn("Sample: IK345_F.ab1", viewer._inspector_panel.text())
        self.assertIn("Length: 4", viewer._inspector_panel.text())
        self.assertIn("Base: —", viewer._inspector_panel.text())

    def test_chromatogram_sequence_record_selection_is_not_duplicated_in_right_inspector(self) -> None:
        state = AppState()
        inspector = InspectorPanel(state)
        viewer = ChromatogramViewer((_read("IK345_F.ab1", "ATGC"),), title="Chromatograms")
        viewer.selection_changed.connect(state.set_selected_item)

        viewer.select_read("IK345_F.ab1")
        self.application.processEvents()

        state.set_active_viewer(viewer)
        self.application.processEvents()

        self.assertFalse(inspector.isVisible())
        self.assertEqual(inspector._title.text(), "")
        self.assertNotEqual(inspector._title.text(), "Sequence Record")

    def test_dataset_with_sanger_references_opens_chromatogram_viewer(self) -> None:
        read = _read("IK345_F.ab1", "ATGC")
        dataset = SequenceDataset(
            dataset_id="ab1-trimmed",
            name="AB1 Trimmed",
            source_type=SourceType.AB1_TRIMMED,
            records=(
                SequenceRecord(
                    sequence_id="IK345_F",
                    sequence=read.trimmed_sequence,
                    source_reference=read,
                ),
            ),
        )
        project = Project.create("project-1", "Project 1").add_dataset(dataset)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        main_window = QMainWindow()
        view.dock_manager.attach_main_window(main_window)
        toolbar = QToolBar()
        view.action_manager.attach_toolbar(toolbar)

        controller.open_project(project)
        self.application.processEvents()
        explorer = view.widget(0)
        tabs = view.widget(1)
        explorer.setCurrentItem(explorer.topLevelItem(0).child(0).child(0))
        self.application.processEvents()

        self.assertTrue(has_chromatogram_sources(dataset))
        self.assertEqual(reads_from_dataset(dataset), (read,))
        action = view.action_manager.action("dataset.open_chromatogram_viewer")
        self.assertIsNotNone(action)
        self.assertTrue(action.isEnabled())
        action.trigger()
        self.application.processEvents()

        self.assertIsInstance(tabs.widget(3), ChromatogramViewer)
        self.assertEqual(tabs.tabText(3), "Chromatograms: AB1 Trimmed")
        self.assertEqual(
            view.tab_manager.viewer_ids(),
            ("dataset-viewer-ab1-trimmed", "chromatogram-viewer-ab1-trimmed"),
        )

    def test_chromatogram_viewer_actions_are_connection_points(self) -> None:
        viewer = ChromatogramViewer((_read("IK345_F.ab1", "ATGC"),), title="Chromatograms")
        provider = viewer.action_providers[0]
        actions = provider.actions_for(viewer)
        action_ids = tuple(action.action_id for action in actions)

        self.assertEqual(
            action_ids,
            (
                "chromatogram.toggle_trim_region",
                "chromatogram.open_sequence_editor",
                "chromatogram.build_consensus",
                "chromatogram.open_quality_report",
                "chromatogram.align",
            ),
        )
        self.assertFalse(viewer.show_trim_region)
        actions[0].callback()
        self.assertTrue(viewer.show_trim_region)
        self.assertFalse(actions[1].enabled)
        self.assertFalse(actions[2].enabled)
        self.assertFalse(actions[3].enabled)
        self.assertFalse(actions[4].enabled)
        viewer.start_paint_profile()
        snapshot = viewer.stop_paint_profile()

        self.assertEqual(snapshot["paint_calls"], 0)
        self.assertEqual(snapshot["paint_calls"], 0)

    def test_chromatogram_dev_profile_actions_are_not_registered_on_toolbar(self) -> None:
        state = AppState()
        manager = ActionManager(state)
        toolbar = QToolBar()
        viewer = ChromatogramViewer((_read("IK345_F.ab1", "ATGC"),), title="Chromatograms")

        manager.attach_toolbar(toolbar)
        state.set_active_viewer(viewer)
        self.application.processEvents()

        start_action = manager.action("chromatogram.dev_start_paint_profile")
        stop_action = manager.action("chromatogram.dev_stop_paint_profile")
        self.assertIsNone(start_action)
        self.assertIsNone(stop_action)
        self.assertNotIn("Dev: Start Paint Profile", [action.text() for action in toolbar.actions()])
        self.assertNotIn("Dev: Stop Paint Profile", [action.text() for action in toolbar.actions()])

    def test_chromatogram_dev_profile_buttons_are_not_present_inside_viewer(self) -> None:
        viewer = ChromatogramViewer((_read("IK345_F.ab1", "ATGC"),), title="Chromatograms")

        self.assertFalse(hasattr(viewer, "_dev_profile_panel"))
        self.assertTrue(callable(viewer.start_paint_profile))
        self.assertTrue(callable(viewer.stop_paint_profile))

    def test_quality_report_viewer_uses_existing_read_quality_metrics(self) -> None:
        viewer = ChromatogramViewer(
            (_read_with_quality("IK345_F.ab1", "ATGC", [35, 35, 10, 10]),),
            title="Chromatograms",
        )

        quality_viewer = QualityReportViewer(viewer.read_views)
        quality_viewer.select_by_hq_threshold(60)

        self.assertEqual(quality_viewer._table.item(0, 1).text(), "IK345_F.ab1")
        self.assertEqual(quality_viewer._table.item(0, 3).text(), "22.5")
        self.assertEqual(quality_viewer.selected_read_ids(), ())

    def test_alignment_chromatogram_viewer_maps_alignment_column_to_trace(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK346_F.ab1", "ATGT"))
        alignment = _alignment(
            (
                ("IK345_F.ab1", "ATGC"),
                ("IK346_F.ab1", "ATGT"),
            )
        )

        viewer = AlignmentChromatogramViewer(reads, alignment=alignment)
        selected = viewer.select_alignment_cell(0, 2)

        self.assertEqual(viewer.viewer_kind, "alignment-chromatogram")
        self.assertEqual(viewer.viewer_title, "Align Chromatograms")
        self.assertIsNotNone(viewer._canvas_widget)
        self.assertEqual(viewer.consensus, "ATGC")
        self.assertEqual(viewer.alignment_column_to_trace_position("IK345_F.ab1", 3), reads[0].trimmed_base_positions[2])
        self.assertEqual(selected[0], "IK345_F.ab1")
        self.assertEqual(selected[1], 3)
        self.assertEqual(selected[2], "G")
        self.assertEqual(viewer.selected_cell, ("IK345_F.ab1", 3))
        self.assertEqual(viewer._selected_trace_position, reads[0].trimmed_base_positions[2])

    def test_alignment_chromatogram_viewer_uses_alignment_columns_and_gap_space(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK346_F.ab1", "ATTC"))
        alignment = _alignment(
            (
                ("IK345_F.ab1", "AT-GC"),
                ("IK346_F.ab1", "ATTGC"),
            )
        )
        viewer = AlignmentChromatogramViewer(reads, alignment=alignment)

        self.assertEqual(_alignment_column_x(1), NAME_WIDTH)
        self.assertEqual(_alignment_column_x(4), NAME_WIDTH + 3 * BASE_WIDTH)
        self.assertIsNone(viewer.alignment_column_to_trace_position("IK345_F.ab1", 3))

        trace = tuple(reads[0].trimmed_traces["A"])
        segments = _trace_segments(
            viewer.maps["IK345_F.ab1"],
            trace,
            first_col=1,
            last_col=5,
        )

        self.assertEqual(len(segments), 2)
        self.assertEqual(tuple(point[0] for point in segments[0]), (1, 2))
        self.assertEqual(tuple(point[0] for point in segments[1]), (4, 5))

    def test_alignment_chromatogram_viewer_draws_raw_peak_to_peak_trace_samples(self) -> None:
        mapping = {1: 25, 2: 50, 3: None, 4: 75, 5: 100}
        trace = tuple(range(140))

        segments = _peak_to_peak_trace_segments(
            mapping,
            trace,
            first_col=1,
            last_col=5,
        )

        self.assertEqual(len(segments), 2)
        self.assertEqual(len(segments[0]), 26)
        self.assertEqual(len(segments[1]), 26)
        self.assertEqual(segments[0][0].trace_position, 25)
        self.assertEqual(segments[0][-1].trace_position, 50)
        self.assertEqual(segments[1][0].trace_position, 75)
        self.assertEqual(segments[1][-1].trace_position, 100)
        self.assertEqual(segments[0][0].x, _alignment_column_x(1))
        self.assertEqual(segments[0][-1].x, _alignment_column_x(2))
        self.assertEqual(segments[1][0].x, _alignment_column_x(4))
        self.assertEqual(segments[1][-1].x, _alignment_column_x(5))

    def test_alignment_chromatogram_viewer_uses_compact_review_layout(self) -> None:
        self.assertLess(NAME_WIDTH, 180)
        self.assertLess(BASE_WIDTH, 28)
        self.assertLess(ROW_HEIGHT, 180)

    def test_alignment_chromatogram_viewer_uses_qpainter_path_for_raw_trace_samples(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"),)
        alignment = _alignment((("IK345_F.ab1", "ATGC"),))
        viewer = AlignmentChromatogramViewer(reads, alignment=alignment)
        trace = tuple(reads[0].trimmed_traces["A"])
        segment = _peak_to_peak_trace_segments(
            viewer.maps["IK345_F.ab1"],
            trace,
            first_col=1,
            last_col=2,
        )[0]

        path = _raw_trace_path(segment, x_offset=0, y_base=100)

        self.assertEqual(path.elementCount(), len(segment))
        self.assertGreater(path.elementCount(), 2)

    def test_alignment_chromatogram_viewer_uses_lower_trace_gain_without_changing_mapping(self) -> None:
        mapping = {1: 10, 2: 20}
        trace = tuple(range(30))

        segment = _peak_to_peak_trace_segments(mapping, trace, first_col=1, last_col=2)[0]
        path = _raw_trace_path(segment, x_offset=0, y_base=100)

        self.assertEqual(ALIGNMENT_TRACE_GAIN, 0.022)
        self.assertEqual(segment[0].trace_position, 10)
        self.assertEqual(segment[-1].trace_position, 20)
        self.assertAlmostEqual(path.elementAt(0).y, 100 - 10 * ALIGNMENT_TRACE_GAIN)

    def test_alignment_chromatogram_column_click_recenters_horizontal_scroll(self) -> None:
        sequence = "ATGC" * 20
        reads = (_read("IK345_F.ab1", sequence),)
        alignment = _alignment((("IK345_F.ab1", sequence),))
        viewer = AlignmentChromatogramViewer(reads, alignment=alignment)
        viewer._canvas_widget.setFixedSize(360, 260)
        viewer.refresh()

        selected = viewer.select_alignment_cell(0, 49)

        plot_width = viewer._canvas_widget.width() - NAME_WIDTH
        expected = max(0, int((50 - 1) * BASE_WIDTH - plot_width / 2))
        self.assertEqual(selected[1], 50)
        self.assertEqual(viewer._x_offset, expected)
        viewport_x = viewer._canvas_widget._viewport_x_for_column(50)
        self.assertAlmostEqual(viewport_x, NAME_WIDTH + plot_width / 2, delta=BASE_WIDTH)
        self.assertEqual(viewer.selected_cell, ("IK345_F.ab1", 50))

    def test_alignment_chromatogram_gap_click_highlights_without_trace_mapping(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"),)
        alignment = _alignment((("IK345_F.ab1", "AT-GC"),))
        viewer = AlignmentChromatogramViewer(reads, alignment=alignment)

        selected = viewer.select_alignment_cell(0, 2)

        self.assertEqual(selected[1], 3)
        self.assertEqual(selected[2], "-")
        self.assertIsNone(selected[3])
        self.assertEqual(viewer.selected_cell, ("IK345_F.ab1", 3))
        self.assertIn("Base: GAP", viewer._status.text())
        self.assertIn("Trim trace position: —", viewer._status.text())

    def test_alignment_chromatogram_viewer_syncs_trace_position_back_to_alignment(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK346_F.ab1", "ATGT"))
        alignment = _alignment(
            (
                ("IK345_F.ab1", "ATGC"),
                ("IK346_F.ab1", "ATGT"),
            )
        )
        viewer = AlignmentChromatogramViewer(reads, alignment=alignment)

        selected = viewer.select_trace_position("IK345_F.ab1", reads[0].trimmed_base_positions[1])

        self.assertEqual(viewer.selected_cell, ("IK345_F.ab1", 2))
        self.assertEqual(selected[1], 2)
        self.assertEqual(selected[2], "T")

    def test_alignment_chromatogram_viewer_toolbar_actions_delegate_to_chromatogram_workflow(self) -> None:
        viewer = AlignmentChromatogramViewer(
            (_read("IK345_F.ab1", "ATGC"),),
            alignment=_alignment((("IK345_F.ab1", "ATGC"),)),
        )
        provider = viewer.action_providers[0]
        actions = provider.actions_for(viewer)
        action_ids = tuple(action.action_id for action in actions)

        self.assertEqual(
            action_ids,
            (
                "alignment_chromatogram.toggle_trim_region",
                "alignment_chromatogram.toggle_quality",
                "alignment_chromatogram.open_quality_report",
                "alignment_chromatogram.review_consensus",
            ),
        )
        self.assertFalse(actions[3].enabled)
        self.assertFalse(viewer.show_trim_region)
        actions[0].callback()
        self.assertTrue(viewer.show_trim_region)
        self.assertTrue(viewer.show_quality)
        actions[1].callback()
        self.assertFalse(viewer.show_quality)

    def test_alignment_chromatogram_viewer_adapts_quality_to_alignment_columns(self) -> None:
        reads = (
            _read_with_quality("IK345_F.ab1", "A", [35]),
        )
        alignment = _alignment(
            (
                ("IK345_F.ab1", "----A"),
            )
        )

        viewer = AlignmentChromatogramViewer(reads, alignment=alignment)

        self.assertEqual(viewer.consensus, "----A")
        self.assertEqual(viewer._confidence[-1], 100.0)
        self.assertEqual(viewer._consensus_warning, "")

    def test_alignment_chromatogram_quality_uses_mapped_base_and_gap_has_no_quality(self) -> None:
        raw_read = _read_untrimmed("IK345_F.ab1", "AT")
        raw_read.quality = [12, 39]
        alignment_read = _read("IK345_F.ab1", "ATGC")
        alignment = _alignment((("IK345_F.ab1", "AT-GC"),))
        viewer = AlignmentChromatogramViewer((alignment_read,), alignment=alignment)

        mapping = viewer.maps["IK345_F.ab1"]
        self.assertEqual(_quality_for_trace_position(raw_read, raw_read.base_positions[0]), 12)
        self.assertIsNone(mapping[3])
        self.assertEqual(_quality_for_trace_position(raw_read, raw_read.base_positions[1]), 39)

    def test_dataset_viewer_actions_open_quality_and_alignment_tabs(self) -> None:
        read = _read("IK345_F.ab1", "ATGC")
        dataset = SequenceDataset(
            dataset_id="ab1-trimmed",
            name="AB1 Trimmed",
            source_type=SourceType.AB1_TRIMMED,
            records=(
                SequenceRecord(
                    sequence_id="IK345_F",
                    sequence=read.trimmed_sequence,
                    source_reference=read,
                ),
            ),
        )
        project = Project.create("project-1", "Project 1").add_dataset(dataset)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        main_window = QMainWindow()
        view.dock_manager.attach_main_window(main_window)
        toolbar = QToolBar()
        view.action_manager.attach_toolbar(toolbar)

        controller.open_project(project)
        self.application.processEvents()
        explorer = view.widget(0)
        tabs = view.widget(1)
        explorer.setCurrentItem(explorer.topLevelItem(0).child(0).child(0))
        self.application.processEvents()

        quality_action = view.action_manager.action("dataset.open_quality_report")
        self.assertIsNotNone(quality_action)
        self.assertTrue(quality_action.isEnabled())
        quality_action.trigger()
        self.application.processEvents()

        self.assertIsInstance(view.dock_manager._quality_dock, QualityReportDock)
        self.assertFalse(view.dock_manager._quality_dock.isHidden())

        tabs.setCurrentIndex(2)
        self.application.processEvents()
        chromatogram_action = view.action_manager.action("dataset.open_chromatogram_viewer")
        self.assertIsNotNone(chromatogram_action)
        chromatogram_action.trigger()
        self.application.processEvents()

        tabs.setCurrentIndex(3)
        self.application.processEvents()
        with patch(
            "controllers.project_controller.align_reads",
            return_value=_alignment((("IK345_F.ab1", "ATGC"),)),
        ), patch(
            "controllers.project_controller.AlignmentSettingsDialog.exec",
            return_value=QDialog.DialogCode.Accepted,
        ):
            alignment_action = view.action_manager.action("chromatogram.align")
            self.assertIsNotNone(alignment_action)
            self.assertTrue(alignment_action.isEnabled())
            alignment_action.trigger()
            self.application.processEvents()

        self.assertIsInstance(tabs.widget(4), AlignmentViewer)
        self.assertIsNotNone(state.project)
        self.assertEqual(state.project.dataset_ids, ("ab1-trimmed", "ab1-trimmed_alignment"))

    def test_fixed_toolbar_chromatogram_opens_source_sequence_editor(self) -> None:
        read = _read("IK345_F.ab1", "ATGC")
        dataset = SequenceDataset(
            dataset_id="ab1-source",
            name="AB1 source",
            source_type=SourceType.AB1_TRIMMED,
            records=(
                SequenceRecord(
                    sequence_id="IK345_F",
                    sequence=read.trimmed_sequence,
                    source_reference=read,
                ),
            ),
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        toolbar = QToolBar()
        view.action_manager.attach_toolbar(toolbar)
        controller.open_project(Project.create("project-source", "Source").add_dataset(dataset))
        self.application.processEvents()

        explorer = view.widget(0)
        explorer.setCurrentItem(explorer.topLevelItem(0).child(0).child(0))
        self.application.processEvents()
        view.action_manager.action("dataset.open_chromatogram_viewer").trigger()
        self.application.processEvents()

        fixed = view.action_manager._fixed_actions["sequence_editor"]
        self.assertTrue(fixed.isEnabled())
        fixed.trigger()
        self.application.processEvents()

        tabs = view.widget(1)
        self.assertIsInstance(tabs.currentWidget(), SequenceEditor)

    def test_project_controller_opens_ab1_folder_with_existing_core_reader(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        tabs = view.widget(1)

        with TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            (folder / "IK345_F.ab1").write_bytes(b"fake-ab1")
            (folder / "IK346_F.ab1").write_bytes(b"fake-ab1")

            with patch(
                "controllers.project_controller.read_ab1",
                side_effect=[
                    _read_untrimmed("IK345_F.ab1", "ATGC"),
                    _read_untrimmed("IK346_F.ab1", "ATGT"),
                ],
            ):
                tab_name = controller.open_ab1_folder(str(folder))

        self.application.processEvents()

        self.assertTrue(tab_name.startswith("chromatogram-viewer-"))
        self.assertIsInstance(tabs.widget(2), ChromatogramViewer)
        self.assertEqual(tabs.tabText(2), f"Chromatograms: {Path(temporary_directory).name}")
        self.assertEqual(len(tabs.widget(2).read_views), 2)


def _read(filename: str, sequence: str) -> SangerRead:
    return trim_sequence(_read_untrimmed(filename, sequence))


def _read_with_quality(filename: str, sequence: str, quality: list[int]) -> SangerRead:
    read = _read_untrimmed(filename, sequence)
    read.quality = quality
    read.average_quality = sum(quality) / len(quality)
    return trim_sequence(read)


def _read_untrimmed(filename: str, sequence: str) -> SangerRead:
    trace_length = max(40, len(sequence) * 10)
    traces = {
        "A": [10 + (index % 7) for index in range(trace_length)],
        "C": [8 + (index % 5) for index in range(trace_length)],
        "G": [7 + (index % 3) for index in range(trace_length)],
        "T": [9 + (index % 4) for index in range(trace_length)],
    }
    base_positions = [5 + index * 8 for index in range(len(sequence))]
    return SangerRead(
        filename=filename,
        sequence=sequence,
        quality=[35 for _ in sequence],
        traces=traces,
        base_positions=base_positions,
        average_quality=35.0,
    )


class _AlignmentRecord:
    def __init__(self, record_id: str, sequence: str) -> None:
        self.id = record_id
        self.seq = sequence


def _alignment(records: tuple[tuple[str, str], ...]) -> tuple[_AlignmentRecord, ...]:
    return tuple(_AlignmentRecord(record_id, sequence) for record_id, sequence in records)


class _wheel_event:
    def __init__(self, *, vertical_delta: int = 0, horizontal_delta: int = 0, control: bool = False) -> None:
        self._vertical_delta = vertical_delta
        self._horizontal_delta = horizontal_delta
        self._control = control
        self.accepted = False

    def angleDelta(self):
        return _delta(self._horizontal_delta, self._vertical_delta)

    def pixelDelta(self):
        return _delta(0, 0)

    def modifiers(self):
        return Qt.KeyboardModifier.ControlModifier if self._control else Qt.KeyboardModifier.NoModifier

    def accept(self):
        self.accepted = True


class _delta:
    def __init__(self, x: int, y: int) -> None:
        self._x = x
        self._y = y

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y
