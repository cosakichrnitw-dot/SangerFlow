"""Application-level state shared by SangerFlow-Studio views and controllers."""

from PySide6.QtCore import QObject, Signal


class AppState(QObject):
    """Own visible application state; core models remain immutable values."""

    project_changed = Signal(object)
    repository_changed = Signal(object)
    selection_changed = Signal(object)
    active_tab_changed = Signal(str)
    active_viewer_changed = Signal(object)
    viewer_opened = Signal(object)
    viewer_closed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._project: object | None = None
        self._repository: object | None = None
        self._loaded_bundle: object | None = None
        self._selected_item: object | None = None
        self._active_tab = "Welcome"
        self._active_viewer: object | None = None

    @property
    def project(self) -> object | None:
        return self._project

    @property
    def current_project(self) -> object | None:
        """The Project currently presented by the Studio shell."""

        return self._project

    @property
    def current_repository(self) -> object | None:
        """The extracted result repository associated with the open bundle."""

        return self._repository

    @property
    def selected_item(self) -> object | None:
        return self._selected_item

    @property
    def active_tab(self) -> str:
        return self._active_tab

    @property
    def active_viewer(self) -> object | None:
        return self._active_viewer

    def set_project(self, project: object | None, repository: object | None = None) -> None:
        """Present a Project value without modifying the immutable core model."""

        self._cleanup_loaded_bundle()
        self._project = project
        self._repository = repository
        self._selected_item = None
        self._active_viewer = None
        self.project_changed.emit(project)
        self.repository_changed.emit(repository)
        self.selection_changed.emit(None)
        self.active_viewer_changed.emit(None)

    def set_loaded_project_bundle(self, bundle: object) -> None:
        """Adopt a loaded bundle and expose its Project and Repository values."""

        project = getattr(bundle, "project", None)
        repository = getattr(bundle, "repository", None)
        if project is None or repository is None:
            raise ValueError("loaded bundle must provide project and repository")
        self._cleanup_loaded_bundle()
        self._loaded_bundle = bundle
        self._project = project
        self._repository = repository
        self._selected_item = None
        self._active_viewer = None
        self.project_changed.emit(project)
        self.repository_changed.emit(repository)
        self.selection_changed.emit(None)
        self.active_viewer_changed.emit(None)

    def close_current_bundle(self) -> None:
        """Release the temporary directory owned by the currently open bundle."""

        self._cleanup_loaded_bundle()
        self._repository = None
        self.repository_changed.emit(None)

    def _cleanup_loaded_bundle(self) -> None:
        bundle = self._loaded_bundle
        self._loaded_bundle = None
        cleanup = getattr(bundle, "cleanup", None)
        if callable(cleanup):
            cleanup()

    def set_selected_item(self, item: object | None) -> None:
        self._selected_item = item
        self.selection_changed.emit(item)

    def set_active_tab(self, tab_name: str) -> None:
        if tab_name != self._active_tab:
            self._active_tab = tab_name
            self.active_tab_changed.emit(tab_name)

    def set_active_viewer(self, viewer: object | None) -> None:
        if viewer is not self._active_viewer:
            self._active_viewer = viewer
            self.active_viewer_changed.emit(viewer)
