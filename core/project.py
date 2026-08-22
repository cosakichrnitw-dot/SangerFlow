"""Immutable in-memory project values for grouping sequence datasets.

Projects only describe dataset membership and derivation relationships.  They
do not own dataset contents, persist files, or run analyses.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from core.alignment_dataset import AlignmentDataset
from core.analysis_result import AnalysisResult, AnalysisResultType
from core.lineage import LineageRelation, LineageRelationType, LineageSourceKind
from core.sequence_dataset import SequenceDataset

ProjectDataset = SequenceDataset | AlignmentDataset


class DerivationType(str, Enum):
    """Known ways a project dataset can have been derived."""

    IMPORTED = "IMPORTED"
    TRIMMED_FROM_READS = "TRIMMED_FROM_READS"
    CONSENSUS_FROM_PAIRS = "CONSENSUS_FROM_PAIRS"
    REVIEWED_FROM_CONSENSUS = "REVIEWED_FROM_CONSENSUS"
    ALIGNED_WITH_MAFFT = "ALIGNED_WITH_MAFFT"
    ALIGNMENT_FROM_DATASET = "ALIGNMENT_FROM_DATASET"
    SUBSET_FROM_DATASET = "SUBSET_FROM_DATASET"


class RevisionState(str, Enum):
    """Workspace state of one immutable Dataset revision.

    This is deliberately independent of scientific lineage.  A revision can
    remain a scientific source after it has been superseded or archived.
    """

    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class RevisionOperation(str, Enum):
    """Documented user operation that created a Dataset revision."""

    IMPORTED = "IMPORTED"
    RECORD_RENAME = "RECORD_RENAME"
    BATCH_RENAME = "BATCH_RENAME"
    METADATA_MERGE = "METADATA_MERGE"
    SEQUENCE_EDIT = "SEQUENCE_EDIT"
    ALIGNMENT_EDIT = "ALIGNMENT_EDIT"
    OTHER = "OTHER"


def _freeze_metadata(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return MappingProxyType(dict(value))


def _is_project_dataset(value: object) -> bool:
    return isinstance(value, (SequenceDataset, AlignmentDataset))


def _dataset_id(dataset: ProjectDataset) -> str:
    if isinstance(dataset, SequenceDataset):
        return dataset.dataset_id
    return dataset.alignment_id


@dataclass(frozen=True)
class ProjectDatasetEntry:
    """An immutable Project-local label and typed dataset provenance.

    ``lineage_relations`` is the source of truth.  ``parent_dataset_id`` is
    retained only as a legacy/primary-parent compatibility value and is
    normalized from the first DATASET relation at construction time.
    """

    dataset: ProjectDataset
    display_name: str
    parent_dataset_id: str | None = None
    derivation_type: DerivationType | None = None
    metadata: Mapping[str, object] | None = None
    lineage_relations: tuple[LineageRelation, ...] = ()
    # Revision fields describe the Project workspace only.  They must never
    # be used as substitutes for LineageRelation or RecordProvenance.
    logical_id: str | None = None
    revision_number: int = 1
    revision_state: RevisionState = RevisionState.CURRENT
    revision_operation: RevisionOperation = RevisionOperation.IMPORTED
    supersedes_dataset_id: str | None = None

    def __post_init__(self) -> None:
        if not _is_project_dataset(self.dataset):
            raise ValueError("dataset must be a SequenceDataset or AlignmentDataset")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("display_name must be a non-empty string")
        legacy_parent_id = self.parent_dataset_id
        if legacy_parent_id is not None:
            if not isinstance(legacy_parent_id, str) or not legacy_parent_id.strip():
                raise ValueError("parent_dataset_id must be a non-empty string or None")
            if legacy_parent_id == _dataset_id(self.dataset):
                raise ValueError("a dataset cannot be its own parent")
        if self.derivation_type is not None and not isinstance(self.derivation_type, DerivationType):
            raise ValueError("derivation_type must be a DerivationType or None")
        logical_id = _dataset_id(self.dataset) if self.logical_id is None else self.logical_id
        if not isinstance(logical_id, str) or not logical_id.strip():
            raise ValueError("logical_id must be a non-empty string")
        if (
            not isinstance(self.revision_number, int)
            or isinstance(self.revision_number, bool)
            or self.revision_number < 1
        ):
            raise ValueError("revision_number must be an integer greater than or equal to 1")
        if not isinstance(self.revision_state, RevisionState):
            raise ValueError("revision_state must be a RevisionState")
        if not isinstance(self.revision_operation, RevisionOperation):
            raise ValueError("revision_operation must be a RevisionOperation")
        if self.supersedes_dataset_id is not None:
            if (
                not isinstance(self.supersedes_dataset_id, str)
                or not self.supersedes_dataset_id.strip()
            ):
                raise ValueError("supersedes_dataset_id must be a non-empty string or None")
            if self.supersedes_dataset_id == _dataset_id(self.dataset):
                raise ValueError("a dataset revision cannot supersede itself")
        relations = tuple(self.lineage_relations)
        if any(not isinstance(relation, LineageRelation) for relation in relations):
            raise ValueError("lineage_relations must contain only LineageRelation values")
        if not relations and legacy_parent_id is not None:
            relations = (
                LineageRelation(
                    source_kind=LineageSourceKind.DATASET,
                    source_id=legacy_parent_id,
                    relation_type=_legacy_relation_type(self.derivation_type),
                ),
            )
        if len({relation.identity for relation in relations}) != len(relations):
            raise ValueError("duplicate lineage relations are not allowed")
        dataset_sources = tuple(
            relation.source_id
            for relation in relations
            if relation.source_kind is LineageSourceKind.DATASET
        )
        primary_parent_id = dataset_sources[0] if dataset_sources else None
        if legacy_parent_id is not None and legacy_parent_id != primary_parent_id:
            raise ValueError("parent_dataset_id must match the primary Dataset lineage relation")
        if _dataset_id(self.dataset) in dataset_sources:
            raise ValueError("a dataset cannot be its own lineage source")
        object.__setattr__(self, "lineage_relations", relations)
        object.__setattr__(self, "parent_dataset_id", primary_parent_id)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))
        object.__setattr__(self, "logical_id", logical_id)


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
        self._validate_analysis_results()
        self._validate_lineage()
        self._validate_revisions()

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
        return tuple(_dataset_id(entry.dataset) for entry in self.dataset_entries)

    @property
    def analysis_result_count(self) -> int:
        return len(self.analysis_results)

    @property
    def analysis_result_ids(self) -> tuple[str, ...]:
        return tuple(entry.result_id for entry in self.analysis_results)

    def add_dataset(
        self,
        dataset: ProjectDataset,
        *,
        display_name: str | None = None,
        parent_dataset_id: str | None = None,
        derivation_type: DerivationType | None = None,
        metadata: Mapping[str, object] | None = None,
        lineage_relations: tuple[LineageRelation, ...] = (),
    ) -> "Project":
        """Return a new project with ``dataset`` appended in input order."""

        if not _is_project_dataset(dataset):
            raise ValueError("dataset must be a SequenceDataset or AlignmentDataset")
        dataset_id = _dataset_id(dataset)
        if dataset_id in self.dataset_ids:
            raise ValueError(f"dataset_id already exists in project: {dataset_id}")
        entry = ProjectDatasetEntry(
            dataset=dataset,
            display_name=dataset.name if display_name is None else display_name,
            parent_dataset_id=parent_dataset_id,
            derivation_type=derivation_type,
            metadata=metadata,
            lineage_relations=lineage_relations,
            logical_id=dataset_id,
            revision_number=1,
            revision_state=RevisionState.CURRENT,
            revision_operation=RevisionOperation.IMPORTED,
        )
        self._validate_entry_sources(entry)
        return replace(self, dataset_entries=self.dataset_entries + (entry,))

    def add_dataset_revision(
        self,
        previous_dataset_id: str,
        dataset: ProjectDataset,
        *,
        operation: RevisionOperation,
        display_name: str | None = None,
        parent_dataset_id: str | None = None,
        derivation_type: DerivationType | None = None,
        metadata: Mapping[str, object] | None = None,
        lineage_relations: tuple[LineageRelation, ...] = (),
    ) -> "Project":
        """Append a new immutable revision to an existing logical Dataset.

        The previously current revision is retained and becomes
        :attr:`RevisionState.SUPERSEDED`; neither scientific lineage nor
        payloads are rewritten.
        """

        if not _is_project_dataset(dataset):
            raise ValueError("dataset must be a SequenceDataset or AlignmentDataset")
        if not isinstance(operation, RevisionOperation):
            raise ValueError("operation must be a RevisionOperation")
        previous = self.get_entry(previous_dataset_id)
        if previous.revision_state is not RevisionState.CURRENT:
            raise ValueError("new revisions must supersede the current revision")
        dataset_id = _dataset_id(dataset)
        if dataset_id in self.dataset_ids:
            raise ValueError(f"dataset_id already exists in project: {dataset_id}")
        entry = ProjectDatasetEntry(
            dataset=dataset,
            display_name=dataset.name if display_name is None else display_name,
            parent_dataset_id=parent_dataset_id,
            derivation_type=derivation_type,
            metadata=metadata,
            lineage_relations=lineage_relations,
            logical_id=previous.logical_id,
            revision_number=previous.revision_number + 1,
            revision_state=RevisionState.CURRENT,
            revision_operation=operation,
            supersedes_dataset_id=previous_dataset_id,
        )
        self._validate_entry_sources(entry)
        superseded = replace(previous, revision_state=RevisionState.SUPERSEDED)
        entries = tuple(
            superseded if _dataset_id(current.dataset) == previous_dataset_id else current
            for current in self.dataset_entries
        )
        return replace(self, dataset_entries=entries + (entry,))

    def get_entry(self, dataset_id: str) -> ProjectDatasetEntry:
        for entry in self.dataset_entries:
            if _dataset_id(entry.dataset) == dataset_id:
                return entry
        raise KeyError(dataset_id)

    def get_dataset(self, dataset_id: str) -> ProjectDataset:
        return self.get_entry(dataset_id).dataset

    def has_dataset(self, dataset_id: str) -> bool:
        return dataset_id in self.dataset_ids

    @property
    def logical_dataset_ids(self) -> tuple[str, ...]:
        """Logical Dataset families in order of first Project appearance."""

        seen: set[str] = set()
        values: list[str] = []
        for entry in self.dataset_entries:
            if entry.logical_id not in seen:
                seen.add(entry.logical_id)
                values.append(entry.logical_id)
        return tuple(values)

    def current_dataset_entries(self) -> tuple[ProjectDatasetEntry, ...]:
        """Current, non-archived working revisions without hiding history APIs."""

        return tuple(
            entry
            for entry in self.dataset_entries
            if entry.revision_state is RevisionState.CURRENT
        )

    def current_dataset_entry(self, logical_id: str) -> ProjectDatasetEntry:
        for entry in self.current_dataset_entries():
            if entry.logical_id == logical_id:
                return entry
        raise KeyError(logical_id)

    def dataset_revision_history(self, logical_id: str) -> tuple[ProjectDatasetEntry, ...]:
        history = tuple(
            entry for entry in self.dataset_entries if entry.logical_id == logical_id
        )
        if not history:
            raise KeyError(logical_id)
        return tuple(sorted(history, key=lambda entry: entry.revision_number))

    def archived_dataset_entries(self) -> tuple[ProjectDatasetEntry, ...]:
        return tuple(
            entry
            for entry in self.dataset_entries
            if entry.revision_state is RevisionState.ARCHIVED
        )

    def is_current_revision(self, dataset_id: str) -> bool:
        return self.get_entry(dataset_id).revision_state is RevisionState.CURRENT

    def archive_logical_dataset(self, logical_id: str) -> "Project":
        """Hide a logical Dataset from future working-data queries.

        Archive is reversible workspace state; it neither deletes payloads nor
        weakens dependency validation.
        """

        current = self.current_dataset_entry(logical_id)
        archived = replace(current, revision_state=RevisionState.ARCHIVED)
        return replace(
            self,
            dataset_entries=tuple(
                archived if entry is current else entry for entry in self.dataset_entries
            ),
        )

    def restore_logical_dataset(self, logical_id: str) -> "Project":
        """Restore the archived tip of one logical Dataset as its current revision."""

        archived = tuple(
            entry
            for entry in self.dataset_entries
            if entry.logical_id == logical_id and entry.revision_state is RevisionState.ARCHIVED
        )
        if len(archived) != 1:
            raise KeyError(logical_id)
        restored = replace(archived[0], revision_state=RevisionState.CURRENT)
        return replace(
            self,
            dataset_entries=tuple(
                restored if entry is archived[0] else entry for entry in self.dataset_entries
            ),
        )

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
        dependent_datasets = tuple(
            _dataset_id(entry.dataset)
            for entry in self.dataset_entries
            if any(
                relation.source_kind is LineageSourceKind.ANALYSIS_RESULT
                and relation.source_id == result_id
                for relation in entry.lineage_relations
            )
        )
        if dependent_datasets:
            raise ValueError(
                f"cannot remove analysis result '{result_id}' because derived datasets exist: "
                f"{dependent_datasets}"
            )
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
            renamed_entry if _dataset_id(current.dataset) == dataset_id else current
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
                entry for entry in self.dataset_entries if _dataset_id(entry.dataset) != dataset_id
            ),
        )

    def child_dataset_ids(self, parent_dataset_id: str) -> tuple[str, ...]:
        return tuple(
            _dataset_id(entry.dataset)
            for entry in self.dataset_entries
            if any(
                relation.source_kind is LineageSourceKind.DATASET
                and relation.source_id == parent_dataset_id
                for relation in entry.lineage_relations
            )
        )

    def lineage(self, dataset_id: str) -> tuple[str, ...]:
        """Return ancestor IDs followed by ``dataset_id`` itself."""

        entry = self.get_entry(dataset_id)
        lineage = [_dataset_id(entry.dataset)]
        while entry.parent_dataset_id is not None:
            entry = self.get_entry(entry.parent_dataset_id)
            lineage.append(_dataset_id(entry.dataset))
        return tuple(reversed(lineage))

    def _validate_lineage(self) -> None:
        ids = self.dataset_ids
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate dataset_id values are not allowed in a project")

        for entry in self.dataset_entries:
            self._validate_entry_sources(entry)

        adjacency: dict[str, set[str]] = {f"dataset:{dataset_id}": set() for dataset_id in ids}
        adjacency.update({f"result:{entry.result_id}": set() for entry in self.analysis_results})
        for entry in self.dataset_entries:
            target = f"dataset:{_dataset_id(entry.dataset)}"
            for relation in entry.lineage_relations:
                source = _relation_node_id(relation)
                adjacency.setdefault(source, set()).add(target)
        for result in self.analysis_results:
            adjacency[f"dataset:{result.parent_dataset_id}"].add(f"result:{result.result_id}")
        _validate_acyclic(adjacency)

    def _validate_revisions(self) -> None:
        """Validate workspace revision chains independently of scientific DAGs."""

        by_logical_id: dict[str, list[ProjectDatasetEntry]] = {}
        entries_by_dataset_id = {
            _dataset_id(entry.dataset): entry for entry in self.dataset_entries
        }
        for entry in self.dataset_entries:
            by_logical_id.setdefault(entry.logical_id, []).append(entry)

        for logical_id, entries in by_logical_id.items():
            numbers = tuple(entry.revision_number for entry in entries)
            if len(set(numbers)) != len(numbers):
                raise ValueError(
                    f"duplicate revision_number in logical dataset '{logical_id}'"
                )
            current = tuple(
                entry for entry in entries if entry.revision_state is RevisionState.CURRENT
            )
            archived = tuple(
                entry for entry in entries if entry.revision_state is RevisionState.ARCHIVED
            )
            if len(current) > 1:
                raise ValueError(
                    f"logical dataset '{logical_id}' has more than one current revision"
                )
            if len(archived) > 1:
                raise ValueError(
                    f"logical dataset '{logical_id}' has more than one archived revision"
                )
            if current and archived:
                raise ValueError(
                    f"logical dataset '{logical_id}' cannot be current and archived"
                )

            child_ids: set[str] = set()
            for entry in entries:
                dataset_id = _dataset_id(entry.dataset)
                predecessor_id = entry.supersedes_dataset_id
                if entry.revision_number == 1 and predecessor_id is not None:
                    raise ValueError("revision 1 cannot supersede another dataset")
                if entry.revision_number > 1 and predecessor_id is None:
                    raise ValueError("revision_number greater than 1 requires supersedes_dataset_id")
                if predecessor_id is None:
                    continue
                predecessor = entries_by_dataset_id.get(predecessor_id)
                if predecessor is None:
                    raise ValueError(
                        f"supersedes_dataset_id does not exist in project: {predecessor_id}"
                    )
                if predecessor.logical_id != logical_id:
                    raise ValueError("supersedes_dataset_id must belong to the same logical_id")
                if predecessor.revision_number + 1 != entry.revision_number:
                    raise ValueError("revision_number must directly follow the superseded revision")
                child_ids.add(predecessor_id)

            tips = tuple(
                entry for entry in entries if _dataset_id(entry.dataset) not in child_ids
            )
            if len(tips) != 1:
                raise ValueError(
                    f"logical dataset '{logical_id}' revision history must have one tip"
                )
            tip = tips[0]
            if tip.revision_state not in {RevisionState.CURRENT, RevisionState.ARCHIVED}:
                raise ValueError("revision history tip must be CURRENT or ARCHIVED")
            if any(
                entry is not tip and entry.revision_state is not RevisionState.SUPERSEDED
                for entry in entries
            ):
                raise ValueError("non-tip dataset revisions must be SUPERSEDED")
            _validate_revision_chain_cycle(entries_by_dataset_id, entries)

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

    def _validate_entry_sources(self, entry: ProjectDatasetEntry) -> None:
        for relation in entry.lineage_relations:
            if relation.source_kind is LineageSourceKind.DATASET:
                if not self.has_dataset(relation.source_id):
                    raise ValueError(
                        "dataset lineage source does not exist in project: "
                        f"{relation.source_id}"
                    )
            elif not self.has_analysis_result(relation.source_id):
                raise ValueError(
                    "analysis-result lineage source does not exist in project: "
                    f"{relation.source_id}"
                )


def _legacy_relation_type(derivation_type: DerivationType | None) -> LineageRelationType:
    mapping = {
        DerivationType.SUBSET_FROM_DATASET: LineageRelationType.SUBSET_FROM_DATASET,
        DerivationType.ALIGNMENT_FROM_DATASET: LineageRelationType.ALIGNMENT_FROM_DATASET,
        DerivationType.ALIGNED_WITH_MAFFT: LineageRelationType.ALIGNMENT_FROM_DATASET,
        DerivationType.CONSENSUS_FROM_PAIRS: LineageRelationType.CONSENSUS_FROM_READS,
        DerivationType.REVIEWED_FROM_CONSENSUS: LineageRelationType.REVIEWED_FROM_CONSENSUS,
    }
    return mapping.get(derivation_type, LineageRelationType.LEGACY_PARENT_DATASET)


def _relation_node_id(relation: LineageRelation) -> str:
    prefix = "dataset" if relation.source_kind is LineageSourceKind.DATASET else "result"
    return f"{prefix}:{relation.source_id}"


def _validate_acyclic(adjacency: Mapping[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("project lineage contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for target in adjacency.get(node, set()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in adjacency:
        visit(node)


def _validate_revision_chain_cycle(
    entries_by_dataset_id: Mapping[str, ProjectDatasetEntry],
    entries: tuple[ProjectDatasetEntry, ...] | list[ProjectDatasetEntry],
) -> None:
    """Reject a revision cycle without involving scientific lineage edges."""

    family_ids = {_dataset_id(entry.dataset) for entry in entries}
    for entry in entries:
        seen: set[str] = set()
        current = entry
        while current.supersedes_dataset_id is not None:
            predecessor_id = current.supersedes_dataset_id
            if predecessor_id in seen:
                raise ValueError("dataset revision history contains a cycle")
            seen.add(predecessor_id)
            predecessor = entries_by_dataset_id.get(predecessor_id)
            # Existence and same-family checks are performed by the caller.
            if predecessor is None or predecessor_id not in family_ids:
                return
            current = predecessor
