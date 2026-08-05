"""Application-layer callback registry for dataset opening routes.

The registry stores opaque callbacks only.  It intentionally imports no
viewer, GUI toolkit, aligner, or analysis module.
"""

from __future__ import annotations

from typing import Callable

from core.dataset_open_router import DatasetOpenCallback, DatasetOpenRouter
from core.sequence_dataset import SequenceDataset, SourceType


class DatasetViewerRegistry:
    """Manage one explicit open callback for each ``SourceType``."""

    def __init__(self) -> None:
        self._callbacks: dict[SourceType, DatasetOpenCallback] = {}

    def register(self, source_type: SourceType, callback: DatasetOpenCallback) -> None:
        """Register a callback, rejecting accidental replacement."""

        self._validate_source_type(source_type)
        if not callable(callback):
            raise ValueError("callback must be callable")
        if source_type in self._callbacks:
            raise ValueError(f"callback already registered for source type: {source_type.value}")
        self._callbacks[source_type] = callback

    def unregister(self, source_type: SourceType) -> None:
        """Remove a registration; unknown source types are a no-op."""

        self._validate_source_type(source_type)
        self._callbacks.pop(source_type, None)

    def has_callback(self, source_type: SourceType) -> bool:
        self._validate_source_type(source_type)
        return source_type in self._callbacks

    def get_callback(self, source_type: SourceType) -> DatasetOpenCallback:
        """Return one registered callback or raise a clear lookup error."""

        self._validate_source_type(source_type)
        try:
            return self._callbacks[source_type]
        except KeyError as error:
            raise KeyError(f"no callback registered for source type: {source_type.value}") from error

    def register_router(self, router: DatasetOpenRouter) -> None:
        """Copy every current registry entry into a supplied router."""

        if not isinstance(router, DatasetOpenRouter):
            raise ValueError("router must be a DatasetOpenRouter")
        for source_type, callback in self._callbacks.items():
            router.register(source_type, callback)

    @staticmethod
    def _validate_source_type(source_type: SourceType) -> None:
        if not isinstance(source_type, SourceType):
            raise ValueError("source_type must be a SourceType")


AlignmentDatasetCallback = Callable[[SequenceDataset], object]


def register_alignment_dataset_viewer(
    registry: DatasetViewerRegistry,
    alignment_callback: AlignmentDatasetCallback,
) -> None:
    """Register a dataset-level callback for ``IMPORTED_ALIGNMENT`` values.

    The registry/router protocol uses ``DatasetOpenContext``.  This adapter is
    intentionally the small application-layer boundary that exposes only the
    immutable alignment dataset to a future viewer callback.
    """

    if not isinstance(registry, DatasetViewerRegistry):
        raise ValueError("registry must be a DatasetViewerRegistry")
    if not callable(alignment_callback):
        raise ValueError("alignment_callback must be callable")

    def route_alignment_context(context):
        return alignment_callback(context.dataset)

    registry.register(SourceType.IMPORTED_ALIGNMENT, route_alignment_context)


def register_default_dataset_viewers(
    registry: DatasetViewerRegistry,
    *,
    alignment_callback: AlignmentDatasetCallback,
) -> None:
    """Register the currently supported default dataset viewer route.

    Only alignment datasets are supported in this minimal registry connection.
    The callback receives an ``AlignmentViewerInput``, not a raw
    ``SequenceDataset``.  No viewer module is imported or instantiated here.
    """

    if not callable(alignment_callback):
        raise ValueError("alignment_callback must be callable")

    def open_alignment_dataset(dataset: SequenceDataset):
        # Local import preserves the registry's no-GUI import boundary.
        from workflow.alignment_viewer_adapter import create_alignment_viewer_input

        return alignment_callback(create_alignment_viewer_input(dataset))

    register_alignment_dataset_viewer(registry, open_alignment_dataset)
