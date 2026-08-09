"""Partition definitions derived from immutable AlignmentDataset marker regions."""

from __future__ import annotations

from dataclasses import dataclass

from core.alignment_dataset import AlignmentDataset, MarkerRegion


@dataclass(frozen=True)
class PartitionDefinition:
    """Validated named alignment partitions in stable marker-region order."""

    regions: tuple[MarkerRegion, ...]

    @property
    def iqtree(self) -> str:
        """IQ-TREE-compatible named ranges, one partition per line."""
        return "\n".join(
            f"{region.name} = {region.start}-{region.end}" for region in self.regions
        )

    @property
    def raxml(self) -> str:
        """RAxML DNA partition declarations, one partition per line."""
        return "\n".join(
            f"DNA, {region.name} = {region.start}-{region.end}" for region in self.regions
        )

    @property
    def nexus_charset(self) -> str:
        """NEXUS CHARSET declarations suitable for a ``BEGIN SETS`` block."""
        return "\n".join(
            f"CHARSET {region.name} = {region.start}-{region.end};"
            for region in self.regions
        )


def create_partition_definition(alignment_dataset: AlignmentDataset) -> PartitionDefinition:
    """Return non-overlapping partitions from an AlignmentDataset's markers.

    Region coordinates are 1-based and inclusive.  AlignmentDataset itself
    validates individual region ranges; this export boundary additionally
    rejects overlap because partition-based phylogenetic programs treat each
    column as belonging to at most one partition in this workflow.
    """
    if not isinstance(alignment_dataset, AlignmentDataset):
        raise ValueError("alignment_dataset must be an AlignmentDataset")
    regions = alignment_dataset.marker_regions
    if not regions:
        raise ValueError("alignment_dataset must contain at least one marker region")
    _validate_non_overlapping_regions(regions, alignment_dataset.length)
    return PartitionDefinition(regions=regions)


def _validate_non_overlapping_regions(
    regions: tuple[MarkerRegion, ...],
    alignment_length: int,
) -> None:
    previous_end = 0
    for region in sorted(regions, key=lambda value: (value.start, value.end, value.name)):
        if region.start < 1 or region.end < region.start or region.end > alignment_length:
            raise ValueError("marker region is outside the alignment range")
        if region.start <= previous_end:
            raise ValueError("marker regions must not overlap")
        previous_end = region.end
