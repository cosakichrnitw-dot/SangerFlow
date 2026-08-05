"""Derived assembly-orientation views for trimmed reverse Sanger reads.

The functions in this module never write to :class:`core.models.SangerRead`.
They validate the current trimming invariants before exposing mappings back to
the original read, rather than inferring coordinates from incomplete data.
"""

from dataclasses import dataclass
from typing import Tuple

from core.models import SangerRead


_IUPAC_COMPLEMENT = {
    "A": "T",
    "C": "G",
    "G": "C",
    "T": "A",
    "R": "Y",
    "Y": "R",
    "S": "S",
    "W": "W",
    "K": "M",
    "M": "K",
    "B": "V",
    "D": "H",
    "H": "D",
    "V": "B",
    "N": "N",
}


@dataclass(frozen=True)
class ReverseComplementView:
    """A non-mutating assembly-direction representation of one reverse read.

    All sequence indexes are 0-based.  Each mapping tuple is indexed by the
    assembly-direction index.  ``trimmed_trace_positions`` are positions in
    the current trimmed chromatogram, while ``raw_trace_positions`` are PLOC
    positions in the untrimmed AB1 trace coordinate system.
    """

    source_filename: str
    sequence: str
    quality: Tuple[object, ...]
    assembly_to_trimmed_index: Tuple[int, ...]
    assembly_to_raw_index: Tuple[int, ...]
    assembly_to_raw_trace_position: Tuple[object, ...]
    assembly_to_trimmed_trace_position: Tuple[object, ...]

    @property
    def length(self) -> int:
        """Return the number of assembly-direction bases."""

        return len(self.sequence)


def build_reverse_complement_view(read: SangerRead) -> ReverseComplementView:
    """Build a validated reverse-complement view from a trimmed reverse read.

    Standard DNA IUPAC ambiguity symbols (``RYSWKMBDHVN``) are supported,
    case-insensitively.  ``N`` remains ``N``.  Other characters, including
    RNA ``U`` and alignment gaps, are rejected because they are not valid
    trimmed DNA base calls for this view.

    The function requires the current ``trim_start`` / ``trim_end`` interval
    to exactly describe ``trimmed_sequence`` in the raw read.  This makes the
    returned raw-index and raw-trace mappings exact rather than inferred.
    """

    _validate_trimmed_read(read)

    trimmed_sequence = read.trimmed_sequence
    length = len(trimmed_sequence)
    assembly_to_trimmed_index = tuple(range(length - 1, -1, -1))

    try:
        sequence = "".join(
            _IUPAC_COMPLEMENT[trimmed_sequence[index].upper()]
            for index in assembly_to_trimmed_index
        )
    except KeyError as error:
        invalid_base = error.args[0]
        raise ValueError(
            f"Unsupported trimmed base character: {invalid_base!r}"
        ) from None

    assembly_to_raw_index = tuple(
        read.trim_start + trimmed_index
        for trimmed_index in assembly_to_trimmed_index
    )

    return ReverseComplementView(
        source_filename=read.filename,
        sequence=sequence,
        quality=tuple(read.trimmed_quality[index] for index in assembly_to_trimmed_index),
        assembly_to_trimmed_index=assembly_to_trimmed_index,
        assembly_to_raw_index=assembly_to_raw_index,
        assembly_to_raw_trace_position=tuple(
            read.base_positions[raw_index] for raw_index in assembly_to_raw_index
        ),
        assembly_to_trimmed_trace_position=tuple(
            read.trimmed_base_positions[trimmed_index]
            for trimmed_index in assembly_to_trimmed_index
        ),
    )


def _validate_trimmed_read(read: SangerRead) -> None:
    """Validate the invariants required for exact coordinate restoration."""

    required_values = {
        "sequence": read.sequence,
        "quality": read.quality,
        "base_positions": read.base_positions,
        "trimmed_sequence": read.trimmed_sequence,
        "trimmed_quality": read.trimmed_quality,
        "trimmed_base_positions": read.trimmed_base_positions,
    }
    missing = [name for name, value in required_values.items() if value is None]
    if missing:
        raise ValueError(f"Missing required read data: {', '.join(missing)}")

    if not isinstance(read.trimmed_sequence, str) or not read.trimmed_sequence:
        raise ValueError("trimmed_sequence must be a non-empty string")
    if not isinstance(read.sequence, str):
        raise ValueError("sequence must be a string")
    if not isinstance(read.trim_start, int) or isinstance(read.trim_start, bool):
        raise ValueError("trim_start must be an integer")
    if not isinstance(read.trim_end, int) or isinstance(read.trim_end, bool):
        raise ValueError("trim_end must be an integer")

    start = read.trim_start
    end = read.trim_end
    if start < 0 or end < start or end > len(read.sequence):
        raise ValueError("trim_start and trim_end are outside the raw sequence")

    trimmed_length = len(read.trimmed_sequence)
    if end - start != trimmed_length:
        raise ValueError("trim interval length does not match trimmed_sequence")
    if len(read.trimmed_quality) != trimmed_length:
        raise ValueError("trimmed_sequence and trimmed_quality lengths differ")
    if len(read.trimmed_base_positions) != trimmed_length:
        raise ValueError(
            "trimmed_sequence and trimmed_base_positions lengths differ"
        )
    if len(read.quality) != len(read.sequence):
        raise ValueError("sequence and quality lengths differ")
    if len(read.base_positions) != len(read.sequence):
        raise ValueError("sequence and base_positions lengths differ")
    if read.sequence[start:end].upper() != read.trimmed_sequence.upper():
        raise ValueError("trimmed_sequence does not match the raw trim interval")
