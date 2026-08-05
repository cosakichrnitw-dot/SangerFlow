import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from core.mafft import run_mafft
from core.selection import (
    save_selection,
    load_selection,
)


class QualityPanel(tk.Toplevel):

    def __init__(
        self,
        parent,
        reads,
    ):

        super().__init__(parent)

        self.title(
            "Sequence Quality"
        )

        self.geometry(
            "900x600"
        )

        self.minsize(
            760,
            420,
        )

        self.reads = reads

        # Checkbox management
        self.check_vars = []

        self.apply_callback = None

        # =====================
        # Header
        # =====================

        header = tk.Label(
            self,
            text=(
                "Select     Sample                    "
                "Length     HQ%      Q20      Q30"
            ),
            font=(
                "Courier",
                10,
                "bold",
            ),
            anchor="w",
        )

        header.pack(
            fill="x",
            padx=10,
            pady=(
                8,
                4,
            ),
        )

        # =====================
        # Scrollable sample area
        # =====================

        self.scroll_container = tk.Frame(
            self
        )

        self.scroll_container.pack(
            fill="both",
            expand=True,
            padx=8,
            pady=0,
        )

        self.list_canvas = tk.Canvas(
            self.scroll_container,
            highlightthickness=0,
            borderwidth=0,
        )

        self.vertical_scrollbar = tk.Scrollbar(
            self.scroll_container,
            orient="vertical",
            command=self.list_canvas.yview,
        )

        self.list_canvas.configure(
            yscrollcommand=self.vertical_scrollbar.set
        )

        self.vertical_scrollbar.pack(
            side="right",
            fill="y",
        )

        self.list_canvas.pack(
            side="left",
            fill="both",
            expand=True,
        )

        # Frame inside the Canvas
        self.list_frame = tk.Frame(
            self.list_canvas
        )

        self.list_window = self.list_canvas.create_window(
            (
                0,
                0,
            ),
            window=self.list_frame,
            anchor="nw",
        )

        # Update scroll region when rows are added
        self.list_frame.bind(
            "<Configure>",
            self._update_scroll_region,
        )

        # Keep inner frame width synchronized with Canvas
        self.list_canvas.bind(
            "<Configure>",
            self._resize_list_frame,
        )

        # Mouse wheel / Mac trackpad
        self.list_canvas.bind(
            "<Enter>",
            self._bind_mousewheel,
        )

        self.list_canvas.bind(
            "<Leave>",
            self._unbind_mousewheel,
        )

        # =====================
        # Create sample rows
        # =====================

        self.create_rows()

        # =====================
        # Fixed bottom controls
        # =====================

        bottom = tk.Frame(
            self
        )

        bottom.pack(
            fill="x",
            padx=8,
            pady=(
                6,
                10,
            ),
        )

        # ---------------------
        # HQ threshold row
        # ---------------------

        threshold_row = tk.Frame(
            bottom
        )

        threshold_row.pack(
            fill="x",
            pady=(
                0,
                6,
            ),
        )

        tk.Label(
            threshold_row,
            text="HQ threshold (%)",
        ).pack(
            side="left",
            padx=(
                0,
                5,
            ),
        )

        self.hq_entry = tk.Entry(
            threshold_row,
            width=8,
        )

        self.hq_entry.insert(
            0,
            "70",
        )

        self.hq_entry.pack(
            side="left"
        )

        self.select_button = tk.Button(
            threshold_row,
            text="HQ > threshold Select",
            command=self.select_by_hq,
        )

        self.select_button.pack(
            side="left",
            padx=10,
        )

        # ---------------------
        # First action row
        # ---------------------

        action_row_1 = tk.Frame(
            bottom
        )

        action_row_1.pack(
            fill="x",
            pady=(
                0,
                5,
            ),
        )

        self.apply_button = tk.Button(
            action_row_1,
            text="Apply to Viewer",
            command=self.apply_to_viewer,
        )

        self.apply_button.pack(
            side="left",
            padx=(
                0,
                6,
            ),
        )

        self.export_button = tk.Button(
            action_row_1,
            text="Export Selected FASTA",
            command=self.export_fasta,
        )

        self.export_button.pack(
            side="left",
            padx=6,
        )

        self.align_button = tk.Button(
            action_row_1,
            text="Align Selected",
            command=self.align_selected,
        )

        self.align_button.pack(
            side="left",
            padx=6,
        )

        # ---------------------
        # Second action row
        # ---------------------

        action_row_2 = tk.Frame(
            bottom
        )

        action_row_2.pack(
            fill="x"
        )

        self.save_button = tk.Button(
            action_row_2,
            text="Save Selection",
            command=self.save_selection_file,
        )

        self.save_button.pack(
            side="left",
            padx=(
                0,
                6,
            ),
        )

        self.load_button = tk.Button(
            action_row_2,
            text="Load Selection",
            command=self.load_selection_file,
        )

        self.load_button.pack(
            side="left",
            padx=6,
        )

    # ==================================================
    # Scroll handling
    # ==================================================

    def _update_scroll_region(
        self,
        _event=None,
    ):

        bbox = self.list_canvas.bbox(
            "all"
        )

        if bbox:

            self.list_canvas.configure(
                scrollregion=bbox
            )

    def _resize_list_frame(
        self,
        event,
    ):

        self.list_canvas.itemconfigure(
            self.list_window,
            width=event.width,
        )

    def _bind_mousewheel(
        self,
        _event=None,
    ):

        self.list_canvas.bind_all(
            "<MouseWheel>",
            self._on_mousewheel,
        )

    def _unbind_mousewheel(
        self,
        _event=None,
    ):

        self.list_canvas.unbind_all(
            "<MouseWheel>"
        )

    def _on_mousewheel(
        self,
        event,
    ):

        if event.delta == 0:

            return

        # macOS trackpad often reports small delta values
        if abs(event.delta) < 120:

            units = (
                -1
                if event.delta > 0
                else 1
            )

        else:

            units = int(
                -event.delta
                /
                120
            )

        self.list_canvas.yview_scroll(
            units,
            "units",
        )

    # ==================================================
    # Register apply callback
    # ==================================================

    def set_apply_callback(
        self,
        callback,
    ):

        self.apply_callback = callback

    # ==================================================
    # Create rows
    # ==================================================

    def create_rows(
        self
    ):

        for read in self.reads:

            var = tk.BooleanVar(
                value=getattr(
                    read,
                    "selected",
                    True,
                )
            )

            self.check_vars.append(
                (
                    read,
                    var,
                )
            )

            row = tk.Frame(
                self.list_frame
            )

            row.pack(
                fill="x",
                padx=10,
                pady=2,
            )

            tk.Checkbutton(
                row,
                variable=var,
            ).pack(
                side="left"
            )

            text = (
                f"{read.filename:<28}"
                f"{len(read.sequence):<10}"
                f"{read.hq_percent:>6.1f}%   "
                f"{read.q20_rate:>6.1f}%   "
                f"{read.q30_rate:>6.1f}%"
            )

            tk.Label(
                row,
                text=text,
                font=(
                    "Courier",
                    10,
                ),
                anchor="w",
            ).pack(
                side="left"
            )

    # ==================================================
    # HQ selection
    # ==================================================

    def select_by_hq(
        self
    ):

        try:

            threshold = float(
                self.hq_entry.get()
            )

        except ValueError:

            print(
                "HQ threshold must be a number."
            )

            return

        for read, var in self.check_vars:

            if read.hq_percent >= threshold:

                var.set(
                    True
                )

            else:

                var.set(
                    False
                )

    # ==================================================
    # Get selected reads
    # ==================================================

    def get_selected_reads(
        self
    ):

        selected = []

        for read, var in self.check_vars:

            if var.get():

                selected.append(
                    read
                )

        return selected

    # ==================================================
    # Export FASTA
    # ==================================================

    def export_fasta(
        self
    ):

        selected = self.get_selected_reads()

        if len(selected) == 0:

            print(
                "No selected reads."
            )

            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".fas",
            filetypes=[
                (
                    "FASTA files",
                    "*.fas",
                ),
                (
                    "FASTA files",
                    "*.fasta",
                ),
            ],
        )

        if not filepath:

            return

        with open(
            filepath,
            "w",
            encoding="utf-8",
        ) as fasta_file:

            for read in selected:

                fasta_file.write(
                    f">{read.filename}\n"
                )

                fasta_file.write(
                    f"{read.trimmed_sequence}\n"
                )

        print(
            f"Exported {len(selected)} sequences."
        )

    # ==================================================
    # Save Selection
    # ==================================================

    def save_selection_file(
        self
    ):

        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[
                (
                    "JSON files",
                    "*.json",
                ),
            ],
        )

        if not filepath:

            return

        # Reflect GUI state in each read
        for read, var in self.check_vars:

            read.selected = var.get()

        save_selection(
            self.reads,
            filepath,
        )

        print(
            "Selection saved:",
            filepath,
        )

    # ==================================================
    # Load Selection
    # ==================================================

    def load_selection_file(
        self
    ):

        filepath = filedialog.askopenfilename(
            filetypes=[
                (
                    "JSON files",
                    "*.json",
                ),
            ],
        )

        if not filepath:

            return

        load_selection(
            self.reads,
            filepath,
        )

        # Reflect loaded state in GUI
        for read, var in self.check_vars:

            var.set(
                getattr(
                    read,
                    "selected",
                    True,
                )
            )

        print(
            "Selection loaded:",
            filepath,
        )

    # ==================================================
    # MAFFT Alignment
    # ==================================================

    def align_selected(
        self
    ):

        selected = self.get_selected_reads()

        if len(selected) == 0:

            print(
                "No selected reads."
            )

            return

        temp_fasta = Path(
            "selected_sequences.fas"
        )

        output_fasta = filedialog.asksaveasfilename(
            title="Save aligned FASTA",
            defaultextension=".fas",
            filetypes=[
                (
                    "FASTA files",
                    "*.fas",
                ),
            ],
        )

        if not output_fasta:

            return

        with open(
            temp_fasta,
            "w",
            encoding="utf-8",
        ) as fasta_file:

            for read in selected:

                fasta_file.write(
                    f">{read.filename}\n"
                )

                fasta_file.write(
                    f"{read.trimmed_sequence}\n"
                )

        success = run_mafft(
            temp_fasta,
            output_fasta,
        )

        if success:

            print(
                "MAFFT alignment completed."
            )

            from gui.alignment_window import AlignmentWindow

            AlignmentWindow(
                self,
                output_fasta,
            )

        else:

            print(
                "MAFFT failed."
            )

    # ==================================================
    # Apply selection to Main Viewer
    # ==================================================

    def apply_to_viewer(
        self
    ):

        selected = self.get_selected_reads()

        if self.apply_callback is not None:

            self.apply_callback(
                selected
            )

        print(
            f"Applied {len(selected)} reads to viewer."
        )