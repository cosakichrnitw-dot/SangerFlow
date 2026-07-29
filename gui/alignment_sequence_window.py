import tkinter as tk
from tkinter import filedialog


from gui.alignment_canvas import AlignmentCanvas

from core.exporter import export_consensus_fasta



class AlignmentSequenceWindow(tk.Toplevel):


    def __init__(
        self,
        parent,
        alignment,
        click_callback=None
    ):


        super().__init__(
            parent
        )


        self.title(
            "MAFFT Sequence Alignment"
        )


        self.geometry(
            "1200x800"
        )


        self.alignment = alignment

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



        self.export_button = tk.Button(

            button_frame,

            text="Export Consensus FASTA",

            command=self.export_consensus

        )


        self.export_button.pack(

            side="left",

            padx=10

        )



        # =====================
        # Alignment Viewer
        # =====================

        self.viewer = AlignmentCanvas(

            self,

            click_callback=self.alignment_clicked

        )


        self.viewer.pack(

            fill="both",

            expand=True,

            padx=10,

            pady=10

        )



        self.load_alignment()



    # ==================================================
    # Load alignment
    # ==================================================

    def load_alignment(
        self
    ):


        self.viewer.alignment = {}



        for record in self.alignment:


            self.viewer.alignment[

                record.id

            ] = str(

                record.seq

            )



        self.viewer.draw()



    # ==================================================
    # Export consensus
    # ==================================================

    def export_consensus(
        self
    ):


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

        position,

        base

    ):


        print(
            "Sequence alignment click"
        )


        print(
            "Sample:",
            sample_name
        )


        print(
            "Position:",
            position
        )


        print(
            "Base:",
            base
        )



        if self.click_callback:


            self.click_callback(

                sample_name,

                position,

                base

            )