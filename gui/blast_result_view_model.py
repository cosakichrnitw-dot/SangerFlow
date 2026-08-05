"""Read-only GUI projection of an immutable :class:`BlastResultDataset`."""

from __future__ import annotations

from dataclasses import dataclass

from core.blast_result import BlastHit, BlastResultDataset


@dataclass(frozen=True)
class BlastResultSummaryRow:
    """The first-ranked hit displayed for one BLAST query."""

    query_id: str
    top_accession: str
    top_scientific_name: str
    top_organism: str
    identity: float
    coverage: float
    evalue: float


@dataclass(frozen=True)
class BlastResultViewModel:
    """A display-only adapter over a non-empty immutable BLAST result."""

    blast_result: BlastResultDataset

    def __post_init__(self) -> None:
        if not isinstance(self.blast_result, BlastResultDataset):
            raise ValueError("blast_result must be a BlastResultDataset")
        if not self.blast_result.hits:
            raise ValueError("blast_result must contain at least one hit to view")

    @classmethod
    def from_result(cls, blast_result: BlastResultDataset) -> "BlastResultViewModel":
        return cls(blast_result=blast_result)

    def summary_rows(self) -> tuple[BlastResultSummaryRow, ...]:
        """Return one top-hit display row per query in first-hit order."""

        return tuple(
            _summary_row(query_id, self.blast_result.get_hits(query_id)[0])
            for query_id in self.blast_result.query_ids()
        )

    def get_hits(self, query_id: str) -> tuple[BlastHit, ...]:
        """Return the immutable hits for one query in their stored order."""

        return self.blast_result.get_hits(query_id)


def _summary_row(query_id: str, top_hit: BlastHit) -> BlastResultSummaryRow:
    return BlastResultSummaryRow(
        query_id=query_id,
        top_accession=top_hit.hit_accession,
        top_scientific_name=top_hit.scientific_name,
        top_organism=top_hit.organism,
        identity=top_hit.identity,
        coverage=top_hit.query_coverage,
        evalue=top_hit.evalue,
    )
