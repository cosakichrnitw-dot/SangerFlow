"""Right-side metadata inspector for the current Project selection."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton, QSizePolicy, QWidget

from app.app_state import AppState
from app.selection import SelectionKind, StudioSelection
from widgets.metadata_presentation import (
    metadata_summary,
    show_source_filepaths_dialog,
    source_filepaths,
)


class InspectorPanel(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._layout = QFormLayout(self)
        self._title = QLabel("No selection")
        self._layout.addRow(self._title)
        self._suppress_selection = False
        state.active_viewer_changed.connect(self._active_viewer_changed)
        state.selection_changed.connect(self._render_selection)

    def _render_selection(self, selection: object | None) -> None:
        while self._layout.rowCount() > 1:
            self._layout.removeRow(1)
        if self._suppress_selection:
            self._title.setText("")
            return
        selection = _normalize_selection(selection)
        if selection is None:
            self._title.setText("No selection")
            return
        if selection.kind == SelectionKind.DATASET:
            entry = selection.payload
            dataset = entry.dataset
            self._title.setText("Dataset")
            self._add("Name", dataset.name)
            self._add("ID", _dataset_id(dataset))
            self._add("Type", _dataset_type(dataset))
            self._add("Sequence count", str(dataset.sequence_count))
            self._add("Sequence data", "Available")
            self._add("Chromatogram source", _chromatogram_source_status(dataset))
            self._add_metadata(dataset.metadata)
        elif selection.kind == SelectionKind.ANALYSIS_RESULT:
            entry = selection.payload
            self._title.setText("Analysis Result")
            self._add("Name", entry.display_name)
            self._add("ID", entry.result_id)
            self._add("Type", entry.result_type.value)
            self._add("Parent Dataset", entry.parent_dataset_id)
            self._add_metadata(entry.metadata)
        elif selection.kind == SelectionKind.PROJECT:
            project = selection.payload
            self._title.setText("Project")
            self._add("Name", project.name)
            self._add("ID", project.project_id)
            self._add("Dataset count", str(project.dataset_count))
            self._add("Analysis count", str(project.analysis_result_count))
            self._add_metadata(project.metadata)
        elif selection.kind == SelectionKind.VIEWER:
            viewer = selection.payload
            self._title.setText("Viewer")
            self._add("Name", getattr(viewer, "viewer_title", "-"))
            self._add("ID", getattr(viewer, "viewer_id", "-"))
            self._add("Type", getattr(viewer, "viewer_kind", "-"))
        elif selection.kind == SelectionKind.SEQUENCE_RECORD:
            if str(selection.source_viewer_id or "").startswith(
                ("chromatogram-viewer-", "alignment-chromatogram-")
            ):
                self._title.setText("")
                return
            record = selection.payload
            self._title.setText("Sequence Record")
            self._add("ID", getattr(record, "read_id", selection.object_id or "-"))
            self._add("Length", str(getattr(record, "sequence_length", "-")))
            self._add("Mean Q", f"{getattr(record, 'average_quality', 0.0):.1f}")
            self._add("Q20", f"{getattr(record, 'q20_rate', 0.0):.1f}%")
            self._add("Q30", f"{getattr(record, 'q30_rate', 0.0):.1f}%")
            self._add(
                "Trim",
                f"{getattr(record, 'trim_start', '-')}–{getattr(record, 'trim_end', '-')}",
            )
        else:
            self._title.setText("No selection")

    def _add(self, label: str, value: str) -> None:
        widget = QLabel(str(value))
        widget.setWordWrap(True)
        widget.setTextInteractionFlags(
            widget.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        widget.setMinimumWidth(0)
        self._layout.addRow(label, widget)

    def _add_metadata(self, metadata: object) -> None:
        paths = source_filepaths(metadata)
        self._add("Metadata", metadata_summary(metadata))
        if paths:
            button = QPushButton(f"{len(paths)} files  [Show…]", self)
            button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda: show_source_filepaths_dialog(self, paths))
            self._layout.addRow("Source files", button)

    def _active_viewer_changed(self, viewer: object | None) -> None:
        viewer_kind = getattr(viewer, "viewer_kind", "")
        self._suppress_selection = viewer_kind in {"chromatogram", "alignment-chromatogram"}
        self.setVisible(not self._suppress_selection)
        if self._suppress_selection:
            while self._layout.rowCount() > 1:
                self._layout.removeRow(1)
            self._title.setText("")


def _dataset_id(dataset: object) -> str:
    return str(getattr(dataset, "dataset_id", None) or getattr(dataset, "alignment_id", "-"))


def _dataset_type(dataset: object) -> str:
    source_type = getattr(dataset, "source_type", None)
    if source_type is not None:
        return getattr(source_type, "value", str(source_type))
    if hasattr(dataset, "alignment_id"):
        return "AlignmentDataset"
    return type(dataset).__name__


def _chromatogram_source_status(dataset: object) -> str:
    records = tuple(getattr(dataset, "records", ()))
    paths = [str(getattr(record, "metadata", {}).get("source_filepath", "")) for record in records]
    paths = [path for path in paths if path]
    if not paths:
        return "Not Applicable"
    return "Linked" if all(Path(path).is_file() for path in paths) else "Missing"


def _normalize_selection(selection: object | None) -> StudioSelection | None:
    if isinstance(selection, StudioSelection):
        return selection
    if not isinstance(selection, dict):
        return None
    kind = selection.get("kind")
    if kind == "dataset":
        return StudioSelection.dataset(selection["entry"])
    if kind == "analysis_result":
        return StudioSelection.analysis_result(selection["entry"])
    if kind == "project":
        return StudioSelection.project(selection["project"])
    return None
