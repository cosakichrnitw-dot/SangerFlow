# SangerFlow-Studio GUI Architecture Review

## Scope

This review audits the current `SangerFlow-Studio/` GUI foundation before
adding the first production-style viewers. It is based on the current Studio
implementation and `docs/GUI_ARCHITECTURE_V1.md`.

No changes to existing SangerFlow `core/`, `workflow/`, or `persistence/`
modules are assumed. Studio remains an application layer above immutable
Project, Dataset, and AnalysisResult models.

## Summary Verdict

The current Studio foundation is good enough to start a viewer framework, but
not yet good enough to add large scientific viewers directly into
`WorkspaceTabs`.

Before implementing Chromatogram Viewer, Studio should add a small but formal
viewer layer:

- `BaseViewer`
- `ViewerRegistry`
- `ViewerContext`
- `TabManager`
- typed selection model

The present `MainWindow`, `ProjectController`, `AppState`, `ProjectExplorer`,
and `InspectorPanel` are appropriately small. Their main gap is that selection
is still represented as loose dictionaries and `WorkspaceTabs` is still a
static `QTabWidget` rather than a viewer lifecycle manager.

## 1. Viewer Framework Readiness

### Proposed module location

The proposed location is acceptable:

```text
widgets/
  viewers/
    base_viewer.py
    viewer_registry.py
    viewer_context.py
```

For v1.0, this can work if these modules remain GUI-only and do not import
scientific workflow logic directly. A later cleanup may move them to
`viewers/` at the Studio root, but `widgets/viewers/` is fine for the first
implementation phase.

### BaseViewer responsibility

`BaseViewer` should define the GUI contract shared by all viewer tabs.

Responsibilities:

- Own one tab's visual widget.
- Render one Project, Dataset, AnalysisResult, or derived view.
- Maintain transient UI state such as selection, scroll position, zoom, and
  local display options.
- Expose supported actions for toolbar/menu enablement.
- Emit intent signals such as selection changed, export requested, and open
  related object requested.
- Save and restore UI state.

Non-responsibilities:

- No Project mutation.
- No direct Project Bundle loading.
- No direct MAFFT, BLAST, BOLD, consensus, trim, or export execution.
- No direct sibling-widget updates.
- No in-place modification of core models.

Recommended minimal interface:

```python
class BaseViewer(QWidget):
    selection_changed = Signal(object)
    status_message_changed = Signal(str)
    export_requested = Signal(object)
    open_related_requested = Signal(object)

    @property
    def viewer_id(self) -> str: ...

    @property
    def viewer_title(self) -> str: ...

    @property
    def supported_actions(self) -> tuple[str, ...]: ...

    def open_dataset(self, dataset: object) -> None: ...
    def open_result(self, result: object) -> None: ...
    def refresh(self) -> None: ...
    def close_viewer(self) -> bool: ...
    def save_state(self) -> dict: ...
```

### Viewer Registry responsibility

`ViewerRegistry` should map model type/source type/result type to viewer
factories. It should not create tabs by itself.

Responsibilities:

- Register viewer descriptors.
- Resolve default viewer for a Dataset or AnalysisResult.
- Return alternate viewer choices where useful.
- Keep Viewer imports local to Studio.
- Hide or disable viewers whose dependencies are unavailable.

Non-responsibilities:

- No tab lifecycle.
- No Project updates.
- No workflow execution.
- No scientific data conversion.

Recommended flow:

```text
Dataset / AnalysisResult
    |
    v
ViewerRegistry.resolve(...)
    |
    v
ViewerDescriptor(factory, label, action_id)
```

### ViewerContext responsibility

`ViewerContext` should carry application services into viewers without letting
viewers import the whole app shell.

Recommended fields:

- `app_state`
- `project_controller`
- `dataset_controller`
- `analysis_controller`
- `result_resolver`
- `action_manager`

The context should be intentionally small. If it becomes a general service
container, the viewer boundary will become cloudy.

### TabManager connection

`TabManager` should be the only object that adds/removes viewer widgets from
the workspace tab widget.

Expected path:

```text
ProjectExplorer item open
    |
    v
ProjectController.open_selected_item()
    |
    v
ViewerRegistry resolves viewer factory
    |
    v
TabManager creates or focuses viewer tab
    |
    v
AppState.active_viewer_changed
```

`WorkspaceTabs` should become a display component owned by `TabManager`, not the
place where Dataset/AnalysisResult routing decisions are made.

### Dataset / AnalysisResult opening path

The current Project Explorer already emits selection through
`ProjectController.select_item()`. For opening viewers, add a separate command
path instead of overloading selection.

Recommended:

```text
single click
  -> update selection
  -> Inspector refresh

double click / Open action
  -> controller.open_selected_item()
  -> viewer routing
  -> tab open
```

This keeps inspection and opening separate, which matters once datasets,
analysis results, and viewer-internal selections coexist.

## 2. Chromatogram Viewer Design Check

### Existing core responsibilities

Current Sanger-related core objects and functions include:

- `SangerRead` in `core/models.py`
- AB1 loading in `core/ab1_reader.py`
- trace arrays in `SangerRead.traces`
- base positions in `SangerRead.base_positions`
- quality values in `SangerRead.quality`
- trim state on `SangerRead`
- trimming functions in `core/trimming.py`
- quality summaries in `core/quality.py`
- consensus and review logic in existing consensus/review modules

The current `SangerRead` model is mutable, especially around trim fields. Studio
should treat it carefully and avoid letting a viewer mutate it silently.

### Layer ownership

Chromatogram Viewer should be split this way:

View layer:

- Draw trace channels.
- Draw base calls.
- Draw quality and trim overlays.
- Handle zoom, pan, selected base/trace position.
- Emit selection changes.
- Request actions such as trim, export, BLAST, or consensus.

Controller/action layer:

- Load AB1 through existing core.
- Apply trim through existing trimming functions.
- Convert trimmed reads to SequenceDataset where needed.
- Add generated datasets to Project.
- Open Consensus Review from selected F/R reads.
- Publish results through AppState.

Core/workflow layer:

- AB1 reading.
- Quality calculation.
- Trim calculation/application.
- Pair assembly.
- Consensus generation.
- Dataset adapters.

AppState:

- Current Project.
- Current Dataset/Read selection.
- Active viewer.
- Status/progress/error events.

### Recommended Chromatogram Viewer input

The first version should accept a display adapter instead of raw loose fields:

```python
ChromatogramViewModel(
    read_id,
    filename,
    sequence,
    quality,
    traces,
    base_positions,
    trim_start,
    trim_end,
    selected=True,
    metadata={...},
)
```

This adapter can be created from `SangerRead`, `SequenceRecord.source_reference`,
or future long-read models. The viewer then renders a stable view model instead
of reaching into mutable core fields throughout the canvas code.

### Trim action policy

The viewer may show trim handles, but trim execution should be delegated:

```text
Viewer trim requested
    |
    v
ChromatogramController.apply_trim(read_id, parameters)
    |
    v
core.trimming / workflow adapter
    |
    v
new Project/Dataset state or updated read view model
```

For v1.0, avoid in-place Project mutation and avoid hidden mutation of
`SangerRead` inside the viewer.

## 3. Signal / Slot Design Review

### Existing signals

Current `AppState` has:

- `project_changed`
- `repository_changed`
- `selection_changed`
- `active_tab_changed`

These are sufficient for the current prototype but too coarse for v1.0.

### Required event signals

Project changed:

- Emitted when a Project Bundle is opened, Project is closed, or immutable
  Project is replaced after dataset/result addition.
- Consumers: Project Explorer, Inspector, ActionManager, TabManager.

Dataset selected:

- Should be a typed `StudioSelection`, not a dictionary.
- Consumers: Inspector, ActionManager, status bar, optional viewer focus logic.

Viewer generated:

- Emitted by `TabManager` after a viewer tab is created.
- Consumers: AppState, ActionManager, status bar.

Viewer closed:

- Emitted by `TabManager` after `viewer.close_viewer()` succeeds.
- Consumers: AppState, ActionManager, workspace UI.

Analysis completed:

- Emitted by controller/task service when workflow output is available.
- Controller should update Project first, then publish the new state.
- Consumers: Project Explorer, Inspector, status bar, optional result viewer.

### Proposed signal set

`AppState` should eventually provide:

```python
project_changed = Signal(object)
repository_changed = Signal(object)
selection_changed = Signal(object)
active_viewer_changed = Signal(object)
viewer_opened = Signal(object)
viewer_closed = Signal(str)
workflow_started = Signal(str)
workflow_finished = Signal(str, object)
workflow_failed = Signal(str, str)
status_message_changed = Signal(str)
```

### Typed selection

Replace dictionary selections with a small immutable model:

```python
class SelectionKind(Enum):
    PROJECT = "PROJECT"
    DATASET = "DATASET"
    ANALYSIS_RESULT = "ANALYSIS_RESULT"
    VIEWER = "VIEWER"
    SEQUENCE_RECORD = "SEQUENCE_RECORD"
    CHROMATOGRAM_POSITION = "CHROMATOGRAM_POSITION"
    ALIGNMENT_COLUMN = "ALIGNMENT_COLUMN"
    CONSENSUS_POSITION = "CONSENSUS_POSITION"
    BLAST_HIT = "BLAST_HIT"
    BOLD_HIT = "BOLD_HIT"

@dataclass(frozen=True)
class StudioSelection:
    kind: SelectionKind
    object_id: str | None
    payload: object | None
    source_viewer_id: str | None = None
```

This is the main design step needed before many viewers can share the same
Inspector and ActionManager without fragile `dict["kind"]` branching.

## 4. v1.0 GUI Implementation Priority

Recommended order:

1. Viewer framework foundation
2. Dataset Viewer
3. Chromatogram Viewer
4. Alignment Viewer
5. Consensus Review Viewer
6. BLAST/BOLD Viewer
7. Tree Viewer

This is slightly different from the candidate order. The reason is practical:
Chromatogram Viewer should be first scientific viewer, but Dataset Viewer and
viewer framework should come first as infrastructure.

### Priority 0: Viewer foundation

Implement before any large viewer:

- `BaseViewer`
- `ViewerRegistry`
- `ViewerContext`
- `TabManager`
- typed `StudioSelection`
- minimal ActionManager skeleton

### Priority 1: Dataset Viewer

Dataset Viewer should come before Chromatogram Viewer because it gives a simple
way to open, inspect, and route datasets from Project Explorer. It is the best
low-risk test for Viewer Registry and TabManager.

### Priority 2: Chromatogram Viewer

This should be the first scientific viewer. It validates:

- rendering performance
- read/base selection
- trace coordinate handling
- quality/trim overlays
- controller-mediated actions

### Priority 3: Alignment Viewer

Alignment Viewer should follow after the tab and selection model are stable.
It will stress horizontal scrolling, large matrix rendering, row/column
selection, and export actions.

### Priority 4: Consensus Review Viewer

Consensus Review depends on trace evidence navigation and should reuse
Chromatogram Viewer selection/navigation semantics.

### Priority 5: BLAST/BOLD Viewer

BLAST and BOLD viewers are important, but their current core models are already
separated from sequence rendering. They can wait until Dataset/AnalysisResult
routing is solid.

### Priority 6: Tree Viewer

Tree Viewer should wait until AlignmentDataset and export/partition paths are
settled.

## 5. Ten-Year Extensibility Review

### Can the current direction survive long-term expansion?

Yes, if Studio formalizes viewer boundaries before adding scientific viewers.
The current shell is small enough to grow well, but only if `WorkspaceTabs` does
not become a mixed controller, router, and widget container.

### What works for long-term expansion

The following current choices are strong:

- Studio is separate from existing SangerFlow core.
- MainWindow is still a shell.
- Project data is immutable at the app boundary.
- Project Bundle opening is controller-mediated.
- Project Explorer and Inspector already refresh from AppState.
- Runtime-specific PySide6 handling is Studio-local.

### Risks for long-term expansion

Current risks:

- Selection is still a loose dictionary.
- No TabManager.
- No BaseViewer contract.
- No ActionManager.
- No worker/task boundary for long-running analysis.
- Viewer routing is documented but not implemented.
- `SangerRead` is mutable, so viewers must not treat it as a safe immutable
  Project value without an adapter.

### Long-read and non-Sanger support

The architecture can support long-read and other sequencing technologies if
viewers depend on view models and dataset/result interfaces rather than
Sanger-only fields.

For example:

- Chromatogram Viewer remains Sanger-specific.
- Dataset Viewer remains technology-neutral.
- Alignment Viewer remains sequence/alignment-model driven.
- Consensus Viewer may become one implementation of a broader Review Viewer.
- Result viewers remain AnalysisResult-driven.

Avoid naming the whole viewer framework around Sanger concepts. Keep
Sanger-specific logic inside `ChromatogramViewer` and consensus-specific
viewers.

### Additional analysis support

The planned Viewer Registry + AnalysisResult route should support:

- BLAST
- BOLD
- ASAP/species delimitation
- phylogeny
- distance matrices
- haplotype networks
- future local database searches

The important design rule is that each analysis result gets:

- a stable result model
- a Project AnalysisResult entry
- a viewer factory
- optional export actions
- optional selection-to-dataset adapter

## Final Review Conclusion

The existing Studio GUI foundation is adequate for the next phase, but the next
phase should be the viewer framework, not Chromatogram Viewer directly.

Recommended immediate implementation sequence:

1. Add `widgets/viewers/base_viewer.py`.
2. Add `widgets/viewers/viewer_context.py`.
3. Add `widgets/viewers/viewer_registry.py`.
4. Add `app/selection.py` with typed `StudioSelection`.
5. Add `app/tab_manager.py` and connect it to `WorkspaceTabs`.
6. Add a minimal Dataset Viewer to prove routing.
7. Implement Chromatogram Viewer through the same route.

This gives SangerFlow-Studio a stable enough GUI spine for daily research use
and for later expansion into long-read data, additional sequencing platforms,
and new downstream analyses.
