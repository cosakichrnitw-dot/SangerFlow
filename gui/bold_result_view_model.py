"""Read-only GUI projection of an immutable :class:`BoldResultDataset`."""

from __future__ import annotations

from dataclasses import dataclass

from core.bold_result import BoldHit, BoldResultDataset


@dataclass(frozen=True)
class BoldResultSummaryRow:
    """The first BOLD reference hit displayed for one query."""

    query_id: str
    species_name: str | None
    genus: str | None
    similarity: float | None
    bin_uri: str | None


@dataclass(frozen=True)
class BoldResultViewModel:
    """A display-only adapter over a non-empty immutable BOLD result."""

    bold_result: BoldResultDataset

    def __post_init__(self) -> None:
        if not isinstance(self.bold_result, BoldResultDataset):
            raise ValueError("bold_result must be a BoldResultDataset")
        if not self.bold_result.hits:
            raise ValueError("bold_result must contain at least one hit to view")

    @classmethod
    def from_result(cls, bold_result: BoldResultDataset) -> "BoldResultViewModel":
        return cls(bold_result=bold_result)

    def summary_rows(self) -> tuple[BoldResultSummaryRow, ...]:
        """Return one first-hit display row per query in stored query order."""

        return tuple(
            _summary_row(query_id, self.bold_result.get_hits(query_id)[0])
            for query_id in self.bold_result.query_ids()
        )

    def get_hits(self, query_id: str) -> tuple[BoldHit, ...]:
        """Return immutable BOLD hits for one query in their stored order."""

        return self.bold_result.get_hits(query_id)


def _summary_row(query_id: str, top_hit: BoldHit) -> BoldResultSummaryRow:
    return BoldResultSummaryRow(
        query_id=query_id,
        species_name=top_hit.species_name,
        genus=top_hit.genus,
        similarity=top_hit.similarity,
        bin_uri=top_hit.bin_uri,
    )
