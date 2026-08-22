"""Application-level state shared by SangerFlow-Studio views and controllers."""

from PySide6.QtCore import QObject, Signal

from app.gui_thread import assert_main_gui_thread


class AppState(QObject):
    """Own visible application state; core models remain immutable values."""

    project_changed = Signal(object)
    repository_changed = Signal(object)
    selection_changed = Signal(object)
    active_tab_changed = Signal(str)
    active_viewer_changed = Signal(object)
    viewer_opened = Signal(object)
    viewer_closed = Signal(str)
    dirty_changed = Signal(bool)
    bundle_path_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._project: object | None = None
        self._repository: object | None = None
        self._loaded_bundle: object | None = None
        self._current_bundle_path: str | None = None
        self._is_dirty = False
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
    def current_bundle_path(self) -> str | None:
        """Path used by Save Project, if the Project was opened or saved."""

        return self._current_bundle_path

    @property
    def is_dirty(self) -> bool:
        """Whether the Project has unsaved membership changes."""

        return self._is_dirty

    @property
    def selected_item(self) -> object | None:
        return self._selected_item

    @property
    def active_tab(self) -> str:
        return self._active_tab

    @property
    def active_viewer(self) -> object | None:
        return self._active_viewer

    def set_project(
        self,
        project: object | None,
        repository: object | None = None,
        *,
        dirty: bool = False,
        bundle_path: str | None = None,
    ) -> None:
        """Present a Project value without modifying the immutable core model."""

        assert_main_gui_thread("AppState.set_project")
        self._cleanup_loaded_bundle()
        self._project = project
        self._repository = repository
        self._current_bundle_path = bundle_path
        self._selected_item = None
        self._active_viewer = None
        self._set_dirty(dirty)
        self.project_changed.emit(project)
        self.repository_changed.emit(repository)
        self.bundle_path_changed.emit(bundle_path)
        self.selection_changed.emit(None)
        self.active_viewer_changed.emit(None)

    def set_loaded_project_bundle(self, bundle: object, *, bundle_path: str | None = None) -> None:
        """Adopt a loaded bundle and expose its Project and Repository values."""

        assert_main_gui_thread("AppState.set_loaded_project_bundle")
        project = getattr(bundle, "project", None)
        repository = getattr(bundle, "repository", None)
        if project is None or repository is None:
            raise ValueError("loaded bundle must provide project and repository")
        self._cleanup_loaded_bundle()
        self._loaded_bundle = bundle
        self._project = project
        self._repository = repository
        self._current_bundle_path = bundle_path
        self._selected_item = None
        self._active_viewer = None
        self._set_dirty(False)
        self.project_changed.emit(project)
        self.repository_changed.emit(repository)
        self.bundle_path_changed.emit(bundle_path)
        self.selection_changed.emit(None)
        self.active_viewer_changed.emit(None)

    def replace_project(self, project: object, *, dirty: bool = True) -> None:
        """Replace the Project value while preserving bundle/repository context."""

        assert_main_gui_thread("AppState.replace_project")
        self._project = project
        self._selected_item = None
        self._set_dirty(dirty)
        self.project_changed.emit(project)
        self.selection_changed.emit(None)

    def set_repository(self, repository: object | None) -> None:
        """Replace the active analysis-result repository without changing Project."""

        assert_main_gui_thread("AppState.set_repository")
        self._repository = repository
        self.repository_changed.emit(repository)

    def close_current_bundle(self) -> None:
        """Release the temporary directory owned by the currently open bundle."""

        assert_main_gui_thread("AppState.close_current_bundle")
        self._cleanup_loaded_bundle()
        self._repository = None
        self._current_bundle_path = None
        self.repository_changed.emit(None)
        self.bundle_path_changed.emit(None)

    def close_project(self) -> None:
        """Return the Studio shell to its no-Project state and release bundle state."""

        self.set_project(None, repository=None, dirty=False, bundle_path=None)
        self.set_active_tab("Welcome")

    def set_bundle_path(self, bundle_path: str | None) -> None:
        assert_main_gui_thread("AppState.set_bundle_path")
        self._current_bundle_path = bundle_path
        self.bundle_path_changed.emit(bundle_path)

    def mark_dirty(self) -> None:
        assert_main_gui_thread("AppState.mark_dirty")
        self._set_dirty(True)

    def mark_clean(self) -> None:
        assert_main_gui_thread("AppState.mark_clean")
        self._set_dirty(False)

    def _set_dirty(self, dirty: bool) -> None:
        dirty = bool(dirty)
        if dirty != self._is_dirty:
            self._is_dirty = dirty
            self.dirty_changed.emit(dirty)

    def _cleanup_loaded_bundle(self) -> None:
        bundle = self._loaded_bundle
        self._loaded_bundle = None
        cleanup = getattr(bundle, "cleanup", None)
        if callable(cleanup):
            cleanup()

    def set_selected_item(self, item: object | None) -> None:
        assert_main_gui_thread("AppState.set_selected_item")
        self._selected_item = item
        self.selection_changed.emit(item)

    def set_active_tab(self, tab_name: str) -> None:
        assert_main_gui_thread("AppState.set_active_tab")
        if tab_name != self._active_tab:
            self._active_tab = tab_name
            self.active_tab_changed.emit(tab_name)

    def set_active_viewer(self, viewer: object | None) -> None:
        assert_main_gui_thread("AppState.set_active_viewer")
        if viewer is not self._active_viewer:
            self._active_viewer = viewer
            self.active_viewer_changed.emit(viewer)
