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
        # Scroll
        # =====================

        self.scrollbar = tk.Scrollbar(
            self,
            orient="horizontal"
        )

        self.scrollbar.pack(
            side="bottom",
            fill="x"
        )


        # =====================
        # Canvas
        # =====================

        self.canvas = tk.Canvas(
            self,
            bg="white",
            height=600,
            xscrollcommand=self.scrollbar.set
        )

        self.canvas.pack(
            fill="both",
            expand=True
        )


        self.scrollbar.config(
            command=self.canvas.xview
        )
        
        # =====================
        # Zoom control
        # =====================

        self.zoom_factor = 1.2

        self.canvas.bind(
            "<MouseWheel>",
            self.zoom
        )

        # =====================
        # Reads
        # Future:
        # multiple chromatograms
        # =====================

        self.reads = []


        self.scale_x = 5


        self.trace_top = 180

        self.trace_height = 220


        self.sequence_y = 120

        self.ruler_y = 50



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


        if len(self.reads) == 0:
            return


        for i, read in enumerate(self.reads):

            self.draw_single_read(
                read,
                i
            )
    
    # ==================================================
    # Single read renderer
    # ==================================================

    def draw_single_read(
        self,
        read,
        index
    ):

        viewer = ChromatogramRead(

            canvas=self.canvas,

            read=read,

            scale_x=self.scale_x,

            trace_top=self.trace_top,

            trace_height=self.trace_height,

            sequence_y=self.sequence_y,

            ruler_y=self.ruler_y,

            y_offset=index * 300

        )


        viewer.draw()


        self.canvas.config(
            scrollregion=self.canvas.bbox("all")
        )

      

    # ==================================================
    # Zoom
    # ==================================================

    def zoom(
        self,
        event
    ):

        if event.delta > 0:

            scale = self.zoom_factor

        else:

            scale = 1 / self.zoom_factor



        # mouse position in canvas coordinates

        x = self.canvas.canvasx(
            event.x
        )

        y = self.canvas.canvasy(
            event.y
        )


        self.canvas.scale(
            "all",
            x,
            y,
            scale,
            scale
        )


        self.canvas.configure(
            scrollregion=
            self.canvas.bbox("all")
        )