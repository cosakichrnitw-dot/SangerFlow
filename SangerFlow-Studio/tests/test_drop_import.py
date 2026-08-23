"""External Finder drop classification and MainWindow routing tests."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from PySide6.QtCore import QMimeData, QPoint, QUrl, Qt
from PySide6.QtGui import QDragEnterEvent

from app.drop_import import (
    ExternalDropError,
    ExternalDropKind,
    classify_external_drop_paths,
)
from app.main import build_application


class ExternalDropClassificationTests(unittest.TestCase):
    def test_ab1_folder_is_routed_as_folder(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory) / "reads"
            folder.mkdir()
            (folder / "read.ab1").touch()
            request = classify_external_drop_paths((folder,))
        self.assertEqual(request.kind, ExternalDropKind.AB1_FOLDER)

    def test_folder_without_ab1_is_rejected_before_import(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory) / "not-reads"
            folder.mkdir()
            with self.assertRaisesRegex(ExternalDropError, "does not contain AB1"):
                classify_external_drop_paths((folder,))

    def test_multiple_ab1_files_are_routed_together(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            first = folder / "F.ab1"
            second = folder / "R.abi"
            first.touch()
            second.touch()
            request = classify_external_drop_paths((first, second))
        self.assertEqual(request.kind, ExternalDropKind.AB1_FILES)

    def test_supported_sequence_file_is_routed_to_existing_import(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sequences.fasta"
            path.write_text(">sample\nATGC\n", encoding="utf-8")
            request = classify_external_drop_paths((path,))
        self.assertEqual(request.kind, ExternalDropKind.SEQUENCE_FILE)

    def test_project_bundle_is_routed_to_existing_open_project(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.sangerflow"
            path.touch()
            request = classify_external_drop_paths((path,))
        self.assertEqual(request.kind, ExternalDropKind.PROJECT_BUNDLE)

    def test_unsupported_and_mixed_inputs_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            pdf = folder / "notes.pdf"
            ab1 = folder / "read.ab1"
            fasta = folder / "sequence.fas"
            for path in (pdf, ab1, fasta):
                path.touch()
            with self.assertRaisesRegex(ExternalDropError, "Unsupported file type"):
                classify_external_drop_paths((pdf,))
            with self.assertRaisesRegex(ExternalDropError, "Mixed file types"):
                classify_external_drop_paths((ab1, fasta))


class MainWindowExternalDropTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application, self.window = build_application()
        self.window.show()
        self.application.processEvents()

    def tearDown(self) -> None:
        self.window.close()

    def test_drag_enter_accepts_supported_local_drop_and_shows_feedback(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "read.ab1"
            path.touch()
            mime_data = QMimeData()
            mime_data.setUrls((QUrl.fromLocalFile(str(path)),))
            event = QDragEnterEvent(
                QPoint(10, 10), Qt.DropAction.CopyAction, mime_data,
                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
            )
            self.window.dragEnterEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertTrue(self.window._drop_overlay.isVisible())
        self.window.dragLeaveEvent(event)
        self.assertFalse(self.window._drop_overlay.isVisible())

    def test_drop_routes_multiple_ab1_files_through_controller_and_copy_mode(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "F.ab1"
            second = root / "R.ab1"
            first.touch()
            second.touch()
            request = classify_external_drop_paths((first, second))
            with (
                patch.object(self.window, "_choose_ab1_source_handling", return_value="copy"),
                patch.object(self.window._controller, "open_ab1_files", return_value="tab") as opened,
            ):
                self.window._route_external_drop(request)
        opened.assert_called_once_with((str(first), str(second)), source_file_handling="copy")

    def test_drop_routes_sequence_and_project_to_existing_controller_methods(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fasta = root / "sequence.fas"
            bundle = root / "project.sangerflow"
            fasta.write_text(">sample\nATGC\n", encoding="utf-8")
            bundle.touch()
            with patch.object(self.window, "_open_sequence_file_path") as sequence_opened:
                self.window._route_external_drop(classify_external_drop_paths((fasta,)))
            sequence_opened.assert_called_once_with(str(fasta))
            with (
                patch.object(self.window, "_confirm_discard_or_save", return_value=True),
                patch.object(self.window, "_open_project_bundle_path") as bundle_opened,
            ):
                self.window._route_external_drop(classify_external_drop_paths((bundle,)))
            bundle_opened.assert_called_once_with(str(bundle))
