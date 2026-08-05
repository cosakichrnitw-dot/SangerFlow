# Data Model

Version: 1.0
Status: Stable
Last Updated: 2026-07-31

---

# 1. Overview

The data model defines how sequencing data is represented and transferred throughout SangerFlow.

Every analysis module operates on shared data models instead of raw files.

This approach ensures consistency, maintainability, and future extensibility.

---

# 2. Design Philosophy

The data model follows four principles.

## Single Source of Truth

Each biological object should exist only once.

Different modules should reference the same object instead of maintaining duplicated copies.

---

## Separation of Data and Presentation

Data models contain biological information only.

Visualization is handled exclusively by GUI components.

---

## Immutable Raw Data

The original sequencing data should never be modified after loading.

All editing operations should be performed on derived data.

---

## Shared Object Model

All Core modules should exchange data through common model classes.

No module should define its own incompatible sequence object.

---

# 3. Main Data Flow

```
AB1 File
    │
    ▼
SangerRead
    │
    ├── Quality
    ├── QC
    ├── Trimming
    ├── Alignment
    ├── Consensus
    ├── BLAST
    └── Export
```

SangerRead is the central object of the software.

---

# 4. SangerRead

Purpose

Represent one sequencing read loaded from an AB1 file.

Typical contents include:

- Sample name
- Base sequence
- Quality values
- Peak positions
- Chromatogram traces
- File path

SangerRead is considered the canonical representation of one sequencing read.

---

# 5. Alignment Data

Alignment results should contain

- aligned sequences
- gap positions
- sequence order
- alignment length

Alignment objects should reference the corresponding SangerRead objects whenever possible.

---

# 6. Consensus Data

Consensus objects represent one consensus sequence generated from multiple aligned reads.

Typical contents include

- consensus sequence
- consensus quality
- supporting reads
- alignment information

---

# 7. BLAST Result

BLAST results are independent objects.

Typical information includes

- Species name
- Scientific name
- Identity
- Coverage
- E-value
- Accession

BLAST results should reference the originating SangerRead.

---

# 8. Export Data

Export operations should never modify biological data.

They convert existing objects into external formats such as

- FASTA
- CSV
- Excel

---

# 9. Future Extensions

Future versions may introduce additional model classes, including

- EditedRead
- Project
- Sample
- Population
- SpeciesRecord

These extensions should remain compatible with the existing SangerRead model.

---

# 10. Summary

The data model serves as the communication layer between all Core modules.

Maintaining a consistent object model ensures that new functionality can be added without redesigning the existing architecture.

---

## Related design documents

- [Architecture.md](Architecture.md)
- [PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md)
- [PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md) — proposed pair assembly results, metrics, and provenance
