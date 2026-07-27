import tkinter as tk
from tkinter import filedialog, messagebox

from core.blast_controller import (
    run_blast_folder
)


from core.sequence_loader import (
    load_ab1_file,
    load_ab1_folder
)


from gui.chromatogram_canvas import ChromatogramCanvas
from gui.status_bar import StatusBar
from gui.sample_panel import SamplePanel
from gui.quality_panel import QualityPanel
from gui.alignment_window import AlignmentWindow
from gui.button_bar import ButtonBar
from gui.blast_dialog import BlastDialog

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
                    self.open_quality_panel

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



        self.chrom_viewer.load_reads(

            reads

        )



        self.current_read = reads[0]


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
    # Open Alignment
    # ==================================================

    def open_alignment(self):


        if not hasattr(
            self,
            "reads"
        ):

            print(
                "No reads loaded."
            )

            return



        from core.chromatogram_alignment import align_reads



        print(
            "Running MAFFT alignment..."
        )


        alignment = align_reads(

            self.reads

        )


        print(
            "Alignment generated."
        )



        AlignmentWindow(

            self.root,

            alignment,

            self.reads,

            click_callback=self.alignment_clicked

        )

    # ==================================================
    # Align chromatograms
    # ==================================================

    def align_chromatograms(self):


        if not hasattr(
            self,
            "reads"
        ) or not self.reads:


            print(
                "No AB1 reads loaded."
            )

            return



        from core.chromatogram_alignment import align_reads


        print(
            "Running MAFFT alignment..."
        )


        alignment = align_reads(

            self.reads

        )


        print(
            "Alignment finished."
        )


        AlignmentWindow(

            self.root,

            alignment=alignment,

            reads=self.reads,

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
            "reads"
        ):

            return


        QualityPanel(
            self.root,
            self.reads
        )