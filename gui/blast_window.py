import tkinter as tk
from tkinter import ttk
import re



class BlastWindow(tk.Toplevel):


    def __init__(
        self,
        parent,
        sample_name,
        results
    ):

        super().__init__(parent)


        self.title(
            f"BLAST Result - {sample_name}"
        )


        self.geometry(
            "1000x600"
        )


        self.results = results



        # =====================
        # Main frame
        # =====================

        self.main_frame = tk.Frame(
            self
        )

        self.main_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )



        # =====================
        # Table
        # =====================

        columns = (

            "Rank",
            "Species",
            "Identity",
            "Coverage",
            "E-value",
            "Accession"

        )


        self.tree = ttk.Treeview(

            self.main_frame,

            columns=columns,

            show="headings",

            height=15

        )



        for col in columns:


            self.tree.heading(

                col,

                text=col

            )


            self.tree.column(

                col,

                width=120

            )



        self.tree.column(

            "Species",

            width=220

        )


        self.tree.pack(

            fill="both",

            expand=True

        )



        # =====================
        # Detail area
        # =====================

        detail_label = tk.Label(

            self.main_frame,

            text="Hit Detail",

            font=(

                "Arial",

                11,

                "bold"

            )

        )


        detail_label.pack(

            anchor="w",

            pady=(10,0)

        )



        self.detail = tk.Text(

            self.main_frame,

            height=8,

            font=(

                "Courier",

                10

            )

        )


        self.detail.pack(

            fill="x"

        )



        self.tree.bind(

            "<<TreeviewSelect>>",

            self.show_detail

        )



        self.populate()



    # ==================================================
    # Extract accession
    # ==================================================

    def extract_accession(
        self,
        title
    ):


        # gb|XXXX|
        match = re.search(

            r"\|([A-Z]{1,3}\d+\.\d+)\|",

            title

        )


        if match:

            return match.group(1)



        return "Unknown"



    # ==================================================
    # Populate table
    # ==================================================

    def populate(self):


        for i, result in enumerate(

            self.results,

            start=1

        ):


            accession = self.extract_accession(

                result["title"]

            )


            self.tree.insert(

                "",

                "end",

                iid=str(i-1),

                values=(

                    i,

                    result["species"],

                    f'{result["identity"]:.3f}',

                    f'{result["coverage"]:.3f}',

                    result["e_value"],

                    accession

                )

            )



    # ==================================================
    # Show selected hit
    # ==================================================

    def show_detail(
        self,
        event=None
    ):


        selected = self.tree.selection()


        if not selected:

            return



        index = int(

            selected[0]

        )


        result = self.results[index]



        self.detail.delete(

            "1.0",

            "end"

        )


        self.detail.insert(

            "end",

            result["title"]

        )