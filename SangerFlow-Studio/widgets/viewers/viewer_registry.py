"""Resolve datasets and analysis results to Studio viewer factories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from widgets.viewers.viewer_context import ViewerContext

ViewerFactory = Callable[[ViewerContext, object], object]


@dataclass(frozen=True)
class ViewerDescriptor:
    """Description of a registered viewer factory."""

    viewer_key: str
    label: str
    factory: ViewerFactory
    default: bool = False


class ViewerRegistry:
    """Application-layer registry for dataset and analysis result viewers."""

    def __init__(self) -> None:
        self._dataset_viewers: dict[object, list[ViewerDescriptor]] = {}
        self._model_viewers: dict[type, list[ViewerDescriptor]] = {}
        self._result_viewers: dict[object, list[ViewerDescriptor]] = {}

    def register_dataset_viewer(
        self,
        source_type: object,
        descriptor: ViewerDescriptor | None = None,
        *,
        viewer_key: str | None = None,
        label: str | None = None,
        factory: ViewerFactory | None = None,
        default: bool = False,
    ) -> None:
        self._register(
            self._dataset_viewers,
            source_type,
            _coerce_descriptor(descriptor, viewer_key, label, factory, default),
        )

    def register_model_viewer(
        self,
        model_type: type,
        descriptor: ViewerDescriptor | None = None,
        *,
        viewer_key: str | None = None,
        label: str | None = None,
        factory: ViewerFactory | None = None,
        default: bool = False,
    ) -> None:
        self._register(
            self._model_viewers,
            model_type,
            _coerce_descriptor(descriptor, viewer_key, label, factory, default),
        )

    def register_result_viewer(
        self,
        result_type: object,
        descriptor: ViewerDescriptor | None = None,
        *,
        viewer_key: str | None = None,
        label: str | None = None,
        factory: ViewerFactory | None = None,
        default: bool = False,
    ) -> None:
        self._register(
            self._result_viewers,
            result_type,
            _coerce_descriptor(descriptor, viewer_key, label, factory, default),
        )

    def dataset_viewers_for(self, dataset: object) -> tuple[ViewerDescriptor, ...]:
        descriptors: list[ViewerDescriptor] = []
        for model_type, values in self._model_viewers.items():
            if isinstance(dataset, model_type):
                descriptors.extend(values)
        descriptors.extend(self._dataset_viewers.get(getattr(dataset, "source_type", None), ()))
        return tuple(descriptors)

    def result_viewers_for(self, result: object) -> tuple[ViewerDescriptor, ...]:
        return tuple(self._result_viewers.get(getattr(result, "result_type", None), ()))

    def viewer_choices_for(self, obj: object) -> tuple[ViewerDescriptor, ...]:
        if hasattr(obj, "source_type") or any(
            isinstance(obj, model_type) for model_type in self._model_viewers
        ):
            return self.dataset_viewers_for(obj)
        if hasattr(obj, "result_type"):
            return self.result_viewers_for(obj)
        return ()

    def default_viewer_for(self, obj: object) -> ViewerDescriptor:
        choices = self.viewer_choices_for(obj)
        if not choices:
            raise LookupError(f"no viewer registered for {type(obj).__name__}")
        for descriptor in choices:
            if descriptor.default:
                return descriptor
        return choices[0]

    def create_viewer_for(self, obj: object, context: ViewerContext) -> object:
        return self.default_viewer_for(obj).factory(context, obj)

    @staticmethod
    def _register(
        target: dict[object, list[ViewerDescriptor]],
        key: object,
        descriptor: ViewerDescriptor,
    ) -> None:
        descriptors = target.setdefault(key, [])
        if any(existing.viewer_key == descriptor.viewer_key for existing in descriptors):
            raise ValueError(f"viewer already registered: {descriptor.viewer_key}")
        if descriptor.default and any(existing.default for existing in descriptors):
            raise ValueError(f"default viewer already registered for {key}")
        descriptors.append(descriptor)


def _coerce_descriptor(
    descriptor: ViewerDescriptor | None,
    viewer_key: str | None,
    label: str | None,
    factory: ViewerFactory | None,
    default: bool,
) -> ViewerDescriptor:
    if descriptor is not None:
        return descriptor
    if not viewer_key or not label or factory is None:
        raise ValueError("viewer_key, label, and factory are required")
    return ViewerDescriptor(
        viewer_key=viewer_key,
        label=label,
        factory=factory,
        default=default,
    )
