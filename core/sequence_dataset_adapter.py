"""Small adapters from existing sequence values into ``SequenceDataset``.

Only the trimmed-sequence boundary is implemented here.  This module does not
read AB1 files, trim sequences, alter source objects, or connect to a GUI.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType


def from_trimmed_sequences(
    dataset_id: str,
    name: str,
    sequences: Iterable[tuple[str, str]],
    *,
    metadata: Mapping[str, object] | None = None,
) -> SequenceDataset:
    """Create an immutable ``AB1_TRIMMED`` dataset from ordered ID/sequence pairs.

    The supplied values are read only.  ``SequenceDataset`` and
    ``SequenceRecord`` provide the actual ID uniqueness, DNA/IUPAC validation,
    upper-case normalization, and immutable metadata guarantees.
    """

    records = tuple(
        SequenceRecord(sequence_id=sequence_id, sequence=sequence)
        for sequence_id, sequence in sequences
    )
    return SequenceDataset(
        dataset_id=dataset_id,
        name=name,
        source_type=SourceType.AB1_TRIMMED,
        records=records,
        metadata=metadata,
    )
