import tkinter as tk
import numpy as np


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
    # Load single read
    # ==================================================

    def load_data(
        self,
        result
    ):

        self.reads = [
            result
        ]


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


        read = self.reads[0]


        # Background layer
        self.draw_quality_overlay(
            read
        )


        # Trace layer
        self.draw_traces(
            read
        )


        # Text layer
        self.draw_sequence(
            read
        )


        # Ruler layer
        self.draw_ruler(
            read
        )



    # ==================================================
    # Quality Track
    # ==================================================

    

    def draw_quality_overlay(
        self,
        read
    ):

        quality = read.quality
        positions = read.base_positions


        if len(quality) == 0:
            return


        base_y = self.trace_top + self.trace_height / 2


        max_height = self.trace_height

        max_q = 40


        points = []


        for i, q in enumerate(quality):

            if i >= len(positions):
                break


            x = (
                positions[i]
                *
                self.scale_x
            )


            height = (
                min(q, max_q)
                /
                max_q
                *
                max_height
            )


            points.append(
                x
            )

            points.append(
                base_y - height
            )


        if len(points) < 4:
            return


        # close polygon

        first_x = points[0]

        last_x = points[-2]


        polygon = points + [

            last_x,
            base_y,

            first_x,
            base_y

        ]


        self.canvas.create_polygon(

            polygon,

            fill="#EEF9FF",

            outline=""

        )



    # ==================================================
    # Ruler
    # ==================================================

    def draw_ruler(
        self,
        read
    ):


        for i,pos in enumerate(
            read.base_positions
        ):


            if i % 10 != 0:
                continue


            x = (
                pos *
                self.scale_x
            )


            self.canvas.create_text(

                x,

                self.ruler_y,

                text=str(i),

                font=(
                    "Courier",
                    10
                )
            )


            self.canvas.create_line(

                x,

                self.ruler_y+10,

                x,

                self.ruler_y+20

            )



    # ==================================================
    # Sequence
    # ==================================================

    def draw_sequence(
        self,
        read
    ):


        colors = {

            "A":"green",

            "C":"blue",

            "G":"black",

            "T":"red"

        }


        for base,pos in zip(

            read.sequence,

            read.base_positions

        ):


            x = (
                pos *
                self.scale_x
            )


            self.canvas.create_text(

                x,

                self.sequence_y,

                text=base,

                fill=colors.get(
                    base,
                    "black"
                ),

                font=(
                    "Courier",
                    12,
                    "bold"
                )
            )



    # ==================================================
    # Trace
    # ==================================================

    def draw_traces(
        self,
        read
    ):


        colors = {

            "A":"green",

            "C":"blue",

            "G":"black",

            "T":"red"

        }



        max_length = len(
            read.traces["A"]
        )


        self.canvas.config(

            scrollregion=(

                0,

                0,

                max_length*self.scale_x,

                600

            )

        )



        for base in [

            "A",

            "C",

            "G",

            "T"

        ]:


            signal = np.array(

                read.traces[base]

            )


            if signal.max()==0:
                continue



            signal = (

                signal /

                signal.max()

                *

                self.trace_height/2

            )



            points=[]



            for i,value in enumerate(signal):


                x = (

                    i *

                    self.scale_x

                )


                y = (

                    self.trace_top

                    +

                    self.trace_height/2

                    -

                    value

                )


                points.extend(
                    [
                        x,
                        y
                    ]
                )


            self.canvas.create_line(

                points,

                fill=colors[base],

                width=1

            )