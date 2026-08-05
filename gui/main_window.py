import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from core.blast_controller import (
    run_blast_folder
)


from core.sequence_loader import (
    load_ab1_file,
    load_ab1_folder
)
from core.sequence_dataset import SequenceDataset
from core.sequence_dataset_adapter import from_trimmed_sequences
from core.project import DerivationType, Project


from gui.chromatogram_canvas import ChromatogramCanvas
from gui.status_bar import StatusBar
from gui.sample_panel import SamplePanel
from gui.quality_panel import QualityPanel
from gui.alignment_window import AlignmentWindow
from gui.button_bar import ButtonBar
from gui.blast_dialog import BlastDialog
from gui.alignment_sequence_window import AlignmentSequenceWindow
from gui.consensus_viewer import SingleConsensusReviewWindow
from gui.multiple_consensus_viewer import MultipleConsensusAlignmentWindow
from gui.consensus_review_manager import (
    ConsensusReviewCandidate,
    ConsensusReviewManagerWindow,
)
from gui.consensus_review_entry import (
    build_consensus_review_pair_rows,
    build_consensus_review_manager_inputs,
    build_review_view_model,
    discover_clear_pairs,
)

class MainWindow:


    def __init__(self, root):

        self.root = root


        self.root.title(
            "SangerFlow v0.8"
        )


        self.root.geometry(
            "1400x900"
        )


        # =====================
        # Button Bar
        # =====================

        self.button_bar = ButtonBar(

            root,

            {

                "open_file":
                    self.open_file,

                "open_folder":
                    self.open_folder,

                "open_alignment":
                    self.open_alignment,

                "align_chromatograms":
                    self.align_chromatograms,

                "toggle_trim_region":
                    self.toggle_trim_region,

                "open_blast_dialog":
                    self.open_blast_dialog,

                "open_quality_panel":
                    self.open_quality_panel,

                "open_consensus_review":
                    self.open_consensus_review_manager

            }

        )

        # =====================
        # Main area
        # =====================

        self.main_frame = tk.Frame(
            root
        )

        self.main_frame.pack(
            fill="both",
            expand=True
        )


        # Sample panel

        self.sample_panel = SamplePanel(
            self.main_frame
        )

        self.sample_panel.pack(
            side="left",
            fill="y"
        )


        # Chromatogram

        self.chrom_viewer = ChromatogramCanvas(
            self.main_frame
        )

        self.chrom_viewer.pack(
            side="right",
            fill="both",
            expand=True
        )


        # =====================
        # Status Bar
        # =====================

        self.status_bar = StatusBar(
            root
        )

        self.status_bar.pack(
            fill="x",
            side="bottom"
        )

    def create_sequence_dataset(
        self,
        dataset_id: str,
        name: str,
        *,
        reads=None,
        creation_context: str = "current Main Viewer trimmed reads",
    ) -> SequenceDataset:
        """Create a new immutable dataset from already-trimmed viewer reads.

        This is a data boundary only: it does not alter ``SangerRead`` values,
        change viewer selection, add the dataset to a Project, or open another
        GUI.  The default source is the currently selected read collection;
        callers may explicitly provide an ordered collection for testing or a
        future GUI action.
        """

        read_values = tuple(reads) if reads is not None else self._dataset_source_reads()
        sequence_pairs = []
        for read in read_values:
            filename = getattr(read, "filename", None)
            trimmed_sequence = getattr(read, "trimmed_sequence", None)
            if not isinstance(filename, str) or not filename:
                raise ValueError("Main Viewer read must have a non-empty filename")
            if not isinstance(trimmed_sequence, str) or not trimmed_sequence:
                raise ValueError(f"trimmed_sequence is empty for read: {filename}")
            sequence_pairs.append((Path(filename).stem, trimmed_sequence))

        return from_trimmed_sequences(
            dataset_id=dataset_id,
            name=name,
            sequences=sequence_pairs,
            metadata={
                "source": "Main Viewer",
                "read_count": len(read_values),
                "creation_context": creation_context,
            },
        )

    def _dataset_source_reads(self):
        """Return the current viewer ordering without changing any GUI state."""

        if hasattr(self, "selected_reads"):
            return self.selected_reads
        if hasattr(self, "reads"):
            return self.reads
        if hasattr(self, "current_read"):
            return (self.current_read,)
        raise ValueError("No reads are loaded in Main Viewer")

    def add_trimmed_sequence_dataset_to_project(
        self,
        project: Project,
        dataset_id: str,
        name: str,
        *,
        reads=None,
        display_name: str | None = None,
        creation_context: str = "current Main Viewer trimmed reads",
        on_project_changed=None,
    ) -> Project:
        """Create a trimmed dataset and return a new Project containing it.

        The caller owns the returned immutable Project through the optional
        callback.  Main Viewer deliberately does not store the Project, update
        another GUI, or persist anything in this minimal connection.
        """

        if not isinstance(project, Project):
            raise ValueError("project must be a Project")
        if on_project_changed is not None and not callable(on_project_changed):
            raise ValueError("on_project_changed must be callable or None")

        dataset = self.create_sequence_dataset(
            dataset_id,
            name,
            reads=reads,
            creation_context=creation_context,
        )
        updated_project = project.add_dataset(
            dataset,
            display_name=display_name,
            derivation_type=DerivationType.TRIMMED_FROM_READS,
        )
        if on_project_changed is not None:
            on_project_changed(updated_project)
        return updated_project



    # ==================================================
    # Open single AB1
    # ==================================================

    def open_file(self):


        filepath = filedialog.askopenfilename(

            filetypes=[

                (
                    "AB1 files",
                    "*.ab1"
                )

            ]

        )


        if not filepath:

            return



        result = load_ab1_file(

            filepath

        )



        self.current_read = result



        self.chrom_viewer.load_data(

            result

        )



        self.status_bar.set_text(

            f"{result.filename}   "
            f"{len(result.sequence)} bp   "
            f"Average Q {result.average_quality:.1f}   "
            f"HQ% {result.hq_percent:.1f}%"

        )

    # ==================================================
    # Open folder
    # ==================================================

    def open_folder(self):


        folder = filedialog.askdirectory()


        if not folder:

            return



        reads = load_ab1_folder(

            folder

        )



        if len(reads) == 0:


            print(

                "No AB1 files found."

            )

            return



        # =====================
        # Keep all samples
        # =====================

        self.all_reads = reads


        # Current viewer selection
        # 初期状態は全表示

        self.selected_reads = reads



        self.reads = reads



        # =====================
        # Viewer
        # =====================

        self.chrom_viewer.load_reads(

            self.selected_reads

        )



        self.current_read = reads[0]



        # =====================
        # Sample Panel
        # 常に全サンプルを保持
        # =====================

        self.sample_panel.update_samples(

            self.all_reads

        )

        self.sample_panel.set_callback(

            self.sample_selected

        )

        self.status_bar.set_text(

            f"{len(reads)} samples loaded"

        )

    # ==================================================
    # Toggle Trim Region
    # ==================================================

    def toggle_trim_region(self):


        self.chrom_viewer.show_trim_region = (

            not self.chrom_viewer.show_trim_region

        )


        self.chrom_viewer.draw()



    # ==================================================
    # Open BLAST Dialog
    # ==================================================

    def open_blast_dialog(self):


        dialog = BlastDialog(
            self.root
        )


        self.root.wait_window(
            dialog
        )


        if dialog.result is None:

            return



        self.blast_settings = dialog.result



        print(
            "BLAST settings:",
            self.blast_settings
        )



        try:

            # ============================
            # FASTA BLAST
            # ============================

            if self.blast_settings["target"] == "fasta":


                from core.blast import blast_fasta


                print(
                    "Running FASTA BLAST..."
                )


                results = blast_fasta(

                    self.blast_settings["input_path"],

                    database=self.blast_settings["database"],

                    max_hits=self.blast_settings["hits"]

                )


                from core.blast_exporter import export_blast_excel


                export_blast_excel(

                    results,

                    [],

                    self.blast_settings["save_path"]

                )


            # ============================
            # Folder BLAST
            # ============================

            elif self.blast_settings["target"] == "folder":


                run_blast_folder(

                    self.blast_settings["input_path"],

                    self.blast_settings["save_path"],

                    hits=self.blast_settings["hits"],

                    database=self.blast_settings["database"]

                )



            messagebox.showinfo(

                "BLAST completed",

                "Excel exported successfully."

            )



        except Exception as e:


            messagebox.showerror(

                "BLAST Error",

                str(e)

            )


    # ==================================================
    # Open Alignment (FASTA)
    # ==================================================

    def open_alignment(self):


        filepath = filedialog.askopenfilename(

            filetypes=[

                (

                    "FASTA files",

                    "*.fas *.fasta"

                )

            ]

        )


        if not filepath:

            return



        from core.chromatogram_alignment import align_fasta

        from gui.alignment_sequence_window import AlignmentSequenceWindow



        print(

            "Running FASTA MAFFT alignment..."

        )



        try:


            alignment = align_fasta(

                filepath

            )


        except Exception as e:


            messagebox.showerror(

                "Alignment Error",

                str(e)

            )

            return



        print(

            "FASTA alignment finished."

        )



        AlignmentSequenceWindow(

            self.root,

            alignment

        )
    # ==================================================
    # Align chromatograms
    # ==================================================

    def align_chromatograms(self):

        if not hasattr(self, "reads"):

            print("No AB1 reads loaded.")
            return

        from core.chromatogram_alignment import align_reads

        reads = getattr(
            self,
            "selected_reads",
            self.reads
        )

        if len(reads) == 0:

            print("No samples selected.")
            return

        alignment = align_reads(
            reads
        )

        AlignmentWindow(
            self.root,
            alignment=alignment,
            reads=reads,
            click_callback=self.alignment_clicked
        )

    # ==================================================
    # Alignment click receiver
    # ==================================================

    def alignment_clicked(

        self,

        sample_name,

        position,

        base

    ):


        print(
            "MainWindow received:"
        )


        print(
            "Sample:",
            sample_name
        )


        print(
            "Alignment position:",
            position
        )


        print(
            "Base:",
            base
        )


        if hasattr(

            self,

            "chrom_viewer"

        ):


            self.chrom_viewer.goto_position(

                position

            )
        
    # ==================================================
    # Open Quality Panel
    # ==================================================

    def open_quality_panel(self):


        if not hasattr(

            self,

            "all_reads"

        ):

            return



        panel = QualityPanel(

            self.root,

            self.all_reads

        )


        panel.set_apply_callback(

            self.apply_quality_selection

        )

    # ==================================================
    # Apply QualityPanel selection
    # ==================================================

    def apply_quality_selection(

        self,

        selected_reads

    ):


        if len(selected_reads) == 0:

            return



        self.selected_reads = selected_reads



        self.chrom_viewer.load_reads(

            selected_reads

        )



        self.status_bar.set_text(

            f"{len(selected_reads)} reads applied"

        )

    # ==================================================
    # Apply HQ filter
    # ==================================================

    def apply_quality_filter(
        self,
        filtered_reads
    ):

        self.selected_reads = filtered_reads

        self.sample_panel.update_samples(
            filtered_reads
        )

        self.chrom_viewer.load_reads(
            filtered_reads
        )

        self.status_bar.set_text(
            f"{len(filtered_reads)} samples selected"
        )

    # ==================================================
    # SamplePanel selection changed
    # ==================================================

    def sample_selected(

        self,

        selected_reads

    ):


        if len(selected_reads) == 0:

            return



        self.selected_reads = selected_reads



        self.chrom_viewer.load_reads(

            selected_reads

        )



        self.status_bar.set_text(

            f"{len(selected_reads)} samples displayed"

        )

    # ==================================================
    # Alignment click callback
    # ==================================================

    def alignment_clicked(
        self,
        sample_name,
        trace_position,
        base
    ):


        print(
            "MainViewer jump request:"
        )

        print(
            sample_name,
            trace_position,
            base
        )


        if trace_position is None:

            return


        for read in self.reads:


            if read.filename == sample_name:


                self.current_read = read


                self.chrom_viewer.load_data(
                    read
                )


                self.chrom_viewer.goto_position(
                    trace_position
                )


                break

    def open_single_consensus_review(
        self,
        view_model,
    ):
        """Open the review prototype with this window's trace-jump callback."""

        return SingleConsensusReviewWindow(
            self.root,
            view_model,
            on_trace_jump=self._jump_to_consensus_trace,
        )

    def open_consensus_review_manager(self):
        """Open the existing review-manager workflow for loaded clear pairs.

        Main Viewer only supplies its loaded reads and callback routes. Pair
        detection and candidate/evidence preparation remain in
        ``gui.consensus_review_entry``; MAFFT remains delegated by the manager
        for Multiple mode.
        """

        reads = getattr(self, "reads", ())
        if not reads:
            messagebox.showinfo(
                "Consensus Review",
                "Load a folder containing Forward/Reverse AB1 reads first.",
            )
            return None

        clear_pairs = discover_clear_pairs(reads)
        if not clear_pairs:
            messagebox.showinfo(
                "Consensus Review",
                "No clear _F/_R pairs were detected in the loaded AB1 reads.",
            )
            return None

        try:
            review_inputs = build_consensus_review_manager_inputs(clear_pairs)
        except Exception as error:
            messagebox.showerror(
                "Consensus Review",
                f"Could not build consensus review candidates: {error}",
            )
            return None

        self.status_bar.set_text(
            f"{len(review_inputs.candidates)} consensus candidate(s) ready for review"
        )
        return ConsensusReviewManagerWindow(
            self.root,
            review_inputs.candidates,
            on_open_single=self._open_consensus_review_candidate,
            on_open_multiple=lambda aligned_set: self._open_multiple_consensus_review(
                aligned_set,
                review_inputs.evidence_map,
            ),
        )

    def _open_consensus_review_candidate(
        self,
        candidate: ConsensusReviewCandidate,
    ):
        """Route a manager Single selection into the existing single viewer."""

        view_model = candidate.single_review_input
        if view_model is None:
            raise ValueError("selected candidate has no Single Consensus Review input")
        return self.open_single_consensus_review(view_model)

    def _open_multiple_consensus_review(self, aligned_consensus_set, evidence_map):
        """Route manager-owned MAFFT output into the existing multiple viewer."""

        return MultipleConsensusAlignmentWindow(
            self.root,
            aligned_consensus_set,
            evidence_map=evidence_map,
            on_trace_jump=self._jump_to_consensus_trace,
        )

    def open_consensus_review_selector(self):
        """Backward-compatible alias for the manager-based review entry."""

        return self.open_consensus_review_manager()

    def _open_legacy_single_consensus_review_selector(self):
        """Retained legacy direct-single selector; no longer exposed by the button."""

        reads = getattr(self, "reads", ())
        if not reads:
            messagebox.showinfo(
                "Consensus Review",
                "Load a folder containing Forward/Reverse AB1 reads first.",
            )
            return

        clear_pairs = discover_clear_pairs(reads)
        if not clear_pairs:
            messagebox.showinfo(
                "Consensus Review",
                "No clear _F/_R pairs were detected in the loaded AB1 reads.",
            )
            return

        sample = self._choose_consensus_review_pair(clear_pairs)
        if sample is None:
            return

        try:
            view_model = build_review_view_model(sample)
        except Exception as error:
            messagebox.showerror(
                "Consensus Review",
                f"Could not build a consensus review for {sample.sample_id}: {error}",
            )
            return

        self.open_single_consensus_review(view_model)

    def _choose_consensus_review_pair(self, clear_pairs):
        """Show a small modal selector for already classified clear pairs."""

        dialog = tk.Toplevel(self.root)
        dialog.title("Select pair for Consensus Review")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("620x320")
        dialog.minsize(520, 240)

        tk.Label(
            dialog,
            text="Select one filename-derived Forward/Reverse pair:",
            anchor="w",
            padx=12,
            pady=10,
        ).pack(fill="x")
        pair_rows = build_consensus_review_pair_rows(clear_pairs)
        table_frame = tk.Frame(dialog)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        pair_table = ttk.Treeview(
            table_frame,
            columns=("sample", "forward", "reverse", "forward_bp", "reverse_bp"),
            show="headings",
            selectmode="browse",
        )
        table_columns = (
            ("sample", "Sample", 120, True),
            ("forward", "Forward filename", 180, True),
            ("reverse", "Reverse filename", 180, True),
            ("forward_bp", "F input bp", 82, False),
            ("reverse_bp", "R input bp", 82, False),
        )
        for column_id, heading, width, stretch in table_columns:
            pair_table.heading(column_id, text=heading)
            pair_table.column(column_id, width=width, stretch=stretch)
        table_scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=pair_table.yview,
        )
        pair_table.configure(yscrollcommand=table_scrollbar.set)
        pair_table.pack(side="left", fill="both", expand=True)
        table_scrollbar.pack(side="right", fill="y")
        for index, row in enumerate(pair_rows):
            pair_table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    row.sample_id,
                    row.forward_filename,
                    row.reverse_filename,
                    _display_pair_input_length(row.forward_input_length),
                    _display_pair_input_length(row.reverse_input_length),
                ),
            )
        pair_table.selection_set("0")
        pair_table.focus("0")

        result = {"sample": None}

        def choose():
            selected = pair_table.selection()
            if selected:
                result["sample"] = pair_rows[int(selected[0])].sample
            dialog.destroy()

        buttons = tk.Frame(dialog)
        buttons.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        tk.Button(buttons, text="Open review", command=choose).pack(
            side="right",
            padx=(0, 8),
        )
        pair_table.bind("<Double-Button-1>", lambda _event: choose())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.root.wait_window(dialog)
        return result["sample"]

    def _jump_to_consensus_trace(
        self,
        read_identifier,
        raw_trace_position,
    ):
        """Delegate a bridge-provided raw trace coordinate to Main Viewer."""

        self.alignment_clicked(
            read_identifier,
            raw_trace_position,
            None,
        )

    # ==================================================
    # MainViewer click callback
    # ==================================================

    def main_viewer_clicked(
        self,
        sample_name,
        trace_position
    ):


        if hasattr(
            self,
            "alignment_window"
        ):


            self.alignment_window.goto_trace_position(

                sample_name,

                trace_position

            )


def _display_pair_input_length(length):
    """Format an already available consensus-input length for the selector."""

    return "—" if length is None else f"{length} bp"
