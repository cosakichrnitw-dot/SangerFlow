"""Immutable data models for future Forward/Reverse pair alignment results.

This module intentionally contains no alignment, consensus, metric, or GUI
logic.  It stores validated assembly-direction views and alignment columns so
that later stages can trace every non-gap column back to its source read.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Integral, Real
from typing import Optional, Sequence, Tuple


class ReadOrientation(str, Enum):
    """The biological read role within a Forward/Reverse pair."""

    FORWARD = "FORWARD"
    REVERSE = "REVERSE"


@dataclass(frozen=True)
class AssemblyReadView:
    """A validated, assembly-direction representation of one trimmed read.

    All mappings are indexed by 0-based assembly index.  The view owns no
    chromatogram trace data and never mutates the source ``SangerRead``.
    """

    source_filename: str
    orientation: ReadOrientation
    sequence: str
    quality: Sequence[Real]
    assembly_to_trimmed_index: Sequence[Integral]
    assembly_to_raw_index: Sequence[Integral]
    assembly_to_raw_trace_position: Sequence[Integral]
    assembly_to_trimmed_trace_position: Sequence[Integral]

    def __post_init__(self) -> None:
        if not isinstance(self.source_filename, str) or not self.source_filename:
            raise ValueError("source_filename must be a non-empty string")
        if not isinstance(self.orientation, ReadOrientation):
            raise ValueError("orientation must be a ReadOrientation")
        if not isinstance(self.sequence, str) or not self.sequence:
            raise ValueError("sequence must be a non-empty string")

        quality = tuple(self.quality)
        mappings = {
            "assembly_to_trimmed_index": tuple(self.assembly_to_trimmed_index),
            "assembly_to_raw_index": tuple(self.assembly_to_raw_index),
            "assembly_to_raw_trace_position": tuple(
                self.assembly_to_raw_trace_position
            ),
            "assembly_to_trimmed_trace_position": tuple(
                self.assembly_to_trimmed_trace_position
            ),
        }
        expected_length = len(self.sequence)
        if len(quality) != expected_length:
            raise ValueError("sequence and quality lengths differ")
        for name, values in mappings.items():
            if len(values) != expected_length:
                raise ValueError(f"sequence and {name} lengths differ")

        for value in quality:
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError("quality values must be finite numbers greater than or equal to zero")
        for name, values in mappings.items():
            for value in values:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, Integral)
                    or value < 0
                ):
                    raise ValueError(f"{name} values must be non-negative integers")

        object.__setattr__(self, "quality", quality)
        for name, values in mappings.items():
            object.__setattr__(self, name, tuple(int(value) for value in values))

    @property
    def length(self) -> int:
        """Return the number of bases in assembly direction."""

        return len(self.sequence)

    def coordinate_at(self, assembly_index: int) -> "ReadCoordinate":
        """Return immutable source coordinates for one 0-based assembly index."""

        _require_non_negative_index("assembly_index", assembly_index)
        if assembly_index >= self.length:
            raise IndexError("assembly_index is outside the AssemblyReadView")
        return ReadCoordinate(
            assembly_index=assembly_index,
            trimmed_index=self.assembly_to_trimmed_index[assembly_index],
            raw_index=self.assembly_to_raw_index[assembly_index],
            raw_trace_position=self.assembly_to_raw_trace_position[assembly_index],
            trimmed_trace_position=self.assembly_to_trimmed_trace_position[
                assembly_index
            ],
        )


@dataclass(frozen=True)
class ReadCoordinate:
    """One non-gap column's traceable coordinates in a source read."""

    assembly_index: int
    trimmed_index: int
    raw_index: int
    raw_trace_position: int
    trimmed_trace_position: int

    def __post_init__(self) -> None:
        for name in (
            "assembly_index",
            "trimmed_index",
            "raw_index",
            "raw_trace_position",
            "trimmed_trace_position",
        ):
            _require_non_negative_index(name, getattr(self, name))


@dataclass(frozen=True)
class AlignmentColumn:
    """One 0-based pair-alignment column.

    A ``None`` side is a gap.  A gap-gap column is invalid.  The coordinate
    objects retain all source information needed by a future provenance layer.
    """

    alignment_index: int
    forward: Optional[ReadCoordinate]
    reverse: Optional[ReadCoordinate]

    def __post_init__(self) -> None:
        _require_non_negative_index("alignment_index", self.alignment_index)
        if self.forward is None and self.reverse is None:
            raise ValueError("AlignmentColumn cannot contain a gap-gap column")
        if self.forward is not None and not isinstance(self.forward, ReadCoordinate):
            raise ValueError("forward must be a ReadCoordinate or None")
        if self.reverse is not None and not isinstance(self.reverse, ReadCoordinate):
            raise ValueError("reverse must be a ReadCoordinate or None")

    @property
    def forward_index(self) -> Optional[int]:
        """Return the Forward assembly index, or ``None`` for a gap."""

        return None if self.forward is None else self.forward.assembly_index

    @property
    def reverse_index(self) -> Optional[int]:
        """Return the Reverse assembly index, or ``None`` for a gap."""

        return None if self.reverse is None else self.reverse.assembly_index

    @property
    def forward_is_gap(self) -> bool:
        """Whether the Forward side is a gap."""

        return self.forward is None

    @property
    def reverse_is_gap(self) -> bool:
        """Whether the Reverse side is a gap."""

        return self.reverse is None


@dataclass(frozen=True)
class PairAlignment:
    """A validated alignment-column mapping for one Forward/Reverse pair.

    This class intentionally does not contain an alignment score, overlap
    metrics, consensus, or status.  Those belong to later processing stages.
    """

    forward_view: AssemblyReadView
    reverse_view: AssemblyReadView
    columns: Sequence[AlignmentColumn]

    def __post_init__(self) -> None:
        if not isinstance(self.forward_view, AssemblyReadView):
            raise ValueError("forward_view must be an AssemblyReadView")
        if not isinstance(self.reverse_view, AssemblyReadView):
            raise ValueError("reverse_view must be an AssemblyReadView")
        if self.forward_view.orientation is not ReadOrientation.FORWARD:
            raise ValueError("forward_view orientation must be FORWARD")
        if self.reverse_view.orientation is not ReadOrientation.REVERSE:
            raise ValueError("reverse_view orientation must be REVERSE")

        columns = tuple(self.columns)
        if not columns:
            raise ValueError("PairAlignment must contain at least one column")
        for expected_index, column in enumerate(columns):
            if not isinstance(column, AlignmentColumn):
                raise ValueError("columns must contain AlignmentColumn values")
            if column.alignment_index != expected_index:
                raise ValueError("alignment_index values must be contiguous and 0-based")

        self._validate_side(columns, "forward", self.forward_view)
        self._validate_side(columns, "reverse", self.reverse_view)
        if not any(
            column.forward is not None and column.reverse is not None
            for column in columns
        ):
            raise ValueError("PairAlignment must contain at least one overlap column")
        object.__setattr__(self, "columns", columns)

    @staticmethod
    def _validate_side(
        columns: Tuple[AlignmentColumn, ...],
        side_name: str,
        view: AssemblyReadView,
    ) -> None:
        observed_indexes = []
        for column in columns:
            coordinate = getattr(column, side_name)
            if coordinate is None:
                continue
            expected = view.coordinate_at(coordinate.assembly_index)
            if coordinate != expected:
                raise ValueError(
                    f"{side_name} coordinate does not match its AssemblyReadView"
                )
            observed_indexes.append(coordinate.assembly_index)

        expected_indexes = list(range(view.length))
        if observed_indexes != expected_indexes:
            raise ValueError(
                f"{side_name} assembly indexes must cover the complete AssemblyReadView"
            )

    @property
    def length(self) -> int:
        """Return the number of alignment columns."""

        return len(self.columns)

    def column_at(self, alignment_index: int) -> AlignmentColumn:
        """Return one 0-based alignment column."""

        _require_non_negative_index("alignment_index", alignment_index)
        if alignment_index >= self.length:
            raise IndexError("alignment_index is outside the PairAlignment")
        return self.columns[alignment_index]


def _require_non_negative_index(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
