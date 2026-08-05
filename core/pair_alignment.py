"""Baseline two-read semi-global overlap alignment for assembly views.

This module deliberately produces only a coordinate-preserving
``PairAlignment``.  Consensus, status, metrics, and GUI behavior remain in
later layers.
"""

from dataclasses import dataclass
from math import isfinite
from typing import List, Optional, Sequence, Tuple
import warnings

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)


_DNA_IUPAC = frozenset("ACGTRYSWKMBDHVN")
_UNAMBIGUOUS_BASES = frozenset("ACGT")
_NEGATIVE_INFINITY = float("-inf")


class NoCredibleOverlapError(ValueError):
    """Raised when no structurally credible pair overlap is available."""


class AmbiguousAlignmentWarning(UserWarning):
    """Warn that equal-scoring, equally ranked alignments were found."""


@dataclass(frozen=True)
class AlignmentScoring:
    """Configurable, uncalibrated baseline scoring parameters.

    These values are engineering defaults for deterministic candidate ranking,
    not scientific quality thresholds.  They must be benchmarked on curated
    Sanger read pairs before scientific use.
    """

    match_score: float = 2.0
    mismatch_penalty: float = 2.0
    gap_open_penalty: float = 3.0
    gap_extend_penalty: float = 1.0
    match_quality_bonus: float = 2.0
    mismatch_quality_penalty: float = 2.0
    gap_quality_penalty: float = 1.0
    quality_cap: float = 40.0
    min_overlap_bases: int = 1
    min_unambiguous_matches: int = 1

    def __post_init__(self) -> None:
        positive_values = (
            "match_score",
            "mismatch_penalty",
            "gap_open_penalty",
            "gap_extend_penalty",
            "quality_cap",
        )
        non_negative_values = (
            "match_quality_bonus",
            "mismatch_quality_penalty",
            "gap_quality_penalty",
        )
        for name in positive_values:
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be greater than zero")
        for name in non_negative_values:
            value = getattr(self, name)
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be greater than or equal to zero")
        if self.min_overlap_bases < 1:
            raise ValueError("min_overlap_bases must be at least one")
        if self.min_unambiguous_matches < 1:
            raise ValueError("min_unambiguous_matches must be at least one")


@dataclass(frozen=True)
class _PathStats:
    unambiguous_pairs: int = 0
    unambiguous_matches: int = 0
    internal_gap_opens: int = 0
    leading_terminal_bases: int = 0

    def with_pair(self, is_unambiguous: bool, is_match: bool) -> "_PathStats":
        return _PathStats(
            unambiguous_pairs=self.unambiguous_pairs + int(is_unambiguous),
            unambiguous_matches=self.unambiguous_matches + int(is_match),
            internal_gap_opens=self.internal_gap_opens,
            leading_terminal_bases=self.leading_terminal_bases,
        )

    def with_gap_open(self) -> "_PathStats":
        return _PathStats(
            unambiguous_pairs=self.unambiguous_pairs,
            unambiguous_matches=self.unambiguous_matches,
            internal_gap_opens=self.internal_gap_opens + 1,
            leading_terminal_bases=self.leading_terminal_bases,
        )


def align_pair(
    forward_view: AssemblyReadView,
    reverse_view: AssemblyReadView,
    scoring: Optional[AlignmentScoring] = None,
) -> PairAlignment:
    """Return a deterministic semi-global alignment for one pair of views.

    The algorithm uses a full affine-gap DP matrix.  Leading and trailing
    one-sided regions are represented as free terminal-gap columns; gaps
    between the first and final paired columns receive affine penalties.
    """

    _validate_input_views(forward_view, reverse_view)
    if scoring is None:
        scoring = AlignmentScoring()
    if not isinstance(scoring, AlignmentScoring):
        raise ValueError("scoring must be an AlignmentScoring")

    endpoint, endpoint_tie, traceback_context = _find_best_endpoint(
        forward_view, reverse_view, scoring
    )
    end_i, end_j, state, stats = endpoint
    index_columns = _traceback_index_columns(
        forward_view.length,
        reverse_view.length,
        end_i,
        end_j,
        state,
        traceback_context,
    )
    overlap_bases = sum(
        forward_index is not None and reverse_index is not None
        for forward_index, reverse_index in index_columns
    )
    if (
        overlap_bases < scoring.min_overlap_bases
        or stats.unambiguous_matches < scoring.min_unambiguous_matches
    ):
        raise NoCredibleOverlapError(
            "No credible overlap satisfies the configured structural criteria"
        )

    if endpoint_tie:
        warnings.warn(
            "Multiple equally ranked semi-global alignments were found; "
            "a deterministic traceback was selected.",
            AmbiguousAlignmentWarning,
            stacklevel=2,
        )

    columns = [
        AlignmentColumn(
            alignment_index=alignment_index,
            forward=(
                None
                if forward_index is None
                else forward_view.coordinate_at(forward_index)
            ),
            reverse=(
                None
                if reverse_index is None
                else reverse_view.coordinate_at(reverse_index)
            ),
        )
        for alignment_index, (forward_index, reverse_index) in enumerate(
            index_columns
        )
    ]
    return PairAlignment(
        forward_view=forward_view,
        reverse_view=reverse_view,
        columns=columns,
    )


def _validate_input_views(
    forward_view: AssemblyReadView,
    reverse_view: AssemblyReadView,
) -> None:
    if not isinstance(forward_view, AssemblyReadView):
        raise ValueError("forward_view must be an AssemblyReadView")
    if not isinstance(reverse_view, AssemblyReadView):
        raise ValueError("reverse_view must be an AssemblyReadView")
    if forward_view is reverse_view:
        raise ValueError("the same AssemblyReadView cannot be both pair sides")
    if forward_view.orientation is not ReadOrientation.FORWARD:
        raise ValueError("forward_view orientation must be FORWARD")
    if reverse_view.orientation is not ReadOrientation.REVERSE:
        raise ValueError("reverse_view orientation must be REVERSE")
    _validate_bases("forward_view", forward_view.sequence)
    _validate_bases("reverse_view", reverse_view.sequence)


def _validate_bases(name: str, sequence: str) -> None:
    invalid_bases = sorted({base for base in sequence.upper() if base not in _DNA_IUPAC})
    if invalid_bases:
        raise ValueError(f"{name} contains unsupported base characters: {invalid_bases}")


def _find_best_endpoint(
    forward_view: AssemblyReadView,
    reverse_view: AssemblyReadView,
    scoring: AlignmentScoring,
) -> Tuple[Tuple[int, int, str, _PathStats], bool, dict]:
    """Populate affine DP states and choose a ranked diagonal endpoint."""

    forward = forward_view.sequence.upper()
    reverse = reverse_view.sequence.upper()
    forward_length = len(forward)
    reverse_length = len(reverse)

    match_scores = _matrix(forward_length + 1, reverse_length + 1, _NEGATIVE_INFINITY)
    forward_gap_scores = _matrix(
        forward_length + 1, reverse_length + 1, _NEGATIVE_INFINITY
    )
    reverse_gap_scores = _matrix(
        forward_length + 1, reverse_length + 1, _NEGATIVE_INFINITY
    )
    match_stats = _matrix(forward_length + 1, reverse_length + 1, None)
    forward_gap_stats = _matrix(forward_length + 1, reverse_length + 1, None)
    reverse_gap_stats = _matrix(forward_length + 1, reverse_length + 1, None)
    match_pointers = _matrix(forward_length + 1, reverse_length + 1, None)
    forward_gap_pointers = _matrix(forward_length + 1, reverse_length + 1, None)
    reverse_gap_pointers = _matrix(forward_length + 1, reverse_length + 1, None)
    match_ties = _matrix(forward_length + 1, reverse_length + 1, False)
    forward_gap_ties = _matrix(forward_length + 1, reverse_length + 1, False)
    reverse_gap_ties = _matrix(forward_length + 1, reverse_length + 1, False)

    for forward_index in range(1, forward_length + 1):
        for reverse_index in range(1, reverse_length + 1):
            pair_score, is_unambiguous, is_match = _pair_score(
                forward_view,
                reverse_view,
                forward_index - 1,
                reverse_index - 1,
                scoring,
            )
            match_choice = _choose_transition(
                (
                    (match_scores[forward_index - 1][reverse_index - 1], match_stats[forward_index - 1][reverse_index - 1], "M"),
                    (forward_gap_scores[forward_index - 1][reverse_index - 1], forward_gap_stats[forward_index - 1][reverse_index - 1], "F"),
                    (reverse_gap_scores[forward_index - 1][reverse_index - 1], reverse_gap_stats[forward_index - 1][reverse_index - 1], "R"),
                    (
                        0.0,
                        _PathStats(
                            leading_terminal_bases=forward_index + reverse_index - 2
                        ),
                        "S",
                    ),
                ),
                (
                    match_ties[forward_index - 1][reverse_index - 1],
                    forward_gap_ties[forward_index - 1][reverse_index - 1],
                    reverse_gap_ties[forward_index - 1][reverse_index - 1],
                    False,
                ),
            )
            if match_choice is not None:
                score, stats, previous_state, tie_detected = match_choice
                match_scores[forward_index][reverse_index] = score + pair_score
                match_stats[forward_index][reverse_index] = stats.with_pair(
                    is_unambiguous, is_match
                )
                match_pointers[forward_index][reverse_index] = (
                    previous_state,
                    forward_index - 1,
                    reverse_index - 1,
                )
                match_ties[forward_index][reverse_index] = tie_detected

            forward_gap_choice = _choose_transition(
                (
                    (
                        match_scores[forward_index - 1][reverse_index]
                        - _gap_open_score(forward_view, forward_index - 1, scoring),
                        _stats_with_gap_open(
                            match_stats[forward_index - 1][reverse_index]
                        ),
                        "M",
                    ),
                    (
                        forward_gap_scores[forward_index - 1][reverse_index]
                        - scoring.gap_extend_penalty,
                        forward_gap_stats[forward_index - 1][reverse_index],
                        "F",
                    ),
                ),
                (
                    match_ties[forward_index - 1][reverse_index],
                    forward_gap_ties[forward_index - 1][reverse_index],
                ),
            )
            if forward_gap_choice is not None:
                score, stats, previous_state, tie_detected = forward_gap_choice
                forward_gap_scores[forward_index][reverse_index] = score
                forward_gap_stats[forward_index][reverse_index] = stats
                forward_gap_pointers[forward_index][reverse_index] = (
                    previous_state,
                    forward_index - 1,
                    reverse_index,
                )
                forward_gap_ties[forward_index][reverse_index] = tie_detected

            reverse_gap_choice = _choose_transition(
                (
                    (
                        match_scores[forward_index][reverse_index - 1]
                        - _gap_open_score(reverse_view, reverse_index - 1, scoring),
                        _stats_with_gap_open(
                            match_stats[forward_index][reverse_index - 1]
                        ),
                        "M",
                    ),
                    (
                        reverse_gap_scores[forward_index][reverse_index - 1]
                        - scoring.gap_extend_penalty,
                        reverse_gap_stats[forward_index][reverse_index - 1],
                        "R",
                    ),
                ),
                (
                    match_ties[forward_index][reverse_index - 1],
                    reverse_gap_ties[forward_index][reverse_index - 1],
                ),
            )
            if reverse_gap_choice is not None:
                score, stats, previous_state, tie_detected = reverse_gap_choice
                reverse_gap_scores[forward_index][reverse_index] = score
                reverse_gap_stats[forward_index][reverse_index] = stats
                reverse_gap_pointers[forward_index][reverse_index] = (
                    previous_state,
                    forward_index,
                    reverse_index - 1,
                )
                reverse_gap_ties[forward_index][reverse_index] = tie_detected

    endpoint_candidates = []
    for forward_index in range(1, forward_length + 1):
        for reverse_index in range(1, reverse_length + 1):
            stats = match_stats[forward_index][reverse_index]
            score = match_scores[forward_index][reverse_index]
            if stats is not None and score != _NEGATIVE_INFINITY:
                terminal_overhang = (
                    stats.leading_terminal_bases
                    + forward_length
                    - forward_index
                    + reverse_length
                    - reverse_index
                )
                endpoint_candidates.append(
                    (
                        score,
                        stats,
                        terminal_overhang,
                        forward_index,
                        reverse_index,
                        match_ties[forward_index][reverse_index],
                    )
                )

    if not endpoint_candidates:
        raise NoCredibleOverlapError("No paired alignment columns were generated")

    best_rank = max(_endpoint_rank(candidate) for candidate in endpoint_candidates)
    best_candidates = [
        candidate for candidate in endpoint_candidates if _endpoint_rank(candidate) == best_rank
    ]
    selected = min(best_candidates, key=lambda candidate: (candidate[3], candidate[4]))
    _, stats, _, forward_index, reverse_index, selected_path_tie = selected

    traceback_context = {
        "M": match_pointers,
        "F": forward_gap_pointers,
        "R": reverse_gap_pointers,
    }
    return (
        (forward_index, reverse_index, "M", stats),
        len(best_candidates) > 1 or selected_path_tie,
        traceback_context,
    )


def _endpoint_rank(candidate: Tuple[float, _PathStats, int, int, int, bool]) -> Tuple[float, int, int, int, int]:
    score, stats, terminal_overhang, _, _, _ = candidate
    return (
        score,
        stats.unambiguous_pairs,
        stats.unambiguous_matches,
        -stats.internal_gap_opens,
        -terminal_overhang,
    )


def _choose_transition(
    candidates: Sequence[Tuple[float, Optional[_PathStats], str]],
    inherited_ties: Sequence[bool],
) -> Optional[Tuple[float, _PathStats, str, bool]]:
    valid_candidates = [
        candidate
        for candidate in candidates
        if candidate[0] != _NEGATIVE_INFINITY and candidate[1] is not None
    ]
    if not valid_candidates:
        return None
    best_rank = max(_transition_rank(candidate) for candidate in valid_candidates)
    tied_candidates = [
        candidate for candidate in valid_candidates if _transition_rank(candidate) == best_rank
    ]
    selected = max(
        valid_candidates,
        key=lambda candidate: (
            *_transition_rank(candidate),
            -("MFRS".index(candidate[2])),
        ),
    )
    selected_index = candidates.index(selected)
    return (*selected, len(tied_candidates) > 1 or inherited_ties[selected_index])


def _transition_rank(candidate: Tuple[float, _PathStats, str]) -> Tuple[float, int, int, int]:
    return (
        candidate[0],
        candidate[1].unambiguous_pairs,
        candidate[1].unambiguous_matches,
        -candidate[1].internal_gap_opens,
    )


def _pair_score(
    forward_view: AssemblyReadView,
    reverse_view: AssemblyReadView,
    forward_index: int,
    reverse_index: int,
    scoring: AlignmentScoring,
) -> Tuple[float, bool, bool]:
    forward_base = forward_view.sequence[forward_index].upper()
    reverse_base = reverse_view.sequence[reverse_index].upper()
    if forward_base not in _UNAMBIGUOUS_BASES or reverse_base not in _UNAMBIGUOUS_BASES:
        return 0.0, False, False

    quality_support = min(
        _normalize_quality(forward_view.quality[forward_index], scoring),
        _normalize_quality(reverse_view.quality[reverse_index], scoring),
    )
    if forward_base == reverse_base:
        return scoring.match_score + scoring.match_quality_bonus * quality_support, True, True
    return -(
        scoring.mismatch_penalty
        + scoring.mismatch_quality_penalty * quality_support
    ), True, False


def _gap_open_score(
    view: AssemblyReadView,
    assembly_index: int,
    scoring: AlignmentScoring,
) -> float:
    return scoring.gap_open_penalty + scoring.gap_quality_penalty * _normalize_quality(
        view.quality[assembly_index], scoring
    )


def _normalize_quality(quality: float, scoring: AlignmentScoring) -> float:
    return min(float(quality), scoring.quality_cap) / scoring.quality_cap


def _stats_with_gap_open(stats: Optional[_PathStats]) -> Optional[_PathStats]:
    return None if stats is None else stats.with_gap_open()


def _traceback_index_columns(
    forward_length: int,
    reverse_length: int,
    end_i: int,
    end_j: int,
    state: str,
    traceback_context: dict,
) -> List[Tuple[Optional[int], Optional[int]]]:
    """Trace one deterministic DP path and append free terminal suffixes."""

    columns_reversed = []
    forward_index = end_i
    reverse_index = end_j
    while state != "S":
        pointers = traceback_context[state]
        pointer = pointers[forward_index][reverse_index]
        if pointer is None:
            raise RuntimeError("Incomplete semi-global alignment traceback")
        if state == "M":
            columns_reversed.append((forward_index - 1, reverse_index - 1))
        elif state == "F":
            columns_reversed.append((forward_index - 1, None))
        else:
            columns_reversed.append((None, reverse_index - 1))
        state, forward_index, reverse_index = pointer

    for index in range(reverse_index - 1, -1, -1):
        columns_reversed.append((None, index))
    for index in range(forward_index - 1, -1, -1):
        columns_reversed.append((index, None))

    columns = list(reversed(columns_reversed))
    columns.extend((index, None) for index in range(end_i, forward_length))
    columns.extend((None, index) for index in range(end_j, reverse_length))
    return columns


def _matrix(rows: int, columns: int, value: object) -> list:
    return [[value for _ in range(columns)] for _ in range(rows)]
