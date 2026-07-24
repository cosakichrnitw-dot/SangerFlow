import tkinter as tk
from tkinter import filedialog

from pathlib import Path

from core.mafft import run_mafft

from pathlib import Path

from core.selection import (
    save_selection,
    load_selection
)


class QualityPanel(tk.Toplevel):


    def __init__(
        self,
        parent,
        reads
    ):

        super().__init__(parent)


        self.title(
            "Sequence Quality"
        )


        self.geometry(
            "700x500"
        )


        self.reads = reads


        # checkbox管理

        self.check_vars = []



        # =====================
        # Header
        # =====================

        header = tk.Label(
            self,
            text=(
                "Select     Sample              "
                "Length     HQ%      Q20      Q30"
            ),
            font=(
                "Courier",
                10,
                "bold"
            )
        )

        header.pack(
            anchor="w",
            padx=10,
            pady=5
        )



        # =====================
        # Scroll frame
        # =====================

        self.list_frame = tk.Frame(
            self
        )

        self.list_frame.pack(
            fill="both",
            expand=True
        )



        self.create_rows()



        # =====================
        # HQ Select area
        # =====================

        bottom = tk.Frame(
            self
        )

        bottom.pack(
            fill="x",
            pady=10
        )



        tk.Label(
            bottom,
            text="HQ threshold (%)"
        ).pack(
            side="left",
            padx=5
        )



        self.hq_entry = tk.Entry(
            bottom,
            width=8
        )

        self.hq_entry.insert(
            0,
            "70"
        )

        self.hq_entry.pack(
            side="left"
        )



        self.select_button = tk.Button(

            bottom,

            text="HQ > threshold Select",

            command=self.select_by_hq

        )


        self.select_button.pack(

            side="left",

            padx=10

        )

        self.export_button = tk.Button(
            bottom,
            text="Export Selected FASTA",
            command=self.export_fasta
        )

        self.export_button.pack(
            side="left",
            padx=10
        )

        self.align_button = tk.Button(
            bottom,
            text="Align Selected",
            command=self.align_selected
        )


        self.align_button.pack(
            side="left",
            padx=10
        )

        self.save_button = tk.Button(
            bottom,
            text="Save Selection",
            command=self.save_selection_file
        )

        self.save_button.pack(
            side="left",
            padx=10
        )


        self.load_button = tk.Button(
            bottom,
            text="Load Selection",
            command=self.load_selection_file
        )

        self.load_button.pack(
            side="left",
            padx=10
        )

    # ==================================================
    # Create rows
    # ==================================================

    def create_rows(self):


        for read in self.reads:


            var = tk.BooleanVar(

                value=getattr(
                    read,
                    "selected",
                    True
                    )

            )


            self.check_vars.append(

                (
                    read,
                    var
                )

            )



            row = tk.Frame(

                self.list_frame

            )

            row.pack(

                fill="x",

                padx=10,

                pady=2

            )



            tk.Checkbutton(

                row,

                variable=var

            ).pack(

                side="left"

            )



            text = (

                f"{read.filename:<25}"

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

                    10

                )

            ).pack(

                side="left"

            )





    # ==================================================
    # HQ selection
    # ==================================================

    def select_by_hq(self):


        try:

            threshold = float(

                self.hq_entry.get()

            )

        except:


            return




        for read, var in self.check_vars:


            if read.hq_percent >= threshold:

                var.set(True)


            else:

                var.set(False)



    # ==================================================
    # Get selected reads
    # ==================================================

    def get_selected_reads(self):


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

    def export_fasta(self):


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



        with open(
            filepath,
            "w"
        ) as f:


            for read in selected:


                f.write(
                    f">{read.filename}\n"
                )


                f.write(
                    f"{read.trimmed_sequence}\n"
                )


        print(
            f"Exported {len(selected)} sequences."
        )

    # ==================================================
    # Save Selection
    # ==================================================

    def save_selection_file(self):


        filepath = filedialog.asksaveasfilename(

            defaultextension=".json",

            filetypes=[

                (
                    "JSON files",
                    "*.json"
                )

            ]

        )


        if not filepath:

            return



        # GUI状態をreadへ反映

        for read, var in self.check_vars:

            read.selected = var.get()



        save_selection(

            self.reads,

            filepath

        )


        print(
            "Selection saved:",
            filepath
        )



    # ==================================================
    # Load Selection
    # ==================================================

    def load_selection_file(self):


        filepath = filedialog.askopenfilename(

            filetypes=[

                (
                    "JSON files",
                    "*.json"
                )

            ]

        )


        if not filepath:

            return



        load_selection(

            self.reads,

            filepath

        )



        # GUIへ反映

        for read, var in self.check_vars:

            var.set(

                getattr(
                    read,
                    "selected",
                    True
                )

            )


        print(
            "Selection loaded:",
            filepath
        )

    # ==================================================
    # MAFFT Alignment
    # ==================================================

    def align_selected(self):


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
                    "*.fas"
                )

            ]

        )


        if not output_fasta:

            return



        # =====================
        # Create temporary FASTA
        # =====================

        with open(
            temp_fasta,
            "w"
        ) as f:


            for read in selected:


                f.write(
                    f">{read.filename}\n"
                )


                f.write(
                    f"{read.trimmed_sequence}\n"
                )



        # =====================
        # Run MAFFT
        # =====================

        success = run_mafft(

            temp_fasta,

            output_fasta

        )



        if success:


            print(
                "MAFFT alignment completed."
            )

            from gui.alignment_window import AlignmentWindow

            AlignmentWindow(

                self,

                output_fasta
            )


        else:


            print(
                "MAFFT failed."
            )