"""Route an existing sequence dataset to a registered callback.

The router deliberately does not import GUI modules or analysis modules.  It
only classifies an already-created ``SequenceDataset`` by its authoritative
``SourceType`` and passes supplementary structural hints to a callback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from core.sequence_dataset import SequenceDataset, SourceType


class DatasetOpenRouteError(ValueError):
    """Raised when an input cannot be safely routed to an open callback."""


@dataclass(frozen=True)
class DatasetOpenContext:
    """Read-only routing facts derived from one immutable dataset.

    ``source_type`` is the only callback-selection key.  Gap/equal-length
    values and the parser's ``inferred_alignment`` metadata are descriptive
    hints for a future callback; they never override ``source_type``.
    """

    dataset: SequenceDataset
    source_type: SourceType
    has_gaps: bool
    is_equal_length: bool
    inferred_alignment: bool


DatasetOpenCallback = Callable[[DatasetOpenContext], object]


class DatasetOpenRouter:
    """A small callback registry keyed by authoritative ``SourceType``."""

    def __init__(
        self,
        callbacks: Mapping[SourceType, DatasetOpenCallback] | None = None,
        *,
        fallback_callback: Optional[DatasetOpenCallback] = None,
    ) -> None:
        if fallback_callback is not None and not callable(fallback_callback):
            raise ValueError("fallback_callback must be callable or None")
        self._callbacks: dict[SourceType, DatasetOpenCallback] = {}
        self._fallback_callback = fallback_callback
        if callbacks is not None:
            for source_type, callback in callbacks.items():
                self.register(source_type, callback)

    def register(self, source_type: SourceType, callback: DatasetOpenCallback) -> None:
        """Register or replace the callback for one source type."""

        if not isinstance(source_type, SourceType):
            raise ValueError("source_type must be a SourceType")
        if not callable(callback):
            raise ValueError("callback must be callable")
        self._callbacks[source_type] = callback

    def unregister(self, source_type: SourceType) -> None:
        """Remove a callback if present; no error is raised when absent."""

        if not isinstance(source_type, SourceType):
            raise ValueError("source_type must be a SourceType")
        self._callbacks.pop(source_type, None)

    def has_callback(self, source_type: SourceType) -> bool:
        if not isinstance(source_type, SourceType):
            raise ValueError("source_type must be a SourceType")
        return source_type in self._callbacks

    def build_context(self, dataset: SequenceDataset) -> DatasetOpenContext:
        if not isinstance(dataset, SequenceDataset):
            raise DatasetOpenRouteError("dataset must be a SequenceDataset")
        return DatasetOpenContext(
            dataset=dataset,
            source_type=dataset.source_type,
            has_gaps=dataset.has_gaps,
            is_equal_length=dataset.is_equal_length,
            inferred_alignment=dataset.metadata.get("inferred_alignment") is True,
        )

    def open(self, dataset: SequenceDataset) -> object:
        """Build a context and call the matching registered callback.

        A missing source-type callback uses the explicitly configured fallback.
        Without one, the method raises ``DatasetOpenRouteError`` instead of
        importing a viewer, creating a GUI, or guessing an analysis workflow.
        """

        context = self.build_context(dataset)
        callback = self._callbacks.get(context.source_type, self._fallback_callback)
        if callback is None:
            raise DatasetOpenRouteError(
                "no open callback registered for source type: "
                f"{context.source_type.value}"
            )
        return callback(context)
