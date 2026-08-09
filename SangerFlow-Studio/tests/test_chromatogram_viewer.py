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

from app.app_state import AppState
from app.action_manager import ActionManager
from app.selection import SelectionKind
from controllers.project_controller import ProjectController
from core.models import SangerRead
from core.project import Project
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from core.trimming import trim_sequence
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGraphicsView, QMainWindow, QToolBar
from app.read_visibility import ReadVisibilityManager
from views.project_view import ProjectView
from widgets.viewers.viewer_context import ViewerContext
from widgets.viewers.chromatogram_viewer import (
    ChromatogramViewer,
    has_chromatogram_sources,
    reads_from_dataset,
)
from widgets.viewers.alignment_chromatogram_viewer import (
    BASE_WIDTH,
    LOCAL_TRACE_WINDOW,
    NAME_WIDTH,
    AlignmentChromatogramViewer,
    _alignment_column_x,
    _local_trace_segments,
    _smoothed_trace_path,
    _trace_segments,
)
from widgets.viewers.alignment_viewer import AlignmentViewer
from widgets.viewers.quality_report_viewer import QualityReportViewer
from widgets.quality_report_dock import QualityReportDock
from widgets.inspector_panel import InspectorPanel


class ChromatogramViewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = QApplication.instance() or QApplication([])

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
        events = []
        viewer.open_related_requested.connect(events.append)

        self.assertEqual(
            action_ids,
            (
                "chromatogram.toggle_trim_region",
                "chromatogram.export",
                "chromatogram.run_blast",
                "chromatogram.build_consensus",
                "chromatogram.open_quality_report",
                "chromatogram.align",
                "chromatogram.dev_start_paint_profile",
                "chromatogram.dev_stop_paint_profile",
            ),
        )
        self.assertFalse(viewer.show_trim_region)
        actions[0].callback()
        self.assertTrue(viewer.show_trim_region)
        actions[2].callback()
        actions[3].callback()
        with patch("builtins.print") as print_mock:
            actions[-2].callback()
            snapshot = actions[-1].callback()

        self.assertEqual(events[0]["action"], "BLAST")
        self.assertEqual(events[1]["action"], "CONSENSUS")
        self.assertEqual(snapshot["paint_calls"], 0)
        printed_text = "\n".join(str(call.args[0]) for call in print_mock.call_args_list)
        self.assertIn("[PROFILE] started", printed_text)
        self.assertIn("=== Chromatogram Paint Profile ===", printed_text)
        self.assertIn("dominant section:", printed_text)

    def test_chromatogram_dev_profile_actions_are_registered_on_toolbar(self) -> None:
        state = AppState()
        manager = ActionManager(state)
        toolbar = QToolBar()
        viewer = ChromatogramViewer((_read("IK345_F.ab1", "ATGC"),), title="Chromatograms")

        manager.attach_toolbar(toolbar)
        state.set_active_viewer(viewer)
        self.application.processEvents()

        start_action = manager.action("chromatogram.dev_start_paint_profile")
        stop_action = manager.action("chromatogram.dev_stop_paint_profile")
        self.assertIsNotNone(start_action)
        self.assertIsNotNone(stop_action)
        self.assertIn("Dev: Start Paint Profile", [action.text() for action in toolbar.actions()])
        self.assertIn("Dev: Stop Paint Profile", [action.text() for action in toolbar.actions()])

        with patch("builtins.print") as print_mock:
            start_action.trigger()
            stop_action.trigger()

        printed_text = "\n".join(str(call.args[0]) for call in print_mock.call_args_list)
        self.assertIn("[PROFILE] started", printed_text)
        self.assertIn("=== Chromatogram Paint Profile ===", printed_text)
        self.assertIn("[PROFILE] stopped", printed_text)

    def test_chromatogram_dev_profile_buttons_are_available_inside_viewer(self) -> None:
        viewer = ChromatogramViewer((_read("IK345_F.ab1", "ATGC"),), title="Chromatograms")

        self.assertFalse(viewer._dev_profile_panel.isHidden())
        self.assertEqual(viewer._dev_start_profile_button.text(), "Start Paint Profile")
        self.assertEqual(viewer._dev_stop_profile_button.text(), "Stop Paint Profile")

        with patch("builtins.print") as print_mock:
            viewer._dev_start_profile_button.click()
            viewer._dev_stop_profile_button.click()

        printed_text = "\n".join(str(call.args[0]) for call in print_mock.call_args_list)
        self.assertIn("[PROFILE] started", printed_text)
        self.assertIn("=== Chromatogram Paint Profile ===", printed_text)
        self.assertIn("[PROFILE] stopped", printed_text)

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

    def test_alignment_chromatogram_viewer_draws_local_trace_around_each_peak(self) -> None:
        mapping = {1: 25, 2: 50, 3: None, 4: 75, 5: 100}
        trace = tuple(range(140))

        segments = _local_trace_segments(
            mapping,
            trace,
            first_col=1,
            last_col=5,
        )

        self.assertEqual(LOCAL_TRACE_WINDOW, 20)
        self.assertEqual(len(segments), 4)
        self.assertGreater(len(segments[0]), 2)
        self.assertGreater(len(segments[1]), 2)
        self.assertGreater(len(segments[2]), 2)
        self.assertGreater(len(segments[3]), 2)
        self.assertEqual(
            tuple({point.alignment_column for point in segment} for segment in segments),
            ({1}, {2}, {4}, {5}),
        )
        self.assertGreaterEqual(
            len([point for point in segments[0] if point.alignment_column == 1]),
            LOCAL_TRACE_WINDOW + 1,
        )
        for left, right in zip(segments, segments[1:]):
            self.assertLess(left[-1].x, _alignment_column_x(left[-1].alignment_column) + BASE_WIDTH / 2)
            self.assertGreater(right[0].x, _alignment_column_x(right[0].alignment_column) - BASE_WIDTH / 2)

    def test_alignment_chromatogram_viewer_uses_smoothed_qpainter_path(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"),)
        alignment = _alignment((("IK345_F.ab1", "ATGC"),))
        viewer = AlignmentChromatogramViewer(reads, alignment=alignment)
        trace = tuple(reads[0].trimmed_traces["A"])
        segment = _local_trace_segments(
            viewer.maps["IK345_F.ab1"],
            trace,
            first_col=1,
            last_col=2,
        )[0]

        path = _smoothed_trace_path(segment, x_offset=0, y_base=100)

        element_types = tuple(path.elementAt(index).type for index in range(path.elementCount()))
        self.assertIn(path.ElementType.CurveToElement, element_types)

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
                "alignment_chromatogram.align",
                "alignment_chromatogram.toggle_trim_region",
                "alignment_chromatogram.open_quality_report",
                "alignment_chromatogram.build_consensus",
                "alignment_chromatogram.export",
                "alignment_chromatogram.run_blast",
            ),
        )
        self.assertFalse(viewer.show_trim_region)
        actions[1].callback()
        self.assertTrue(viewer.show_trim_region)

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
        ):
            alignment_action = view.action_manager.action("chromatogram.align")
            self.assertIsNotNone(alignment_action)
            self.assertTrue(alignment_action.isEnabled())
            alignment_action.trigger()
            self.application.processEvents()

        self.assertIsInstance(tabs.widget(4), AlignmentViewer)
        self.assertIsNotNone(state.project)
        self.assertEqual(state.project.dataset_ids, ("ab1-trimmed", "ab1-trimmed_alignment"))

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
