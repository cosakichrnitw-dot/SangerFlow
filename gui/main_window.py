import tkinter as tk
from tkinter import filedialog

from core.ab1_reader import read_ab1
from core.trimming import trim_sequence
from core.quality import (
    calculate_hq_percent,
    calculate_average_quality,
    calculate_q20_rate,
    calculate_q30_rate
)

from gui.chromatogram_canvas import ChromatogramCanvas
from gui.status_bar import StatusBar
from gui.sample_panel import SamplePanel
from gui.quality_panel import QualityPanel
from gui.alignment_window import AlignmentWindow



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
        # Button frame
        # =====================

        self.button_frame = tk.Frame(
            root
        )

        self.button_frame.pack(
            pady=5
        )


        self.open_button = tk.Button(
            self.button_frame,
            text="Open AB1",
            command=self.open_file,
            width=15
        )

        self.open_button.pack(
            side="left",
            padx=5
        )


        self.folder_button = tk.Button(
            self.button_frame,
            text="Open Folder",
            command=self.open_folder,
            width=15
        )

        self.folder_button.pack(
            side="left",
            padx=5
        )

        self.alignment_button = tk.Button(

            self.button_frame,

            text="Open Alignment",

            command=self.open_alignment,

            width=15

        )


        self.alignment_button.pack(

            side="left",

            padx=5

        )

        self.trim_view_button = tk.Button(
            self.button_frame,
            text="Show Trim Region",
            command=self.toggle_trim_region,
            width=15
        )

        self.trim_view_button.pack(
            side="left",
            padx=5
        )

        self.quality_button = tk.Button(
            self.button_frame,
            text="Quality Report",
            command=self.open_quality_panel,
            width=15
        )

        self.quality_button.pack(
            side="left",
            padx=5
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



        result = read_ab1(
            filepath
        )


        trim_sequence(
            result
        )


        result.hq_percent = calculate_hq_percent(
            result
        )

        result.average_quality = (
            calculate_average_quality(result)
        )


        result.q20_rate = (
            calculate_q20_rate(result)
        )


        result.q30_rate = (
            calculate_q30_rate(result)
        )

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



        from pathlib import Path


        reads = []



        for filepath in sorted(

            Path(folder).glob("*.ab1")

        ):


            try:


                read = read_ab1(

                    filepath

                )



                trim_sequence(

                    read

                )



                read.hq_percent = calculate_hq_percent(

                    read

                )
                read.average_quality = (
                    calculate_average_quality(read)
                )


                read.q20_rate = (
                    calculate_q20_rate(read)
                )


                read.q30_rate = (
                    calculate_q30_rate(read)
                )


                # =====================
                # Trim Report
                # =====================

                print("")

                print(
                    "========== Trim Report =========="
                )


                print(
                    "File:",
                    read.filename
                )


                print(
                    "Original length:",
                    len(read.sequence),
                    "bp"
                )


                print(
                    "Trim start:",
                    read.trim_start
                )


                print(
                    "Trim end:",
                    read.trim_end
                )


                print(
                    "Trimmed length:",
                    len(read.trimmed_sequence),
                    "bp"
                )


                print(
                    "HQ%:",
                    f"{read.hq_percent:.1f}%"
                )


                print(
                    "================================"
                )


                print("")



                reads.append(

                    read

                )



            except Exception as e:


                print(

                    f"Failed: {filepath.name}"

                )


                print(e)




        if len(reads) == 0:


            print(
                "No AB1 files found."
            )

            return




        self.chrom_viewer.load_reads(

            reads

        )


        self.reads = reads



        self.sample_panel.update_samples(

            reads

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
    # Open Alignment
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


        AlignmentWindow(

            self.root,

            filepath

        )
        
    # ==================================================
    # Open Quality Panel
    # ==================================================

    def open_quality_panel(self):

        if not hasattr(
            self,
            "reads"
        ):

            return


        QualityPanel(
            self.root,
            self.reads
        )