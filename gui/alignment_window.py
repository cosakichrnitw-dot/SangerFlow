import tkinter as tk
from gui.alignment_canvas import AlignmentCanvas


class AlignmentWindow(tk.Toplevel):


    def __init__(
        self,
        parent,
        alignment_file
    ):

        super().__init__(parent)


        self.title(
            "MAFFT Alignment"
        )


        self.geometry(
            "900x600"
        )


        self.alignment_file = alignment_file



        # =====================
        # Alignment viewer
        # =====================

        self.viewer = AlignmentCanvas(

            self

        )


        self.viewer.pack(

            fill="both",

            expand=True,

            padx=10,

            pady=10

        )


        self.viewer.load_alignment(

            self.alignment_file

        )