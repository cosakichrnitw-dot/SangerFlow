"""Placeholder viewer used to validate Dataset-to-viewer action routing."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout

from widgets.viewers.base_viewer import BaseViewer


class PlaceholderViewer(BaseViewer):
    """Temporary target viewer until scientific viewers are implemented."""

    def __init__(self, *, dataset: object, viewer_kind: str = "placeholder") -> None:
        dataset_id = _dataset_identifier(dataset)
        self._dataset = dataset
        super().__init__(
            viewer_id=f"{viewer_kind}-viewer-{dataset_id}",
            viewer_title=f"Placeholder: {getattr(dataset, 'name', dataset_id)}",
            viewer_kind=viewer_kind,
            source_object_id=dataset_id,
        )
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Placeholder Viewer"))
        layout.addWidget(QLabel(f"Dataset: {getattr(dataset, 'name', dataset_id)}"))
        layout.addWidget(QLabel("Chromatogram Viewer is not implemented yet."))
        layout.addStretch()

    @property
    def dataset(self) -> object:
        return self._dataset


def _dataset_identifier(dataset: object) -> str:
    return (
        getattr(dataset, "dataset_id", None)
        or getattr(dataset, "alignment_id", None)
        or str(id(dataset))
    )
