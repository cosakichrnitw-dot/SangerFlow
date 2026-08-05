"""FASTA-to-:class:`SequenceDataset` import helpers.

This module intentionally only reads and validates FASTA into the existing
sequence dataset model.  It does not align records or alter the source file.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from Bio import SeqIO

from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType


class FastaOpenMode(str, Enum):
    """How an imported FASTA should be classified by the caller."""

    AUTO = "auto"
    UNALIGNED = "unaligned"
    ALIGNMENT = "alignment"


def read_fasta_dataset(
    filepath: str | Path,
    *,
    dataset_id: str | None = None,
    name: str | None = None,
    open_as: FastaOpenMode | str = FastaOpenMode.AUTO,
) -> SequenceDataset:
    """Read one FASTA file into an immutable :class:`SequenceDataset`.

    FASTA content is accepted irrespective of its filename extension.  This
    permits common ``.fas``, ``.fasta``, ``.fa``, and ``.fna`` files without
    making an extension a correctness requirement.

    ``auto`` is conservative: it marks input as an imported alignment only
    when every record has the same length *and* at least one record contains a
    gap.  Equal-length ungapped sequences remain ``IMPORTED_FASTA``.
    """

    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"FASTA file does not exist: {path}")

    requested_open_as = _coerce_open_mode(open_as)
    try:
        with path.open("r", encoding="utf-8") as fasta_handle:
            parsed_records = list(SeqIO.parse(fasta_handle, "fasta"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Could not parse FASTA file '{path}': {error}") from error

    if not parsed_records:
        raise ValueError(f"FASTA file contains no records: {path}")

    records = tuple(_to_sequence_record(record) for record in parsed_records)
    lengths = tuple(len(record.sequence) for record in records)
    has_gaps = any("-" in record.sequence for record in records)
    equal_length = len(set(lengths)) == 1
    inferred_alignment = has_gaps and equal_length
    source_type = _source_type_for(requested_open_as, inferred_alignment)

    return SequenceDataset(
        dataset_id=dataset_id if dataset_id is not None else _safe_dataset_id(path.stem),
        name=name if name is not None else path.name,
        source_type=source_type,
        records=records,
        metadata={
            "source_filepath": str(path.resolve()),
            "original_filename": path.name,
            "requested_open_as": requested_open_as.value,
            "inferred_alignment": inferred_alignment,
            "sequence_count": len(records),
            "minimum_length": min(lengths),
            "maximum_length": max(lengths),
            "has_gaps": has_gaps,
        },
    )


def _coerce_open_mode(open_as: FastaOpenMode | str) -> FastaOpenMode:
    if isinstance(open_as, FastaOpenMode):
        return open_as
    try:
        return FastaOpenMode(open_as.lower())
    except (AttributeError, ValueError) as error:
        allowed = ", ".join(mode.value for mode in FastaOpenMode)
        raise ValueError(f"open_as must be one of: {allowed}") from error


def _to_sequence_record(record: object) -> SequenceRecord:
    """Translate a Biopython FASTA record without redefining sequence models."""

    sequence_id = record.id
    full_header = record.description
    description = full_header[len(sequence_id) :].lstrip() or None
    return SequenceRecord(
        sequence_id=sequence_id,
        sequence=str(record.seq),
        description=description,
    )


def _source_type_for(open_mode: FastaOpenMode, inferred_alignment: bool) -> SourceType:
    if open_mode is FastaOpenMode.ALIGNMENT:
        return SourceType.IMPORTED_ALIGNMENT
    if open_mode is FastaOpenMode.UNALIGNED:
        return SourceType.IMPORTED_FASTA
    return SourceType.IMPORTED_ALIGNMENT if inferred_alignment else SourceType.IMPORTED_FASTA


def _safe_dataset_id(stem: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in stem).strip("_")
    return cleaned or "imported_fasta"
