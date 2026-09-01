"""Read-only, model-backed Project lineage visualization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QTimer, Qt, Slot
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QTransform
from PySide6.QtWidgets import (
    QGestureEvent,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QMenu,
    QMessageBox,
)

from app.app_state import AppState
from app.icon_registry import studio_icon
from app.selection import SelectionKind, StudioSelection
from core.project import RevisionState


_NODE_WIDTH = 238.0
_NODE_HORIZONTAL_GAP = 84.0
_NODE_VERTICAL_GAP = 42.0
_NODE_PADDING_X = 12.0
_NODE_PADDING_Y = 11.0
_NODE_LINE_GAP = 4.0
_MIN_ZOOM_SCALE = 0.35
_MAX_ZOOM_SCALE = 4.0


@dataclass(frozen=True)
class _NodeGeometry:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class _NodeSpec:
    identifier: str
    depth: int
    lines: tuple[str, ...]
    tooltip: str
    color: QColor
    selection: StudioSelection


@dataclass(frozen=True)
class _EdgeSpec:
    source_identifier: str
    target_identifier: str
    relation_type: str
    edge_kind: str = "scientific"
    display_label: str = ""


class ProjectSummaryGraph(QGraphicsView):
    """Compact lineage overview; detailed metadata remains in the Inspector."""

    def __init__(self, state: AppState, controller: object) -> None:
        super().__init__()
        self._state = state
        self._controller = controller
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        # On macOS, QAbstractScrollArea commonly delivers pinch/native events
        # to its viewport rather than the QGraphicsView wrapper.  Observe both
        # paths: registered QPinchGesture is portable, NativeGesture preserves
        # the native magnify signal where Qt provides it.
        self.viewport().grabGesture(Qt.GestureType.PinchGesture)
        self.viewport().installEventFilter(self)
        self._pinch_total_scale = 1.0
        self._view_history: list[tuple[QTransform, QPointF]] = []
        self._interaction_start: tuple[QTransform, QPointF] | None = None
        self._refresh_pending = False
        # The timer is owned by this graph.  Unlike a static singleShot callback,
        # it is destroyed with the graph and cannot call a deleted QGraphicsView.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self._refresh_from_state_change)
        # Direct QObject-bound slots let Qt remove the connection when this
        # widget is destroyed.  Do not use a receiver-less lambda here.
        state.project_changed.connect(self._on_project_changed)
        state.repository_changed.connect(self._on_repository_changed)
        self.refresh()

    def zoom_in(self) -> None:
        self._apply_zoom_factor(1.2)

    def zoom_out(self) -> None:
        self._apply_zoom_factor(1 / 1.2)

    def _apply_zoom_factor(self, requested_factor: float, *, remember: bool = True) -> bool:
        """Apply a reversible, bounded transform shared by every zoom route."""

        current_scale = abs(float(self.transform().m11()))
        if current_scale <= 0:
            current_scale = 1.0
        target_scale = max(_MIN_ZOOM_SCALE, min(_MAX_ZOOM_SCALE, current_scale * requested_factor))
        factor = target_scale / current_scale
        if abs(factor - 1.0) < 1e-9:
            return False
        if remember:
            self._remember_view_state()
        self.scale(factor, factor)
        return True

    def reset_zoom(self) -> None:
        self._remember_view_state()
        self.resetTransform()

    def fit_all(self) -> None:
        scene = self.scene()
        if scene is None:
            return
        bounds = scene.itemsBoundingRect()
        if not bounds.isNull():
            self._remember_view_state()
            self.fitInView(bounds.adjusted(-24, -24, 24, 24), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_back(self) -> bool:
        if not self._view_history:
            return False
        transform, center = self._view_history.pop()
        self.setTransform(transform)
        self.centerOn(center)
        return True

    def _view_state(self) -> tuple[QTransform, QPointF]:
        return QTransform(self.transform()), self.mapToScene(self.viewport().rect().center())

    def _remember_view_state(self) -> None:
        state = self._view_state()
        if self._view_history and self._view_history[-1] == state:
            return
        self._view_history.append(state)
        del self._view_history[:-16]

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        # Preserve normal trackpad/mouse scrolling.  Ctrl/Command + wheel is
        # the conventional precise zoom gesture; visible controls cover mice.
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            (self.zoom_in if event.angleDelta().y() > 0 else self.zoom_out)()
            event.accept()
            return
        # Trackpads report high-resolution pixel deltas.  QGraphicsView's
        # wheel fallback is not consistently horizontal on macOS, so pan both
        # scroll bars directly while retaining standard mouse-wheel handling.
        pixel_delta = event.pixelDelta()
        if not pixel_delta.isNull():
            self._remember_view_state()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - pixel_delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - pixel_delta.y())
            event.accept()
            return
        super().wheelEvent(event)

    def nativeGestureEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Use macOS pinch gestures for graph zoom without affecting scroll."""

        if self._handle_native_zoom(event):
            return
        super().nativeGestureEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        """Receive trackpad gestures delivered to QGraphicsView's viewport."""

        if watched is self.viewport():
            if event.type() == QEvent.Type.NativeGesture and self._handle_native_zoom(event):
                return True
            if event.type() == QEvent.Type.Gesture and self._handle_pinch_gesture(event):
                return True
        return super().eventFilter(watched, event)

    def _handle_native_zoom(self, event) -> bool:
        if event.gestureType() != Qt.NativeGestureType.ZoomNativeGesture:
            return False
        value = float(event.value())
        if value:
            self._apply_zoom_factor(max(0.5, min(2.0, 1.0 + value)))
        event.accept()
        return True

    def _handle_pinch_gesture(self, event: QGestureEvent) -> bool:
        pinch = event.gesture(Qt.GestureType.PinchGesture)
        if pinch is None:
            return False
        state = pinch.state()
        if state == Qt.GestureState.GestureStarted:
            self._pinch_total_scale = 1.0
            self._remember_view_state()
        total_scale = max(0.01, float(pinch.totalScaleFactor()))
        # totalScaleFactor is cumulative across one gesture.  Applying its
        # delta makes the gesture continuous instead of exponentially scaling
        # on every update event.
        self._apply_zoom_factor(total_scale / self._pinch_total_scale, remember=False)
        self._pinch_total_scale = total_scale
        event.accept(pinch)
        return True

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Offer entity-specific commands only when a formal node was hit."""

        menu = QMenu(self)
        selection = self._selection_for_item(self.itemAt(event.pos()))
        actions: dict[str, object] = {}
        if selection is not None and selection.kind is SelectionKind.DATASET:
            entry = selection.payload
            dataset = getattr(entry, "dataset", None)
            dataset_id = _dataset_id(dataset)
            if dataset_id:
                open_label = (
                    "Open Read Only"
                    if getattr(entry, "revision_state", None) is RevisionState.ARCHIVED
                    else "Open"
                )
                actions["open"] = menu.addAction(studio_icon("sequence_editor"), open_label)
                menu.addSeparator()
                if getattr(entry, "revision_state", None) is RevisionState.ARCHIVED:
                    actions["restore"] = menu.addAction(studio_icon("restore"), "Restore")
                elif self._is_current_dataset_revision(dataset_id):
                    actions["archive"] = menu.addAction(studio_icon("archive"), "Archive")
                actions["delete"] = menu.addAction(studio_icon("delete"), "Delete from Project…")
                menu.addSeparator()
        zoom_in = menu.addAction("Zoom In")
        zoom_out = menu.addAction("Zoom Out")
        fit = menu.addAction("Fit All")
        reset = menu.addAction("Reset Zoom (100%)")
        back = menu.addAction("Zoom Back")
        back.setEnabled(bool(self._view_history))
        selected = menu.exec(event.globalPos())
        if selected is actions.get("open") and selection is not None:
            self._controller.select_item(selection, open_viewer=False)
            self._controller.open_selected_item()
        elif selected is actions.get("archive") and selection is not None:
            self._archive_dataset_entry(selection.payload)
        elif selected is actions.get("restore") and selection is not None:
            self._restore_dataset_entry(selection.payload)
        elif selected is actions.get("delete") and selection is not None:
            self._delete_dataset_entry(selection.payload)
        elif selected is zoom_in:
            self.zoom_in()
        elif selected is zoom_out:
            self.zoom_out()
        elif selected is fit:
            self.fit_all()
        elif selected is reset:
            self.reset_zoom()
        elif selected is back:
            self.zoom_back()

    def _is_current_dataset_revision(self, dataset_id: str) -> bool:
        project = self._state.current_project
        checker = getattr(project, "is_current_revision", None)
        return bool(callable(checker) and checker(dataset_id))

    def _archive_dataset_entry(self, entry: object) -> None:
        method = getattr(self._controller, "archive_logical_dataset", None)
        current_entry = self._current_project_entry(entry)
        logical_id = getattr(current_entry, "logical_id", None)
        if (
            not callable(method)
            or not logical_id
            or getattr(current_entry, "revision_state", None) is not RevisionState.CURRENT
        ):
            return
        try:
            method(logical_id)
        except (KeyError, ValueError) as error:
            QMessageBox.warning(self, "Archive Dataset", str(error))

    def _restore_dataset_entry(self, entry: object) -> None:
        method = getattr(self._controller, "restore_logical_dataset", None)
        current_entry = self._current_project_entry(entry)
        logical_id = getattr(current_entry, "logical_id", None)
        if (
            not callable(method)
            or not logical_id
            or getattr(current_entry, "revision_state", None) is not RevisionState.ARCHIVED
        ):
            return
        try:
            method(logical_id)
        except (KeyError, ValueError) as error:
            QMessageBox.warning(self, "Restore Dataset", str(error))

    def _delete_dataset_entry(self, entry: object) -> None:
        current_entry = self._current_project_entry(entry)
        dataset_id = _dataset_id(getattr(current_entry, "dataset", None))
        if not dataset_id:
            return
        name = str(getattr(current_entry, "display_name", dataset_id))
        dependencies_method = getattr(self._controller, "dataset_delete_dependencies", None)
        try:
            dependencies = tuple(dependencies_method(dataset_id)) if callable(dependencies_method) else ()
        except (KeyError, ValueError):
            return
        if dependencies:
            QMessageBox.information(
                self,
                f"Cannot delete “{name}”.",
                "This dataset is used by:\n" + "\n".join(f"- {value}" for value in dependencies)
                + "\n\nArchive it instead?",
            )
            return
        response = QMessageBox.question(
            self,
            "Delete from Project",
            f"Delete “{name}” from this Project? This only succeeds for a safe leaf Dataset.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        method = getattr(self._controller, "remove_dataset", None)
        if not callable(method):
            return
        try:
            method(dataset_id)
        except (KeyError, ValueError) as error:
            QMessageBox.warning(self, f"Cannot delete “{name}”.", str(error))

    def _current_project_entry(self, entry: object) -> object | None:
        """Resolve a graph node's immutable revision in the current Project.

        Scene nodes retain the entry that existed when the graph was painted.
        Project changes are refreshed asynchronously, so a user can still
        trigger a context action against a stale node.  The immutable dataset
        ID identifies that revision; logical_id is then read from the current
        Project entry for Archive and Restore. Display labels are
        presentation-only and never participate in lifecycle operations.
        """

        dataset_id = _dataset_id(getattr(entry, "dataset", None))
        project = self._state.current_project
        getter = getattr(project, "get_entry", None)
        if not dataset_id or not callable(getter):
            return None
        try:
            return getter(dataset_id)
        except KeyError:
            return None

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._interaction_start = self._view_state()
        item = self.itemAt(event.position().toPoint())
        selection = self._selection_for_item(item)
        if selection is not None:
            self._controller.select_item(selection, open_viewer=False)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().mouseReleaseEvent(event)
        previous = self._interaction_start
        self._interaction_start = None
        if previous is not None and previous != self._view_state():
            self._view_history.append(previous)
            del self._view_history[:-16]

    @Slot(object)
    def _on_project_changed(self, _project: object) -> None:
        self._schedule_refresh()

    @Slot(object)
    def _on_repository_changed(self, _repository: object) -> None:
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        """Coalesce a Project/Repository state update into one scene rebuild."""

        if self._refresh_timer.isActive():
            return
        self._refresh_pending = True
        self._refresh_timer.start()

    @Slot()
    def _refresh_from_state_change(self) -> None:
        self._refresh_pending = False
        self.refresh()

    def refresh(self) -> None:
        scene = self.scene()
        if scene is None:
            return
        # QGraphicsScene owns all items.  Clearing it removes every prior node,
        # text child, and edge before formal Project entries are redrawn.
        scene.clear()
        project = self._state.current_project
        if project is None:
            scene.addText("Open a Project to view its lineage.")
            return

        entries = tuple(getattr(project, "dataset_entries", ()))
        results = tuple(getattr(project, "analysis_results", ()))
        specs: list[_NodeSpec] = []
        for entry in entries:
            dataset = entry.dataset
            dataset_id = _dataset_id(dataset)
            specs.append(
                _NodeSpec(
                    identifier=f"dataset:{dataset_id}",
                    depth=0,
                    lines=_dataset_lines(entry),
                    tooltip=_dataset_tooltip(entry),
                    color=_dataset_color(dataset),
                    selection=StudioSelection.dataset(entry),
                )
            )
        for result in results:
            specs.append(
                _NodeSpec(
                    identifier=f"result:{result.result_id}",
                    depth=0,
                    lines=_result_lines(result, self._state.current_repository),
                    tooltip=_result_tooltip(result),
                    color=QColor("#eef8e7") if _result_available(self._state.current_repository, result.result_id) else QColor("#fff1e5"),
                    selection=StudioSelection.analysis_result(result),
                )
            )

        # Scientific lineage and workspace revision history are intentionally
        # distinct.  The latter is rendered from supersedes_dataset_id only;
        # it never becomes a Project LineageRelation.
        edge_specs = _display_edge_specs(entries, results)
        node_ids = {spec.identifier for spec in specs}
        depths = _layered_depths(node_ids, edge_specs)
        specs = [
            _NodeSpec(
                identifier=spec.identifier,
                depth=depths.get(spec.identifier, 0),
                lines=spec.lines,
                tooltip=spec.tooltip,
                color=spec.color,
                selection=spec.selection,
            )
            for spec in specs
        ]

        specs_by_depth: dict[int, list[_NodeSpec]] = {}
        for spec in specs:
            specs_by_depth.setdefault(spec.depth, []).append(spec)

        # Keep the existing layered DAG, but order each downstream layer by
        # the median vertical rank of its already-placed formal parents.  This
        # small barycentric pass lowers avoidable crossings without inventing
        # or altering any lineage relationship.
        source_order: dict[str, float] = {}
        incoming: dict[str, list[str]] = {}
        for edge in edge_specs:
            incoming.setdefault(edge.target_identifier, []).append(edge.source_identifier)
        for depth in sorted(specs_by_depth):
            column_specs = specs_by_depth[depth]
            original_order = {spec.identifier: index for index, spec in enumerate(column_specs)}
            if depth:
                def sort_key(spec: _NodeSpec) -> tuple[float, int]:
                    parent_orders = sorted(
                        source_order[source]
                        for source in incoming.get(spec.identifier, ())
                        if source in source_order
                    )
                    if not parent_orders:
                        return float(original_order[spec.identifier]), original_order[spec.identifier]
                    return parent_orders[len(parent_orders) // 2], original_order[spec.identifier]
                column_specs.sort(key=sort_key)
            source_order.update(
                {spec.identifier: float(index) for index, spec in enumerate(column_specs)}
            )

        geometries: dict[str, _NodeGeometry] = {}
        for column, column_specs in sorted(specs_by_depth.items()):
            y = 0.0
            x = column * (_NODE_WIDTH + _NODE_HORIZONTAL_GAP)
            for spec in column_specs:
                height = self._node_height(spec.lines)
                geometry = _NodeGeometry(x, y, _NODE_WIDTH, height)
                geometries[spec.identifier] = geometry
                self._add_node(spec, geometry)
                y += height + _NODE_VERTICAL_GAP

        for edge_spec in edge_specs:
            edge_pen = _edge_pen(edge_spec)
            self._add_edge(
                geometries.get(edge_spec.source_identifier),
                geometries.get(edge_spec.target_identifier),
                edge_pen,
                edge_spec,
            )

        bounds = scene.itemsBoundingRect()
        scene.setSceneRect(bounds.adjusted(-48, -48, 48, 48))

    def node_items(self) -> tuple[QGraphicsRectItem, ...]:
        """Expose only formal Project nodes for lightweight regression checks."""

        scene = self.scene()
        if scene is None:
            return ()
        return tuple(
            item
            for item in scene.items()
            if isinstance(item, QGraphicsRectItem) and isinstance(item.data(0), StudioSelection)
        )

    def edge_items(self) -> tuple[QGraphicsLineItem, ...]:
        """Expose formal lineage edges for regression tests and diagnostics."""

        scene = self.scene()
        if scene is None:
            return ()
        return tuple(
            item
            for item in scene.items()
            if isinstance(item, QGraphicsLineItem) and isinstance(item.data(0), _EdgeSpec)
        )

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API
        item = self.itemAt(event.position().toPoint())
        selection = self._selection_for_item(item)
        if selection is not None:
            self._controller.select_item(selection, open_viewer=False)
            self._controller.open_selected_item()
        super().mouseDoubleClickEvent(event)

    def _node_height(self, lines: tuple[str, ...]) -> float:
        regular_metrics = QFontMetrics(self._regular_font())
        title_metrics = QFontMetrics(self._title_font())
        line_heights = [title_metrics.height(), *(regular_metrics.height() for _ in lines[1:])]
        return _NODE_PADDING_Y * 2 + sum(line_heights) + _NODE_LINE_GAP * (len(lines) - 1)

    def _add_node(self, spec: _NodeSpec, geometry: _NodeGeometry) -> None:
        scene = self.scene()
        if scene is None:
            return
        # A GraphicsItem's rect is local geometry.  Keep it at (0, 0) and set
        # the item position separately so child text uses the same node-local
        # coordinate system instead of being stranded near scene origin.
        node = QGraphicsRectItem(0.0, 0.0, geometry.width, geometry.height)
        node.setPos(geometry.x, geometry.y)
        node.setBrush(QBrush(spec.color))
        node.setPen(QPen(QColor("#57708a"), 1.2))
        node.setData(0, spec.selection)
        node.setToolTip(spec.tooltip)
        scene.addItem(node)

        y = _NODE_PADDING_Y
        for index, line in enumerate(spec.lines):
            font = self._title_font() if index == 0 else self._regular_font()
            metrics = QFontMetrics(font)
            text = QGraphicsSimpleTextItem(metrics.elidedText(
                line,
                Qt.TextElideMode.ElideRight,
                int(geometry.width - 2 * _NODE_PADDING_X),
            ), node)
            text.setFont(font)
            text.setPos(_NODE_PADDING_X, y)
            y += metrics.height() + _NODE_LINE_GAP

    def _add_edge(
        self,
        start: _NodeGeometry | None,
        end: _NodeGeometry | None,
        pen: QPen,
        edge_spec: _EdgeSpec,
    ) -> None:
        if start is None or end is None:
            return
        scene = self.scene()
        if scene is None:
            return
        edge = scene.addLine(
            start.x + start.width,
            start.y + start.height / 2,
            end.x,
            end.y + end.height / 2,
            pen,
        )
        edge.setData(0, edge_spec)
        edge.setToolTip(edge_spec.display_label or edge_spec.relation_type)
        # Edges are explicitly behind opaque nodes, never over their text.
        edge.setZValue(-1)
        if edge_spec.display_label:
            label = QGraphicsSimpleTextItem(edge_spec.display_label)
            font = self._regular_font()
            font.setPointSize(max(7, font.pointSize() - 1))
            label.setFont(font)
            label.setBrush(QBrush(QColor("#66737f")))
            label.setPos(
                (start.x + start.width + end.x) / 2 - label.boundingRect().width() / 2,
                (start.y + start.height / 2 + end.y + end.height / 2) / 2 - label.boundingRect().height() - 3,
            )
            label.setZValue(-0.5)
            scene.addItem(label)

    @staticmethod
    def _title_font() -> QFont:
        font = QFont()
        font.setBold(True)
        return font

    @staticmethod
    def _regular_font() -> QFont:
        return QFont()

    @staticmethod
    def _selection_for_item(item: object | None) -> StudioSelection | None:
        while item is not None:
            selection = item.data(0) if hasattr(item, "data") else None
            if isinstance(selection, StudioSelection):
                return selection
            item = item.parentItem() if hasattr(item, "parentItem") else None
        return None


def _dataset_lines(entry: object) -> tuple[str, ...]:
    dataset = entry.dataset
    count = int(getattr(dataset, "sequence_count", 0))
    revision = _revision_summary(entry)
    if hasattr(dataset, "alignment_id"):
        return (entry.display_name, "Alignment" + revision, f"{count} sequences")
    status = _source_status(dataset)
    return (entry.display_name, "Sequence Dataset" + revision, f"{count} records", status)


def _dataset_tooltip(entry: object) -> str:
    dataset = entry.dataset
    return "\n".join((
        entry.display_name,
        _dataset_id(dataset),
        _dataset_type(dataset),
        _source_status(dataset),
    ))


def _result_lines(entry: object, repository: object | None) -> tuple[str, ...]:
    available = _result_available(repository, entry.result_id)
    type_name = str(getattr(entry.result_type, "value", entry.result_type))
    return (
        entry.display_name,
        f"{type_name} Result",
        "● Result available" if available else "○ Result unavailable",
    )


def _result_tooltip(entry: object) -> str:
    return "\n".join((entry.display_name, entry.result_id, str(entry.parent_dataset_id)))


def _dataset_id(dataset: object) -> str:
    return str(getattr(dataset, "dataset_id", None) or getattr(dataset, "alignment_id", ""))


def _dataset_type(dataset: object) -> str:
    source_type = getattr(dataset, "source_type", None)
    return getattr(source_type, "value", "AlignmentDataset")


def _dataset_color(dataset: object) -> QColor:
    """Temporary type differentiation without depending on final icon assets."""

    if hasattr(dataset, "alignment_id"):
        return QColor("#f1e9ff")
    return QColor("#e6f2ff")


def _display_edge_specs(entries: tuple[object, ...], results: tuple[object, ...]) -> tuple[_EdgeSpec, ...]:
    """Build visual-only lineage and revision edges without altering Project data."""

    edges: list[_EdgeSpec] = []
    for entry in entries:
        target = f"dataset:{_dataset_id(entry.dataset)}"
        # Revision descendants inherit their scientific source relations in
        # core, but visually repeating those links makes them look like an
        # independent second MAFFT/derivation.  Their scientific provenance is
        # shown through the first revision, followed by a separate dashed edge.
        if getattr(entry, "supersedes_dataset_id", None):
            continue
        for relation in tuple(getattr(entry, "lineage_relations", ())):
            source_kind = getattr(getattr(relation, "source_kind", None), "value", "")
            source_id = str(getattr(relation, "source_id", ""))
            relation_type = str(getattr(getattr(relation, "relation_type", None), "value", ""))
            if not source_id or source_kind not in {"DATASET", "ANALYSIS_RESULT"}:
                continue
            prefix = "dataset" if source_kind == "DATASET" else "result"
            edges.append(
                _EdgeSpec(
                    f"{prefix}:{source_id}",
                    target,
                    relation_type,
                    display_label=_scientific_edge_label(entry, relation_type),
                )
            )
    for result in results:
        parent_id = str(getattr(result, "parent_dataset_id", ""))
        result_id = str(getattr(result, "result_id", ""))
        if parent_id and result_id:
            edges.append(
                _EdgeSpec(
                    f"dataset:{parent_id}",
                    f"result:{result_id}",
                    "ANALYSIS_RESULT_PARENT",
                )
            )
    for entry in entries:
        predecessor = getattr(entry, "supersedes_dataset_id", None)
        if predecessor:
            edges.append(
                _EdgeSpec(
                    f"dataset:{predecessor}",
                    f"dataset:{_dataset_id(entry.dataset)}",
                    "REVISION",
                    edge_kind="revision",
                    display_label=_revision_edge_label(entry),
                )
            )
    # Preserve Project ordering while ensuring malformed input cannot create
    # duplicated painted edges.
    deduplicated: list[_EdgeSpec] = []
    for edge in edges:
        if edge not in deduplicated:
            deduplicated.append(edge)
    return tuple(deduplicated)


def _revision_summary(entry: object) -> str:
    number = int(getattr(entry, "revision_number", 1))
    state = getattr(getattr(entry, "revision_state", None), "value", "CURRENT")
    if number == 1 and state == "CURRENT":
        return ""
    return f" • r{number} [{state}]"


def _revision_edge_label(entry: object) -> str:
    operation = getattr(getattr(entry, "revision_operation", None), "value", "")
    labels = {
        "ALIGNMENT_EDIT": "edited revision",
        "SEQUENCE_EDIT": "edited revision",
        "RECORD_RENAME": "renamed revision",
        "BATCH_RENAME": "renamed revision",
        "METADATA_MERGE": "metadata revision",
    }
    return labels.get(str(operation), "revision")


def _scientific_edge_label(entry: object, relation_type: str) -> str:
    metadata = {
        **dict(getattr(entry, "metadata", {}) or {}),
        **dict(getattr(getattr(entry, "dataset", None), "metadata", {}) or {}),
    }
    method = str(metadata.get("alignment_method", "")).strip()
    if relation_type == "ALIGNMENT_FROM_DATASET" and method:
        return method
    return ""


def _edge_pen(edge_spec: _EdgeSpec) -> QPen:
    if edge_spec.edge_kind == "revision":
        pen = QPen(QColor("#9aa3ad"), 1.2)
        pen.setStyle(Qt.PenStyle.DashLine)
        return pen
    return QPen(QColor("#8191a1"), 1.3)


def _layered_depths(node_ids: set[str], edges: tuple[_EdgeSpec, ...]) -> dict[str, int]:
    """Longest-source-path layering with a visited set for malformed inputs."""

    sources_by_target: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        if edge.source_identifier in node_ids and edge.target_identifier in node_ids:
            sources_by_target.setdefault(edge.target_identifier, []).append(edge.source_identifier)
    cache: dict[str, int] = {}
    visiting: set[str] = set()

    def depth(node_id: str) -> int:
        if node_id in cache:
            return cache[node_id]
        if node_id in visiting:
            # Project core rejects cycles.  This guard simply keeps a malformed
            # externally supplied value from freezing the GUI.
            return 0
        visiting.add(node_id)
        parents = sources_by_target.get(node_id, ())
        value = 0 if not parents else max(depth(parent) + 1 for parent in parents)
        visiting.remove(node_id)
        cache[node_id] = value
        return value

    return {node_id: depth(node_id) for node_id in node_ids}


def _source_status(dataset: object) -> str:
    if not hasattr(dataset, "source_type"):
        return "○ Chromatogram not applicable"
    records = tuple(getattr(dataset, "records", ()))
    paths = [str(getattr(record, "metadata", {}).get("source_filepath", "")) for record in records]
    paths = [path for path in paths if path]
    if not paths:
        return "○ Chromatogram unavailable"
    return "● Chromatogram linked" if all(Path(path).is_file() for path in paths) else "○ Chromatogram missing"


def _result_available(repository: object | None, result_id: str) -> bool:
    has_result = getattr(repository, "has_result", None)
    return bool(callable(has_result) and has_result(result_id))
