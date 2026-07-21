import tkinter as tk
from tkinter import filedialog

from core.ab1_reader import read_ab1

from gui.chromatogram_canvas import ChromatogramCanvas



class MainWindow:


    def __init__(self, root):

        self.root = root


        self.root.title(
            "SangerFlow v0.6"
        )


        self.root.geometry(
            "1400x900"
        )



        # =====================
        # Open button
        # =====================


        self.open_button = tk.Button(
            root,
            text="Open AB1",
            command=self.open_file
        )


        self.open_button.pack(
            pady=5
        )



        # =====================
        # Chromatogram Viewer
        # =====================


        self.chrom_viewer = ChromatogramCanvas(
            root
        )


        self.chrom_viewer.pack(
            fill="both",
            expand=True,
            pady=10
            )
        



        # =====================
        # Sequence display
        # =====================


        self.sequence_box = tk.Text(
            root,
            height=5,
            font=("Courier",12)
        )


        self.sequence_box.pack(
            fill="x"
        )




    # ==================================================
    # Open AB1
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



        result = read_ab1(
            filepath
        )



        # chromatogram表示

        self.chrom_viewer.load_data(
            result
        )



        # sequence表示

        self.sequence_box.delete(
            "1.0",
            tk.END
        )


        self.sequence_box.insert(
            tk.END,
            result.sequence
        )