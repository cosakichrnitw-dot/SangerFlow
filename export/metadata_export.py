"""Flat, research-friendly metadata table exports for SequenceDataset values."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from core.sequence_dataset import SequenceDataset


BASE_COLUMNS = ("Sample_ID", "Sequence_length", "Source_type")


def metadata_field_names(dataset: SequenceDataset) -> tuple[str, ...]:
    if not isinstance(dataset, SequenceDataset):
        raise ValueError("dataset must be a SequenceDataset")
    return tuple(sorted({str(key) for record in dataset.records for key in record.metadata}))


def export_dataset_metadata_to_csv(
    dataset: SequenceDataset, filepath: str | Path, *, fields: Sequence[str] | None = None,
) -> None:
    header, rows = metadata_table_rows(dataset, fields=fields)
    output = _path(filepath, ".csv")
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def export_dataset_metadata_to_xlsx(
    dataset: SequenceDataset, filepath: str | Path, *, fields: Sequence[str] | None = None,
) -> None:
    header, rows = metadata_table_rows(dataset, fields=fields)
    output = _path(filepath, ".xlsx")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Metadata"
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    workbook.save(output)


def metadata_table_rows(dataset: SequenceDataset, *, fields: Sequence[str] | None = None) -> tuple[tuple[str, ...], tuple[tuple[object, ...], ...]]:
    if not isinstance(dataset, SequenceDataset):
        raise ValueError("dataset must be a SequenceDataset")
    selected = tuple(fields) if fields is not None else metadata_field_names(dataset)
    if len(set(selected)) != len(selected) or any(not isinstance(field, str) or not field for field in selected):
        raise ValueError("fields must be unique non-empty metadata field names")
    header = (*BASE_COLUMNS, *selected)
    rows = tuple(
        (
            record.sequence_id,
            len(record.sequence),
            dataset.source_type.value,
            *(record.metadata.get(field, "") for field in selected),
        )
        for record in dataset.records
    )
    return header, rows


def _path(filepath: str | Path, suffix: str) -> Path:
    if not isinstance(filepath, (str, Path)):
        raise ValueError("filepath must be a path string or Path")
    path = Path(filepath)
    if path.suffix.lower() != suffix or not path.parent.is_dir() or (path.exists() and path.is_dir()):
        raise ValueError(f"filepath must be a writable {suffix} file")
    return path
