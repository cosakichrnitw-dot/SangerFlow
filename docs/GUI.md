# GUI Architecture

Version: 1.0
Status: Stable
Last Updated: 2026-07-31

---

# 1. Overview

The GUI package provides the graphical user interface of SangerFlow.

Its primary responsibility is to present biological data to the user and translate user interactions into Core operations.

The GUI must never implement biological algorithms.

---

# 2. Design Principles

The GUI follows the principles below.

## Separation of Responsibilities

The graphical interface is responsible only for

- displaying information,
- collecting user input, and
- invoking Core functions.

All biological processing must remain inside the Core package.

---

## Stateless Visualization

Whenever possible, GUI widgets should avoid storing biological data internally.

Instead, they should display information obtained from Core objects.

---

## Loose Coupling

GUI components should communicate through well-defined interfaces.

Individual widgets should remain independent whenever possible.

---

## Readability

Each window should represent one major workflow.

Complex windows should be divided into reusable widgets.

---

# 3. GUI Architecture

```
Main Window
│
├── Menu Bar
├── Toolbar
├── Sample Panel
├── Chromatogram Viewer
├── Quality Panel
├── Status Bar
└── Dialog Windows
```

The Main Window coordinates all GUI components.

Individual widgets should remain responsible for only their own display logic.

---

# 4. Main Window

Purpose

The Main Window serves as the central controller of the graphical interface.

Responsibilities

- Open sequencing files
- Coordinate widgets
- Dispatch user actions
- Display analysis results

The Main Window should avoid implementing biological algorithms directly.

---

# 5. Sample Panel

Purpose

Display all loaded sequencing samples.

Typical responsibilities

- Sample selection
- Current sample indication
- Multiple sample management

The Sample Panel does not modify sequencing data.

---

# 6. Chromatogram Viewer

Purpose

Display chromatogram traces.

Responsibilities

- Draw chromatograms
- Display called bases
- Display quality information
- Cursor synchronization
- Zoom and navigation

The viewer should never perform base calling or trimming calculations.

---

# 7. Quality Panel

Purpose

Present sequencing quality statistics.

Typical contents include

- Average quality
- Q20 percentage
- Q30 percentage
- PASS / WARNING / FAIL

Values are calculated by the Core package.

---

# 8. Alignment Window

Purpose

Display multiple aligned sequences.

Responsibilities

- Alignment visualization
- Sequence scrolling
- Position synchronization
- Consensus display

Alignment calculations remain inside the Core package.

---

# 9. BLAST Window

Purpose

Display BLAST search results.

Responsibilities

- Species list
- Identity
- Coverage
- E-value
- Accession

The GUI only displays results returned by the Core package.

---

# 10. Dialog Windows

Dialog windows provide temporary user interactions.

Examples include

- File selection
- Export settings
- BLAST options
- Preferences

Dialogs should not contain biological algorithms.

---

# 11. Event Flow

Typical GUI interaction

```
User Action
      │
      ▼
GUI Widget
      │
      ▼
Main Window
      │
      ▼
Core Module
      │
      ▼
Result
      │
      ▼
GUI Update
```

The GUI should never bypass the Core package.

---

# 12. Future Expansion

Future GUI components may include

- Project Explorer
- Sequence Editor
- Annotation Viewer
- Phylogenetic Tree Viewer
- Population Genetics Viewer
- Plugin Manager

New windows should follow the same architectural principles.

---

# 13. Summary

The GUI package is responsible for user interaction and visualization.

Maintaining a strict separation between presentation and biological computation improves maintainability, simplifies testing, and allows future replacement of the graphical framework without modifying the Core package.