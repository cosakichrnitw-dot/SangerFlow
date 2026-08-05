"""Prototype GUI for reviewing one Forward/Reverse consensus candidate.

The window displays immutable v2.1 decisions and diagnostic bridge evidence.
It never recalculates consensus, edits a base, draws chromatograms, or imports
the existing Main Window.  A caller may optionally provide a callback to open
a chromatogram in an existing viewer.
"""

from dataclasses import dataclass
from typing import Callable, Optional, Sequence
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from core.assembly_models import PairAlignment
from core.consensus_review_bridge import ReviewEvidence, TraceJumpTarget, create_review_evidence
from core.consensus_v2_1 import ConsensusV21Result


TraceJumpCallback = Callable[[str, int], None]
_SEQUENCE_LEFT_PADDING = 12
_SEQUENCE_PANEL_HEIGHT = 84
_SEQUENCE_FRAME_HEIGHT = 128
_SEQUENCE_RULER_Y = 29
_SEQUENCE_RULER_LABEL_Y = 11
_SEQUENCE_BASE_Y = 55
_RULER_INTERVAL = 10
_RULER_MAJOR_INTERVAL = 50
_SEQUENCE_MINIMUM_CELL_WIDTH = 18
_SEQUENCE_CELL_HORIZONTAL_PADDING = 8
_CHROMATOGRAM_BASE_COLORS = {
    "A": "#E06666",
    "C": "#7BC67B",
    "G": "#F6E15A",
    "T": "#6FA8DC",
    "N": "#B7B7B7",
}
_BASE_CELL_OUTLINE = "#b8b8b8"
_SELECTION_COLOR = "#1f4e79"
_REVIEW_GROUPS = (
    ("needs-attention", "Needs attention"),
    ("conflict-resolved", "Conflict resolved"),
    ("low-quality", "Low quality"),
    ("terminal-one-sided", "Terminal one-sided"),
)


@dataclass(frozen=True)
class SingleConsensusColumn:
    """GUI-ready, immutable representation of one consensus base."""

    consensus_position: int
    base: str
    status: str
    confidence_level: str
    selected_source: str
    review_evidence: ReviewEvidence


@dataclass(frozen=True)
class SingleConsensusViewModel:
    """GUI adapter that keeps display state separate from core data."""

    sample_identifier: str
    consensus_sequence: str
    columns: Sequence[SingleConsensusColumn]

    def __post_init__(self) -> None:
        if not isinstance(self.sample_identifier, str) or not self.sample_identifier:
            raise ValueError("sample_identifier must be a non-empty string")
        if not isinstance(self.consensus_sequence, str):
            raise ValueError("consensus_sequence must be a string")
        columns = tuple(self.columns)
        if len(columns) != len(self.consensus_sequence):
            raise ValueError("columns and consensus_sequence lengths differ")
        for index, column in enumerate(columns):
            if not isinstance(column, SingleConsensusColumn):
                raise ValueError("columns must contain SingleConsensusColumn values")
            if column.consensus_position != index:
                raise ValueError("consensus positions must be contiguous and 0-based")
            if column.base != self.consensus_sequence[index]:
                raise ValueError("column base must match consensus_sequence")
        object.__setattr__(self, "columns", columns)

    def column_at(self, consensus_position: int) -> SingleConsensusColumn:
        if isinstance(consensus_position, bool) or not isinstance(consensus_position, int):
            raise ValueError("consensus_position must be an integer")
        if not 0 <= consensus_position < len(self.columns):
            raise IndexError("consensus_position is outside the view model")
        return self.columns[consensus_position]


def build_single_consensus_view_model(
    sample_identifier: str,
    pair_alignment: PairAlignment,
    consensus_result: ConsensusV21Result,
    *,
    v1_bases: Optional[Sequence[str]] = None,
) -> SingleConsensusViewModel:
    """Adapt existing v2.1 decisions to GUI data without changing core state.

    ``v1_bases`` is optional comparison-only display information.  It must be
    an index-aligned sequence when supplied; the adapter does not calculate v1.
    """

    if not isinstance(pair_alignment, PairAlignment):
        raise ValueError("pair_alignment must be a PairAlignment")
    if not isinstance(consensus_result, ConsensusV21Result):
        raise ValueError("consensus_result must be a ConsensusV21Result")
    if pair_alignment.length != len(consensus_result.decisions):
        raise ValueError("pair_alignment and consensus_result lengths differ")
    if v1_bases is not None and len(v1_bases) != pair_alignment.length:
        raise ValueError("v1_bases and pair_alignment lengths differ")

    columns = []
    for decision in consensus_result.decisions:
        v1_base = None if v1_bases is None else v1_bases[decision.alignment_index]
        evidence = create_review_evidence(
            decision,
            pair_alignment,
            sample_identifier=sample_identifier,
            v1_base=v1_base,
        )
        columns.append(
            SingleConsensusColumn(
                consensus_position=decision.alignment_index,
                base=decision.consensus_base,
                status=_display_status(decision.decision_reason.value, decision.consensus_base),
                confidence_level=decision.confidence_level.value,
                selected_source=decision.selected_source.value,
                review_evidence=evidence,
            )
        )
    return SingleConsensusViewModel(
        sample_identifier=sample_identifier,
        consensus_sequence=consensus_result.consensus_sequence,
        columns=columns,
    )


def dispatch_trace_jump(
    callback: Optional[TraceJumpCallback], target: Optional[TraceJumpTarget]
) -> bool:
    """Invoke the optional GUI-neutral jump callback when a target exists."""

    if target is None or callback is None:
        return False
    callback(target.read_identifier, target.raw_trace_position)
    return True


class SingleConsensusReviewWindow(tk.Toplevel):
    """Minimal Tkinter prototype for Single Consensus Review Mode."""

    def __init__(
        self,
        master,
        view_model: SingleConsensusViewModel,
        *,
        on_trace_jump: Optional[TraceJumpCallback] = None,
    ) -> None:
        if not isinstance(view_model, SingleConsensusViewModel):
            raise ValueError("view_model must be a SingleConsensusViewModel")
        if on_trace_jump is not None and not callable(on_trace_jump):
            raise ValueError("on_trace_jump must be callable or None")
        super().__init__(master)
        self.view_model = view_model
        self.on_trace_jump = on_trace_jump
        self.selected_position: Optional[int] = None
        self._review_site_items = {}
        self._review_site_positions_by_item = {}
        self.title(f"Single Consensus Review — {view_model.sample_identifier}")
        self.geometry("1280x720")
        self.minsize(950, 540)
        self._build_layout()

    def _build_layout(self) -> None:
        header = tk.Label(
            self,
            text=f"Sample: {self.view_model.sample_identifier}",
            anchor="w",
            font=("TkDefaultFont", 12, "bold"),
            padx=12,
            pady=8,
        )
        header.pack(fill="x")

        sequence_frame = tk.LabelFrame(
            self,
            text="Consensus sequence",
            padx=8,
            pady=8,
            height=_SEQUENCE_FRAME_HEIGHT,
        )
        # This panel is a one-line sequence strip.  Keep its requested height
        # bounded so the resizable review/evidence/navigation area always
        # receives the remaining vertical space.
        sequence_frame.pack(fill="x", expand=False, padx=10, pady=(0, 8))
        sequence_frame.pack_propagate(False)
        canvas = tk.Canvas(
            sequence_frame,
            height=_SEQUENCE_PANEL_HEIGHT,
            highlightthickness=0,
        )
        scrollbar = tk.Scrollbar(sequence_frame, orient="horizontal", command=canvas.xview)
        canvas.configure(xscrollcommand=scrollbar.set)
        scrollbar.pack(side="bottom", fill="x")
        # Only the horizontal dimension is elastic.  Vertical expansion here
        # would push the review panes below the window in some Tk layouts.
        canvas.pack(side="top", fill="x", expand=False)
        self._sequence_canvas = canvas
        self._sequence_font = tkfont.nametofont("TkFixedFont").copy()
        self._sequence_font.configure(size=12, weight="bold")
        self._sequence_character_width = max(
            _SEQUENCE_MINIMUM_CELL_WIDTH,
            self._sequence_font.measure("A") + _SEQUENCE_CELL_HORIZONTAL_PADDING,
        )
        self._sequence_text_height = self._sequence_font.metrics("linespace")
        self._selection_item = canvas.create_rectangle(
            0,
            _SEQUENCE_BASE_Y - (self._sequence_text_height / 2) - 2,
            0,
            _SEQUENCE_BASE_Y + (self._sequence_text_height / 2) + 2,
            fill="",
            outline=_SELECTION_COLOR,
            width=3,
            state="hidden",
        )
        self._selection_ruler_item = canvas.create_line(
            0,
            _SEQUENCE_RULER_Y - 10,
            0,
            _SEQUENCE_RULER_Y + 10,
            fill=_SELECTION_COLOR,
            width=2,
            state="hidden",
        )
        canvas.create_line(
            _SEQUENCE_LEFT_PADDING,
            _SEQUENCE_RULER_Y,
            _sequence_scroll_width(
                len(self.view_model.columns),
                self._sequence_character_width,
            )
            - _SEQUENCE_LEFT_PADDING,
            _SEQUENCE_RULER_Y,
            fill="#777777",
        )
        for consensus_position in _ruler_positions(len(self.view_model.columns)):
            center_x = _sequence_column_center(
                consensus_position,
                self._sequence_character_width,
            )
            is_major = (
                consensus_position == 0
                or (consensus_position + 1) % _RULER_MAJOR_INTERVAL == 0
            )
            if is_major:
                canvas.create_text(
                    center_x,
                    _SEQUENCE_RULER_LABEL_Y,
                    text=str(consensus_position + 1),
                    font=("TkDefaultFont", 8, "bold"),
                )
            canvas.create_line(
                center_x,
                _SEQUENCE_RULER_Y - (7 if is_major else 3),
                center_x,
                _SEQUENCE_RULER_Y + (7 if is_major else 3),
                fill="#555555" if is_major else "#888888",
            )
        self._sequence_base_items = []
        for column in self.view_model.columns:
            left_x = _sequence_column_left(
                column.consensus_position,
                self._sequence_character_width,
            )
            center_x = _sequence_column_center(
                column.consensus_position,
                self._sequence_character_width,
            )
            column_tag = f"alignment-column-{column.consensus_position}"
            canvas.create_rectangle(
                left_x,
                _SEQUENCE_BASE_Y - (self._sequence_text_height / 2) - 1,
                left_x + self._sequence_character_width,
                _SEQUENCE_BASE_Y + (self._sequence_text_height / 2) + 1,
                fill=_chromatogram_base_color(column.base),
                outline=_BASE_CELL_OUTLINE,
                tags=("consensus-base-background", column_tag),
            )
            base_item = canvas.create_text(
                center_x,
                _SEQUENCE_BASE_Y,
                anchor="center",
                text=column.base,
                fill=_base_text_color(column.base),
                font=self._sequence_font,
                tags=("consensus-base", column_tag),
            )
            self._sequence_base_items.append(base_item)
        canvas.tag_raise("consensus-base")
        canvas.configure(
            scrollregion=(
                0,
                0,
                _sequence_scroll_width(
                    len(self.view_model.columns),
                    self._sequence_character_width,
                ),
                _SEQUENCE_PANEL_HEIGHT,
            )
        )
        canvas.bind("<Button-1>", self._on_sequence_canvas_click)
        # The sequence panel has no vertical content.  Treat both a horizontal
        # trackpad gesture (normally exposed by Tk as Shift-MouseWheel) and a
        # wheel event while the pointer is over this Canvas as horizontal
        # Canvas movement.  The native scrollbar remains the other xview
        # control; no sequence or selection state is recalculated here.
        canvas.bind("<MouseWheel>", self._on_sequence_horizontal_wheel)
        canvas.bind("<Shift-MouseWheel>", self._on_sequence_horizontal_wheel)
        # Some Tk windowing systems expose horizontal wheel input as buttons
        # rather than a MouseWheel event.  Keeping these bindings local to the
        # sequence Canvas avoids changing scrolling in the rest of the GUI.
        # macOS Tk does not recognise Button-6/Button-7, so retain the native
        # MouseWheel bindings there instead of preventing the window opening.
        try:
            canvas.bind("<Button-6>", self._on_sequence_horizontal_scroll_left)
            canvas.bind("<Button-7>", self._on_sequence_horizontal_scroll_right)
        except tk.TclError:
            pass

        body = tk.PanedWindow(self, orient="horizontal", sashrelief="raised")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        review_frame = tk.LabelFrame(body, text="Review sites", padx=6, pady=6)
        body.add(review_frame, minsize=480)
        self._review_site_list = ttk.Treeview(
            review_frame,
            columns=("position", "v1", "consensus", "reason", "confidence"),
            show="tree headings",
            selectmode="browse",
            height=16,
        )
        self._review_site_list.heading("#0", text="Group")
        self._review_site_list.column("#0", width=135, stretch=False)
        for column_id, label, width in (
            ("position", "Position", 62),
            ("v1", "v1", 35),
            ("consensus", "Base", 45),
            ("reason", "Decision reason", 165),
            ("confidence", "Confidence", 70),
        ):
            self._review_site_list.heading(column_id, text=label)
            self._review_site_list.column(column_id, width=width, stretch=False)
        review_scrollbar = ttk.Scrollbar(
            review_frame,
            orient="vertical",
            command=self._review_site_list.yview,
        )
        self._review_site_list.configure(yscrollcommand=review_scrollbar.set)
        self._review_site_list.pack(side="left", fill="both", expand=True)
        review_scrollbar.pack(side="right", fill="y")
        self._populate_review_sites()
        self._review_site_list.bind(
            "<<TreeviewSelect>>",
            self._on_review_site_selected,
        )

        evidence_frame = tk.LabelFrame(body, text="Evidence", padx=10, pady=10)
        body.add(evidence_frame, minsize=380)
        self._evidence_text = tk.Text(evidence_frame, height=20, width=70, state="disabled", wrap="none")
        self._evidence_text.pack(fill="both", expand=True)

        navigation = tk.LabelFrame(body, text="Chromatogram navigation", padx=10, pady=10)
        body.add(navigation, minsize=185)
        self._forward_button = tk.Button(
            navigation,
            text="Open Forward chromatogram",
            state="disabled",
            command=lambda: self._jump("forward"),
        )
        self._forward_button.pack(fill="x", pady=(0, 8))
        self._reverse_button = tk.Button(
            navigation,
            text="Open Reverse chromatogram",
            state="disabled",
            command=lambda: self._jump("reverse"),
        )
        self._reverse_button.pack(fill="x")
        tk.Label(
            navigation,
            text="Jump uses the existing\nread identifier and raw\ntrace position callback.",
            justify="left",
            pady=12,
        ).pack(anchor="w")

        if self.view_model.columns:
            self.select_base(0)

    def select_base(
        self,
        consensus_position: int,
        *,
        synchronize_review_site: bool = True,
    ) -> None:
        """Select one base and refresh its read-only evidence display."""

        column = self.view_model.column_at(consensus_position)
        self.selected_position = consensus_position
        left_x = _sequence_column_left(
            consensus_position,
            self._sequence_character_width,
        )
        self._sequence_canvas.coords(
            self._selection_item,
            left_x,
            _SEQUENCE_BASE_Y - (self._sequence_text_height / 2) - 2,
            left_x + self._sequence_character_width,
            _SEQUENCE_BASE_Y + (self._sequence_text_height / 2) + 2,
        )
        self._sequence_canvas.itemconfigure(self._selection_item, state="normal")
        center_x = _sequence_column_center(
            consensus_position,
            self._sequence_character_width,
        )
        self._sequence_canvas.coords(
            self._selection_ruler_item,
            center_x,
            _SEQUENCE_RULER_Y - 10,
            center_x,
            _SEQUENCE_RULER_Y + 10,
        )
        self._sequence_canvas.itemconfigure(
            self._selection_ruler_item,
            state="normal",
        )
        self._sequence_canvas.tag_raise(self._selection_item)
        self._sequence_canvas.tag_raise(self._selection_ruler_item)
        evidence = column.review_evidence
        self._set_evidence_text(_format_evidence(column, evidence))
        self._forward_button.configure(
            state=(
                "normal"
                if (
                    self.on_trace_jump is not None
                    and evidence.forward_jump_target is not None
                )
                else "disabled"
            )
        )
        self._reverse_button.configure(
            state=(
                "normal"
                if (
                    self.on_trace_jump is not None
                    and evidence.reverse_jump_target is not None
                )
                else "disabled"
            )
        )
        if (
            synchronize_review_site
            and consensus_position in self._review_site_items
        ):
            item_id = self._review_site_items[consensus_position]
            self._review_site_list.selection_set(item_id)
            self._review_site_list.focus(item_id)
            self._review_site_list.see(item_id)

    def _jump(self, side: str) -> None:
        if self.selected_position is None:
            return
        evidence = self.view_model.column_at(self.selected_position).review_evidence
        target = (
            evidence.forward_jump_target if side == "forward" else evidence.reverse_jump_target
        )
        dispatch_trace_jump(self.on_trace_jump, target)

    def _set_evidence_text(self, text: str) -> None:
        self._evidence_text.configure(state="normal")
        self._evidence_text.delete("1.0", "end")
        self._evidence_text.insert("1.0", text)
        self._evidence_text.configure(state="disabled")

    def _on_sequence_canvas_click(self, event) -> None:
        """Map a Canvas click to its zero-based alignment column."""

        consensus_position = _sequence_x_to_consensus_position(
            self._sequence_canvas.canvasx(event.x),
            len(self.view_model.columns),
            character_width=self._sequence_character_width,
        )
        if consensus_position is not None:
            self.select_base(consensus_position)

    def _on_sequence_horizontal_wheel(self, event):
        """Scroll this Canvas horizontally for local wheel/trackpad input."""

        steps = _wheel_delta_to_scroll_steps(getattr(event, "delta", 0))
        if steps:
            self._sequence_canvas.xview_scroll(steps, "units")
        return "break"

    def _on_sequence_horizontal_scroll_left(self, _event):
        """Support Tk platforms that expose horizontal wheel input as Button-6."""

        self._sequence_canvas.xview_scroll(-1, "units")
        return "break"

    def _on_sequence_horizontal_scroll_right(self, _event):
        """Support Tk platforms that expose horizontal wheel input as Button-7."""

        self._sequence_canvas.xview_scroll(1, "units")
        return "break"

    def _populate_review_sites(self) -> None:
        """List UI-level inspection candidates without changing review status."""

        grouped_columns = {group_id: [] for group_id, _label in _REVIEW_GROUPS}
        for column in self.view_model.columns:
            group_id = _review_site_group(
                column.base,
                column.review_evidence.decision_reason,
            )
            if group_id is not None:
                grouped_columns[group_id].append(column)
        for group_id, group_label in _REVIEW_GROUPS:
            columns = grouped_columns[group_id]
            if not columns:
                continue
            group_item_id = f"group:{group_id}"
            self._review_site_list.insert(
                "",
                "end",
                iid=group_item_id,
                text=group_label,
                open=True,
            )
            for column in columns:
                evidence = column.review_evidence
                item_id = f"site:{column.consensus_position}"
                self._review_site_list.insert(
                    group_item_id,
                    "end",
                    iid=item_id,
                    text="",
                    values=(
                        column.consensus_position + 1,
                        _display_value(evidence.v1_base),
                        column.base,
                        evidence.decision_reason,
                        column.confidence_level,
                    ),
                )
                self._review_site_items[column.consensus_position] = item_id
                self._review_site_positions_by_item[item_id] = column.consensus_position

    def _on_review_site_selected(self, _event=None) -> None:
        selected = self._review_site_list.selection()
        if not selected or selected[0] not in self._review_site_positions_by_item:
            return
        consensus_position = self._review_site_positions_by_item[selected[0]]
        self._scroll_to_sequence_position(consensus_position)
        self.select_base(consensus_position, synchronize_review_site=False)

    def _scroll_to_sequence_position(self, consensus_position: int) -> None:
        total_width = _sequence_scroll_width(
            len(self.view_model.columns),
            self._sequence_character_width,
        )
        visible_width = self._sequence_canvas.winfo_width()
        scrollable_width = total_width - visible_width
        if scrollable_width <= 0:
            return
        target_center = _sequence_column_center(
            consensus_position,
            self._sequence_character_width,
        )
        target_start = target_center - (visible_width / 2)
        target_start = max(0, min(target_start, scrollable_width))
        self._sequence_canvas.xview_moveto(target_start / scrollable_width)


def _display_status(decision_reason: str, consensus_base: str) -> str:
    if consensus_base == "N":
        return "N"
    if decision_reason == "TWO_SIDED_AGREEMENT":
        return "TWO_SIDED_AGREEMENT"
    if decision_reason in ("HIGHER_QUALITY_FORWARD", "HIGHER_QUALITY_REVERSE"):
        return decision_reason
    if decision_reason in ("UNRESOLVED_CONFLICT", "INSUFFICIENT_EVIDENCE"):
        return "UNRESOLVED"
    return "NORMAL"


def _wheel_delta_to_scroll_steps(delta: int) -> int:
    """Convert platform-specific Tk wheel deltas to Canvas xview units."""

    if not delta:
        return 0
    if abs(delta) >= 120:
        return -int(delta / 120)
    return -int(delta)


def _sequence_column_left(consensus_position: int, character_width: int) -> int:
    return _SEQUENCE_LEFT_PADDING + (consensus_position * character_width)


def _sequence_column_center(consensus_position: int, character_width: int) -> float:
    return _sequence_column_left(consensus_position, character_width) + (
        character_width / 2
    )


def _sequence_scroll_width(column_count: int, character_width: int) -> int:
    return max(
        1,
        (2 * _SEQUENCE_LEFT_PADDING) + (column_count * character_width),
    )


def _ruler_positions(column_count: int) -> Sequence[int]:
    if column_count < 1:
        return ()
    positions = [0]
    positions.extend(range(_RULER_INTERVAL - 1, column_count, _RULER_INTERVAL))
    return tuple(positions)


def _chromatogram_base_color(base: str) -> str:
    """Return the pale cell background associated with a displayed base."""

    return _CHROMATOGRAM_BASE_COLORS.get(base.upper(), _CHROMATOGRAM_BASE_COLORS["N"])


def _base_text_color(base: str) -> str:
    return "black"


def _review_site_group(
    consensus_base: str,
    decision_reason: str,
) -> Optional[str]:
    """Classify only the GUI inspection list; this is not a review decision."""

    if consensus_base == "N" or decision_reason in (
        "UNRESOLVED_CONFLICT",
        "INSUFFICIENT_EVIDENCE",
        "AMBIGUOUS_INPUT",
        "GAP_ONLY",
    ):
        return "needs-attention"
    if decision_reason in ("HIGHER_QUALITY_FORWARD", "HIGHER_QUALITY_REVERSE"):
        return "conflict-resolved"
    if decision_reason == "LOW_QUALITY":
        return "low-quality"
    if decision_reason in ("ONE_SIDED_FORWARD", "ONE_SIDED_REVERSE"):
        return "terminal-one-sided"
    return None


def _display_value(value: object | None) -> str:
    return "-" if value is None else str(value)


def _sequence_x_to_consensus_position(
    canvas_x: float,
    column_count: int,
    *,
    character_width: int,
) -> Optional[int]:
    """Return the clicked zero-based alignment column, or None for margins."""

    if column_count < 1 or character_width < 1:
        return None
    relative_x = canvas_x - _SEQUENCE_LEFT_PADDING
    if relative_x < 0:
        return None
    consensus_position = int(relative_x // character_width)
    if consensus_position >= column_count:
        return None
    return consensus_position


def _format_evidence(column: SingleConsensusColumn, evidence: ReviewEvidence) -> str:
    return "\n".join(
        (
            "Consensus",
            f"Position (1-based): {column.consensus_position + 1}",
            f"Alignment column (0-based): {evidence.alignment_column}",
            f"Base: {evidence.consensus_base}",
            f"Status: {column.status}",
            f"Decision reason: {evidence.decision_reason}",
            f"Selected source: {column.selected_source}",
            f"Confidence: {column.confidence_level}",
            f"v1 base: {_value(evidence.v1_base)}",
            "",
            "Forward evidence",
            _format_side(
                evidence.forward_read_identifier,
                evidence.forward_base,
                evidence.forward_quality,
                evidence.forward_raw_index,
                evidence.forward_trimmed_index,
                evidence.forward_raw_trace_position,
                evidence.forward_trimmed_trace_position,
            ),
            "",
            "Reverse evidence",
            _format_side(
                evidence.reverse_read_identifier,
                evidence.reverse_base,
                evidence.reverse_quality,
                evidence.reverse_raw_index,
                evidence.reverse_trimmed_index,
                evidence.reverse_raw_trace_position,
                evidence.reverse_trimmed_trace_position,
            ),
        )
    )


def _format_side(read_identifier, base, quality, raw_index, trimmed_index, raw_trace, trimmed_trace):
    return "\n".join(
        (
            f"Read: {read_identifier}",
            f"Base: {_value(base)}",
            f"Quality: {_value(quality)}",
            f"Raw index: {_value(raw_index)}",
            f"Trimmed index: {_value(trimmed_index)}",
            f"Raw trace position: {_value(raw_trace)}",
            f"Trimmed trace position: {_value(trimmed_trace)}",
        )
    )


def _value(value) -> str:
    return "None" if value is None else str(value)
