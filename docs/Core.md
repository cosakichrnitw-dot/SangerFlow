# Core Architecture

> **Legacy note:** references to the Tkinter GUI are retained as historical
> implementation context. v1.0's supported GUI is PySide6 SangerFlow Studio.

Version: 1.0
Status: Stable
Last Updated: 2026-07-31

---

# 1. Overview

The Core package contains all biological algorithms and data processing logic used by SangerFlow.

The Core layer is completely independent of the graphical user interface and can be executed from either the GUI or command-line interface (CLI).

Every biological operation performed by SangerFlow must be implemented inside the Core package.

---

# 2. Design Principles

The Core follows the following principles.

## GUI Independence

The Core must never import any module from `gui/`.

The same Core code should work with:

- Tkinter
- PySide
- Command-line interface
- Future web interfaces

without modification.

---

## Single Responsibility

Each module should perform one primary task.

Examples:

- AB1 reading
- Sequence trimming
- Quality calculation
- Alignment
- Consensus generation

should all remain independent.

---

## Reusability

Every module should be reusable independently.

Example:

The trimming module should work regardless of whether the sequence was loaded from an AB1 file or a FASTA file.

---

## Testability

Every module should be executable without launching the GUI.

Unit testing should target Core modules directly.

---

# 3. Core Workflow

The Core processing pipeline is illustrated below.

AB1 File
↓

ab1_reader

↓

quality

↓

waveform_qc

↓

trimming

↓

(Optional)
blast

↓

(Optional)
alignment

↓

(Optional)
consensus

↓

exporter

Each processing step should receive data from the previous stage and return processed data without modifying unrelated components.

---

# 4. Module Responsibilities

## ab1_reader.py

Purpose

Read ABI chromatogram files.

Responsibilities

- Read nucleotide sequence
- Read chromatogram traces
- Read quality values
- Read peak positions
- Construct SangerRead

Must NOT

- Trim sequences
- Calculate quality metrics
- Perform BLAST
- Draw graphics

---

## quality.py

Purpose

Calculate sequence quality statistics.

Responsibilities

- Average quality
- Q20 ratio
- Q30 ratio
- Basic quality metrics

Must NOT

- Read AB1 files
- Trim sequences
- Export files

---

## waveform_qc.py

Purpose

Determine whether sequencing results satisfy predefined quality criteria.

Responsibilities

- PASS
- WARNING
- FAIL

based on

- Mean quality
- Terminal quality
- Longest Q30 block
- User-defined thresholds

---

## trimming.py

Purpose

Remove low-quality regions.

Responsibilities

- Modified Mott algorithm
- Trim position detection
- Return trimmed sequence

Must NOT

- Perform GUI updates
- Export files

---

## blast.py

Purpose

Communicate with the NCBI BLAST service.

Responsibilities

- Submit sequence
- Receive BLAST results
- Parse XML output

Must NOT

- Format GUI tables
- Save reports

---

## blast_controller.py

Purpose

Coordinate BLAST execution.

Responsibilities

- Manage BLAST workflow
- Handle multiple requests
- Return processed results

---

## blast_summary.py

Purpose

Summarize BLAST results.

Responsibilities

- Species summary
- Identity
- Coverage
- E-value

---

## blast_exporter.py

Purpose

Export BLAST results.

Responsibilities

- CSV
- Excel

---

## chromatogram_alignment.py

Purpose

Generate chromatogram alignment.

Responsibilities

- Coordinate alignment
- Trace synchronization
- Gap handling

---

## mafft.py

Purpose

Execute MAFFT.

Responsibilities

- Create temporary FASTA
- Run MAFFT
- Read alignment

---

## consensus.py

Purpose

Generate consensus sequences.

Responsibilities

- Majority vote
- Quality-aware consensus
- Gap handling

---

## exporter.py

Purpose

Export processed sequences.

Responsibilities

- FASTA
- Other sequence formats

---

## merge.py

Purpose

Merge multiple FASTA sequences.

---

## report.py

Purpose

Generate summary reports.

Responsibilities

- Excel
- Statistics
- QC summaries

---

## selection.py

Purpose

Manage sequence selection used by downstream analyses.

---

## config.py

Purpose

Provide configuration loading utilities.

---

## sequence_loader.py

Purpose

Load previously exported sequences.

---

## models.py

Purpose

Define shared data models used throughout the Core package.

This module should contain shared data structures only.

No biological algorithms should be implemented here.

---

# 5. Dependency Rules

The following dependency hierarchy should be respected.

models

↑

ab1_reader

↑

quality

↑

waveform_qc

↑

trimming

↑

blast

↑

alignment

↑

consensus

↑

export

Lower-level modules must never depend on higher-level modules.

---

# 6. Public API

Only public functions should be imported outside each module.

Private helper functions should remain internal.

Public APIs should remain stable across minor releases whenever possible.

---

# 7. Future Extension

Future Core modules may include

- BOLD
- ASAP
- ABGD
- Distance Matrix
- Population Genetics
- Phylogenetic Analysis

These should be implemented as independent modules without modifying existing Core functionality whenever possible.

---

# 8. Conclusion

The Core package is the computational engine of SangerFlow.

Future development should prioritize stability, modularity, and maintainability.

New biological analyses should extend the Core through additional modules rather than increasing coupling between existing components.
