"""Consensus-level multiple sequence alignment with explicit coordinate maps.

This module accepts independent, unaligned consensus candidates and delegates
multiple alignment to MAFFT. It does not import GUI, consensus-decision,
review, or export modules. The result is immutable and records only the
coordinate system needed by later display or review layers.
"""

from dataclasses import dataclass
from io import StringIO
from math import isclose
import shutil
import subprocess
from typing import Callable, Mapping, Optional, Sequence

from Bio import SeqIO


_CONSENSUS_SYMBOLS = frozenset("ACGTNRYSWKMBDHV")
_ALIGNED_SYMBOLS = _CONSENSUS_SYMBOLS | {"-"}


class MafftExecutableNotFoundError(RuntimeError):
    """Raised when MAFFT is unavailable and no alignment can be run."""


class ConsensusAlignmentExecutionError(RuntimeError):
    """Raised when MAFFT returns an error or invalid aligned FASTA."""


@dataclass(frozen=True)
class ConsensusAlignmentInput:
    """One unaligned consensus candidate supplied to MAFFT."""

    sample_id: str
    sequence: str
    metadata: Optional[Mapping[str, object]] = None

    def __post_init__(self) -> None:
        _validate_sample_id(self.sample_id)
        _validate_sequence(self.sequence, allowed_symbols=_CONSENSUS_SYMBOLS)
        if self.metadata is not None and not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a mapping or None")


@dataclass(frozen=True)
class AlignedConsensusSequence:
    """One original consensus and its aligned row with a gap-aware map."""

    sample_id: str
    original_sequence: str
    aligned_sequence: str
    consensus_position_mapping: tuple[Optional[int], ...]
    metadata: Optional[Mapping[str, object]] = None

    def __post_init__(self) -> None:
        _validate_sample_id(self.sample_id)
        _validate_sequence(self.original_sequence, allowed_symbols=_CONSENSUS_SYMBOLS)
        _validate_sequence(self.aligned_sequence, allowed_symbols=_ALIGNED_SYMBOLS)
        if len(self.consensus_position_mapping) != len(self.aligned_sequence):
            raise ValueError("consensus position mapping and aligned sequence lengths differ")
        expected_mapping = build_consensus_position_mapping(
            self.original_sequence,
            self.aligned_sequence,
        )
        if tuple(self.consensus_position_mapping) != expected_mapping:
            raise ValueError("consensus position mapping does not match aligned sequence")
        if self.metadata is not None and not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a mapping or None")

    def consensus_position_at(self, alignment_column: int) -> Optional[int]:
        """Return the original 0-based position, or ``None`` for a MAFFT gap."""

        return self.consensus_position_mapping[alignment_column]


@dataclass(frozen=True)
class AlignedConsensusSet:
    """Immutable multiple-alignment result for a set of consensus candidates."""

    sequences: tuple[AlignedConsensusSequence, ...]
    alignment_length: int
    gap_count: int
    gap_percentage: float
    alignment_id: Optional[str] = None

    def __post_init__(self) -> None:
        if len(self.sequences) < 2:
            raise ValueError("at least two aligned consensus sequences are required")
        if not isinstance(self.alignment_length, int) or self.alignment_length <= 0:
            raise ValueError("alignment_length must be a positive integer")
        sample_ids = tuple(sequence.sample_id for sequence in self.sequences)
        if len(set(sample_ids)) != len(sample_ids):
            raise ValueError("aligned consensus sample_id values must be unique")
        if any(
            len(sequence.aligned_sequence) != self.alignment_length
            for sequence in self.sequences
        ):
            raise ValueError("all aligned consensus sequences must have alignment_length")
        calculated_gap_count = sum(
            sequence.aligned_sequence.count("-") for sequence in self.sequences
        )
        if self.gap_count != calculated_gap_count:
            raise ValueError("gap_count does not match aligned consensus sequences")
        total_cells = self.alignment_length * len(self.sequences)
        calculated_gap_percentage = (calculated_gap_count / total_cells) * 100.0
        if not isclose(self.gap_percentage, calculated_gap_percentage):
            raise ValueError("gap_percentage does not match aligned consensus sequences")
        if self.alignment_id is not None and (
            not isinstance(self.alignment_id, str) or not self.alignment_id
        ):
            raise ValueError("alignment_id must be a non-empty string or None")

    @property
    def number_of_sequences(self) -> int:
        """Return the number of aligned sample rows."""

        return len(self.sequences)

    @property
    def aligned_sequences(self) -> tuple[str, ...]:
        """Return aligned strings in the same stable order as ``sequences``."""

        return tuple(sequence.aligned_sequence for sequence in self.sequences)

    @property
    def column_mappings(self) -> tuple[tuple[Optional[int], ...], ...]:
        """Return one alignment-column-to-consensus map per sample row."""

        return tuple(
            sequence.consensus_position_mapping for sequence in self.sequences
        )

    def sequence_for_sample(self, sample_id: str) -> AlignedConsensusSequence:
        """Return the aligned record for one known sample identifier."""

        for sequence in self.sequences:
            if sequence.sample_id == sample_id:
                return sequence
        raise KeyError(sample_id)


def run_consensus_alignment(
    sequences: Sequence[Mapping[str, object] | ConsensusAlignmentInput],
    *,
    mafft_executable: str = "mafft",
    alignment_id: Optional[str] = None,
    runner: Optional[Callable[..., object]] = None,
) -> AlignedConsensusSet:
    """Run MAFFT on consensus candidates and return gap-aware aligned records.

    MAFFT receives an in-memory FASTA document through standard input. No
    fallback alignment is produced: absence of MAFFT raises
    ``MafftExecutableNotFoundError`` with an actionable message.
    """

    inputs = _coerce_alignment_inputs(sequences)
    resolved_executable = shutil.which(mafft_executable)
    if resolved_executable is None:
        raise MafftExecutableNotFoundError(
            "MAFFT executable not found. Install MAFFT to enable consensus alignment."
        )
    execute = subprocess.run if runner is None else runner
    fasta_input = _format_input_fasta(inputs)
    try:
        result = execute(
            [resolved_executable, "--auto", "-"],
            input=fasta_input,
            text=True,
            capture_output=True,
        )
    except OSError as error:
        raise ConsensusAlignmentExecutionError(
            f"MAFFT execution failed: {error}"
        ) from error
    if getattr(result, "returncode", None) != 0:
        error_text = getattr(result, "stderr", "") or "unknown MAFFT error"
        raise ConsensusAlignmentExecutionError(f"MAFFT alignment failed: {error_text}")
    return _build_aligned_consensus_set(
        inputs,
        getattr(result, "stdout", ""),
        alignment_id=alignment_id,
    )


def build_consensus_position_mapping(
    original_sequence: str,
    aligned_sequence: str,
) -> tuple[Optional[int], ...]:
    """Map each aligned column to the original 0-based consensus position.

    MAFFT gaps are represented by ``None``. The non-gap aligned sequence must
    match the original sequence exactly; no position is inferred or repaired.
    """

    _validate_sequence(original_sequence, allowed_symbols=_CONSENSUS_SYMBOLS)
    _validate_sequence(aligned_sequence, allowed_symbols=_ALIGNED_SYMBOLS)
    mapping = []
    original_position = 0
    for base in aligned_sequence:
        if base == "-":
            mapping.append(None)
            continue
        if original_position >= len(original_sequence) or base != original_sequence[original_position]:
            raise ValueError("aligned non-gap sequence does not match original consensus")
        mapping.append(original_position)
        original_position += 1
    if original_position != len(original_sequence):
        raise ValueError("aligned sequence omits original consensus bases")
    return tuple(mapping)


def _coerce_alignment_inputs(
    sequences: Sequence[Mapping[str, object] | ConsensusAlignmentInput],
) -> tuple[ConsensusAlignmentInput, ...]:
    inputs = []
    for item in sequences:
        if isinstance(item, ConsensusAlignmentInput):
            alignment_input = item
        elif isinstance(item, Mapping):
            alignment_input = ConsensusAlignmentInput(
                sample_id=item.get("sample_id"),
                sequence=item.get("sequence"),
                metadata=item.get("metadata"),
            )
        else:
            raise ValueError("each consensus input must be a mapping or ConsensusAlignmentInput")
        inputs.append(alignment_input)
    if len(inputs) < 2:
        raise ValueError("at least two consensus sequences are required")
    sample_ids = tuple(alignment_input.sample_id for alignment_input in inputs)
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("consensus input sample_id values must be unique")
    return tuple(inputs)


def _format_input_fasta(inputs: Sequence[ConsensusAlignmentInput]) -> str:
    return "".join(
        f">{alignment_input.sample_id}\n{alignment_input.sequence}\n"
        for alignment_input in inputs
    )


def _build_aligned_consensus_set(
    inputs: Sequence[ConsensusAlignmentInput],
    mafft_fasta: str,
    *,
    alignment_id: Optional[str],
) -> AlignedConsensusSet:
    try:
        records = list(SeqIO.parse(StringIO(mafft_fasta), "fasta"))
    except ValueError as error:
        raise ConsensusAlignmentExecutionError(
            f"MAFFT returned invalid FASTA: {error}"
        ) from error
    if not records:
        raise ConsensusAlignmentExecutionError("MAFFT returned no aligned FASTA records")
    aligned_by_sample_id = {}
    for record in records:
        sample_id = str(record.id)
        if sample_id in aligned_by_sample_id:
            raise ConsensusAlignmentExecutionError(
                f"MAFFT returned duplicate sample_id: {sample_id}"
            )
        aligned_by_sample_id[sample_id] = str(record.seq).upper()
    input_sample_ids = {alignment_input.sample_id for alignment_input in inputs}
    if set(aligned_by_sample_id) != input_sample_ids:
        raise ConsensusAlignmentExecutionError(
            "MAFFT output sample IDs do not match consensus alignment input"
        )

    aligned_sequences = tuple(
        AlignedConsensusSequence(
            sample_id=alignment_input.sample_id,
            original_sequence=alignment_input.sequence,
            aligned_sequence=aligned_by_sample_id[alignment_input.sample_id],
            consensus_position_mapping=build_consensus_position_mapping(
                alignment_input.sequence,
                aligned_by_sample_id[alignment_input.sample_id],
            ),
            metadata=alignment_input.metadata,
        )
        for alignment_input in inputs
    )
    alignment_lengths = {len(sequence.aligned_sequence) for sequence in aligned_sequences}
    if len(alignment_lengths) != 1:
        raise ConsensusAlignmentExecutionError(
            "MAFFT output rows do not have a common alignment length"
        )
    alignment_length = alignment_lengths.pop()
    gap_count = sum(sequence.aligned_sequence.count("-") for sequence in aligned_sequences)
    gap_percentage = (gap_count / (alignment_length * len(aligned_sequences))) * 100.0
    return AlignedConsensusSet(
        sequences=aligned_sequences,
        alignment_length=alignment_length,
        gap_count=gap_count,
        gap_percentage=gap_percentage,
        alignment_id=alignment_id,
    )


def _validate_sample_id(sample_id: object) -> None:
    if not isinstance(sample_id, str) or not sample_id:
        raise ValueError("sample_id must be a non-empty string")
    if any(character.isspace() for character in sample_id):
        raise ValueError("sample_id must not contain whitespace for FASTA round-tripping")


def _validate_sequence(sequence: object, *, allowed_symbols: frozenset[str]) -> None:
    if not isinstance(sequence, str) or not sequence:
        raise ValueError("sequence must be a non-empty string")
    unsupported = set(sequence.upper()) - allowed_symbols
    if unsupported:
        raise ValueError(
            "sequence contains unsupported symbols: " + ", ".join(sorted(unsupported))
        )
