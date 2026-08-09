# SangerFlow-Studio GUI Architecture v1.0

## Scope

This document audits the current SangerFlow-Studio implementation and defines
the v1.0 GUI architecture for future viewer-based expansion.

This is a Studio application-layer design. Existing SangerFlow `core/`,
`workflow/`, and `persistence/` modules remain the source of scientific and
project data behavior. Studio views must not reimplement Sanger processing,
alignment, consensus, BLAST, BOLD, export, or persistence logic.

Current implemented Studio components:

- `MainWindow`
- `AppState`
- `ProjectController`
- `ProjectExplorer`
- `InspectorPanel`
- `WorkspaceTabs`
- Project Bundle Open
- macOS PySide6 runtime guard

## 1. MainWindow Architecture

### Current responsibilities

`MainWindow` is the outer application shell. Its current responsibilities are:

- Own the `QMainWindow` frame.
- Build the menu bar, toolbar, status bar, and central project workspace.
- Present `ProjectView` as the central widget.
- Route File menu events to `ProjectController`.
- Show user-facing error messages for failed bundle opening.

`MainWindow` currently does not own Project data directly. It receives an
`AppState` and a `ProjectController` at construction time.

### Boundary with Controller

The current boundary is correct and should be preserved:

```text
MainWindow QAction
    |
    v
ProjectController
    |
    v
persistence / core / workflow
    |
    v
AppState update
    |
    v
Views refresh through signals
```

GUI widgets may gather user input such as a filepath, but they should not call
`load_project_bundle()`, MAFFT, BLAST, BOLD, consensus, or export APIs directly.
Those calls belong in controllers or workflow action services.

### Relationship with AppState

`AppState` is the visible application state bus. It currently holds:

- current Project
- current Result Repository
- selected item
- active tab name

`MainWindow` should not inspect or mutate core objects directly. It should use
controllers, and views should refresh from `AppState` signals.

### Future viewer connection points

Future viewers should enter through three extension points:

- `MainWindow` menu and toolbar actions
- `ProjectExplorer` selection and open commands
- `WorkspaceTabs` / future `TabManager`

`MainWindow` should remain a shell. It should not become a viewer registry,
dataset router, or analysis workflow executor.

## 2. Tab Workspace Architecture

### Current state

`WorkspaceTabs` is currently a small `QTabWidget` with:

- Welcome
- Project Summary

It tracks active tab changes through `ProjectController.activate_tab()`, but it
does not yet manage typed viewers, dirty state, routing, or close behavior.

### v1.0 target

SangerFlow-Studio should use a Geneious-style tab workspace:

```text
Project Explorer | Workspace Tabs | Inspector

Workspace Tabs:
  Project Tab
  Chromatogram Viewer
  Alignment Viewer
  Consensus Review Viewer
  BLAST Viewer
  BOLD Viewer
  Tree Viewer
```

### TabManager

Add a `TabManager` as the single owner of viewer tab lifecycle.

Recommended responsibilities:

- Open a viewer tab for a Dataset, AnalysisResult, or Project item.
- Reuse an existing tab when the same resource is already open.
- Assign stable viewer IDs.
- Track active viewer.
- Close viewer tabs safely.
- Ask viewers for unsaved UI state before closing.
- Restore viewer state from project/session state in the future.
- Emit active-viewer changes to `AppState`.

Suggested API:

```python
class TabManager:
    def open_project_summary(project) -> str: ...
    def open_dataset(dataset, *, viewer_hint=None) -> str: ...
    def open_analysis_result(result, *, viewer_hint=None) -> str: ...
    def open_viewer(viewer: BaseViewer) -> str: ...
    def close_viewer(viewer_id: str) -> None: ...
    def active_viewer(self) -> BaseViewer | None: ...
```

`WorkspaceTabs` should become the Qt widget implementation used by
`TabManager`, not the place where routing decisions live.

### Viewer lifecycle

Viewer lifecycle should be explicit:

```text
create
  |
  v
open_dataset / open_result / open_project
  |
  v
shown in tab
  |
  v
refresh on AppState or data replacement
  |
  v
save_state before close
  |
  v
close_viewer
```

Viewer widgets should be disposable. Persistent data remains in immutable core
models, Project entries, Result Repository payloads, and future session state.

### Dataset-to-viewer routing

Dataset opening should be routed through a Studio-level viewer registry:

```text
ProjectExplorer double-click / Open action
    |
    v
ProjectController.open_selected_item()
    |
    v
DatasetOpenRouter / ViewerRegistry
    |
    v
TabManager.open_viewer(...)
```

Routing should use source type and model type first, metadata only as a hint.

Example routing:

| Input | Default viewer |
| --- | --- |
| `SourceType.AB1_RAW` | Chromatogram Viewer |
| `SourceType.AB1_TRIMMED` | Chromatogram or Dataset Viewer |
| `SourceType.CONSENSUS_CANDIDATE` | Consensus Review Viewer |
| `SourceType.REVIEWED_CONSENSUS` | Dataset Viewer |
| `SourceType.IMPORTED_FASTA` | Dataset Viewer |
| `SourceType.IMPORTED_ALIGNMENT` | Alignment Viewer |
| `AlignmentDataset` | Alignment Viewer |
| `BlastResultDataset` / `AnalysisResultType.BLAST` | BLAST Viewer |
| `BoldResultDataset` / `AnalysisResultType.BOLD` | BOLD Viewer |
| Tree result | Tree Viewer |

## 3. Viewer Plugin Architecture

### BaseViewer

Each domain viewer should inherit from a common Qt-facing base class. This is a
GUI contract, not a scientific model contract.

Required interface:

```python
class BaseViewer(QWidget):
    viewer_id: str
    viewer_title: str
    viewer_kind: str

    def open_dataset(self, dataset: object) -> None: ...
    def open_result(self, result: object) -> None: ...
    def close_viewer(self) -> bool: ...
    def refresh(self) -> None: ...
    def export(self, target=None) -> None: ...
    def save_state(self) -> dict: ...
```

Recommended additional properties:

- `source_object_id`
- `is_dirty`
- `supported_actions`
- `selection`
- `metadata`

### Viewer ownership rules

Viewers may:

- Render immutable core/workflow/result values.
- Maintain transient UI state such as zoom, scroll position, selected row, and
  selected base.
- Emit viewer-level signals such as selection changed or export requested.

Viewers must not:

- Modify core objects in place.
- Open Project bundles.
- Add datasets/results to Project directly.
- Run MAFFT, BLAST, BOLD, consensus, or export directly unless delegated through
  controller/action services.
- Reach into sibling widgets such as Project Explorer or Inspector.

### Viewer subclasses

Recommended v1.0 viewer classes:

- `ProjectSummaryViewer`
- `DatasetViewer`
- `ChromatogramViewer`
- `AlignmentViewer`
- `ConsensusViewer`
- `BlastViewer`
- `BoldViewer`
- `TreeViewer`

`ChromatogramViewer`, `AlignmentViewer`, and `ConsensusViewer` should be
implemented as first-class viewers rather than embedded helper widgets. This
keeps action routing, tab lifecycle, and selection behavior consistent.

### Viewer plugin registry

Studio should have a viewer registry separate from `DatasetOpenRouter`.

Recommended responsibilities:

- Register viewer factories.
- Resolve default viewer for a dataset/result.
- Provide alternate viewers for the same object.
- Hide unavailable viewers when dependencies are missing.

Suggested API:

```python
class ViewerPluginRegistry:
    def register_dataset_viewer(source_type, factory, *, default=False): ...
    def register_result_viewer(result_type, factory, *, default=False): ...
    def viewer_choices_for(obj) -> tuple[ViewerDescriptor, ...]: ...
    def default_viewer_for(obj) -> ViewerDescriptor: ...
```

This registry should live in the Studio application layer, not in `core/`.

## 4. Action / Toolbar Architecture

### Current state

`MainWindow` currently defines:

- File menu with `Open Project Bundle...`
- placeholder Project, Tools, Help menus
- Main toolbar with a Welcome action

This is enough for the prototype, but v1.0 needs context-aware actions.

### Action groups

Recommended top-level action groups:

- File actions
- Project actions
- Dataset actions
- Analysis actions
- Export actions
- Viewer actions

`MainWindow` should own `QAction` objects and menus. Action enablement should be
computed by a central `ActionManager` from current `AppState` and active viewer.

### ActionManager

Recommended responsibilities:

- Define stable action IDs.
- Own `QAction` instances.
- Update enabled/disabled state.
- Dispatch action invocations to controllers.
- Query active viewer for context actions.
- Keep menu and toolbar state synchronized.

Suggested flow:

```text
AppState selection changed
    |
    v
ActionManager.update_actions()
    |
    v
QAction enabled/visible state changes
```

### Core action groups

File actions:

- Open Project Bundle
- Save Project Bundle
- Close Project
- Import FASTA
- Export

Dataset actions:

- Open Dataset
- Rename Dataset
- Create Subset
- Run MAFFT
- Run BLAST
- Run BOLD

Analysis actions:

- Open Result
- Filter Result
- Create Dataset from Selection
- Export Result

Export actions:

- Export FASTA
- Export aligned FASTA
- Export PHYLIP
- Export NEXUS
- Export partition file
- Export BLAST/BOLD report

Viewer actions:

- Close Viewer
- Refresh
- Zoom In / Zoom Out
- Copy Selection
- Export Current View

### Viewer context actions

Each viewer should expose context actions through `supported_actions`.

Chromatogram Viewer:

- Trim
- Create Consensus
- BLAST
- Export FASTA
- Open raw trace position

Alignment Viewer:

- Run MAFFT
- Export NEXUS
- Export PHYLIP
- Export partition
- Open selected sample

Consensus Viewer:

- Open chromatogram evidence
- Save review decision
- Build Reviewed Consensus
- Export reviewed FASTA

BLAST Viewer:

- Filter hits
- Create Dataset from Selection
- Export Excel
- Export TSV

BOLD Viewer:

- Filter records
- Create Dataset from Selection
- Export Excel
- Export TSV

Tree Viewer:

- Export tree
- Export image
- Root tree
- Show metadata

## 5. Signal Design

### Current signals

`AppState` currently provides:

- `project_changed`
- `repository_changed`
- `selection_changed`
- `active_tab_changed`

These are the right starting signals.

### v1.0 AppState signals

Recommended additions:

```python
project_changed = Signal(object)
repository_changed = Signal(object)
selection_changed = Signal(object)
active_viewer_changed = Signal(object)
viewer_opened = Signal(object)
viewer_closed = Signal(str)
dataset_added = Signal(object)
dataset_removed = Signal(str)
analysis_result_added = Signal(object)
analysis_result_removed = Signal(str)
workflow_started = Signal(str)
workflow_finished = Signal(str, object)
workflow_failed = Signal(str, str)
status_message_changed = Signal(str)
```

### Selection signal model

Selection should be a typed value rather than a loose dictionary in v1.0.

Suggested model:

```python
@dataclass(frozen=True)
class StudioSelection:
    kind: SelectionKind
    object_id: str | None
    payload: object | None
    source_viewer_id: str | None = None
```

Selection kinds:

- Project
- Dataset
- AnalysisResult
- Viewer
- SequenceRecord
- AlignmentColumn
- ChromatogramPosition
- ConsensusPosition
- BlastHit
- BoldHit

This lets Project Explorer, viewers, Inspector, and actions share one selection
language.

### Workflow signals

Long-running tasks such as MAFFT, BLAST, BOLD, tree inference, and bundle
loading should not block the GUI thread.

Recommended flow:

```text
ActionManager QAction triggered
    |
    v
Controller starts worker
    |
    v
workflow_started
    |
    v
worker emits result / error
    |
    v
Controller updates Project/AppState
    |
    v
workflow_finished or workflow_failed
```

Use `QThread`, `QRunnable`, or a small task service. Do not call subprocess,
network, or heavy parsing directly in Qt widgets.

### Viewer update signals

Viewer-level signals should be narrow:

```python
selection_changed = Signal(object)
state_changed = Signal(object)
export_requested = Signal(object)
open_related_requested = Signal(object)
```

The viewer emits intent. Controllers decide what changes.

## 6. GUI Implementation Priority

### Priority S: GUI shell stabilization

1. Keep PySide6 runtime stable on macOS.
2. Formalize `TabManager`.
3. Add `BaseViewer`.
4. Add typed `StudioSelection`.
5. Add `ActionManager`.
6. Convert `WorkspaceTabs` from static tabs to managed viewer tabs.

Reason: every later viewer depends on tab lifecycle, action enablement, and
selection semantics.

### Priority A: Data and Project usability

1. Dataset Viewer
2. Project Summary Viewer
3. Import FASTA action
4. Export Dataset action
5. Project Bundle save/open roundtrip UI

Reason: researchers need to inspect datasets before starting analysis.
This also validates Project, SequenceDataset, AlignmentDataset, and Result
Repository integration.

### Priority B: Core scientific viewers

1. Chromatogram Viewer
2. Alignment Viewer
3. Consensus Review Viewer

Recommended order:

1. Chromatogram Viewer
2. Dataset Viewer integration with Chromatogram open
3. Alignment Viewer
4. Consensus Review Viewer

Reason: SangerFlow's core identity starts with AB1 inspection and trace-based
evidence. Alignment and consensus viewers should reuse the same selection and
trace-navigation patterns.

### Priority C: Analysis result viewers

1. BLAST Viewer
2. BOLD Viewer
3. BLAST/BOLD Filter Dialogs
4. Create Dataset from Selection
5. Export result reports

Reason: BLAST/BOLD workflows already have result models and filters, but they
should sit on top of stable Dataset, Project, TabManager, and ActionManager
layers.

### Priority D: Downstream analysis

1. Tree Viewer
2. Partition export integration
3. Species delimitation result viewer
4. Distance/network viewers

Reason: these depend on stable AlignmentDataset, metadata, and export layers.

## Proposed v1.0 Module Layout

Recommended Studio-only additions:

```text
SangerFlow-Studio/
  app/
    main.py
    main_window.py
    app_state.py
    qt_runtime.py
    actions.py
    tab_manager.py
    selection.py

  controllers/
    project_controller.py
    dataset_controller.py
    analysis_controller.py
    viewer_controller.py

  viewers/
    base_viewer.py
    project_summary_viewer.py
    dataset_viewer.py
    chromatogram_viewer.py
    alignment_viewer.py
    consensus_viewer.py
    blast_viewer.py
    bold_viewer.py
    tree_viewer.py

  widgets/
    project_explorer.py
    inspector_panel.py
    workspace_tabs.py

  registries/
    viewer_plugin_registry.py
    action_registry.py

  services/
    workflow_task_service.py
    result_resolver.py
```

This keeps the current shell intact while giving future viewers a predictable
place to live.

## Current Architecture Assessment

Strengths:

- `MainWindow` is still a shell, not a workflow executor.
- `ProjectController` owns Project Bundle loading.
- `ProjectExplorer` and `InspectorPanel` update from `AppState`.
- `WorkspaceTabs` is isolated from Project Explorer and Inspector.
- macOS PySide6 runtime handling is Studio-local.

Gaps before v1.0:

- No `TabManager`.
- No `BaseViewer`.
- No typed selection model.
- No `ActionManager`.
- `ProjectExplorer` stores selection as dictionaries.
- `WorkspaceTabs` cannot open/close typed viewers.
- Viewer routing is not yet connected to Project items.
- Long-running workflow execution policy is not defined in code.

## Final v1.0 Direction

SangerFlow-Studio should adopt a view/controller/state design:

```text
Qt widget event
    |
    v
Controller / ActionManager
    |
    v
SangerFlow core / workflow / persistence
    |
    v
immutable result object
    |
    v
AppState signal
    |
    v
ProjectExplorer / WorkspaceTabs / InspectorPanel / Viewer refresh
```

The next implementation phase should not start with a large scientific viewer.
It should first add `TabManager`, `BaseViewer`, `StudioSelection`, and
`ActionManager`. After that, individual viewers can be migrated one at a time
without turning `MainWindow` or `WorkspaceTabs` into a controller.
