import tkinter as tk


from gui.alignment_canvas import AlignmentCanvas



class AlignmentSequenceWindow(tk.Toplevel):


    def __init__(
        self,
        parent,
        alignment
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



        # =====================
        # Viewer
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


        self.load_alignment()



    # ==================================================
    # Load alignment
    # ==================================================

    def load_alignment(self):


        self.viewer.alignment = {}


        for record in self.alignment:


            self.viewer.alignment[

                record.id

            ] = str(

                record.seq

            )


        self.viewer.draw()