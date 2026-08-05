"""Prototype entry point for selecting consensus review workflows.

The manager owns only GUI selection and object routing.  It does not build a
pair consensus, alter a review decision, edit a sequence, or import either
viewer implementation.  Multiple-mode alignment is delegated to the existing
consensus-alignment core before the caller's viewer callback receives it.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, Optional, Sequence
import tkinter as tk
from tkinter import ttk

from core.consensus_alignment import AlignedConsensusSet, run_consensus_alignment


class ReviewMode(str, Enum):
    """The two review routes offered by the prototype manager."""

    SINGLE = "single"
    MULTIPLE = "multiple"


class ReviewSelectionError(ValueError):
    """Raised when the selected candidates do not satisfy a review route."""


@dataclass(frozen=True)
class ConsensusReviewCandidate:
    """One immutable candidate available for display and workflow routing.

    ``single_review_input`` is intentionally opaque to this module.  A caller
    may use it to carry the existing single-review input without making the
    manager import PairAlignment, ReviewEvidence, or a viewer implementation.
    """

    sample_id: str
    sequence: str
    single_review_input: object | None = None
    metadata: Optional[Mapping[str, object]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.sample_id, str) or not self.sample_id:
            raise ValueError("sample_id must be a non-empty string")
        if any(character.isspace() for character in self.sample_id):
            raise ValueError("sample_id must not contain whitespace")
        if not isinstance(self.sequence, str) or not self.sequence:
            raise ValueError("sequence must be a non-empty string")
        if self.metadata is not None and not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a mapping or None")


class ConsensusReviewManagerState:
    """Mutable GUI selection state, separate from immutable candidate data."""

    def __init__(self, candidates: Sequence[ConsensusReviewCandidate]) -> None:
        candidate_values = tuple(candidates)
        if not candidate_values:
            raise ValueError("at least one ConsensusReviewCandidate is required")
        if any(not isinstance(candidate, ConsensusReviewCandidate) for candidate in candidate_values):
            raise ValueError("candidates must contain ConsensusReviewCandidate values")
        sample_ids = tuple(candidate.sample_id for candidate in candidate_values)
        if len(set(sample_ids)) != len(sample_ids):
            raise ValueError("candidate sample_id values must be unique")
        self.candidates = candidate_values
        self.mode = ReviewMode.SINGLE
        self._selected_sample_ids: set[str] = set()

    def set_selected(self, sample_id: str, selected: bool) -> None:
        self._candidate_for_sample_id(sample_id)
        if selected:
            self._selected_sample_ids.add(sample_id)
        else:
            self._selected_sample_ids.discard(sample_id)

    def set_mode(self, mode: ReviewMode | str) -> None:
        try:
            self.mode = ReviewMode(mode)
        except ValueError as error:
            raise ValueError("mode must be a ReviewMode value") from error

    def selected_candidates(self) -> tuple[ConsensusReviewCandidate, ...]:
        return tuple(
            candidate
            for candidate in self.candidates
            if candidate.sample_id in self._selected_sample_ids
        )

    def _candidate_for_sample_id(self, sample_id: str) -> ConsensusReviewCandidate:
        for candidate in self.candidates:
            if candidate.sample_id == sample_id:
                return candidate
        raise ValueError(f"unknown candidate sample_id: {sample_id}")


SingleReviewCallback = Callable[[ConsensusReviewCandidate], None]
MultipleReviewCallback = Callable[[AlignedConsensusSet], None]
AlignmentRunner = Callable[[Sequence[Mapping[str, object]]], AlignedConsensusSet]


def dispatch_selected_review(
    state: ConsensusReviewManagerState,
    *,
    on_open_single: Optional[SingleReviewCallback],
    on_open_multiple: Optional[MultipleReviewCallback],
    alignment_runner: AlignmentRunner = run_consensus_alignment,
) -> None:
    """Route the selected workflow without importing or controlling viewers."""

    if not isinstance(state, ConsensusReviewManagerState):
        raise ValueError("state must be a ConsensusReviewManagerState")
    selected = state.selected_candidates()
    if state.mode is ReviewMode.SINGLE:
        if len(selected) != 1:
            raise ReviewSelectionError("Single review requires exactly one selected candidate")
        if on_open_single is None:
            raise ReviewSelectionError("Single review callback is not configured")
        on_open_single(selected[0])
        return

    if len(selected) < 2:
        raise ReviewSelectionError("Multiple review requires at least two selected candidates")
    if on_open_multiple is None:
        raise ReviewSelectionError("Multiple review callback is not configured")
    alignment_inputs = tuple(
        {
            "sample_id": candidate.sample_id,
            "sequence": candidate.sequence,
            "metadata": candidate.metadata,
        }
        for candidate in selected
    )
    on_open_multiple(alignment_runner(alignment_inputs))


class ConsensusReviewManagerWindow(tk.Toplevel):
    """Minimal Tkinter workflow-entry prototype for consensus review."""

    def __init__(
        self,
        master,
        candidates: Sequence[ConsensusReviewCandidate],
        *,
        on_open_single: Optional[SingleReviewCallback] = None,
        on_open_multiple: Optional[MultipleReviewCallback] = None,
        alignment_runner: AlignmentRunner = run_consensus_alignment,
    ) -> None:
        if on_open_single is not None and not callable(on_open_single):
            raise ValueError("on_open_single must be callable or None")
        if on_open_multiple is not None and not callable(on_open_multiple):
            raise ValueError("on_open_multiple must be callable or None")
        if not callable(alignment_runner):
            raise ValueError("alignment_runner must be callable")
        super().__init__(master)
        self.state = ConsensusReviewManagerState(candidates)
        self.on_open_single = on_open_single
        self.on_open_multiple = on_open_multiple
        self.alignment_runner = alignment_runner
        self._selection_vars: dict[str, tk.BooleanVar] = {}
        self._mode_var = tk.StringVar(value=self.state.mode.value)
        self._message_var = tk.StringVar(value="Select candidate(s) and a review mode.")
        self.title("Consensus Review Manager")
        self.geometry("680x480")
        self.minsize(560, 360)
        self._build_layout()

    def _build_layout(self) -> None:
        candidate_frame = tk.LabelFrame(self, text="Consensus candidates", padx=8, pady=8)
        candidate_frame.pack(fill="both", expand=True, padx=10, pady=(10, 8))
        headings = ("Selected", "Sample", "Sequence length")
        for column, heading in enumerate(headings):
            tk.Label(candidate_frame, text=heading, font=("TkDefaultFont", 10, "bold")).grid(
                row=0, column=column, sticky="w", padx=(4, 20), pady=(0, 4)
            )
        for row_index, candidate in enumerate(self.state.candidates, start=1):
            selection_var = tk.BooleanVar(value=False)
            self._selection_vars[candidate.sample_id] = selection_var
            tk.Checkbutton(candidate_frame, variable=selection_var).grid(
                row=row_index, column=0, sticky="w", padx=4
            )
            tk.Label(candidate_frame, text=candidate.sample_id, anchor="w").grid(
                row=row_index, column=1, sticky="w", padx=(4, 20)
            )
            tk.Label(candidate_frame, text=f"{len(candidate.sequence)} bp", anchor="e").grid(
                row=row_index, column=2, sticky="e", padx=4
            )

        mode_frame = tk.LabelFrame(self, text="Review mode", padx=8, pady=8)
        mode_frame.pack(fill="x", padx=10, pady=(0, 8))
        tk.Radiobutton(
            mode_frame,
            text="Single Consensus Review",
            variable=self._mode_var,
            value=ReviewMode.SINGLE.value,
        ).pack(anchor="w")
        tk.Radiobutton(
            mode_frame,
            text="Multiple Consensus Alignment Review",
            variable=self._mode_var,
            value=ReviewMode.MULTIPLE.value,
        ).pack(anchor="w")

        footer = tk.Frame(self)
        footer.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(footer, textvariable=self._message_var, anchor="w").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(footer, text="Open Review", command=self._open_review).pack(side="right")

    def _open_review(self) -> None:
        for sample_id, selection_var in self._selection_vars.items():
            self.state.set_selected(sample_id, selection_var.get())
        self.state.set_mode(self._mode_var.get())
        try:
            dispatch_selected_review(
                self.state,
                on_open_single=self.on_open_single,
                on_open_multiple=self.on_open_multiple,
                alignment_runner=self.alignment_runner,
            )
        except (ReviewSelectionError, ValueError, RuntimeError) as error:
            self._message_var.set(str(error))
        else:
            self._message_var.set("Review request sent to the configured viewer callback.")
