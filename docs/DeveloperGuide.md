# Developer Guide

Version: 1.0  
Status: Stable  
Last Updated: 2026-07-31

---

# 1. Overview

This document defines the development practices used in the SangerFlow project.

Its purpose is to keep the codebase consistent, maintainable, testable, and understandable as the project grows.

All contributors should follow the rules described in this guide unless a documented architectural decision explicitly defines an exception.

---

# 2. Development Principles

SangerFlow development follows five primary principles.

## 2.1 Design Before Implementation

New features should be designed before code is written.

The recommended process is:

```text
Requirement
    │
    ▼
Design
    │
    ▼
Review
    │
    ▼
Implementation
    │
    ▼
Testing
    │
    ▼
Documentation
```

Large features should not be implemented directly without first determining:

- which layer owns the feature,
- which modules will be affected,
- what data structures are required,
- how the feature will be tested, and
- whether existing documentation must be updated.

---

## 2.2 Prefer Small, Focused Changes

Each development task should have one clearly defined objective.

Avoid combining unrelated changes in the same implementation step or Git commit.

Preferred:

```text
Add quality threshold configuration
```

Avoid:

```text
Add quality thresholds, redesign the GUI, rename exporters,
and rewrite alignment handling
```

Small changes are easier to review, test, debug, and revert.

---

## 2.3 Preserve Existing Behavior

Refactoring should not unintentionally change user-visible behavior.

When changing internal architecture:

- preserve existing outputs,
- preserve supported file formats,
- preserve documented public APIs where possible, and
- add tests before modifying critical logic.

Behavioral changes must be intentional and documented.

---

## 2.4 Core Logic Must Remain GUI-Independent

Biological algorithms and data-processing logic belong in `core/`.

The `core/` package must not import from `gui/`.

GUI modules may call Core functions, but Core modules must remain usable from:

- the desktop GUI,
- command-line scripts,
- automated tests, and
- future interfaces.

---

## 2.5 Readability Over Cleverness

Code should be understandable without requiring unnecessary interpretation.

Prefer explicit code over compressed or highly abstract implementations.

Readable:

```python
passed_reads = [
    read
    for read in reads
    if read.qc_status == "PASS"
]
```

Avoid unnecessarily obscure expressions or abstractions that make maintenance difficult.

---

# 3. Repository Structure

The expected repository structure is:

```text
SangerFlow/
├── core/
├── gui/
├── config/
├── docs/
├── tests/
├── input/
├── output/
├── main.py
└── pipeline.py
```

Each directory has a distinct responsibility.

## `core/`

Contains:

- biological algorithms,
- sequence processing,
- shared data models,
- external-tool integration,
- export logic, and
- reporting logic.

## `gui/`

Contains:

- windows,
- dialogs,
- panels,
- canvases,
- user interaction handling, and
- visualization logic.

## `config/`

Contains configuration files and default application settings.

## `docs/`

Contains architectural, technical, and development documentation.

## `tests/`

Contains automated tests.

## `input/`

May contain local test or example input data.

Production code must not assume that this directory always exists or contains specific files.

## `output/`

May contain generated results during local development.

Generated output files should not be treated as source code.

---

# 4. Module Design Rules

## 4.1 One Primary Responsibility Per Module

Each module should have one main purpose.

Examples:

```text
ab1_reader.py       → AB1 file reading
trimming.py         → quality-based trimming
quality.py          → quality statistics
consensus.py        → consensus generation
mafft.py            → MAFFT integration
```

A module may contain helper functions, but they should all support the same primary responsibility.

---

## 4.2 Avoid Circular Dependencies

Circular imports are not allowed.

Invalid:

```text
module_a → module_b
module_b → module_a
```

When two modules require shared structures, move those shared structures into a lower-level module such as:

```text
models.py
```

or another dedicated shared module.

---

## 4.3 Keep External Tool Wrappers Isolated

External tools such as MAFFT or BLAST should be accessed through dedicated wrapper modules.

Application code should not construct external commands throughout the codebase.

Preferred:

```python
alignment = run_mafft(sequences)
```

Avoid repeating subprocess logic in multiple modules.

External-tool wrappers should handle:

- command construction,
- temporary files,
- process execution,
- standard output,
- standard error,
- exit codes, and
- tool-specific errors.

---

## 4.4 Avoid Hidden Global State

Modules should not depend on mutable global variables.

Configuration and state should be passed explicitly through:

- function arguments,
- data objects,
- controller objects, or
- configuration objects.

Constants may remain at module level when they are immutable and clearly named.

---

# 5. Python Coding Standards

SangerFlow follows standard modern Python conventions.

## 5.1 Python Version

The supported Python version should be documented in the project README and package configuration.

New language features should only be used when they are compatible with the minimum supported Python version.

---

## 5.2 Style

Code should generally follow PEP 8.

Recommended formatting includes:

- four spaces per indentation level,
- descriptive names,
- one statement per line,
- limited line length,
- blank lines between logical sections, and
- consistent import ordering.

---

## 5.3 Import Order

Imports should be organized in the following order:

```python
# Standard library
from pathlib import Path
import subprocess

# Third-party packages
from Bio import SeqIO
import numpy as np

# Local application modules
from core.models import SangerRead
from core.quality import calculate_quality_metrics
```

Groups should be separated by blank lines.

Wildcard imports are not allowed.

Avoid:

```python
from module import *
```

---

## 5.4 Naming Conventions

Use `snake_case` for:

- functions,
- methods,
- variables,
- modules, and
- file names.

Examples:

```python
calculate_quality_metrics()
trim_sequence()
sample_name
peak_positions
```

Use `PascalCase` for classes.

Examples:

```python
SangerRead
BlastResult
MainWindow
AlignmentWindow
```

Use `UPPER_CASE` for constants.

Examples:

```python
DEFAULT_Q20_THRESHOLD = 20
SUPPORTED_BASES = {"A", "C", "G", "T", "N"}
```

Boolean variables should clearly indicate a true or false condition.

Preferred:

```python
is_trimmed
has_alignment
can_export
```

Avoid unclear names such as:

```python
flag
check
value2
temp_data
```

unless their scope is extremely small and their meaning is obvious.

---

## 5.5 Function Design

Functions should:

- perform one logical task,
- have clear inputs and outputs,
- avoid unexpected side effects,
- return consistent data types, and
- raise meaningful exceptions when they cannot complete their task.

Preferred:

```python
def calculate_mean_quality(
    quality_scores: list[int],
) -> float:
    ...
```

Avoid functions that simultaneously:

- read files,
- modify GUI widgets,
- perform analysis,
- export results, and
- display error dialogs.

These responsibilities should be separated.

---

## 5.6 Type Hints

Public functions and shared data models should use type hints.

Example:

```python
from pathlib import Path


def load_sequence(path: Path) -> str:
    ...
```

Complex return values should use:

- dataclasses,
- named models,
- TypedDict where appropriate, or
- clearly documented tuples only for small internal helpers.

Avoid returning undocumented dictionaries from major public APIs.

---

## 5.7 Docstrings

Public modules, classes, and functions should include docstrings.

Recommended format:

```python
def trim_sequence(
    sequence: str,
    quality_scores: list[int],
    cutoff: float,
) -> tuple[str, int, int]:
    """
    Trim low-quality sequence regions using the Modified Mott algorithm.

    Parameters
    ----------
    sequence
        Nucleotide sequence to trim.
    quality_scores
        Phred quality scores corresponding to each base.
    cutoff
        Error-probability cutoff used by the trimming algorithm.

    Returns
    -------
    tuple[str, int, int]
        Trimmed sequence, start position, and end position.

    Raises
    ------
    ValueError
        If sequence and quality lengths are inconsistent.
    """
```

Docstrings should explain behavior, not simply repeat the function name.

---

## 5.8 Comments

Comments should explain why code exists, especially when behavior is not obvious.

Good:

```python
# ABI trace channels are stored under instrument-specific DATA tags.
# These mappings follow the format used by the supported sequencer output.
```

Poor:

```python
# Loop through values
for value in values:
```

Comments must be updated when the corresponding code changes.

---

# 6. Data Model Rules

Shared biological data should be represented using models defined in `core/models.py` or another dedicated model module.

## 6.1 Do Not Duplicate Biological State

A sequence should not be independently stored in several GUI widgets and Core modules unless those values represent intentionally distinct states.

For example:

```text
raw_sequence
trimmed_sequence
edited_sequence
aligned_sequence
```

may coexist because they represent different processing stages.

However, multiple unrelated copies of the same current sequence should be avoided.

---

## 6.2 Preserve Raw Input

Raw AB1-derived information should remain unchanged after loading.

The following should be treated as source data:

- original sequence,
- original quality values,
- original chromatogram traces,
- original peak positions, and
- original file path.

Derived or edited data should be stored separately.

---

## 6.3 Validate Model Consistency

Data models should validate important invariants.

Examples:

- sequence length matches quality-score length,
- sequence length matches peak-position length,
- chromatogram channels use supported base labels,
- trim ranges are within the original read length, and
- aligned sequences have equal alignment length.

Invalid state should be rejected early rather than causing failures later in the workflow.

---

# 7. GUI Development Rules

## 7.1 GUI Code Does Not Perform Biological Analysis

GUI modules may:

- collect parameters,
- invoke Core functions,
- present results,
- manage windows, and
- handle user interaction.

GUI modules must not directly implement:

- quality algorithms,
- trimming algorithms,
- alignment algorithms,
- consensus algorithms,
- species-identification logic, or
- sequence-format conversion logic.

---

## 7.2 Widgets Should Have Focused Responsibilities

Examples:

```text
SamplePanel
    → sample selection and display

QualityPanel
    → presentation of quality statistics

ChromatogramCanvas
    → chromatogram visualization

BlastDialog
    → BLAST parameter collection

StatusBar
    → application status messages
```

Large GUI classes should delegate visual responsibilities to smaller components.

---

## 7.3 Keep GUI State Explicit

The Main Window or an appropriate controller may coordinate application state.

Avoid allowing unrelated widgets to modify each other directly.

Preferred:

```text
Widget
  ↓ event
Controller or MainWindow
  ↓ state update
Affected widgets
```

Avoid:

```text
Widget A directly modifies Widget B
Widget B directly modifies Widget C
```

unless the relationship is local, simple, and intentional.

---

## 7.4 Long-Running Operations

Operations such as:

- BLAST requests,
- large alignments,
- report generation, and
- external-process execution

must not permanently freeze the graphical interface.

Long-running tasks should eventually support:

- progress indication,
- cancellation,
- clear error reporting, and
- safe GUI updates.

GUI widgets should only be updated from the appropriate GUI thread.

---

## 7.5 User-Facing Errors

Expected failures should be presented clearly.

Examples:

- unsupported file,
- malformed AB1 data,
- missing MAFFT installation,
- BLAST connection failure,
- empty sequence,
- invalid export path, and
- incompatible alignment input.

User-facing messages should explain:

1. what failed,
2. why it may have failed, and
3. what the user can do next.

Internal stack traces should not be shown as the primary error message to ordinary users.

---

# 8. Error Handling

## 8.1 Use Specific Exceptions

Raise specific exception types whenever possible.

Preferred:

```python
raise FileNotFoundError(path)
```

```python
raise ValueError(
    "Sequence length does not match quality-score length."
)
```

Avoid:

```python
raise Exception("Error")
```

---

## 8.2 Do Not Silently Ignore Failures

Avoid empty exception handlers.

Invalid:

```python
try:
    run_analysis()
except Exception:
    pass
```

Failures should be:

- handled,
- logged,
- converted into a more meaningful exception, or
- allowed to propagate to the appropriate caller.

---

## 8.3 Preserve Error Context

When wrapping exceptions, preserve the original cause.

Example:

```python
try:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
except subprocess.CalledProcessError as exc:
    raise RuntimeError(
        "MAFFT failed to generate an alignment."
    ) from exc
```

---

# 9. Testing

Automated tests should be added for Core functionality.

## 9.1 Test Organization

Test files should mirror source modules.

Example:

```text
core/
├── trimming.py
├── quality.py
└── consensus.py

tests/
├── test_trimming.py
├── test_quality.py
└── test_consensus.py
```

---

## 9.2 Test Naming

Test names should describe expected behavior.

Preferred:

```python
def test_trim_sequence_removes_low_quality_terminal_regions():
    ...
```

```python
def test_consensus_returns_n_for_unresolved_position():
    ...
```

Avoid:

```python
def test_1():
    ...
```

---

## 9.3 Minimum Test Cases

Each analytical module should include tests for:

- normal input,
- empty input,
- minimum-size input,
- malformed input,
- boundary values, and
- biologically relevant edge cases.

For example, trimming tests should consider:

- all high-quality bases,
- all low-quality bases,
- low-quality 5′ region,
- low-quality 3′ region,
- internal quality decrease,
- empty sequence, and
- mismatched sequence and quality lengths.

---

## 9.4 Deterministic Tests

Tests should produce consistent results.

Network-dependent tests and external-tool tests should be separated from ordinary unit tests.

BLAST requests should not be required for every test run.

Where possible, use:

- fixtures,
- saved example responses,
- mocked services, and
- controlled temporary files.

---

## 9.5 Regression Tests

When a bug is fixed, add a test that reproduces the original failure.

The test should fail before the fix and pass afterward.

This prevents the same bug from returning in a later release.

---

# 10. Test Data

Test data should be:

- small,
- legally distributable,
- documented,
- representative, and
- free of sensitive information.

Large AB1 collections should not be committed unnecessarily.

When possible, include only the smallest file required to reproduce a specific behavior.

Test fixtures should clearly state whether they are:

- real sequencing data,
- modified sequencing data, or
- synthetic data.

---

# 11. Configuration

User-adjustable thresholds and environment-specific values should not be hard-coded throughout the application.

Examples include:

- quality thresholds,
- trimming cutoff,
- BLAST settings,
- export defaults,
- external-tool paths, and
- display parameters.

Defaults should be centralized in configuration modules or files.

Configuration loading should include:

- validation,
- fallback defaults,
- meaningful error messages, and
- documented supported values.

---

# 12. Logging

Application events and failures should eventually use Python's `logging` module.

Recommended levels:

- `DEBUG` for detailed development information,
- `INFO` for normal application events,
- `WARNING` for recoverable problems,
- `ERROR` for failed operations, and
- `CRITICAL` for unrecoverable application failures.

Avoid using `print()` for permanent diagnostic output in production code.

Temporary development prints should be removed before committing.

---

# 13. External Dependencies

New dependencies should only be introduced when they provide clear value.

Before adding a dependency, consider:

- whether the standard library can perform the task,
- maintenance status,
- license compatibility,
- installation difficulty,
- platform support,
- package size, and
- long-term availability.

Dependencies required only for development should be separated from runtime dependencies.

---

# 14. Git Workflow

## 14.1 Branches

Development should occur in focused branches.

Recommended branch names:

```text
feature/sequence-editor
feature/project-model
fix/blast-timeout
fix/alignment-scroll-sync
refactor/sanger-read-model
docs/developer-guide
test/trimming-edge-cases
```

Branch names should describe the purpose of the work.

---

## 14.2 Commits

Each commit should represent one coherent change.

Good commit messages:

```text
Add Modified Mott trimming tests
```

```text
Fix chromatogram base-position synchronization
```

```text
Refactor AB1 reader to return SangerRead
```

```text
Document Core dependency rules
```

Avoid vague messages:

```text
update
```

```text
fix
```

```text
changes
```

---

## 14.3 Commit Before Large Refactoring

Before making a large architectural change:

1. confirm that the current version runs,
2. commit the working state,
3. create a dedicated branch, and
4. implement the change incrementally.

This creates a safe recovery point.

---

## 14.4 Do Not Commit Generated or Local Files

The following should normally remain outside version control:

- virtual environments,
- cache directories,
- temporary files,
- local output files,
- credentials,
- API keys,
- machine-specific configuration,
- operating-system metadata, and
- large unpublished datasets.

The `.gitignore` file should be updated when new generated files appear.

---

# 15. Documentation Updates

Documentation is part of the implementation.

The relevant documentation should be updated when a change affects:

- architecture,
- public APIs,
- repository structure,
- workflow,
- configuration,
- installation,
- supported tools,
- user-visible behavior, or
- future development plans.

A feature is not complete when the code and documentation disagree.

---

# 16. Adding a New Core Feature

Use the following process when adding a biological analysis feature.

## Step 1 — Define the Responsibility

Write a one-sentence purpose.

Example:

```text
Calculate pairwise genetic distances from aligned nucleotide sequences.
```

## Step 2 — Define Inputs and Outputs

Example:

```text
Input:
- aligned sequences
- substitution model

Output:
- distance matrix
```

## Step 3 — Select the Appropriate Module

Create a new module if the feature has a distinct responsibility.

Example:

```text
core/genetic_distance.py
```

## Step 4 — Define the Public API

Example:

```python
def calculate_distance_matrix(
    sequences: list[str],
    model: str = "p-distance",
) -> DistanceMatrix:
    ...
```

## Step 5 — Implement Core Logic

Do not begin with GUI integration.

The feature should work independently from Python code or tests.

## Step 6 — Add Tests

Test normal and edge-case behavior.

## Step 7 — Integrate with the GUI

Add GUI controls only after the Core implementation is stable.

## Step 8 — Update Documentation

Update:

- `Core.md`,
- `Workflow.md`,
- `DataModel.md`, if necessary,
- user documentation, and
- `Roadmap.md`.

---

# 17. Adding a New GUI Component

Use the following process when adding a window, panel, dialog, or canvas.

## Step 1 — Define the User Task

Example:

```text
Allow the user to review and edit ambiguous base calls.
```

## Step 2 — Identify Required Core APIs

Do not duplicate analysis logic in the GUI.

## Step 3 — Define Component Responsibility

Example:

```text
SequenceEditorWindow
    → display editable sequence state and capture editing actions
```

## Step 4 — Define State Ownership

Determine whether the state belongs to:

- the shared data model,
- the Main Window,
- a controller,
- the component itself, or
- a temporary dialog result.

## Step 5 — Implement the Smallest Useful Component

Avoid redesigning unrelated windows.

## Step 6 — Test Interaction

Verify:

- valid input,
- invalid input,
- cancellation,
- window closing,
- repeated opening, and
- synchronization with other views.

---

# 18. Code Review Checklist

Before accepting a change, verify the following.

## Architecture

- Does the change belong in the selected layer?
- Does Core remain independent from GUI?
- Are circular dependencies avoided?
- Is the module responsibility clear?

## Code Quality

- Are names descriptive?
- Are functions focused?
- Are type hints present where useful?
- Are errors handled clearly?
- Are temporary prints removed?

## Biological Correctness

- Is the algorithm implemented as intended?
- Are assumptions documented?
- Are sequence coordinates consistent?
- Are gaps, ambiguous bases, and empty inputs handled?

## Testing

- Are normal cases tested?
- Are edge cases tested?
- Is a regression test included for bug fixes?
- Can tests run without launching the GUI?

## Documentation

- Does the documentation match the implementation?
- Are new parameters documented?
- Are workflow changes reflected in `Workflow.md`?
- Are architectural changes recorded?

---

# 19. Definition of Done

A development task is complete when:

- the intended behavior is implemented,
- the code follows the architecture,
- relevant tests pass,
- expected errors are handled,
- temporary debug code is removed,
- documentation is updated,
- the application still starts correctly, and
- the change is committed with a clear message.

For major features, completion should also include:

- manual GUI verification,
- representative biological test data, and
- review of backward compatibility.

---

# 20. Future Development Practices

As the project grows, the following practices may be introduced:

- automated formatting,
- static type checking,
- continuous integration,
- automated test execution,
- code coverage reporting,
- package distribution,
- release automation,
- structured logging,
- plugin APIs, and
- formal deprecation policies.

These practices should be introduced gradually and only when they improve reliability without creating unnecessary development overhead.

---

# 21. Summary

The SangerFlow development process prioritizes:

- clear architecture,
- modular implementation,
- biological correctness,
- reproducibility,
- automated testing,
- explicit documentation, and
- small, reviewable changes.

The objective is not only to make the current version work, but to maintain a codebase that can support long-term scientific development.