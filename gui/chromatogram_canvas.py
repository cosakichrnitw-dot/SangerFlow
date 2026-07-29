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

        self.visible_reads = []

        # Trim region display

        self.show_trim_region = False


        self.scale_x = 1


        self.scale_x = 1


        self.trace_top = 55

        self.trace_height = 70


        self.sequence_y = 20

        self.ruler_y = 5

        self.zoom_factor = 1.2

        # =====================
        # Trim display state
        # =====================

        self.show_trim_region = False

        # =====================
        # Current position marker
        # =====================

        self.current_position = None

        # Current position marker item

        self.position_marker = None

        # Highlight information

        self.highlight_base = None

        # =====================
        # Mouse navigation
        # =====================

        self.canvas.bind(

            "<MouseWheel>",

            self.mouse_scroll

        )


        self.canvas.bind(

            "<ButtonPress-2>",

            self.pan_start

        )


        self.canvas.bind(

            "<B2-Motion>",

            self.pan_move

        )


        self.zoom_factor = 1.2

        self.canvas.bind(
            "<Shift-ButtonPress-1>",
            self.pan_start
        )


        self.canvas.bind(
            "<Shift-B1-Motion>",
            self.pan_move
        )

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

        if self.visible_reads:
            reads = self.visible_reads

        else:
            reads = self.reads

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

    # ==================================================
    # Jump to alignment position
    # ==================================================

    def goto_position(
        self,
        position
    ):


        if position is None:

            return



        self.current_position = position

        self.highlight_base = position - 1

        # Remove previous marker

        if self.position_marker is not None:

            self.canvas.delete(

                self.position_marker

            )


        # Alignment position
        x = (

            position

            *

            self.scale_x

        )

        # Draw current position marker

        bbox = self.canvas.bbox(
            "all"
        )


        if bbox:

            self.position_marker = self.canvas.create_line(

                x,

                bbox[1],

                x,

                bbox[3],

                fill="purple",

                width=2,

                dash=(4,2)

            )

        bbox = self.canvas.bbox(
            "all"
        )


        if not bbox:

            return



        canvas_width = self.canvas.winfo_width()



        total_width = bbox[2]



        if total_width <= canvas_width:

            return



        fraction = (

            x - canvas_width / 2

        ) / total_width



        if fraction < 0:

            fraction = 0



        if fraction > 1:

            fraction = 1



        self.canvas.xview_moveto(

            fraction

        )

    # ==================================================
    # Change visible reads only
    # ==================================================

    def set_visible_reads(
        self,
        reads
    ):

        self.visible_reads = reads

        self.draw()

    # ==================================================
    # Mouse scroll / Zoom
    # ==================================================

    def mouse_scroll(
        self,
        event
    ):


        # =====================
        # Command + scroll Zoom
        # =====================

        if event.state & 0x0008:


            if event.delta > 0:

                self.scale_x *= self.zoom_factor


            else:

                self.scale_x /= self.zoom_factor



            if self.scale_x < 0.3:

                self.scale_x = 0.3


            if self.scale_x > 20:

                self.scale_x = 20



            print(
                "ZOOM:",
                self.scale_x
            )


            self.draw()


            return



        # =====================
        # Normal scroll
        # =====================

        if event.delta > 0:

            self.canvas.yview_scroll(

                -1,

                "units"

            )

            self.label_canvas.yview_scroll(

                -1,

                "units"

            )


        else:

            self.canvas.yview_scroll(

                1,

                "units"

            )

            self.label_canvas.yview_scroll(

                1,

                "units"

            )


    # ==================================================
    # Middle mouse pan
    # ==================================================

    def pan_start(
        self,
        event
    ):


        self.canvas.scan_mark(

            event.x,

            event.y

        )



    def pan_move(
        self,
        event
    ):


        self.canvas.scan_dragto(

            event.x,

            event.y,

            gain=1

        )

    # ==================================================
    # Pan
    # ==================================================

    def pan_start(
        self,
        event
    ):

        self.canvas.scan_mark(
            event.x,
            event.y
        )


    def pan_move(
        self,
        event
    ):

        self.canvas.scan_dragto(
            event.x,
            event.y,
            gain=1
        )

    # ==================================================
    # Toggle Trim Region display
    # ==================================================

    def set_show_trim_region(
        self,
        value
    ):

        self.show_trim_region = value

        self.draw()