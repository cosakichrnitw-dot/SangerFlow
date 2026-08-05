"""Prototype for comparing aligned consensus sequences and recording cell edits.

This module intentionally accepts an alignment supplied by its caller. It uses
the core ``AlignedConsensusSet`` value contract but does not import consensus
decisions, export, or Main Viewer modules. It never calculates an alignment
or changes an input sequence; direct edits are stored as review-session
decisions plus a local display overlay.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import csv
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox

from core.consensus_alignment import AlignedConsensusSet
from core.consensus_evidence_map import ConsensusEvidenceMap
from core.consensus_review_bridge import ReviewEvidence, TraceJumpTarget
from core.consensus_review_session import ConsensusReviewSession
from core.human_review import DecisionType, HumanReviewDecision
from gui.alignment_editor_state import AlignmentEditorState


ConsensusSelectedCallback = Callable[[str, int], None]
TraceJumpCallback = Callable[[str, int], None]
_ALLOWED_ALIGNMENT_SYMBOLS = frozenset("ACGTNRYSWKMBDHV-")
_LABEL_WIDTH = 150
_CELL_WIDTH = 18
_RULER_HEIGHT = 42
# The label and matrix canvases are separate horizontal surfaces, but they
# share one vertical row layout.  Do not introduce canvas-specific row offsets.
_ROW_HEIGHT = 22
_ROW_TOP_MARGIN = _RULER_HEIGHT + 4
_BASE_COLORS = {
    "A": "#E06666",
    "C": "#7BC67B",
    "G": "#F6E15A",
    "T": "#6FA8DC",
}
_AMBIGUOUS_COLOR = "#B7B7B7"
_GAP_COLOR = "#D9D9D9"
_CELL_OUTLINE = "#B8B8B8"
_VARIABLE_OUTLINE = "#8064A2"
_SELECTION_OUTLINE = "#1F4E79"
_EDITED_CELL_BACKGROUND = "#DCEEFF"
_RANGE_SELECTION_FILL = "#EADCF8"
_RANGE_SELECTION_OUTLINE = "#8064A2"
_EDITING_OUTLINE = "#7030A0"
_MATRIX_PANE_MIN_WIDTH = 640
_CONTROL_PANE_MIN_WIDTH = 300
_EDITABLE_ALIGNMENT_SYMBOLS = frozenset("ACGTNRYSWKMBDHV-")


@dataclass(frozen=True)
class MultipleAlignmentRow:
    """One sample row plus its alignment-to-consensus coordinate map."""

    sample_id: str
    aligned_sequence: str
    consensus_position_by_column: tuple[Optional[int], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.sample_id, str) or not self.sample_id:
            raise ValueError("sample_id must be a non-empty string")
        if not isinstance(self.aligned_sequence, str):
            raise ValueError("aligned_sequence must be a string")
        if len(self.consensus_position_by_column) != len(self.aligned_sequence):
            raise ValueError("coordinate map and aligned sequence lengths differ")
        expected_position = 0
        for base, consensus_position in zip(
            self.aligned_sequence,
            self.consensus_position_by_column,
        ):
            if base == "-":
                if consensus_position is not None:
                    raise ValueError("gap columns must not have a consensus position")
                continue
            if consensus_position != expected_position:
                raise ValueError("non-gap consensus positions must be contiguous and 0-based")
            expected_position += 1

    def consensus_position_at(self, alignment_column: int) -> Optional[int]:
        return self.consensus_position_by_column[alignment_column]


@dataclass(frozen=True)
class MultipleAlignmentColumn:
    """Display-only summary for one multiple-alignment column."""

    alignment_column: int
    bases: tuple[str, ...]
    base_counts: tuple[tuple[str, int], ...]
    is_variable: bool

    def __post_init__(self) -> None:
        if self.alignment_column < 0:
            raise ValueError("alignment_column must be 0-based and non-negative")
        if not self.bases:
            raise ValueError("an alignment column needs at least one base")
        if tuple(sorted(Counter(self.bases).items())) != self.base_counts:
            raise ValueError("base_counts must describe bases exactly")


@dataclass(frozen=True)
class VariableSiteSample:
    """One sample's display-only evidence at a variable alignment column."""

    sample_id: str
    base: str
    consensus_position: Optional[int]


@dataclass(frozen=True)
class VariableSite:
    """One variable multiple-alignment column for read-only display."""

    alignment_column: int
    samples: tuple[VariableSiteSample, ...]


@dataclass(frozen=True)
class EditedCell:
    """One review-only overlay entry, addressed in alignment coordinates."""

    sample_id: str
    row_index: int
    alignment_column: int
    consensus_position: Optional[int]
    original_base: str
    edited_base: str


@dataclass(frozen=True)
class MultipleAlignmentViewModel:
    """Immutable display adapter for an already aligned consensus matrix."""

    rows: tuple[MultipleAlignmentRow, ...]
    columns: tuple[MultipleAlignmentColumn, ...]
    alignment_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("at least one aligned consensus row is required")
        alignment_length = len(self.rows[0].aligned_sequence)
        if any(len(row.aligned_sequence) != alignment_length for row in self.rows):
            raise ValueError("all aligned sequences must have the same length")
        if len(self.columns) != alignment_length:
            raise ValueError("columns must match alignment length")
        if tuple(column.alignment_column for column in self.columns) != tuple(
            range(alignment_length)
        ):
            raise ValueError("alignment columns must be contiguous and 0-based")

    @property
    def alignment_length(self) -> int:
        return len(self.columns)

    def row_at(self, row_index: int) -> MultipleAlignmentRow:
        return self.rows[row_index]

    def column_at(self, alignment_column: int) -> MultipleAlignmentColumn:
        return self.columns[alignment_column]


class _CollapsibleSection(tk.Frame):
    """A compact control-panel section with an explicit expanded state."""

    def __init__(self, parent, title: str, *, expanded: bool) -> None:
        super().__init__(parent, borderwidth=1, relief="groove")
        self._title = title
        self._expanded = expanded
        self._toggle_button = tk.Button(
            self,
            anchor="w",
            relief="flat",
            borderwidth=0,
            font=("TkDefaultFont", 10, "bold"),
            command=self.toggle,
        )
        self._toggle_button.pack(fill="x", padx=4, pady=3)
        self.content = tk.Frame(self, padx=8, pady=6)
        self._render_state()

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._render_state()

    def _render_state(self) -> None:
        indicator = "▼" if self._expanded else "▶"
        self._toggle_button.configure(text=f"{indicator} {self._title}")
        if self._expanded:
            self.content.pack(fill="x")
        else:
            self.content.pack_forget()


def build_multiple_alignment_view_model(
    aligned_consensus_set: AlignedConsensusSet | Sequence[Mapping[str, str]],
) -> MultipleAlignmentViewModel:
    """Adapt an ``AlignedConsensusSet`` for read-only matrix display.

    The normal input is the result of ``run_consensus_alignment()``. Its
    original gap-aware mapping is copied without recalculation. A sequence-list
    input remains only as a compatibility path for the pre-core launcher; it
    must already be aligned and has no MAFFT provenance.
    """

    if isinstance(aligned_consensus_set, AlignedConsensusSet):
        return _build_view_model_from_aligned_consensus_set(aligned_consensus_set)
    return _build_legacy_sequence_list_view_model(aligned_consensus_set)


def _build_view_model_from_aligned_consensus_set(
    aligned_consensus_set: AlignedConsensusSet,
) -> MultipleAlignmentViewModel:
    """Copy the core result's aligned rows and original coordinate maps."""

    rows = tuple(
        MultipleAlignmentRow(
            sample_id=sequence.sample_id,
            aligned_sequence=sequence.aligned_sequence,
            consensus_position_by_column=sequence.consensus_position_mapping,
        )
        for sequence in aligned_consensus_set.sequences
    )
    columns = _build_view_columns(rows)
    return MultipleAlignmentViewModel(
        rows=rows,
        columns=columns,
        alignment_id=aligned_consensus_set.alignment_id,
    )


def _build_legacy_sequence_list_view_model(
    consensus_sequences: Sequence[Mapping[str, str]],
) -> MultipleAlignmentViewModel:
    """Preserve the prototype launcher path for pre-aligned display records."""

    rows = []
    seen_sample_ids = set()
    for item in consensus_sequences:
        if not isinstance(item, Mapping):
            raise ValueError("each consensus sequence must be a mapping")
        sample_id = item.get("sample_id")
        sequence = item.get("sequence")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError("each consensus sequence needs a non-empty sample_id")
        if sample_id in seen_sample_ids:
            raise ValueError("sample_id values must be unique")
        if not isinstance(sequence, str) or not sequence:
            raise ValueError("each consensus sequence needs a non-empty sequence")
        aligned_sequence = sequence.upper()
        unsupported = set(aligned_sequence) - _ALLOWED_ALIGNMENT_SYMBOLS
        if unsupported:
            raise ValueError(
                "sequence contains unsupported alignment symbols: "
                + ", ".join(sorted(unsupported))
            )
        rows.append(
            MultipleAlignmentRow(
                sample_id=sample_id,
                aligned_sequence=aligned_sequence,
                consensus_position_by_column=_consensus_positions(aligned_sequence),
            )
        )
        seen_sample_ids.add(sample_id)

    if not rows:
        raise ValueError("at least one consensus sequence is required")
    alignment_length = len(rows[0].aligned_sequence)
    if any(len(row.aligned_sequence) != alignment_length for row in rows):
        raise ValueError("input sequences must already have the same alignment length")

    row_values = tuple(rows)
    return MultipleAlignmentViewModel(
        rows=row_values,
        columns=_build_view_columns(row_values),
    )


class MultipleConsensusAlignmentWindow(tk.Toplevel):
    """Canvas prototype for comparison plus one-cell review edits."""

    def __init__(
        self,
        master,
        view_model: MultipleAlignmentViewModel | AlignedConsensusSet,
        *,
        on_consensus_selected: Optional[ConsensusSelectedCallback] = None,
        evidence_map: Optional[ConsensusEvidenceMap] = None,
        on_trace_jump: Optional[TraceJumpCallback] = None,
    ) -> None:
        if isinstance(view_model, AlignedConsensusSet):
            view_model = build_multiple_alignment_view_model(view_model)
        if not isinstance(view_model, MultipleAlignmentViewModel):
            raise ValueError(
                "view_model must be a MultipleAlignmentViewModel or AlignedConsensusSet"
            )
        if on_consensus_selected is not None and not callable(on_consensus_selected):
            raise ValueError("on_consensus_selected must be callable or None")
        if evidence_map is not None and not isinstance(evidence_map, ConsensusEvidenceMap):
            raise ValueError("evidence_map must be a ConsensusEvidenceMap or None")
        if on_trace_jump is not None and not callable(on_trace_jump):
            raise ValueError("on_trace_jump must be callable or None")
        super().__init__(master)
        self.view_model = view_model
        self.variable_sites = build_variable_sites(view_model)
        self.on_consensus_selected = on_consensus_selected
        self.evidence_map = evidence_map
        self.on_trace_jump = on_trace_jump
        self._selected_review_evidence: Optional[ReviewEvidence] = None
        # The displayed matrix remains an immutable adapter of the MAFFT
        # result.  Edits are a display overlay plus append-only review
        # decisions, grouped by sample in workflow sessions.
        self.review_sessions: dict[str, ConsensusReviewSession] = {}
        self._matrix_cell_edits: dict[tuple[int, int], str] = {}
        self._matrix_cell_items: dict[tuple[int, int], tuple[int, int]] = {}
        self._selected_cells: tuple[tuple[int, int], ...] = ()
        self._selection_anchor: Optional[tuple[int, int]] = None
        self._editing_cells: tuple[tuple[int, int], ...] = ()
        self.editor_state = AlignmentEditorState(
            row_count=len(view_model.rows),
            column_count=view_model.alignment_length,
        )
        self._selected_review_input: Optional[tuple[str, int, str]] = None
        self.selected_row_index: Optional[int] = None
        self.selected_alignment_column: Optional[int] = None
        self._initial_sash_placed = False
        self.title("Multiple Consensus Alignment Review")
        self.geometry("1440x820")
        self.minsize(1080, 620)
        self._build_layout()

    def _build_layout(self) -> None:
        tk.Label(
            self,
            text=(
                f"Multiple Consensus Alignment — {len(self.view_model.rows)} samples, "
                f"{self.view_model.alignment_length} columns"
            ),
            anchor="w",
            font=("TkDefaultFont", 12, "bold"),
            padx=12,
            pady=8,
        ).pack(fill="x")

        # The two panes are deliberately resizable: the matrix is normally
        # wide, while a researcher can enlarge the control side as needed.
        self._workspace_panes = tk.PanedWindow(
            self,
            orient="horizontal",
            sashrelief="raised",
            sashwidth=8,
        )
        self._workspace_panes.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        matrix_frame = tk.LabelFrame(
            self._workspace_panes,
            text="Aligned consensus sequences",
            padx=6,
            pady=6,
        )
        self._workspace_panes.add(
            matrix_frame,
            minsize=_MATRIX_PANE_MIN_WIDTH,
            stretch="always",
        )
        # Four-surface editor grid: headers never scroll independently.
        matrix_frame.grid_rowconfigure(1, weight=1)
        matrix_frame.grid_columnconfigure(1, weight=1)
        self._corner_canvas = tk.Canvas(matrix_frame, width=_LABEL_WIDTH, height=_ROW_TOP_MARGIN, highlightthickness=0, background="white")
        self._position_canvas = tk.Canvas(matrix_frame, height=_ROW_TOP_MARGIN, highlightthickness=0, background="white")
        self._label_canvas = tk.Canvas(
            matrix_frame,
            width=_LABEL_WIDTH,
            highlightthickness=0,
            background="white",
        )
        self._corner_canvas.grid(row=0, column=0, sticky="nsew")
        self._position_canvas.grid(row=0, column=1, sticky="ew")
        self._label_canvas.grid(row=1, column=0, sticky="ns")
        self._label_canvas.bind("<MouseWheel>", self._on_label_wheel)
        self._label_canvas.bind("<Button-1>", self._on_row_header_click)
        self._matrix_canvas = tk.Canvas(
            matrix_frame,
            highlightthickness=0,
            background="white",
        )
        vertical_scrollbar = tk.Scrollbar(
            matrix_frame,
            orient="vertical",
            command=self._scroll_y,
        )
        horizontal_scrollbar = tk.Scrollbar(
            matrix_frame,
            orient="horizontal",
            command=self._matrix_canvas.xview,
        )
        self._vertical_scrollbar = vertical_scrollbar
        self._matrix_canvas.configure(
            xscrollcommand=lambda first, last: self._set_x_scrollbar(horizontal_scrollbar, first, last),
            yscrollcommand=self._set_y_scrollbar,
        )
        # A Canvas can clamp its current yview while its viewport is laid out
        # or resized. Reapply the matrix fraction after either viewport
        # changes so the label side cannot remain at an earlier position.
        self._matrix_canvas.bind("<Configure>", self._on_vertical_viewport_configure)
        self._label_canvas.bind("<Configure>", self._on_vertical_viewport_configure)
        self._matrix_canvas.grid(row=1, column=1, sticky="nsew")
        vertical_scrollbar.grid(row=1, column=2, sticky="ns")
        horizontal_scrollbar.grid(row=2, column=1, sticky="ew")
        self._draw_matrix()
        self._matrix_canvas.bind("<Button-1>", self._on_matrix_click)
        self._matrix_canvas.bind("<Double-Button-1>", self._on_matrix_double_click)
        self._matrix_canvas.bind("<Key>", self._on_matrix_key)
        self._matrix_canvas.bind("<MouseWheel>", self._on_matrix_wheel)
        self._matrix_canvas.bind("<Shift-MouseWheel>", self._on_matrix_wheel)
        try:
            self._matrix_canvas.bind("<Button-6>", self._on_horizontal_scroll_left)
            self._matrix_canvas.bind("<Button-7>", self._on_horizontal_scroll_right)
        except tk.TclError:
            pass

        control_host = tk.Frame(self._workspace_panes)
        self._workspace_panes.add(
            control_host,
            minsize=_CONTROL_PANE_MIN_WIDTH,
            stretch="never",
        )
        self._control_canvas = tk.Canvas(control_host, highlightthickness=0)
        self._control_scrollbar = tk.Scrollbar(
            control_host,
            orient="vertical",
            command=self._control_canvas.yview,
        )
        self._control_canvas.configure(yscrollcommand=self._control_scrollbar.set)
        self._control_scrollbar.pack(side="right", fill="y")
        self._control_canvas.pack(side="left", fill="both", expand=True)
        control_panel = tk.Frame(self._control_canvas)
        self._control_canvas_window = self._control_canvas.create_window(
            (0, 0),
            window=control_panel,
            anchor="nw",
        )
        control_panel.bind("<Configure>", self._update_control_scrollregion)
        self._control_canvas.bind("<Configure>", self._resize_control_panel)
        self._control_canvas.bind("<MouseWheel>", self._on_control_panel_wheel)

        self._selected_section = _CollapsibleSection(
            control_panel,
            "Selected Site",
            expanded=True,
        )
        self._selected_section.pack(fill="x", pady=(0, 6))
        selected_frame = self._selected_section.content
        self._selected_site_text = tk.StringVar(value="Select a base in the matrix.")
        tk.Label(
            selected_frame,
            textvariable=self._selected_site_text,
            anchor="w",
            justify="left",
            font=("TkFixedFont", 10),
        ).pack(fill="x")
        self._open_single_button = tk.Button(
            selected_frame,
            text="Open selected consensus",
            state="disabled",
            command=self._open_selected_consensus,
        )
        self._open_single_button.pack(anchor="e", pady=(6, 0))

        self._evidence_section = _CollapsibleSection(
            control_panel,
            "Consensus Evidence",
            expanded=True,
        )
        self._evidence_section.pack(fill="x", pady=(0, 6))
        evidence_frame = self._evidence_section.content
        self._evidence_text = tk.Text(
            evidence_frame,
            height=8,
            wrap="word",
            state="normal",
            font=("TkFixedFont", 10),
        )
        self._evidence_text.pack(fill="x", expand=True)
        self._set_evidence_text("Select a non-gap sample base to inspect consensus evidence.\n")
        evidence_buttons = tk.Frame(evidence_frame)
        evidence_buttons.pack(fill="x", pady=(6, 0))
        self._forward_chromatogram_button = tk.Button(
            evidence_buttons,
            text="Open Forward Chromatogram",
            state="disabled",
            command=lambda: self._jump_to_evidence_trace("forward"),
        )
        self._forward_chromatogram_button.pack(fill="x")
        self._reverse_chromatogram_button = tk.Button(
            evidence_buttons,
            text="Open Reverse Chromatogram",
            state="disabled",
            command=lambda: self._jump_to_evidence_trace("reverse"),
        )
        self._reverse_chromatogram_button.pack(fill="x", pady=(4, 0))

        self._human_review_section = _CollapsibleSection(
            control_panel,
            "Edited Cells",
            expanded=True,
        )
        self._human_review_section.pack(fill="x", pady=(0, 6))
        human_review_frame = self._human_review_section.content
        self._review_current_base_var = tk.StringVar(value="Current base: unavailable")
        self._review_status_var = tk.StringVar(value="Review status: Not reviewed")
        self._reviewed_base_var = tk.StringVar()
        self._review_reason_var = tk.StringVar()
        tk.Label(human_review_frame, textvariable=self._review_current_base_var).pack(anchor="w")
        self._reviewed_base_label = tk.Label(human_review_frame, text="Edited base")
        self._reviewed_base_entry = tk.Entry(
            human_review_frame,
            width=5,
            textvariable=self._reviewed_base_var,
        )
        self._review_reason_label = tk.Label(human_review_frame, text="Reason")
        self._review_reason_entry = tk.Entry(
            human_review_frame,
            textvariable=self._review_reason_var,
        )
        self._review_save_button = tk.Button(
            human_review_frame,
            text="Save Decision",
            state="disabled",
            command=self._save_human_review_decision,
        )
        self._review_status_label = tk.Label(
            human_review_frame,
            textvariable=self._review_status_var,
            anchor="w",
            justify="left",
        )
        self._reviewed_base_label.pack(anchor="w", pady=(4, 0))
        self._reviewed_base_entry.pack(anchor="w")
        self._review_reason_label.pack(anchor="w", pady=(4, 0))
        self._review_reason_entry.pack(fill="x")
        self._review_save_button.pack(anchor="e", pady=(6, 0))
        self._review_status_label.pack(anchor="w", pady=(4, 0))
        self._set_human_review_available(False)

        edited_list_frame = tk.Frame(human_review_frame)
        edited_list_frame.pack(fill="x", pady=(8, 0))
        tk.Label(edited_list_frame, text="Edited cells", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self._edited_cells_text = tk.Text(
            edited_list_frame, height=9, wrap="none", state="normal", font=("TkFixedFont", 10)
        )
        self._edited_cells_text.pack(fill="x")
        self._refresh_edited_cells_panel()
        self._edited_cells_text.configure(state="disabled")

        self._variable_sites_section = _CollapsibleSection(
            control_panel,
            "Variable Sites",
            expanded=True,
        )
        self._variable_sites_section.pack(fill="x", pady=(0, 6))
        variable_frame = self._variable_sites_section.content
        variable_scrollbar = tk.Scrollbar(variable_frame, orient="vertical")
        variable_scrollbar.pack(side="right", fill="y")
        self._variable_sites_text = tk.Text(
            variable_frame,
            height=10,
            wrap="none",
            state="normal",
            font=("TkFixedFont", 10),
            yscrollcommand=variable_scrollbar.set,
        )
        self._variable_sites_text.pack(side="left", fill="x", expand=True)
        variable_scrollbar.configure(command=self._variable_sites_text.yview)
        self._populate_variable_sites_panel()
        self._variable_sites_text.configure(state="disabled")

        self._review_summary_section = _CollapsibleSection(
            control_panel,
            "Review Summary",
            expanded=False,
        )
        self._review_summary_section.pack(fill="x")
        self._review_summary_var = tk.StringVar(value=_format_review_summary(()))
        tk.Label(
            self._review_summary_section.content,
            textvariable=self._review_summary_var,
            anchor="w",
            justify="left",
            font=("TkFixedFont", 10),
        ).pack(fill="x")
        tk.Button(
            self._review_summary_section.content,
            text="Show edited cells",
            command=self._focus_edited_cells,
        ).pack(anchor="w", pady=(6, 0))

        self._build_export_menu()
        self._workspace_panes.bind("<Configure>", self._place_initial_sash)
        self.after_idle(self._place_initial_sash)

    def _place_initial_sash(self, _event=None) -> None:
        """Set the initial 80/20 split once without overriding user resizing."""

        if self._initial_sash_placed:
            return
        available_width = self._workspace_panes.winfo_width()
        if available_width <= 1:
            return
        maximum_matrix_width = available_width - _CONTROL_PANE_MIN_WIDTH
        if maximum_matrix_width < _MATRIX_PANE_MIN_WIDTH:
            return
        matrix_width = min(
            max(int(available_width * 0.80), _MATRIX_PANE_MIN_WIDTH),
            maximum_matrix_width,
        )
        self._workspace_panes.sash_place(0, matrix_width, 0)
        self._initial_sash_placed = True

    def _build_export_menu(self) -> None:
        """Expose explicit exports without mutating any candidate or alignment."""

        menu_button = tk.Menubutton(self, text="Export", relief="raised")
        menu_button.place(relx=0.985, x=-6, y=9, anchor="ne")
        menu = tk.Menu(menu_button, tearoff=False)
        menu.add_command(label="Original Consensus FASTA…", command=self._export_original_consensus)
        menu.add_command(label="Reviewed Consensus FASTA…", command=self._export_reviewed_consensus)
        menu.add_command(label="Current Alignment FASTA…", command=self._export_current_alignment)
        menu.add_separator()
        menu.add_command(label="Review Report TSV…", command=self._export_review_report)
        menu.add_command(label="Review Report Excel (planned)", state="disabled")
        menu_button.configure(menu=menu)
        self._export_menu_button = menu_button

    def _ask_export_path(self, title: str, extension: str) -> Optional[Path]:
        value = filedialog.asksaveasfilename(
            parent=self,
            title=title,
            defaultextension=extension,
            filetypes=((f"{extension.upper().lstrip('.')} file", f"*{extension}"),),
        )
        return Path(value) if value else None

    def _export_original_consensus(self) -> None:
        path = self._ask_export_path("Export original consensus FASTA", ".fasta")
        if path is not None:
            write_fasta_records(path, ((row.sample_id, _original_sequence(row)) for row in self.view_model.rows))

    def _export_reviewed_consensus(self) -> None:
        path = self._ask_export_path("Export reviewed consensus FASTA", ".fasta")
        if path is None:
            return
        try:
            records = reviewed_consensus_records(self.view_model, self._matrix_cell_edits)
        except ValueError as error:
            messagebox.showerror("Reviewed consensus export", str(error), parent=self)
            return
        write_fasta_records(path, records)

    def _export_current_alignment(self) -> None:
        path = self._ask_export_path("Export current alignment FASTA", ".fasta")
        if path is not None:
            write_fasta_records(path, current_alignment_records(self.view_model, self._matrix_cell_edits))

    def _export_review_report(self) -> None:
        path = self._ask_export_path("Export review report TSV", ".tsv")
        if path is not None:
            write_review_report_tsv(path, build_edited_cells(self.view_model, self._matrix_cell_edits), self.review_sessions)

    def _update_control_scrollregion(self, _event=None) -> None:
        """Keep every control section reachable in a narrow or short window."""

        bounds = self._control_canvas.bbox("all")
        if bounds is not None:
            self._control_canvas.configure(scrollregion=bounds)

    def _resize_control_panel(self, event) -> None:
        """Keep the scrollable control content matched to the right-pane width."""

        self._control_canvas.itemconfigure(self._control_canvas_window, width=event.width)

    def _on_control_panel_wheel(self, event):
        """Allow normal mouse-wheel scrolling when the control canvas has focus."""

        steps = _wheel_delta_to_scroll_steps(getattr(event, "delta", 0))
        if steps:
            self._control_canvas.yview_scroll(steps, "units")
        return "break"

    def select_cell(self, row_index: int, alignment_column: int) -> None:
        """Select a matrix cell and update read-only selection information."""

        row = self.view_model.row_at(row_index)
        base = self._display_base(row_index, alignment_column)
        consensus_position = row.consensus_position_at(alignment_column)
        self.selected_row_index = row_index
        self.select_alignment_column(alignment_column)
        self._matrix_canvas.coords(
            self._selection_item,
            alignment_column * _CELL_WIDTH,
            _row_top_y(row_index),
            (alignment_column + 1) * _CELL_WIDTH,
            _row_top_y(row_index + 1),
        )
        self._matrix_canvas.itemconfigure(self._selection_item, state="normal")
        self._matrix_canvas.tag_raise(self._selection_item)
        self._selected_site_text.set(
            _selected_site_summary(
                row.sample_id,
                alignment_column,
                consensus_position,
                base,
            )
        )
        evidence = _review_evidence_for_selection(
            self.evidence_map,
            row.sample_id,
            consensus_position,
        )
        self._selected_review_evidence = evidence
        self._set_evidence_text(
            _evidence_text_for_selection(
                self.evidence_map,
                row.sample_id,
                consensus_position,
            )
        )
        self._configure_evidence_navigation(evidence)
        # Human Review keeps the candidate base as its immutable original
        # value, even after an edit overlay changes what the matrix displays.
        self._configure_human_review(
            row.sample_id,
            consensus_position,
            row.aligned_sequence[alignment_column],
        )
        self._open_single_button.configure(
            state=(
                "normal"
                if self.on_consensus_selected is not None and consensus_position is not None
                else "disabled"
            )
        )

    def select_alignment_column(self, alignment_column: int) -> None:
        """Highlight one matrix column and bring it into the horizontal viewport."""

        if not 0 <= alignment_column < self.view_model.alignment_length:
            raise ValueError("alignment_column is outside the multiple alignment")
        self.selected_alignment_column = alignment_column
        self._matrix_canvas.coords(
            self._column_selection_item,
            alignment_column * _CELL_WIDTH,
            _ROW_TOP_MARGIN,
            (alignment_column + 1) * _CELL_WIDTH,
            _matrix_content_height(len(self.view_model.rows)),
        )
        self._matrix_canvas.itemconfigure(self._column_selection_item, state="normal")
        self._matrix_canvas.tag_raise(self._column_selection_item)
        self._scroll_column_into_view(alignment_column)

    def _populate_variable_sites_panel(self) -> None:
        """Add display-only site blocks that select their matrix column on click."""

        if not self.variable_sites:
            self._variable_sites_text.insert("1.0", "No variable alignment columns.\n")
            return
        for site in self.variable_sites:
            start = self._variable_sites_text.index("end-1c")
            self._variable_sites_text.insert(
                "end",
                _format_variable_site(site),
            )
            end = self._variable_sites_text.index("end-1c")
            tag_name = f"variable-site-column-{site.alignment_column}"
            self._variable_sites_text.tag_add(tag_name, start, end)
            self._variable_sites_text.tag_configure(tag_name, underline=True)
            self._variable_sites_text.tag_bind(
                tag_name,
                "<Button-1>",
                lambda _event, column=site.alignment_column: self._on_variable_site_click(column),
            )

    def _on_variable_site_click(self, alignment_column: int) -> str:
        """Select only the clicked column; no downstream navigation is performed."""

        self.selected_row_index = None
        self.select_alignment_column(alignment_column)
        self._matrix_canvas.itemconfigure(self._selection_item, state="hidden")
        self._selected_site_text.set(
            f"Alignment column: {alignment_column} (0-based)\n"
            "Select a sample cell to view its consensus position."
        )
        self._set_evidence_text("Select a sample cell to inspect consensus evidence.\n")
        self._selected_review_evidence = None
        self._configure_evidence_navigation(None)
        self._set_human_review_available(False)
        self._open_single_button.configure(state="disabled")
        return "break"

    def _set_evidence_text(self, text: str) -> None:
        """Replace read-only Evidence Panel text without altering evidence data."""

        self._evidence_text.configure(state="normal")
        self._evidence_text.delete("1.0", "end")
        self._evidence_text.insert("1.0", text)
        self._evidence_text.configure(state="disabled")

    def _configure_evidence_navigation(self, evidence: Optional[ReviewEvidence]) -> None:
        """Enable navigation only for existing bridge targets and a callback."""

        self._forward_chromatogram_button.configure(
            state=(
                "normal"
                if self.on_trace_jump is not None
                and evidence is not None
                and evidence.forward_jump_target is not None
                else "disabled"
            )
        )
        self._reverse_chromatogram_button.configure(
            state=(
                "normal"
                if self.on_trace_jump is not None
                and evidence is not None
                and evidence.reverse_jump_target is not None
                else "disabled"
            )
        )

    def _jump_to_evidence_trace(self, side: str) -> None:
        """Pass an existing TraceJumpTarget to the caller; do not calculate it."""

        evidence = self._selected_review_evidence
        target = None
        if evidence is not None:
            target = (
                evidence.forward_jump_target
                if side == "forward"
                else evidence.reverse_jump_target
            )
        dispatch_multiple_evidence_trace_jump(self.on_trace_jump, target)

    def _configure_human_review(
        self,
        sample_id: str,
        consensus_position: Optional[int],
        base: str,
    ) -> None:
        """Enable review only for an existing non-gap consensus base."""

        if consensus_position is None or base == "-":
            self._set_human_review_available(False)
            return
        self._selected_review_input = (sample_id, consensus_position, base)
        self._review_current_base_var.set(f"Current base: {base}")
        self._review_status_var.set("Review status: Not reviewed")
        self._reviewed_base_var.set(base)
        self._review_reason_var.set("")
        self._set_human_review_available(True)

    def _set_human_review_available(self, available: bool) -> None:
        """Disable all edit controls for gaps or when no matrix base is selected."""

        if not available:
            self._selected_review_input = None
            self._review_current_base_var.set("Current base: unavailable")
            self._review_status_var.set("Review status: Gap or no base selected")
        state = "normal" if available else "disabled"
        self._reviewed_base_entry.configure(state=state)
        self._review_reason_entry.configure(state=state)
        self._review_save_button.configure(state=state)

    def _save_human_review_decision(self) -> None:
        """Append one immutable decision; do not build ReviewedConsensus here."""

        selected = self._selected_review_input
        if selected is None:
            self._review_status_var.set("Review status: Gap or no base selected")
            return
        sample_id, consensus_position, original_base = selected
        try:
            decision = create_matrix_edit_decision(
                sample_id=sample_id,
                consensus_position=consensus_position,
                original_base=original_base,
                proposed_base=self._reviewed_base_var.get(),
                reason=self._review_reason_var.get(),
                evidence_reference=self._selected_review_evidence,
            )
        except ValueError as error:
            self._review_status_var.set(f"Review status: {error}")
            return
        if not self._apply_human_review_overlay(decision):
            return
        self._record_review_decision(decision, replace_existing=True)
        self._refresh_edited_cells_panel()
        rendered_base = decision.reviewed_base or decision.original_base
        self._review_status_var.set(
            "Review status: Reviewed\n"
            f"Decision: {decision.decision_type.value} "
            f"{decision.original_base} → {rendered_base}"
        )

    def _apply_human_review_overlay(self, decision: HumanReviewDecision) -> bool:
        """Reflect a saved base-changing form decision in the Matrix overlay.

        The lookup uses the existing per-row consensus-position mapping.  It
        does not recalculate coordinates or alter the immutable MAFFT input.
        """

        if decision.decision_type not in (DecisionType.CHANGE, DecisionType.AMBIGUOUS):
            return True
        if decision.reviewed_base is None:
            return True
        cell = self._find_matrix_cell(
            decision.sample_id,
            decision.consensus_position,
        )
        if cell is None:
            self._review_status_var.set(
                "Review status: Selected consensus position is not available in this matrix"
            )
            return False
        self._matrix_cell_edits[cell] = decision.reviewed_base
        self._repaint_matrix_cell(*cell, decision.reviewed_base)
        return True

    def _find_matrix_cell(
        self,
        sample_id: str,
        consensus_position: int,
    ) -> Optional[tuple[int, int]]:
        """Resolve an existing sample consensus position to one matrix cell."""

        for row_index, row in enumerate(self.view_model.rows):
            if row.sample_id != sample_id:
                continue
            for alignment_column, position in enumerate(row.consensus_position_by_column):
                if position == consensus_position:
                    return row_index, alignment_column
            return None
        return None

    def _scroll_column_into_view(self, alignment_column: int) -> None:
        """Move horizontally only when the selected column is outside the viewport."""

        fraction = _horizontal_fraction_for_column(
            alignment_column,
            alignment_length=self.view_model.alignment_length,
            viewport_width=self._matrix_canvas.winfo_width(),
            current_xview=self._matrix_canvas.xview(),
        )
        if fraction is not None:
            self._matrix_canvas.xview_moveto(fraction)

    def _draw_matrix(self) -> None:
        matrix_width = self.view_model.alignment_length * _CELL_WIDTH
        matrix_height = _matrix_content_height(len(self.view_model.rows))
        font = tkfont.nametofont("TkFixedFont").copy()
        font.configure(size=11, weight="bold")
        self._label_canvas.create_rectangle(
            0, 0, _LABEL_WIDTH, _ROW_TOP_MARGIN,
            fill="#E7E6E6", outline=_CELL_OUTLINE, width=1, tags=("all-header",),
        )
        self._label_canvas.tag_raise("all-header")
        self._label_canvas.create_text(
            _LABEL_WIDTH / 2, 20, text="All\nrows", justify="center",
            font=("TkDefaultFont", 8, "bold"), tags=("all-header",),
        )
        for alignment_column in range(self.view_model.alignment_length):
            center_x = (alignment_column * _CELL_WIDTH) + (_CELL_WIDTH / 2)
            # The digit row is an alignment-column ruler, so gaps remain
            # counted. It shares the Matrix Canvas and therefore x-scrolls
            # with every rendered cell without a second coordinate system.
            self._position_canvas.create_text(
                center_x,
                7,
                text=str((alignment_column + 1) % 10),
                font=("TkFixedFont", 8),
                fill="#555555",
                tags=("alignment-ruler-digit", f"alignment-ruler-column-{alignment_column}"),
            )
            if (alignment_column + 1) % 10 == 0:
                is_major = (alignment_column + 1) % 50 == 0
                self._position_canvas.create_text(
                    center_x,
                    18,
                    text=str(alignment_column + 1),
                    font=("TkDefaultFont", 8, "bold") if is_major else ("TkDefaultFont", 8),
                    tags=("alignment-ruler-label", f"alignment-ruler-column-{alignment_column}"),
                )
                self._position_canvas.create_line(
                    center_x,
                    25,
                    center_x,
                    35 if is_major else 31,
                    fill="#555555" if is_major else "#888888",
                )
            if self.view_model.column_at(alignment_column).is_variable:
                self._matrix_canvas.create_line(
                    center_x,
                    34,
                    center_x,
                    matrix_height,
                    fill="#D9D2E9",
                    width=2,
                    tags=("variable-column",),
                )
        self._position_canvas.create_line(0, 38, matrix_width, 38, fill="#777777")

        for row_index, row in enumerate(self.view_model.rows):
            top_y = _row_top_y(row_index)
            center_y = _row_center_y(row_index)
            self._label_canvas.create_rectangle(
                0, top_y, _LABEL_WIDTH, _row_top_y(row_index + 1),
                fill="#F2F2F2", outline=_CELL_OUTLINE, width=1,
                tags=("row-header", f"row-header-{row_index}"),
            )
            self._label_canvas.create_text(
                5, center_y, text=_sample_label_text(row_index, row.sample_id),
                anchor="w", font=("TkFixedFont", 10, "bold"),
                tags=("row-header", f"row-header-{row_index}"),
            )
            for alignment_column, base in enumerate(row.aligned_sequence):
                is_variable = self.view_model.column_at(alignment_column).is_variable
                outline = _VARIABLE_OUTLINE if is_variable else _CELL_OUTLINE
                cell_tags = (
                    "alignment-cell",
                    f"alignment-column-{alignment_column}",
                    "gap-cell" if base == "-" else "base-cell",
                )
                rectangle_id = self._matrix_canvas.create_rectangle(
                    alignment_column * _CELL_WIDTH,
                    top_y,
                    (alignment_column + 1) * _CELL_WIDTH,
                    _row_top_y(row_index + 1),
                    fill=_base_color(base),
                    outline=outline,
                    width=2 if is_variable else 1,
                    tags=cell_tags,
                )
                text_item = self._matrix_canvas.create_text(
                    (alignment_column * _CELL_WIDTH) + (_CELL_WIDTH / 2),
                    center_y,
                    text=base,
                    font=font,
                    fill="black",
                    tags=cell_tags,
                )
                # Keeping both concrete Canvas ids lets one edited cell be
                # repainted without rebuilding or modifying the immutable
                # alignment model.
                self._matrix_cell_items[(row_index, alignment_column)] = (
                    rectangle_id,
                    text_item,
                )
        self._selection_item = self._matrix_canvas.create_rectangle(
            0,
            0,
            0,
            0,
            fill="",
            outline=_SELECTION_OUTLINE,
            width=3,
            state="hidden",
        )
        self._column_selection_item = self._matrix_canvas.create_rectangle(
            0,
            0,
            0,
            0,
            fill="",
            outline="#7030A0",
            width=3,
            state="hidden",
        )
        self._range_selection_item = self._matrix_canvas.create_rectangle(
            0,
            0,
            0,
            0,
            fill=_RANGE_SELECTION_FILL,
            stipple="gray25",
            outline=_RANGE_SELECTION_OUTLINE,
            width=2,
            state="hidden",
        )
        self._editing_selection_item = self._matrix_canvas.create_rectangle(
            0,
            0,
            0,
            0,
            fill="",
            outline=_EDITING_OUTLINE,
            width=4,
            state="hidden",
        )
        self._matrix_canvas.configure(scrollregion=(0, 0, matrix_width, matrix_height))
        self._position_canvas.configure(scrollregion=(0, 0, matrix_width, _ROW_TOP_MARGIN))
        self._label_canvas.configure(scrollregion=(0, 0, _LABEL_WIDTH, matrix_height))
        self._sync_label_yview_to_matrix()

    def _set_selected_cells(self, cells: Sequence[tuple[int, int]]) -> None:
        """Show a thin purple continuous row/column selection when applicable."""

        self._selected_cells = tuple(cells)
        if cells:
            rows = [row for row, _column in cells]
            columns = [column for _row, column in cells]
            self.editor_state.select_rectangle(
                (min(rows), min(columns)),
                (max(rows), max(columns)),
            )
        if len(cells) <= 1:
            self._matrix_canvas.itemconfigure(self._range_selection_item, state="hidden")
            return
        rows = [row for row, _column in cells]
        columns = [column for _row, column in cells]
        self._matrix_canvas.coords(
            self._range_selection_item,
            min(columns) * _CELL_WIDTH,
            _row_top_y(min(rows)),
            (max(columns) + 1) * _CELL_WIDTH,
            _row_top_y(max(rows) + 1),
        )
        self._matrix_canvas.itemconfigure(self._range_selection_item, state="normal")
        self._matrix_canvas.tag_raise(self._range_selection_item)
        self._matrix_canvas.tag_raise(self._selection_item)
        self._matrix_canvas.tag_raise(self._column_selection_item)

    def _show_editing_selection(self) -> None:
        """Draw a thick edit-mode outline without changing displayed bases."""

        rows = [row for row, _column in self._editing_cells]
        columns = [column for _row, column in self._editing_cells]
        self._matrix_canvas.coords(
            self._editing_selection_item,
            min(columns) * _CELL_WIDTH,
            _row_top_y(min(rows)),
            (max(columns) + 1) * _CELL_WIDTH,
            _row_top_y(max(rows) + 1),
        )
        self._matrix_canvas.itemconfigure(self._editing_selection_item, state="normal")
        self._matrix_canvas.tag_raise(self._editing_selection_item)

    def _cancel_edit_mode(self, *, update_status: bool) -> None:
        """Leave edit mode without changing an overlay or a review session."""

        self._editing_cells = ()
        self._matrix_canvas.itemconfigure(self._editing_selection_item, state="hidden")
        if update_status:
            self._review_status_var.set("Review status: Editing cancelled")

    def _on_matrix_click(self, event) -> None:
        """Select a cell for evidence review; single clicks never edit."""

        canvas_x = self._matrix_canvas.canvasx(event.x)
        canvas_y = self._matrix_canvas.canvasy(event.y)
        if 0 <= canvas_y < _ROW_TOP_MARGIN:
            alignment_column = int(canvas_x // _CELL_WIDTH)
            if 0 <= alignment_column < self.view_model.alignment_length:
                self.select_alignment_column(alignment_column)
                self._set_selected_cells(
                    tuple(
                        (row_index, alignment_column)
                        for row_index in range(len(self.view_model.rows))
                    )
                )
                self.editor_state.select_column(alignment_column)
                self._selected_site_text.set(
                    f"Alignment column: {alignment_column} (0-based)\n"
                    "Select a sample cell to inspect evidence."
                )
            return

        cell = _matrix_coordinate_to_cell(
            canvas_x,
            canvas_y,
            row_count=len(self.view_model.rows),
            alignment_length=self.view_model.alignment_length,
        )
        if cell is not None:
            self._cancel_edit_mode(update_status=False)
            if event.state & 0x0001:
                anchor = self._selection_anchor or cell
                selected_cells = _linear_cell_selection(anchor, cell)
                if selected_cells is None:
                    self._review_status_var.set(
                        "Review status: Shift selection must remain in one row or one column"
                    )
                    return
                self._selection_anchor = anchor
            elif len(self._selected_cells) > 1 and cell in self._selected_cells:
                selected_cells = self._selected_cells
            else:
                selected_cells = (cell,)
                self._selection_anchor = cell
            self.select_cell(*cell)
            self._set_selected_cells(selected_cells)
            self._matrix_canvas.focus_set()

    def _on_row_header_click(self, event) -> None:
        """Use cell-shaped row/corner headers as future editor selection anchors."""

        canvas_y = self._label_canvas.canvasy(event.y)
        if 0 <= canvas_y < _ROW_TOP_MARGIN:
            cells = tuple(
                (row_index, column)
                for row_index in range(len(self.view_model.rows))
                for column in range(self.view_model.alignment_length)
            )
            self._set_selected_cells(cells)
            self.editor_state.select_all()
            self._selected_site_text.set("All rows and columns selected")
            return
        row_index = int((canvas_y - _ROW_TOP_MARGIN) // _ROW_HEIGHT)
        if not 0 <= row_index < len(self.view_model.rows):
            return
        cells = tuple(
            (row_index, column)
            for column in range(self.view_model.alignment_length)
        )
        self._set_selected_cells(cells)
        self.editor_state.select_row(row_index)
        first_non_gap = next(
            (column for column, base in enumerate(self.view_model.row_at(row_index).aligned_sequence) if base != "-"),
            0,
        )
        self.select_cell(row_index, first_non_gap)
        self._matrix_canvas.focus_set()

    def _on_matrix_double_click(self, event) -> str:
        """Enter edit mode only after explicit double-click intent."""

        cell = _matrix_coordinate_to_cell(
            self._matrix_canvas.canvasx(event.x),
            self._matrix_canvas.canvasy(event.y),
            row_count=len(self.view_model.rows),
            alignment_length=self.view_model.alignment_length,
        )
        if cell is None:
            return "break"
        row_index, alignment_column = cell
        selected_cells = (
            self._selected_cells
            if cell in self._selected_cells and self._selected_cells
            else (cell,)
        )
        self.select_cell(row_index, alignment_column)
        self._set_selected_cells(selected_cells)
        if any(
            self.view_model.row_at(row).consensus_position_at(column) is None
            or self.view_model.row_at(row).aligned_sequence[column] == "-"
            for row, column in selected_cells
        ):
            self._review_status_var.set(
                "Review status: A selected gap cell has no consensus coordinate for editing"
            )
            return "break"
        self._editing_cells = selected_cells
        self._show_editing_selection()
        self._matrix_canvas.focus_set()
        self._review_status_var.set(_editing_status_text(self.view_model, selected_cells))
        return "break"

    def _on_matrix_key(self, event):
        """Accept an edit character only while a cell is explicitly editable."""

        if getattr(event, "keysym", "") == "Escape":
            self._cancel_edit_mode(update_status=True)
            return "break"
        proposed_base = getattr(event, "char", "").upper()
        if not proposed_base:
            return None
        if not self._editing_cells:
            self._review_status_var.set(
                "Review status: Double-click a selected cell before editing"
            )
            return "break"
        if proposed_base not in _EDITABLE_ALIGNMENT_SYMBOLS:
            self._review_status_var.set(
                "Review status: Use A/T/G/C/N, IUPAC, or - for a matrix edit"
            )
            return "break"
        self._edit_selected_cells(proposed_base)
        return "break"

    def _edit_selected_cells(self, proposed_base: str) -> None:
        """Overlay the explicit edit selection and replace its latest decisions.

        The operation deliberately does not alter ``AlignedConsensusSet`` or
        its coordinate map.  Re-editing one position is deferred until a
        later version defines revision history or undo/redo semantics.
        """

        if not self._editing_cells:
            self._review_status_var.set("Review status: Double-click a non-gap selection before editing")
            return
        decisions = []
        try:
            for row_index, alignment_column in self._editing_cells:
                row = self.view_model.row_at(row_index)
                consensus_position = row.consensus_position_at(alignment_column)
                if consensus_position is None:
                    raise ValueError("selected gap cell has no consensus coordinate")
                decisions.append(
                    (
                        (row_index, alignment_column),
                        create_matrix_edit_decision(
                            sample_id=row.sample_id,
                            consensus_position=consensus_position,
                            original_base=row.aligned_sequence[alignment_column],
                            proposed_base=proposed_base,
                            evidence_reference=(
                                self._selected_review_evidence
                                if (row_index, alignment_column)
                                == (self.selected_row_index, self.selected_alignment_column)
                                else None
                            ),
                        ),
                    )
                )
        except ValueError as error:
            self._review_status_var.set(f"Review status: {error}")
            return
        for cell_key, decision in decisions:
            self._matrix_cell_edits[cell_key] = proposed_base
            self._repaint_matrix_cell(*cell_key, proposed_base)
            self._record_review_decision(decision, replace_existing=True)
        self._refresh_edited_cells_panel()
        selected_row = self.view_model.row_at(self.selected_row_index)
        selected_position = selected_row.consensus_position_at(self.selected_alignment_column)
        self._selected_site_text.set(
            _selected_site_summary(
                selected_row.sample_id,
                self.selected_alignment_column,
                selected_position,
                proposed_base,
            )
            + f"\nMatrix edit: applied to {len(decisions)} selected cell(s)"
        )
        self._review_status_var.set(
            f"Review status: Edited {len(decisions)} cell(s)\n"
            f"Input: {proposed_base}"
        )
        self._cancel_edit_mode(update_status=False)

    def _display_base(self, row_index: int, alignment_column: int) -> str:
        """Return the edit overlay when present, otherwise the MAFFT base."""

        return self._matrix_cell_edits.get(
            (row_index, alignment_column),
            self.view_model.row_at(row_index).aligned_sequence[alignment_column],
        )

    def _refresh_edited_cells_panel(self) -> None:
        """Render the overlay list; clicks select, and Remove restores one cell."""

        if not hasattr(self, "_edited_cells_text"):
            return
        entries = build_edited_cells(self.view_model, self._matrix_cell_edits)
        text = self._edited_cells_text
        text.configure(state="normal")
        text.delete("1.0", "end")
        if not entries:
            text.insert("end", "No edited cells.\n")
        for entry in entries:
            start = text.index("end-1c")
            position = "None" if entry.consensus_position is None else str(entry.consensus_position)
            text.insert(
                "end",
                f"{entry.sample_id}\ncol {entry.alignment_column}  pos {position}  "
                f"{entry.original_base} → {entry.edited_base}  [Remove]\n",
            )
            end = text.index("end-1c")
            tag = f"edited-cell-{entry.row_index}-{entry.alignment_column}"
            text.tag_add(tag, start, end)
            text.tag_configure(tag, underline=True)
            text.tag_bind(tag, "<Button-1>", lambda _event, value=entry: self._select_edited_cell(value))
            remove_start = f"{end}-9c"
            remove_tag = f"remove-edited-cell-{entry.row_index}-{entry.alignment_column}"
            text.tag_add(remove_tag, remove_start, end)
            text.tag_configure(remove_tag, foreground="#A61C00")
            text.tag_bind(remove_tag, "<Button-1>", lambda _event, value=entry: self._remove_edited_cell(value))
        text.configure(state="disabled")

    def _select_edited_cell(self, entry: EditedCell) -> str:
        self.select_cell(entry.row_index, entry.alignment_column)
        self._selection_anchor = (entry.row_index, entry.alignment_column)
        self._set_selected_cells(((entry.row_index, entry.alignment_column),))
        return "break"

    def _remove_edited_cell(self, entry: EditedCell) -> str:
        """Drop one overlay and its latest decision; never change MAFFT input."""

        key = (entry.row_index, entry.alignment_column)
        self._matrix_cell_edits.pop(key, None)
        self._restore_matrix_cell(*key)
        session = self.review_sessions.get(entry.sample_id)
        if session is not None and entry.consensus_position is not None:
            session.decisions[:] = [
                decision for decision in session.decisions
                if decision.consensus_position != entry.consensus_position
            ]
        self._review_summary_var.set(_format_review_summary(self._all_review_decisions()))
        self._refresh_edited_cells_panel()
        return "break"

    def _focus_edited_cells(self) -> None:
        self._human_review_section.content.focus_set()
        self._control_canvas.yview_moveto(0.45)

    def _repaint_matrix_cell(
        self,
        row_index: int,
        alignment_column: int,
        base: str,
    ) -> None:
        """Paint the existing Canvas items for one review-only edit overlay."""

        rectangle_id, text_id = self._matrix_cell_items[(row_index, alignment_column)]
        is_variable = self.view_model.column_at(alignment_column).is_variable
        self._matrix_canvas.itemconfigure(
            rectangle_id,
            fill=_EDITED_CELL_BACKGROUND,
            outline=_VARIABLE_OUTLINE if is_variable else _CELL_OUTLINE,
            width=2 if is_variable else 1,
        )
        self._matrix_canvas.itemconfigure(text_id, text=base)
        self._matrix_canvas.tag_raise(self._selection_item)
        self._matrix_canvas.tag_raise(self._column_selection_item)

    def _restore_matrix_cell(self, row_index: int, alignment_column: int) -> None:
        """Restore one Canvas cell from immutable aligned input after removal."""

        rectangle_id, text_id = self._matrix_cell_items[(row_index, alignment_column)]
        base = self.view_model.row_at(row_index).aligned_sequence[alignment_column]
        is_variable = self.view_model.column_at(alignment_column).is_variable
        self._matrix_canvas.itemconfigure(
            rectangle_id,
            fill=_base_color(base),
            outline=_VARIABLE_OUTLINE if is_variable else _CELL_OUTLINE,
            width=2 if is_variable else 1,
        )
        self._matrix_canvas.itemconfigure(text_id, text=base)

    def _record_review_decision(
        self,
        decision: HumanReviewDecision,
        *,
        replace_existing: bool = False,
    ) -> None:
        """Store the latest decision for a position and refresh the summary."""

        session = self.review_sessions.get(decision.sample_id)
        if session is None:
            row = next(
                row for row in self.view_model.rows if row.sample_id == decision.sample_id
            )
            session = ConsensusReviewSession(
                sample_id=decision.sample_id,
                candidate_reference=row,
            )
            self.review_sessions[decision.sample_id] = session
        if replace_existing:
            for index, previous in enumerate(session.decisions):
                if previous.consensus_position == decision.consensus_position:
                    session.decisions[index] = decision
                    break
            else:
                session.add_decision(decision)
        else:
            session.add_decision(decision)
        self._review_summary_var.set(
            _format_review_summary(self._all_review_decisions())
        )

    def _all_review_decisions(self) -> tuple[HumanReviewDecision, ...]:
        """Return session decisions in current matrix row order."""

        decisions = []
        for row in self.view_model.rows:
            session = self.review_sessions.get(row.sample_id)
            if session is not None:
                decisions.extend(session.get_decisions())
        return tuple(decisions)

    def _open_selected_consensus(self) -> None:
        if self.selected_row_index is None or self.selected_alignment_column is None:
            return
        row = self.view_model.row_at(self.selected_row_index)
        consensus_position = row.consensus_position_at(self.selected_alignment_column)
        if self.on_consensus_selected is not None and consensus_position is not None:
            self.on_consensus_selected(row.sample_id, consensus_position)

    def _scroll_y(self, *args) -> None:
        """Scroll the matrix, then mirror its actual fraction to the labels.

        The matrix canvas is the sole vertical-scroll authority.  In
        particular, ``scroll`` commands are not replayed on the label canvas:
        Canvas-specific unit sizes could otherwise accumulate a row offset.
        """

        self._matrix_canvas.yview(*args)
        self._sync_label_yview_to_matrix()

    def _set_y_scrollbar(self, first, last) -> None:
        """Mirror every matrix-originated yview update to the label canvas."""

        self._vertical_scrollbar.set(first, last)
        self._label_canvas.yview_moveto(float(first))

    def _set_x_scrollbar(self, scrollbar, first, last) -> None:
        scrollbar.set(first, last)
        self._position_canvas.xview_moveto(float(first))

    def _sync_label_yview_to_matrix(self) -> None:
        """Apply the matrix's current exact vertical fraction to the labels."""

        first, last = self._matrix_canvas.yview()
        self._vertical_scrollbar.set(first, last)
        self._label_canvas.yview_moveto(first)

    def _on_vertical_viewport_configure(self, _event) -> None:
        """Keep the passive label viewport aligned after Tk geometry changes."""

        self.after_idle(self._sync_label_yview_to_matrix)

    def _on_matrix_wheel(self, event):
        steps = _wheel_delta_to_scroll_steps(getattr(event, "delta", 0))
        if not steps:
            return "break"
        if event.state & 0x0001:
            self._matrix_canvas.xview_scroll(steps, "units")
        else:
            self._scroll_y("scroll", steps, "units")
        return "break"

    def _on_label_wheel(self, event):
        """Use the same single-source vertical path when the pointer is on labels."""

        steps = _wheel_delta_to_scroll_steps(getattr(event, "delta", 0))
        if steps:
            self._scroll_y("scroll", steps, "units")
        return "break"

    def _on_horizontal_scroll_left(self, _event):
        self._matrix_canvas.xview_scroll(-1, "units")
        return "break"

    def _on_horizontal_scroll_right(self, _event):
        self._matrix_canvas.xview_scroll(1, "units")
        return "break"


def create_human_review_decision(
    *,
    sample_id: str,
    consensus_position: int,
    original_base: str,
    decision_type: DecisionType,
    reviewed_base: str,
    reason: str,
    evidence_reference: Optional[ReviewEvidence],
    reviewer: str = "prototype-user",
    timestamp: Optional[datetime] = None,
) -> HumanReviewDecision:
    """Create one GUI-originated decision without applying it to a sequence."""

    if not isinstance(decision_type, DecisionType):
        raise ValueError("decision_type must be a DecisionType")
    normalized_original = original_base.upper()
    normalized_reviewed = reviewed_base.strip().upper() or None
    if decision_type is DecisionType.ACCEPT:
        normalized_reviewed = normalized_original
    elif decision_type is DecisionType.REJECT:
        normalized_reviewed = None
    return HumanReviewDecision(
        sample_id=sample_id,
        consensus_position=consensus_position,
        original_base=normalized_original,
        reviewed_base=normalized_reviewed,
        decision_type=decision_type,
        reason=reason,
        evidence_reference=evidence_reference,
        reviewer=reviewer,
        timestamp=datetime.now(timezone.utc) if timestamp is None else timestamp,
    )


def create_matrix_edit_decision(
    *,
    sample_id: str,
    consensus_position: int,
    original_base: str,
    proposed_base: str,
    evidence_reference: Optional[ReviewEvidence],
    reason: str = "",
) -> HumanReviewDecision:
    """Create an audit record for one direct matrix-cell edit.

    A matching input is represented as ``ACCEPT``. Standard bases and ``N``
    become ``CHANGE`` when different; IUPAC codes become ``AMBIGUOUS``. A
    proposed gap is recorded as a review-only ``CHANGE`` and is intentionally
    not applied to the immutable alignment or consensus sequence.
    """

    normalized_proposed = proposed_base.strip().upper()
    normalized_original = original_base.strip().upper()
    if normalized_proposed not in _EDITABLE_ALIGNMENT_SYMBOLS:
        raise ValueError("proposed_base must be A/T/G/C/N, IUPAC, or -")
    if normalized_original not in _ALLOWED_ALIGNMENT_SYMBOLS - {"-"}:
        raise ValueError("original_base must be a non-gap DNA/IUPAC base")
    if normalized_proposed == normalized_original:
        decision_type = DecisionType.ACCEPT
    elif normalized_proposed in frozenset("RYSWKMBDHV"):
        decision_type = DecisionType.AMBIGUOUS
    else:
        decision_type = DecisionType.CHANGE
    return create_human_review_decision(
        sample_id=sample_id,
        consensus_position=consensus_position,
        original_base=normalized_original,
        decision_type=decision_type,
        reviewed_base=normalized_proposed,
        reason=reason,
        evidence_reference=evidence_reference,
        reviewer="matrix-cell-editor",
    )


def _consensus_positions(aligned_sequence: str) -> tuple[Optional[int], ...]:
    """Map each non-gap alignment column to its original 0-based position."""

    positions = []
    consensus_position = 0
    for base in aligned_sequence:
        if base == "-":
            positions.append(None)
        else:
            positions.append(consensus_position)
            consensus_position += 1
    return tuple(positions)


def _build_alignment_column(
    alignment_column: int,
    rows: Sequence[MultipleAlignmentRow],
) -> MultipleAlignmentColumn:
    bases = tuple(row.aligned_sequence[alignment_column] for row in rows)
    counts = tuple(sorted(Counter(bases).items()))
    return MultipleAlignmentColumn(
        alignment_column=alignment_column,
        bases=bases,
        base_counts=counts,
        is_variable=len(set(bases)) > 1,
    )


def _build_view_columns(
    rows: Sequence[MultipleAlignmentRow],
) -> tuple[MultipleAlignmentColumn, ...]:
    """Build display-only summaries from an already aligned set of rows."""

    return tuple(
        _build_alignment_column(alignment_column, rows)
        for alignment_column in range(len(rows[0].aligned_sequence))
    )


def build_variable_sites(
    view_model: MultipleAlignmentViewModel,
) -> tuple[VariableSite, ...]:
    """Return display-only entries for columns with differing aligned bases."""

    if not isinstance(view_model, MultipleAlignmentViewModel):
        raise ValueError("view_model must be a MultipleAlignmentViewModel")
    sites = []
    for column in view_model.columns:
        if not column.is_variable:
            continue
        samples = tuple(
            VariableSiteSample(
                sample_id=row.sample_id,
                base=row.aligned_sequence[column.alignment_column],
                consensus_position=row.consensus_position_at(column.alignment_column),
            )
            for row in view_model.rows
        )
        sites.append(
            VariableSite(
                alignment_column=column.alignment_column,
                samples=samples,
            )
        )
    return tuple(sites)


def build_edited_cells(
    view_model: MultipleAlignmentViewModel,
    overlay: Mapping[tuple[int, int], str],
) -> tuple[EditedCell, ...]:
    """Describe only overlay cells; original aligned rows remain untouched."""

    entries = []
    for (row_index, alignment_column), edited_base in sorted(overlay.items()):
        row = view_model.row_at(row_index)
        entries.append(
            EditedCell(
                sample_id=row.sample_id,
                row_index=row_index,
                alignment_column=alignment_column,
                consensus_position=row.consensus_position_at(alignment_column),
                original_base=row.aligned_sequence[alignment_column],
                edited_base=edited_base,
            )
        )
    return tuple(entries)


def _original_sequence(row: MultipleAlignmentRow) -> str:
    return "".join(base for base in row.aligned_sequence if base != "-")


def current_alignment_records(
    view_model: MultipleAlignmentViewModel,
    overlay: Mapping[tuple[int, int], str],
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            row.sample_id,
            "".join(overlay.get((row_index, column), base) for column, base in enumerate(row.aligned_sequence)),
        )
        for row_index, row in enumerate(view_model.rows)
    )


def reviewed_consensus_records(
    view_model: MultipleAlignmentViewModel,
    overlay: Mapping[tuple[int, int], str],
) -> tuple[tuple[str, str], ...]:
    """Build export-only reviewed records without changing the core model.

    A gap edit has no current ``ReviewedConsensus`` interpretation, so it is
    retained only in Current Alignment export until that workflow is designed.
    """

    records = []
    for row_index, row in enumerate(view_model.rows):
        bases = []
        for column, base in enumerate(row.aligned_sequence):
            if base == "-":
                continue
            edited_base = overlay.get((row_index, column), base)
            if edited_base == "-":
                raise ValueError(
                    "Reviewed Consensus FASTA cannot represent gap edits yet; export Current Alignment FASTA instead."
                )
            bases.append(edited_base)
        records.append((row.sample_id, "".join(bases)))
    return tuple(records)


def write_fasta_records(filepath: Path, records: Sequence[tuple[str, str]]) -> None:
    with filepath.open("w", encoding="utf-8", newline="\n") as output:
        for sample_id, sequence in records:
            output.write(f">{sample_id}\n")
            for start in range(0, len(sequence), 60):
                output.write(sequence[start:start + 60] + "\n")


def write_review_report_tsv(
    filepath: Path,
    entries: Sequence[EditedCell],
    sessions: Mapping[str, ConsensusReviewSession],
) -> None:
    with filepath.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("sample_id", "alignment_column", "consensus_position", "original_base", "edited_base", "decision_type", "reason"))
        for entry in entries:
            session = sessions.get(entry.sample_id)
            decision = next((value for value in session.get_decisions() if value.consensus_position == entry.consensus_position), None) if session is not None else None
            writer.writerow((entry.sample_id, entry.alignment_column, entry.consensus_position, entry.original_base, entry.edited_base, "" if decision is None else decision.decision_type.value, "" if decision is None else decision.reason))


def _format_variable_sites(variable_sites: Sequence[VariableSite]) -> str:
    """Format all variable sites for the intentionally non-interactive panel."""

    if not variable_sites:
        return "No variable alignment columns.\n"
    lines = []
    for site in variable_sites:
        lines.extend(_format_variable_site(site).rstrip("\n").splitlines())
    return "\n".join(lines) + "\n"


def _format_variable_site(site: VariableSite) -> str:
    """Format one clickable variable-site block."""

    lines = [f"Column {site.alignment_column} (0-based)"]
    for sample in site.samples:
        position = (
            "None"
            if sample.consensus_position is None
            else f"{sample.consensus_position} (0-based)"
        )
        lines.append(f"  {sample.sample_id}: {sample.base}  consensus position: {position}")
    return "\n".join(lines) + "\n"


def _format_review_summary(decisions: Sequence[HumanReviewDecision]) -> str:
    """Summarize only the decisions held by this in-memory viewer prototype."""

    if not decisions:
        return "No reviewed decisions."
    counts = Counter(decision.decision_type for decision in decisions)
    lines = ["Reviewed decisions:"]
    for decision_type in DecisionType:
        count = counts.get(decision_type, 0)
        if count:
            lines.append(f"{decision_type.value}: {count}")
    return "\n".join(lines)


def _horizontal_fraction_for_column(
    alignment_column: int,
    *,
    alignment_length: int,
    viewport_width: int,
    current_xview: tuple[float, float],
) -> Optional[float]:
    """Return a centering fraction only when a column is outside the viewport."""

    if not 0 <= alignment_column < alignment_length:
        raise ValueError("alignment_column is outside the multiple alignment")
    content_width = alignment_length * _CELL_WIDTH
    if viewport_width <= 0 or viewport_width >= content_width:
        return None
    left, right = current_xview
    column_left = (alignment_column * _CELL_WIDTH) / content_width
    column_right = ((alignment_column + 1) * _CELL_WIDTH) / content_width
    if column_left >= left and column_right <= right:
        return None
    target_left = (alignment_column * _CELL_WIDTH) - ((viewport_width - _CELL_WIDTH) / 2)
    maximum_left = content_width - viewport_width
    return max(0.0, min(target_left, maximum_left)) / content_width


def _base_color(base: str) -> str:
    """Return the MEGA/Mesquite-style background colour for one symbol."""

    if base == "-":
        return _GAP_COLOR
    return _BASE_COLORS.get(base, _AMBIGUOUS_COLOR)


def _matrix_coordinate_to_cell(
    canvas_x: float,
    canvas_y: float,
    *,
    row_count: int,
    alignment_length: int,
) -> Optional[tuple[int, int]]:
    """Map Canvas coordinates to ``(row_index, alignment_column)``."""

    if canvas_y < _ROW_TOP_MARGIN or canvas_x < 0:
        return None
    row_index = int((canvas_y - _ROW_TOP_MARGIN) // _ROW_HEIGHT)
    alignment_column = int(canvas_x // _CELL_WIDTH)
    if not 0 <= row_index < row_count or not 0 <= alignment_column < alignment_length:
        return None
    return row_index, alignment_column


def _linear_cell_selection(
    anchor: tuple[int, int],
    endpoint: tuple[int, int],
) -> Optional[tuple[tuple[int, int], ...]]:
    """Return an inclusive horizontal or vertical range, never a rectangle."""

    anchor_row, anchor_column = anchor
    end_row, end_column = endpoint
    if anchor_row == end_row:
        step = 1 if end_column >= anchor_column else -1
        return tuple(
            (anchor_row, column)
            for column in range(anchor_column, end_column + step, step)
        )
    if anchor_column == end_column:
        step = 1 if end_row >= anchor_row else -1
        return tuple(
            (row, anchor_column)
            for row in range(anchor_row, end_row + step, step)
        )
    return None


def _editing_status_text(
    view_model: MultipleAlignmentViewModel,
    cells: Sequence[tuple[int, int]],
) -> str:
    """Describe the current edit target using alignment, not raw-read, coordinates."""

    sample_ids = tuple(dict.fromkeys(view_model.row_at(row).sample_id for row, _ in cells))
    columns = [column for _row, column in cells]
    sample_label = sample_ids[0] if len(sample_ids) == 1 else ", ".join(sample_ids)
    column_label = (
        str(columns[0])
        if len(columns) == 1
        else f"{min(columns)}–{max(columns)} ({len(cells)} cells)"
    )
    return (
        "Editing:\n"
        f"Sample: {sample_label}\n"
        f"Alignment column: {column_label}\n"
        "Press A/T/G/C/N/- or IUPAC\n"
        "ESC: cancel"
    )


def _row_top_y(row_index: int) -> int:
    """Return the shared top pixel for a label and its matrix row."""

    return _ROW_TOP_MARGIN + (row_index * _ROW_HEIGHT)


def _row_center_y(row_index: int) -> float:
    """Return the shared text baseline centre for a label and base symbols."""

    return _row_top_y(row_index) + (_ROW_HEIGHT / 2)


def _matrix_content_height(row_count: int) -> int:
    """Return the one shared scrollregion height for both vertical canvases."""

    return _ROW_TOP_MARGIN + (row_count * _ROW_HEIGHT)


def _sample_label_text(row_index: int, sample_id: str) -> str:
    """Return the visible, one-based row number and sample identifier."""

    return f"{row_index + 1}  {sample_id}"


def _selected_site_summary(
    sample_id: str,
    alignment_column: int,
    consensus_position: Optional[int],
    base: str,
) -> str:
    """Format read-only selected-site information with explicit index bases."""

    displayed_consensus_position = (
        "None (gap)"
        if consensus_position is None
        else f"{consensus_position + 1} (1-based)"
    )
    return (
        f"Sample: {sample_id}\n"
        f"Alignment column: {alignment_column + 1} (1-based; internal {alignment_column})\n"
        f"Consensus position: {displayed_consensus_position}\n"
        f"Base: {base}"
    )


def _evidence_text_for_selection(
    evidence_map: Optional[ConsensusEvidenceMap],
    sample_id: str,
    consensus_position: Optional[int],
) -> str:
    """Format existing evidence for a selected matrix cell without navigation."""

    if consensus_position is None:
        return "Gap position has no chromatogram evidence.\n"
    if evidence_map is None:
        return "No ConsensusEvidenceMap is available for this alignment.\n"
    evidence = _review_evidence_for_selection(
        evidence_map,
        sample_id,
        consensus_position,
    )
    if evidence is None:
        return "No ReviewEvidence is available for this sample consensus position.\n"
    return _format_review_evidence(evidence)


def _review_evidence_for_selection(
    evidence_map: Optional[ConsensusEvidenceMap],
    sample_id: str,
    consensus_position: Optional[int],
) -> Optional[ReviewEvidence]:
    """Return only existing evidence; a multiple-alignment gap remains absent."""

    if consensus_position is None or evidence_map is None:
        return None
    return evidence_map.lookup(sample_id, consensus_position)


def dispatch_multiple_evidence_trace_jump(
    callback: Optional[TraceJumpCallback],
    target: Optional[TraceJumpTarget],
) -> bool:
    """Invoke the caller callback for an existing target without GUI coupling."""

    if callback is None or target is None:
        return False
    callback(target.read_identifier, target.raw_trace_position)
    return True


def _format_review_evidence(evidence: ReviewEvidence) -> str:
    """Display copied evidence fields; trace jump controls remain out of scope."""

    return (
        "Consensus\n"
        f"Base: {evidence.consensus_base}\n"
        f"Decision reason: {evidence.decision_reason}\n"
        f"F/R alignment column: {evidence.alignment_column} (0-based)\n\n"
        "Forward\n"
        f"Base: {evidence.forward_base}\n"
        f"Quality: {evidence.forward_quality}\n"
        f"Raw index: {evidence.forward_raw_index}\n"
        f"Trimmed index: {evidence.forward_trimmed_index}\n"
        f"Raw trace position: {evidence.forward_raw_trace_position}\n"
        f"Trimmed trace position: {evidence.forward_trimmed_trace_position}\n\n"
        "Reverse\n"
        f"Base: {evidence.reverse_base}\n"
        f"Quality: {evidence.reverse_quality}\n"
        f"Raw index: {evidence.reverse_raw_index}\n"
        f"Trimmed index: {evidence.reverse_trimmed_index}\n"
        f"Raw trace position: {evidence.reverse_raw_trace_position}\n"
        f"Trimmed trace position: {evidence.reverse_trimmed_trace_position}\n"
    )


def _wheel_delta_to_scroll_steps(delta: int) -> int:
    if not delta:
        return 0
    if abs(delta) >= 120:
        return -int(delta / 120)
    return -int(delta)
