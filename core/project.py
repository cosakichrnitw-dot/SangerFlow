"""Immutable in-memory project values for grouping sequence datasets.

Projects only describe dataset membership and derivation relationships.  They
do not own dataset contents, persist files, or run analyses.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from core.analysis_result import AnalysisResult, AnalysisResultType
from core.sequence_dataset import SequenceDataset


class DerivationType(str, Enum):
    """Known ways a project dataset can have been derived."""

    IMPORTED = "IMPORTED"
    TRIMMED_FROM_READS = "TRIMMED_FROM_READS"
    CONSENSUS_FROM_PAIRS = "CONSENSUS_FROM_PAIRS"
    REVIEWED_FROM_CONSENSUS = "REVIEWED_FROM_CONSENSUS"
    ALIGNED_WITH_MAFFT = "ALIGNED_WITH_MAFFT"
    SUBSET_FROM_DATASET = "SUBSET_FROM_DATASET"


def _freeze_metadata(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class ProjectDatasetEntry:
    """An immutable project-local label and lineage link for one dataset."""

    dataset: SequenceDataset
    display_name: str
    parent_dataset_id: str | None = None
    derivation_type: DerivationType | None = None
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dataset, SequenceDataset):
            raise ValueError("dataset must be a SequenceDataset")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("display_name must be a non-empty string")
        if self.parent_dataset_id is not None:
            if not isinstance(self.parent_dataset_id, str) or not self.parent_dataset_id.strip():
                raise ValueError("parent_dataset_id must be a non-empty string or None")
            if self.parent_dataset_id == self.dataset.dataset_id:
                raise ValueError("a dataset cannot be its own parent")
        if self.derivation_type is not None and not isinstance(self.derivation_type, DerivationType):
            raise ValueError("derivation_type must be a DerivationType or None")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


@dataclass(frozen=True)
class ProjectAnalysisEntry:
    """An immutable project-local label for one analysis result.

    The entry retains the original ``AnalysisResult`` object instead of
    duplicating or modifying its payload.  Its convenience properties expose
    the result identity and source-dataset lineage needed by Project callers.
    """

    analysis_result: AnalysisResult
    display_name: str
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.analysis_result, AnalysisResult):
            raise ValueError("analysis_result must be an AnalysisResult")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("display_name must be a non-empty string")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @property
    def result_id(self) -> str:
        return self.analysis_result.result_id

    @property
    def result_type(self) -> AnalysisResultType:
        return self.analysis_result.result_type

    @property
    def parent_dataset_id(self) -> str:
        return self.analysis_result.parent_dataset_id


@dataclass(frozen=True)
class Project:
    """An immutable ordered collection of datasets and their lineage links."""

    project_id: str
    name: str
    dataset_entries: tuple[ProjectDatasetEntry, ...] = ()
    metadata: Mapping[str, object] | None = None
    analysis_results: tuple[ProjectAnalysisEntry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, str) or not self.project_id.strip():
            raise ValueError("project_id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")

        entries = tuple(self.dataset_entries)
        if any(not isinstance(entry, ProjectDatasetEntry) for entry in entries):
            raise ValueError("dataset_entries must contain only ProjectDatasetEntry values")
        analysis_results = tuple(self.analysis_results)
        if any(not isinstance(entry, ProjectAnalysisEntry) for entry in analysis_results):
            raise ValueError("analysis_results must contain only ProjectAnalysisEntry values")
        object.__setattr__(self, "dataset_entries", entries)
        object.__setattr__(self, "analysis_results", analysis_results)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))
        self._validate_lineage()
        self._validate_analysis_results()

    @classmethod
    def create(
        cls,
        project_id: str,
        name: str,
        metadata: Mapping[str, object] | None = None,
    ) -> "Project":
        """Create an empty project; empty project membership is allowed."""

        return cls(project_id=project_id, name=name, metadata=metadata)

    @property
    def dataset_count(self) -> int:
        return len(self.dataset_entries)

    @property
    def dataset_ids(self) -> tuple[str, ...]:
        return tuple(entry.dataset.dataset_id for entry in self.dataset_entries)

    @property
    def analysis_result_count(self) -> int:
        return len(self.analysis_results)

    @property
    def analysis_result_ids(self) -> tuple[str, ...]:
        return tuple(entry.result_id for entry in self.analysis_results)

    def add_dataset(
        self,
        dataset: SequenceDataset,
        *,
        display_name: str | None = None,
        parent_dataset_id: str | None = None,
        derivation_type: DerivationType | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "Project":
        """Return a new project with ``dataset`` appended in input order."""

        if not isinstance(dataset, SequenceDataset):
            raise ValueError("dataset must be a SequenceDataset")
        if dataset.dataset_id in self.dataset_ids:
            raise ValueError(f"dataset_id already exists in project: {dataset.dataset_id}")
        if parent_dataset_id == dataset.dataset_id:
            raise ValueError("a dataset cannot be its own parent")
        if parent_dataset_id is not None and not self.has_dataset(parent_dataset_id):
            raise ValueError(f"parent_dataset_id does not exist in project: {parent_dataset_id}")

        entry = ProjectDatasetEntry(
            dataset=dataset,
            display_name=dataset.name if display_name is None else display_name,
            parent_dataset_id=parent_dataset_id,
            derivation_type=derivation_type,
            metadata=metadata,
        )
        return replace(self, dataset_entries=self.dataset_entries + (entry,))

    def get_entry(self, dataset_id: str) -> ProjectDatasetEntry:
        for entry in self.dataset_entries:
            if entry.dataset.dataset_id == dataset_id:
                return entry
        raise KeyError(dataset_id)

    def get_dataset(self, dataset_id: str) -> SequenceDataset:
        return self.get_entry(dataset_id).dataset

    def has_dataset(self, dataset_id: str) -> bool:
        return dataset_id in self.dataset_ids

    def add_analysis_result(
        self,
        analysis_result: AnalysisResult,
        *,
        display_name: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "Project":
        """Return a new project with an analysis result appended.

        Results are managed independently of datasets, but their parent
        dataset must already be present in the project to preserve lineage.
        """

        if not isinstance(analysis_result, AnalysisResult):
            raise ValueError("analysis_result must be an AnalysisResult")
        if self.has_analysis_result(analysis_result.result_id):
            raise ValueError(
                "result_id already exists in project: " f"{analysis_result.result_id}"
            )
        if not self.has_dataset(analysis_result.parent_dataset_id):
            raise ValueError(
                "parent_dataset_id does not exist in project: "
                f"{analysis_result.parent_dataset_id}"
            )
        entry = ProjectAnalysisEntry(
            analysis_result=analysis_result,
            display_name=analysis_result.name if display_name is None else display_name,
            metadata=metadata,
        )
        return replace(self, analysis_results=self.analysis_results + (entry,))

    def get_analysis_entry(self, result_id: str) -> ProjectAnalysisEntry:
        for entry in self.analysis_results:
            if entry.result_id == result_id:
                return entry
        raise KeyError(result_id)

    def get_analysis_result(self, result_id: str) -> AnalysisResult:
        return self.get_analysis_entry(result_id).analysis_result

    def has_analysis_result(self, result_id: str) -> bool:
        return result_id in self.analysis_result_ids

    def remove_analysis_result(self, result_id: str) -> "Project":
        """Return a new project without one analysis result entry."""

        self.get_analysis_entry(result_id)
        return replace(
            self,
            analysis_results=tuple(
                entry for entry in self.analysis_results if entry.result_id != result_id
            ),
        )

    def analysis_lineage(self, result_id: str) -> tuple[str, ...]:
        """Return source dataset ancestry followed by the analysis result ID."""

        entry = self.get_analysis_entry(result_id)
        return self.lineage(entry.parent_dataset_id) + (entry.result_id,)

    def rename_dataset(self, dataset_id: str, new_display_name: str) -> "Project":
        entry = self.get_entry(dataset_id)
        renamed_entry = replace(entry, display_name=new_display_name)
        entries = tuple(
            renamed_entry if current.dataset.dataset_id == dataset_id else current
            for current in self.dataset_entries
        )
        return replace(self, dataset_entries=entries)

    def remove_dataset(self, dataset_id: str) -> "Project":
        """Return a new project without a leaf dataset.

        Parents with children cannot be removed.  There is no cascade delete in
        this prototype, so callers must first remove or re-derive child data.
        """

        self.get_entry(dataset_id)
        children = self.child_dataset_ids(dataset_id)
        if children:
            raise ValueError(
                f"cannot remove dataset '{dataset_id}' because children exist: {children}"
            )
        dependent_results = tuple(
            entry.result_id
            for entry in self.analysis_results
            if entry.parent_dataset_id == dataset_id
        )
        if dependent_results:
            raise ValueError(
                f"cannot remove dataset '{dataset_id}' because analysis results exist: "
                f"{dependent_results}"
            )
        return replace(
            self,
            dataset_entries=tuple(
                entry for entry in self.dataset_entries if entry.dataset.dataset_id != dataset_id
            ),
        )

    def child_dataset_ids(self, parent_dataset_id: str) -> tuple[str, ...]:
        return tuple(
            entry.dataset.dataset_id
            for entry in self.dataset_entries
            if entry.parent_dataset_id == parent_dataset_id
        )

    def lineage(self, dataset_id: str) -> tuple[str, ...]:
        """Return ancestor IDs followed by ``dataset_id`` itself."""

        entry = self.get_entry(dataset_id)
        lineage = [entry.dataset.dataset_id]
        while entry.parent_dataset_id is not None:
            entry = self.get_entry(entry.parent_dataset_id)
            lineage.append(entry.dataset.dataset_id)
        return tuple(reversed(lineage))

    def _validate_lineage(self) -> None:
        ids = self.dataset_ids
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate dataset_id values are not allowed in a project")

        known_ids = set(ids)
        for entry in self.dataset_entries:
            if entry.parent_dataset_id is not None and entry.parent_dataset_id not in known_ids:
                raise ValueError(
                    "parent_dataset_id does not exist in project: "
                    f"{entry.parent_dataset_id}"
                )

        for dataset_id in ids:
            visited: set[str] = set()
            current_id: str | None = dataset_id
            while current_id is not None:
                if current_id in visited:
                    raise ValueError("project dataset lineage contains a cycle")
                visited.add(current_id)
                current_id = self.get_entry(current_id).parent_dataset_id

    def _validate_analysis_results(self) -> None:
        result_ids = self.analysis_result_ids
        if len(set(result_ids)) != len(result_ids):
            raise ValueError("duplicate result_id values are not allowed in a project")
        for entry in self.analysis_results:
            if not self.has_dataset(entry.parent_dataset_id):
                raise ValueError(
                    "analysis result parent_dataset_id does not exist in project: "
                    f"{entry.parent_dataset_id}"
                )
