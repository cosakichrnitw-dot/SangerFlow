# SangerFlow-Studio PySide6 GUI Architecture

## GUI responsibility and core boundary

SangerFlow-Studio is a separate application layer. It displays Project,
Dataset, and AnalysisResult values supplied by existing SangerFlow modules.
It does not reimplement scientific algorithms, persistence, or workflows.

The initial executable starts with no Project. The File menu delegates bundle
loading to `ProjectController`, which calls the existing persistence layer and
publishes its immutable Project and extracted Result Repository through
`AppState`.

```text
Qt View event → Controller → SangerFlow core/workflow → AppState → View refresh
```

Views do not call workflow logic directly. Future actions will be added to a
controller, which receives immutable values from core/workflow and publishes
the replacement state through `AppState`.

## Main window and tabs

`MainWindow` owns the menu bar, toolbar, status bar, and one resizable central
`ProjectView` splitter:

```text
ProjectExplorer | WorkspaceTabs | InspectorPanel
```

`WorkspaceTabs` starts with Welcome and Project Summary. Chromatogram,
Consensus Review, Alignment, BLAST, and BOLD should each be implemented as a
dedicated tab widget and opened through the controller layer.

## Adding a future viewer

1. Add a viewer widget under `views/` or `widgets/`; it accepts immutable core
   values and presents them only.
2. Add an intent method to the relevant controller. The controller calls the
   existing core/workflow/persistence API and replaces `AppState` values with
   returned immutable objects.
3. Let `WorkspaceTabs` own the tab lifecycle. No viewer should reach into a
   sibling widget or call the Project Explorer directly.

This keeps project navigation, future dataset actions, and scientific
workflows independently testable while allowing the main shell to grow.

## View/controller structure

- `ProjectExplorer`: tree display and selection events.
- `InspectorPanel`: read-only selected-item metadata.
- `WorkspaceTabs`: tab lifecycle only.
- `ProjectController`: sole route for state-changing view interactions.
- `AppState`: current Project, selection, and active tab.

This keeps widget-to-widget dependencies out of the design and leaves a clear
extension point for future Project Explorer, Dataset Manager, and viewer tabs.
