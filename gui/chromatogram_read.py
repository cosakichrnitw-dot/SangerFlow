import numpy as np


class ChromatogramRead:
    """
    Renderer for a single Sanger sequencing read.

    This class draws one chromatogram.
    Canvas management, scrolling and zooming
    are handled by ChromatogramCanvas.
    """


    def __init__(
        self,
        canvas,
        read,
        scale_x,
        trace_top,
        trace_height,
        sequence_y,
        ruler_y,
        y_offset=0
    ):

        self.canvas = canvas

        self.read = read


        self.scale_x = scale_x


        self.trace_top = trace_top

        self.trace_height = trace_height


        self.sequence_y = sequence_y

        self.ruler_y = ruler_y


        self.y_offset = y_offset



    # ==================================================
    # Draw all layers
    # ==================================================

    def draw(self):

        self.draw_quality_overlay()

        self.draw_traces()

        self.draw_sequence()

        self.draw_ruler()

    # ==================================================
    # Quality background
    # ==================================================

    def draw_quality_overlay(self):

        quality = self.read.quality

        positions = self.read.base_positions


        if len(quality) == 0:
            return


        base_y = (
            self.trace_top
            +
            self.y_offset
            +
            self.trace_height / 2
        )


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


            points.extend(
                [
                    x,
                    base_y - height
                ]
            )


        if len(points) < 4:
            return


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

    def draw_ruler(self):

        for i, pos in enumerate(
            self.read.base_positions
        ):

            if i % 10 != 0:
                continue


            x = (
                pos
                *
                self.scale_x
            )


            y = (
                self.ruler_y
                +
                self.y_offset
            )


            self.canvas.create_text(

                x,

                y,

                text=str(i),

                font=(
                    "Courier",
                    10
                )

            )


            self.canvas.create_line(

                x,

                y + 10,

                x,

                y + 20

            )



    # ==================================================
    # Sequence bases
    # ==================================================

    def draw_sequence(self):

        colors = {

            "A": "green",

            "C": "blue",

            "G": "black",

            "T": "red"

        }


        for base, pos in zip(

            self.read.sequence,

            self.read.base_positions

        ):


            x = (

                pos

                *

                self.scale_x

            )


            self.canvas.create_text(

                x,

                self.sequence_y + self.y_offset,

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
    # Chromatogram trace
    # ==================================================

    def draw_traces(self):

        colors = {

            "A": "green",

            "C": "blue",

            "G": "black",

            "T": "red"

        }


        for base in [

            "A",

            "C",

            "G",

            "T"

        ]:


            signal = np.array(

                self.read.traces[base]

            )


            if signal.max() == 0:

                continue



            signal = (

                signal

                /

                signal.max()

                *

                self.trace_height / 2

            )


            points = []



            for i, value in enumerate(signal):


                x = (

                    i

                    *

                    self.scale_x

                )


                y = (

                    self.trace_top

                    +

                    self.y_offset

                    +

                    self.trace_height / 2

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