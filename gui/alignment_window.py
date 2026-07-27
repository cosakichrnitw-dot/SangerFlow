import tkinter as tk
from tkinter import filedialog

from gui.alignment_chromatogram_canvas import AlignmentChromatogramCanvas

from core.exporter import export_consensus_fasta


class AlignmentWindow(tk.Toplevel):


    def __init__(
        self,
        parent,
        alignment,
        reads,
        click_callback=None
    ):

        super().__init__(parent)


        self.title(
            "MAFFT Chromatogram Alignment"
        )


        self.geometry(
            "1200x800"
        )


        self.alignment = alignment

        self.reads = reads

        self.click_callback = click_callback



        # =====================
        # Button Area
        # =====================

        button_frame = tk.Frame(
            self
        )

        button_frame.pack(
            fill="x",
            pady=5
        )



        self.export_consensus_button = tk.Button(

            button_frame,

            text="Export Consensus FASTA",

            command=self.export_consensus

        )


        self.export_consensus_button.pack(

            side="left",

            padx=10

        )



        # =====================
        # Viewer
        # =====================

        self.viewer = AlignmentChromatogramCanvas(

            self,

            click_callback=self.alignment_clicked

        )


        self.viewer.pack(

            fill="both",

            expand=True,

            padx=10,

            pady=10

        )



        # =====================
        # Load alignment + chromatograms
        # =====================

        self.viewer.load_alignment_reads(

            self.alignment,

            self.reads

        )




    # ==================================================
    # Export Consensus FASTA
    # ==================================================

    def export_consensus(self):


        consensus = getattr(

            self.viewer,

            "consensus",

            None

        )


        if not consensus:


            print(
                "No consensus available."
            )


            return



        filepath = filedialog.asksaveasfilename(

            defaultextension=".fas",

            filetypes=[

                (
                    "FASTA files",
                    "*.fas"
                ),

                (
                    "FASTA files",
                    "*.fasta"
                )

            ]

        )


        if not filepath:

            return



        export_consensus_fasta(

            consensus,

            filepath

        )


        print(

            "Consensus exported:",

            filepath

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
            "============================"
        )


        print(
            "Alignment click"
        )


        print(
            "Sample:",
            sample_name
        )


        print(
            "Trace position:",
            trace_position
        )


        print(
            "Base:",
            base
        )


        print(
            "============================"
        )



        if self.click_callback:


            self.click_callback(

                sample_name,

                trace_position,

                base

            )