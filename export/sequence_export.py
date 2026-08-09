"""Standard sequence and alignment exports for external analysis software.

This module is intentionally separate from BLAST/BOLD result reports.  It
only reads immutable dataset models and writes standard FASTA, relaxed PHYLIP,
and DNA NEXUS matrix documents.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from core.alignment_dataset import AlignmentDataset, AlignmentRecord, MarkerRegion
from core.sequence_dataset import SequenceDataset, SequenceRecord


def export_dataset_to_fasta(dataset: SequenceDataset, filepath: str | Path) -> None:
    """Export ordered SequenceDataset records as FASTA."""
    _validate_sequence_dataset(dataset)
    _write_fasta(_sequence_rows(dataset.records), filepath)


def export_dataset_to_phylip(dataset: SequenceDataset, filepath: str | Path) -> None:
    """Export an equal-length SequenceDataset as relaxed sequential PHYLIP."""
    _validate_sequence_dataset(dataset)
    if not dataset.is_equal_length:
        raise ValueError("PHYLIP export requires equal-length sequences")
    _write_phylip(_sequence_rows(dataset.records), filepath)


def export_dataset_to_nexus(
    dataset: SequenceDataset,
    filepath: str | Path,
    *,
    metadata: Mapping[str, object] | None = None,
) -> None:
    """Export an equal-length SequenceDataset as a standard DNA NEXUS matrix."""
    _validate_sequence_dataset(dataset)
    if not dataset.is_equal_length:
        raise ValueError("NEXUS export requires equal-length sequences")
    _write_nexus(_sequence_rows(dataset.records), filepath, metadata=metadata)


def export_alignment_to_fasta(
    alignment_dataset: AlignmentDataset,
    filepath: str | Path,
) -> None:
    """Export ordered aligned records as aligned FASTA, preserving gaps."""
    _validate_alignment_dataset(alignment_dataset)
    _write_fasta(_alignment_rows(alignment_dataset.records), filepath)


def export_alignment_to_phylip(
    alignment_dataset: AlignmentDataset,
    filepath: str | Path,
) -> None:
    """Export an AlignmentDataset as relaxed sequential PHYLIP."""
    _validate_alignment_dataset(alignment_dataset)
    _write_phylip(_alignment_rows(alignment_dataset.records), filepath)


def export_alignment_to_nexus(
    alignment_dataset: AlignmentDataset,
    filepath: str | Path,
    *,
    metadata: Mapping[str, object] | None = None,
) -> None:
    """Export an AlignmentDataset as NEXUS, including optional marker charsets."""
    _validate_alignment_dataset(alignment_dataset)
    _write_nexus(
        _alignment_rows(alignment_dataset.records),
        filepath,
        marker_regions=alignment_dataset.marker_regions,
        metadata=metadata,
    )


def _validate_sequence_dataset(dataset: object) -> SequenceDataset:
    if not isinstance(dataset, SequenceDataset):
        raise ValueError("dataset must be a SequenceDataset")
    if not dataset.records:
        raise ValueError("dataset must contain at least one record")
    _validate_taxon_ids(record.sequence_id for record in dataset.records)
    return dataset


def _validate_alignment_dataset(dataset: object) -> AlignmentDataset:
    if not isinstance(dataset, AlignmentDataset):
        raise ValueError("alignment_dataset must be an AlignmentDataset")
    if not dataset.records:
        raise ValueError("alignment_dataset must contain at least one record")
    _validate_taxon_ids(record.record_id for record in dataset.records)
    return dataset


def _validate_taxon_ids(taxon_ids: Iterable[str]) -> None:
    values = tuple(taxon_ids)
    if not values:
        raise ValueError("at least one taxon ID is required")
    if len(set(values)) != len(values):
        raise ValueError("taxon IDs must be unique")
    for taxon_id in values:
        if not isinstance(taxon_id, str) or not taxon_id:
            raise ValueError("taxon IDs must be non-empty strings")
        if any(character.isspace() or character in ";[]'\"" for character in taxon_id):
            raise ValueError(
                "taxon IDs for FASTA/PHYLIP/NEXUS export must not contain whitespace or NEXUS delimiters"
            )


def _sequence_rows(records: Iterable[SequenceRecord]) -> tuple[tuple[str, str], ...]:
    return tuple((record.sequence_id, record.sequence) for record in records)


def _alignment_rows(records: Iterable[AlignmentRecord]) -> tuple[tuple[str, str], ...]:
    return tuple((record.record_id, record.aligned_sequence) for record in records)


def _write_fasta(rows: tuple[tuple[str, str], ...], filepath: str | Path) -> None:
    output_path = _validate_output_path(filepath)
    try:
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            for taxon_id, sequence in rows:
                handle.write(f">{taxon_id}\n{sequence}\n")
    except OSError as error:
        raise ValueError(f"unable to write FASTA file: {output_path}") from error


def _write_phylip(rows: tuple[tuple[str, str], ...], filepath: str | Path) -> None:
    output_path = _validate_output_path(filepath)
    length = len(rows[0][1])
    try:
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            # Relaxed PHYLIP keeps full source record IDs while retaining the
            # conventional NTAX/NCHAR header used by most modern tools.
            handle.write(f"{len(rows)} {length}\n")
            for taxon_id, sequence in rows:
                handle.write(f"{taxon_id} {sequence}\n")
    except OSError as error:
        raise ValueError(f"unable to write PHYLIP file: {output_path}") from error


def _write_nexus(
    rows: tuple[tuple[str, str], ...],
    filepath: str | Path,
    *,
    marker_regions: tuple[MarkerRegion, ...] = (),
    metadata: Mapping[str, object] | None = None,
) -> None:
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping or None")
    output_path = _validate_output_path(filepath)
    length = len(rows[0][1])
    comments = _nexus_comments(metadata)
    try:
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("#NEXUS\n")
            handle.write("[ Generated by SangerFlow ]\n")
            for comment in comments:
                handle.write(f"[ {comment} ]\n")
            handle.write("BEGIN DATA;\n")
            handle.write(f"  DIMENSIONS NTAX={len(rows)} NCHAR={length};\n")
            handle.write("  FORMAT DATATYPE=DNA MISSING=N GAP=-;\n")
            handle.write("  MATRIX\n")
            for taxon_id, sequence in rows:
                handle.write(f"  {taxon_id} {sequence}\n")
            handle.write("  ;\nEND;\n")
            if marker_regions:
                handle.write("\nBEGIN SETS;\n")
                for region in marker_regions:
                    handle.write(f"  CHARSET {region.name} = {region.start}-{region.end};\n")
                handle.write("END;\n")
    except OSError as error:
        raise ValueError(f"unable to write NEXUS file: {output_path}") from error


def _nexus_comments(metadata: Mapping[str, object] | None) -> tuple[str, ...]:
    if not metadata:
        return ()
    comments = []
    for key, value in metadata.items():
        if not isinstance(key, str) or any(character in key for character in "[]\n\r"):
            raise ValueError("NEXUS metadata keys must be safe text")
        rendered = str(value)
        if any(character in rendered for character in "[]\n\r"):
            raise ValueError("NEXUS metadata values must not contain brackets or newlines")
        comments.append(f"{key}: {rendered}")
    return tuple(comments)


def _validate_output_path(filepath: str | Path) -> Path:
    if not isinstance(filepath, (str, Path)):
        raise ValueError("filepath must be a path string or Path")
    output_path = Path(filepath)
    if not output_path.name or output_path.exists() and output_path.is_dir():
        raise ValueError("filepath must refer to a file")
    if not output_path.parent.exists() or not output_path.parent.is_dir():
        raise ValueError("filepath parent directory does not exist")
    return output_path
