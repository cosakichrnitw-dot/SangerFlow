from collections import Counter
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Integral, Real
from typing import Optional, Sequence

from core.assembly_models import PairAlignment



# ==================================================
# Build consensus sequence
# ==================================================

def build_consensus(sequences):
    """
    Build majority-rule consensus sequence.

    Parameters
    ----------
    sequences : list[str]
        Aligned sequences

    Returns
    -------
    str
        Consensus sequence
    """


    if len(sequences) == 0:

        return ""



    length = len(sequences[0])


    consensus = []



    for i in range(length):


        column = []



        for seq in sequences:


            if i < len(seq):


                base = seq[i].upper()



                if base != "-":

                    column.append(base)



        if len(column) == 0:


            consensus.append("-")

            continue



        counts = Counter(column)



        most_common = counts.most_common()



        if len(most_common) > 1:


            if most_common[0][1] == most_common[1][1]:


                consensus.append("N")

                continue



        consensus.append(

            most_common[0][0]

        )



    return "".join(consensus)





# ==================================================
# Quality aware consensus
# ==================================================

def build_quality_consensus(
    reads,
    alignment
):

    """
    Build consensus using Phred quality scores.

    Parameters
    ----------
    reads :
        Read objects containing sequence and quality

    alignment :
        Biopython MultipleSeqAlignment


    Returns
    -------
    tuple

        consensus sequence,
        confidence scores

    """



    if len(reads) == 0:

        return "", []



    aligned_sequences = []


    for record in alignment:

        aligned_sequences.append(

            str(record.seq)

        )



    length = len(

        aligned_sequences[0]

    )



    consensus = []

    confidence = []



    for pos in range(length):


        base_scores = {}



        for read, seq in zip(

            reads,

            aligned_sequences

        ):



            if pos >= len(seq):

                continue



            base = seq[pos].upper()



            if base == "-":

                continue



            # original trace position

            try:


                q = read.quality[pos]


            except:


                q = 0



            if base not in base_scores:


                base_scores[base] = 0



            base_scores[base] += q



        if len(base_scores) == 0:


            consensus.append("-")

            confidence.append(0)

            continue



        sorted_scores = sorted(

            base_scores.items(),

            key=lambda x: x[1],

            reverse=True

        )



        best_base = sorted_scores[0][0]

        best_score = sorted_scores[0][1]


        total_score = sum(

            base_scores.values()

        )



        conf = (

            best_score /

            total_score

            *

            100

        )



        consensus.append(

            best_base

        )


        confidence.append(

            round(

                conf,

                1

            )

        )



    return (

        "".join(consensus),

        confidence

    )


# ==================================================
# Pair-alignment consensus (core only)
# ==================================================


_UNAMBIGUOUS_DNA_BASES = frozenset("ACGT")


class DecisionReason(str, Enum):
    """Explain why a pair-alignment column produced its consensus base."""

    BOTH_AGREE = "BOTH_AGREE"
    HIGHER_QUALITY_FORWARD = "HIGHER_QUALITY_FORWARD"
    HIGHER_QUALITY_REVERSE = "HIGHER_QUALITY_REVERSE"
    ONE_SIDED_FORWARD = "ONE_SIDED_FORWARD"
    ONE_SIDED_REVERSE = "ONE_SIDED_REVERSE"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"
    LOW_QUALITY = "LOW_QUALITY"
    GAP_ONLY = "GAP_ONLY"
    AMBIGUOUS_INPUT = "AMBIGUOUS_INPUT"


@dataclass(frozen=True)
class ConsensusScoring:
    """Uncalibrated baseline thresholds for per-column pair consensus.

    These are engineering defaults for an explainable initial implementation,
    not scientific acceptance criteria.  They intentionally do not assign a
    sample-level PASS, REVIEW, or FAIL status.
    """

    minimum_usable_quality: float = 20.0
    minimum_quality_difference: float = 10.0

    def __post_init__(self) -> None:
        for name in ("minimum_usable_quality", "minimum_quality_difference"):
            value = getattr(self, name)
            if not isinstance(value, Real) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite number greater than or equal to zero")


@dataclass(frozen=True)
class ConsensusDecision:
    """Evidence and outcome for one 0-based ``PairAlignment`` column.

    ``alignment_index`` is the stable future attachment point for a
    provenance layer.  A ``None`` base and quality represent a gap; no source
    coordinates or trace data are copied into this core-only model.
    """

    alignment_index: int
    consensus_base: str
    reason: DecisionReason
    forward_base: Optional[str]
    reverse_base: Optional[str]
    forward_quality: Optional[float]
    reverse_quality: Optional[float]

    def __post_init__(self) -> None:
        if isinstance(self.alignment_index, bool) or not isinstance(
            self.alignment_index, Integral
        ) or self.alignment_index < 0:
            raise ValueError("alignment_index must be a non-negative integer")
        if not isinstance(self.consensus_base, str) or len(self.consensus_base) != 1:
            raise ValueError("consensus_base must be a one-character string")
        if not isinstance(self.reason, DecisionReason):
            raise ValueError("reason must be a DecisionReason")
        for name in ("forward_base", "reverse_base"):
            base = getattr(self, name)
            if base is not None and (not isinstance(base, str) or len(base) != 1):
                raise ValueError(f"{name} must be a one-character string or None")
        for name in ("forward_quality", "reverse_quality"):
            quality = getattr(self, name)
            if quality is not None and (
                not isinstance(quality, Real)
                or not isfinite(quality)
                or quality < 0
            ):
                raise ValueError(f"{name} must be a finite number greater than or equal to zero or None")


@dataclass(frozen=True)
class AssemblyMetrics:
    """Minimal, explainable descriptive metrics for one pair consensus."""

    overlap_length: int
    overlap_identity: float
    conflict_count: int
    resolved_conflict_count: int
    unresolved_base_count: int
    one_sided_coverage_count: int

    def __post_init__(self) -> None:
        for name in (
            "overlap_length",
            "conflict_count",
            "resolved_conflict_count",
            "unresolved_base_count",
            "one_sided_coverage_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if (
            not isinstance(self.overlap_identity, Real)
            or not isfinite(self.overlap_identity)
            or not 0.0 <= self.overlap_identity <= 1.0
        ):
            raise ValueError("overlap_identity must be a finite value from 0.0 to 1.0")
        if self.resolved_conflict_count > self.conflict_count:
            raise ValueError("resolved_conflict_count cannot exceed conflict_count")


@dataclass(frozen=True)
class ConsensusResult:
    """Immutable pair consensus sequence, per-column decisions, and metrics."""

    sequence: str
    decisions: Sequence[ConsensusDecision]
    metrics: AssemblyMetrics

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, str):
            raise ValueError("sequence must be a string")
        decisions = tuple(self.decisions)
        if len(self.sequence) != len(decisions):
            raise ValueError("sequence and decisions lengths differ")
        for index, decision in enumerate(decisions):
            if not isinstance(decision, ConsensusDecision):
                raise ValueError("decisions must contain ConsensusDecision values")
            if decision.alignment_index != index:
                raise ValueError("decision alignment_index values must be contiguous and 0-based")
            if self.sequence[index] != decision.consensus_base:
                raise ValueError("sequence must match the consensus bases in decisions")
        if not isinstance(self.metrics, AssemblyMetrics):
            raise ValueError("metrics must be an AssemblyMetrics")
        object.__setattr__(self, "decisions", decisions)


def build_pair_consensus(
    pair_alignment: PairAlignment,
    scoring: Optional[ConsensusScoring] = None,
) -> ConsensusResult:
    """Build an explainable consensus from a coordinate-preserving alignment.

    Only paired bases, their Phred values, and gaps participate.  Trace data,
    status assignment, provenance creation, and downstream integration are
    deliberately outside this function.
    """

    if not isinstance(pair_alignment, PairAlignment):
        raise ValueError("pair_alignment must be a PairAlignment")
    if scoring is None:
        scoring = ConsensusScoring()
    if not isinstance(scoring, ConsensusScoring):
        raise ValueError("scoring must be a ConsensusScoring")

    decisions = []
    overlap_length = 0
    unambiguous_comparisons = 0
    unambiguous_matches = 0
    conflict_count = 0
    resolved_conflict_count = 0
    one_sided_coverage_count = 0

    for column in pair_alignment.columns:
        forward_base, forward_quality = _column_evidence(
            pair_alignment.forward_view, column.forward
        )
        reverse_base, reverse_quality = _column_evidence(
            pair_alignment.reverse_view, column.reverse
        )
        if forward_base is not None and reverse_base is not None:
            overlap_length += 1
            if (
                forward_base in _UNAMBIGUOUS_DNA_BASES
                and reverse_base in _UNAMBIGUOUS_DNA_BASES
            ):
                unambiguous_comparisons += 1
                if forward_base == reverse_base:
                    unambiguous_matches += 1
            if forward_base != reverse_base:
                conflict_count += 1
        elif forward_base is not None or reverse_base is not None:
            one_sided_coverage_count += 1

        consensus_base, reason, resolved = _decide_pair_column(
            forward_base,
            forward_quality,
            reverse_base,
            reverse_quality,
            scoring,
        )
        if resolved:
            resolved_conflict_count += 1
        decisions.append(
            ConsensusDecision(
                alignment_index=column.alignment_index,
                consensus_base=consensus_base,
                reason=reason,
                forward_base=forward_base,
                reverse_base=reverse_base,
                forward_quality=forward_quality,
                reverse_quality=reverse_quality,
            )
        )

    overlap_identity = (
        unambiguous_matches / unambiguous_comparisons
        if unambiguous_comparisons
        else 0.0
    )
    metrics = AssemblyMetrics(
        overlap_length=overlap_length,
        overlap_identity=overlap_identity,
        conflict_count=conflict_count,
        resolved_conflict_count=resolved_conflict_count,
        unresolved_base_count=sum(decision.consensus_base == "N" for decision in decisions),
        one_sided_coverage_count=one_sided_coverage_count,
    )
    return ConsensusResult(
        sequence="".join(decision.consensus_base for decision in decisions),
        decisions=decisions,
        metrics=metrics,
    )


def _column_evidence(view, coordinate):
    """Return one side's upper-case base and Phred value, or a gap pair."""

    if coordinate is None:
        return None, None
    index = coordinate.assembly_index
    return view.sequence[index].upper(), float(view.quality[index])


def _decide_pair_column(
    forward_base: Optional[str],
    forward_quality: Optional[float],
    reverse_base: Optional[str],
    reverse_quality: Optional[float],
    scoring: ConsensusScoring,
):
    """Return consensus base, reason, and whether a conflict was resolved."""

    if forward_base is None and reverse_base is None:
        return "-", DecisionReason.GAP_ONLY, False
    if forward_base is None:
        if _is_usable_unambiguous(reverse_base, reverse_quality, scoring):
            return reverse_base, DecisionReason.ONE_SIDED_REVERSE, False
        return "N", _single_side_reason(reverse_base), False
    if reverse_base is None:
        if _is_usable_unambiguous(forward_base, forward_quality, scoring):
            return forward_base, DecisionReason.ONE_SIDED_FORWARD, False
        return "N", _single_side_reason(forward_base), False

    if (
        forward_base not in _UNAMBIGUOUS_DNA_BASES
        or reverse_base not in _UNAMBIGUOUS_DNA_BASES
    ):
        return "N", DecisionReason.AMBIGUOUS_INPUT, False
    if forward_base == reverse_base:
        if (
            forward_quality >= scoring.minimum_usable_quality
            or reverse_quality >= scoring.minimum_usable_quality
        ):
            return forward_base, DecisionReason.BOTH_AGREE, False
        return "N", DecisionReason.LOW_QUALITY, False
    if (
        forward_quality < scoring.minimum_usable_quality
        and reverse_quality < scoring.minimum_usable_quality
    ):
        return "N", DecisionReason.LOW_QUALITY, False
    difference = forward_quality - reverse_quality
    if abs(difference) < scoring.minimum_quality_difference:
        return "N", DecisionReason.UNRESOLVED_CONFLICT, False
    if difference > 0 and forward_quality >= scoring.minimum_usable_quality:
        return forward_base, DecisionReason.HIGHER_QUALITY_FORWARD, True
    if difference < 0 and reverse_quality >= scoring.minimum_usable_quality:
        return reverse_base, DecisionReason.HIGHER_QUALITY_REVERSE, True
    return "N", DecisionReason.LOW_QUALITY, False


def _is_usable_unambiguous(
    base: str, quality: float, scoring: ConsensusScoring
) -> bool:
    return (
        base in _UNAMBIGUOUS_DNA_BASES
        and quality is not None
        and quality >= scoring.minimum_usable_quality
    )


def _single_side_reason(base: str) -> DecisionReason:
    if base not in _UNAMBIGUOUS_DNA_BASES:
        return DecisionReason.AMBIGUOUS_INPUT
    return DecisionReason.LOW_QUALITY
