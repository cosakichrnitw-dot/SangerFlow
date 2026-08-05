"""Immutable common metadata for results produced from a sequence dataset.

``AnalysisResult`` is deliberately separate from :mod:`core.sequence_dataset`:
it records an analysis outcome and its input dataset lineage, not biological
sequence records.  Concrete result models can retain their domain-specific
fields while exposing this shared result representation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class AnalysisResultType(str, Enum):
    """Kinds of analyses that can produce a project-traceable result."""

    BLAST = "BLAST"
    BOLD = "BOLD"
    PHYLOGENY = "PHYLOGENY"
    SPECIES_DELIMITATION = "SPECIES_DELIMITATION"


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _freeze_metadata(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class AnalysisResult:
    """Common immutable lineage information for an analysis result.

    ``parent_dataset_id`` identifies the source ``SequenceDataset`` without
    importing or copying that dataset.  Result payloads such as BLAST hits or
    phylogenetic trees intentionally remain in concrete result models.
    """

    result_id: str
    name: str
    result_type: AnalysisResultType
    parent_dataset_id: str
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _required_text(self.result_id, "result_id")
        _required_text(self.name, "name")
        if not isinstance(self.result_type, AnalysisResultType):
            raise ValueError("result_type must be an AnalysisResultType")
        _required_text(self.parent_dataset_id, "parent_dataset_id")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))
