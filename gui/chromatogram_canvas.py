import tkinter as tk

from gui.chromatogram_read import ChromatogramRead



class ChromatogramCanvas(tk.Frame):


    def __init__(self, parent):

        super().__init__(
            parent,
            relief="groove",
            borderwidth=2
        )


        # =====================
        # Layout
        # =====================

        self.row_height = 130



        # =====================
        # Scrollbars
        # =====================

        self.h_scrollbar = tk.Scrollbar(
            self,
            orient="horizontal"
        )

        self.h_scrollbar.pack(
            side="bottom",
            fill="x"
        )


        self.v_scrollbar = tk.Scrollbar(
            self,
            orient="vertical"
        )

        self.v_scrollbar.pack(
            side="right",
            fill="y"
        )



        # =====================
        # Main frame
        # =====================

        self.main_frame = tk.Frame(
            self
        )

        self.main_frame.pack(
            fill="both",
            expand=True,
            padx=0,
            pady=0
        )



        # =====================
        # Fixed sample label
        # =====================

        self.label_canvas = tk.Canvas(
            self.main_frame,
            width=110,
            bg="white",
            highlightthickness=0
        )

        self.label_canvas.pack(
            side="left",
            fill="y"
        )



        # =====================
        # Chromatogram canvas
        # =====================

        self.canvas = tk.Canvas(
            self.main_frame,
            bg="white",
            highlightthickness=0,
            xscrollcommand=self.h_scrollbar.set,
            yscrollcommand=self.v_scrollbar.set
        )

        self.canvas.pack(
            side="right",
            fill="both",
            expand=True
        )



        # =====================
        # Scroll connection
        # =====================

        def x_scroll(*args):

            self.canvas.xview(*args)


        self.h_scrollbar.config(
            command=x_scroll
        )



        def y_scroll(*args):

            self.canvas.yview(*args)

            self.label_canvas.yview(*args)


        self.v_scrollbar.config(
            command=y_scroll
        )



        # =====================
        # Data
        # =====================

        self.reads = []

        # Trim region display

        self.show_trim_region = False


        self.scale_x = 1


        self.scale_x = 1


        self.trace_top = 55

        self.trace_height = 70


        self.sequence_y = 20

        self.ruler_y = 5




    # ==================================================
    # Load single read
    # ==================================================

    def load_data(
        self,
        read
    ):

        self.reads = [
            read
        ]

        self.draw()



    # ==================================================
    # Load multiple reads
    # ==================================================

    def load_reads(
        self,
        reads
    ):

        self.reads = reads

        self.draw()




    # ==================================================
    # Main draw
    # ==================================================

    def draw(self):

        self.canvas.delete(
            "all"
        )

        self.label_canvas.delete(
            "all"
        )


        if len(self.reads) == 0:
            return



        for i, read in enumerate(self.reads):

            self.draw_single_read(
                read,
                i
            )



        # =====================
        # Scroll region
        # =====================

        bbox = self.canvas.bbox(
            "all"
        )


        if bbox:

            self.canvas.config(
                scrollregion=bbox
            )


            self.label_canvas.config(
                scrollregion=(
                    0,
                    0,
                    110,
                    bbox[3]
                )
            )




    # ==================================================
    # Single read
    # ==================================================

    def draw_single_read(
        self,
        read,
        index
    ):


        y_offset = (
            index *
            self.row_height
        )



        # =====================
        # Sample label
        # =====================

        self.label_canvas.create_text(

            5,

            y_offset + self.sequence_y,

            text=read.filename,

            anchor="w",

            font=(
                "Courier",
                9,
                "bold"
            )

        )



        # =====================
        # Chromatogram
        # =====================

        viewer = ChromatogramRead(

            canvas=self.canvas,

            read=read,

            scale_x=self.scale_x,

            trace_top=self.trace_top,

            trace_height=self.trace_height,

            sequence_y=self.sequence_y,

            ruler_y=self.ruler_y,

            y_offset=y_offset
            )

        viewer.show_trim_region = (
            self.show_trim_region
        )

        viewer.draw()