"""Adapters that derive common pair-alignment views from existing read models."""

from core.assembly_models import AssemblyReadView, ReadOrientation
from core.models import SangerRead
from core.reverse_complement import (
    ReverseComplementView,
    build_reverse_complement_view,
)


def build_forward_assembly_view(read: SangerRead) -> AssemblyReadView:
    """Create an assembly-direction Forward view from one trimmed read.

    The source read is not modified.  The validation ensures that raw index
    and raw trace mappings are restored from the current trim interval rather
    than inferred from independently edited values.
    """

    _validate_trimmed_read_for_forward_view(read)
    length = len(read.trimmed_sequence)
    assembly_indexes = range(length)

    return AssemblyReadView(
        source_filename=read.filename,
        orientation=ReadOrientation.FORWARD,
        sequence=read.trimmed_sequence,
        quality=read.trimmed_quality,
        assembly_to_trimmed_index=assembly_indexes,
        assembly_to_raw_index=(read.trim_start + index for index in assembly_indexes),
        assembly_to_raw_trace_position=(
            read.base_positions[read.trim_start + index]
            for index in assembly_indexes
        ),
        assembly_to_trimmed_trace_position=read.trimmed_base_positions,
    )


def build_reverse_assembly_view(read: SangerRead) -> AssemblyReadView:
    """Create an assembly-direction Reverse view using ``reverse_complement``."""

    return adapt_reverse_complement_view(build_reverse_complement_view(read))


def adapt_reverse_complement_view(
    reverse_view: ReverseComplementView,
) -> AssemblyReadView:
    """Add pair orientation to an existing immutable reverse-complement view."""

    if not isinstance(reverse_view, ReverseComplementView):
        raise ValueError("reverse_view must be a ReverseComplementView")
    return AssemblyReadView(
        source_filename=reverse_view.source_filename,
        orientation=ReadOrientation.REVERSE,
        sequence=reverse_view.sequence,
        quality=reverse_view.quality,
        assembly_to_trimmed_index=reverse_view.assembly_to_trimmed_index,
        assembly_to_raw_index=reverse_view.assembly_to_raw_index,
        assembly_to_raw_trace_position=reverse_view.assembly_to_raw_trace_position,
        assembly_to_trimmed_trace_position=(
            reverse_view.assembly_to_trimmed_trace_position
        ),
    )


def _validate_trimmed_read_for_forward_view(read: SangerRead) -> None:
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

    if not isinstance(read.sequence, str):
        raise ValueError("sequence must be a string")
    if not isinstance(read.trimmed_sequence, str) or not read.trimmed_sequence:
        raise ValueError("trimmed_sequence must be a non-empty string")
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
