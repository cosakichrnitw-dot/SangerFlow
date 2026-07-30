import numpy as np


class ChromatogramRead:


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

        # =====================
        # Highlight position
        # =====================

        self.highlight_position = None

        # =====================
        # Shared trace coordinate
        # =====================

        self.trace_area_top = (
            self.trace_top
            +
            self.y_offset
        )


        self.trace_area_bottom = (
            self.trace_top
            +
            self.y_offset
            +
            self.trace_height
        )


     # ==================================================
    # Draw
    # ==================================================

    def draw(self):


        # Quality background
        self.draw_quality_overlay()


        # Trim Region
        if self.show_trim_region:

            self.draw_trim_region()


        # Raw chromatogram
        self.draw_traces()


        # Raw bases
        self.draw_sequence()



    # ==================================================
    # Quality background
    # ==================================================

    def draw_quality_overlay(self):

        quality = self.read.quality

        positions = self.read.base_positions


        if len(quality) == 0:
            return


        if len(positions) == 0:
            return



        points = []


        # 波形中心

        center_y = (
            self.trace_top
            +
            self.y_offset
            +
            self.trace_height / 2
        )


        max_height = (
            self.trace_height / 2
        )


        max_q = 40



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
                    center_y - height
                ]
            )



        if len(points) < 4:
            return



        # 下側を波形中心で閉じる

        polygon = points.copy()


        polygon.extend(
            [
                points[-2],
                center_y,

                points[0],
                center_y
            ]
        )



        self.canvas.create_polygon(

            polygon,

            fill="#EEF9FF",

            outline=""

        )



    def draw_trim_region(self):

        start = getattr(
            self.read,
            "trim_start",
            None
        )

        end = getattr(
            self.read,
            "trim_end",
            None
        )


        if start is None or end is None:
            return


        positions = (
            self.read.base_positions
        )


        if len(positions) == 0:
            return



        # =====================
        # Match quality background height
        # =====================

        center_y = (
            self.trace_top
            +
            self.y_offset
            +
            self.trace_height / 2
        )


        trim_height = (
            self.trace_height / 2
        )


        y1 = (
            center_y
            -
            trim_height
        )


        y2 = center_y



        # =====================
        # Width
        # =====================

        total_width = (
            positions[-1]
            *
            self.scale_x
        )



        # =====================
        # Left low quality
        # =====================

        if start > 0:

            x2 = (
                positions[start]
                *
                self.scale_x
            )


            self.canvas.create_rectangle(

                0,

                y1,

                x2,

                y2,

                fill="#FF9999",

                outline=""

            )



        # =====================
        # Right low quality
        # =====================

        if end < len(positions):

            x1 = (
                positions[end]
                *
                self.scale_x
            )


            self.canvas.create_rectangle(

                x1,

                y1,

                total_width,

                y2,

                fill="#FF9999",

                outline=""
            )



    # ==================================================
    # Sequence
    # ==================================================

    def draw_sequence(self):

        colors = {

            "A":"green",
            "C":"blue",
            "G":"black",
            "T":"red"

        }


        sequence = (
            self.read.sequence
        )

        positions = (
            self.read.base_positions
        )


        for base, pos in zip(

            sequence,

            positions

        ):

            x = (

                pos
                *
                self.scale_x

            )

            # =====================
            # Highlight selected base
            # =====================

            if (

                self.highlight_position is not None

                and

                abs(
                    pos -
                    self.highlight_position
                ) < 5

            ):

                self.canvas.create_rectangle(

                    x - 8,

                    self.sequence_y + self.y_offset - 12,

                    x + 8,

                    self.sequence_y + self.y_offset + 12,

                    fill="yellow",

                    outline=""

                )


            # =====================
            # Draw base letter
            # =====================

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

                    10,

                    "bold"

                )

            )

    # ==================================================
    # Trace
    # ==================================================

    def draw_traces(self):


        colors = {

            "A":"green",

            "C":"blue",

            "G":"black",

            "T":"red"

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
                self.trace_height
                /
                2

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