# gui/alignment_chromatogram_canvas.py

import tkinter as tk


from core.chromatogram_alignment import align_reads

from core.alignment_mapper import (
    alignment_to_trace_positions
)
from core.consensus import (
    build_quality_consensus
)


class AlignmentChromatogramCanvas(tk.Frame):


    def __init__(
        self,
        parent,
        click_callback=None
    ):


        super().__init__(
            parent,
            relief="groove",
            borderwidth=2
        )


        self.click_callback = click_callback



        # =====================
        # Display settings
        # =====================

        self.name_width = 180

        self.base_width = 18

        self.row_height = 180



        # =====================
        # Data
        # =====================

        self.reads = []

        self.alignment = None

        self.maps = {}

        self.consensus = ""

        self.confidence = []


        # =====================
        # Canvas
        # =====================

        self.canvas = tk.Canvas(
            self,
            bg="white"
        )


        self.x_scroll = tk.Scrollbar(
            self,
            orient="horizontal",
            command=self.canvas.xview
        )


        self.y_scroll = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview
        )


        self.canvas.configure(
            xscrollcommand=self.x_scroll.set,
            yscrollcommand=self.y_scroll.set
        )


        self.y_scroll.pack(
            side="right",
            fill="y"
        )


        self.x_scroll.pack(
            side="bottom",
            fill="x"
        )


        self.canvas.pack(
            fill="both",
            expand=True
        )

        # =====================
        # Mouse click event
        # =====================

        self.canvas.bind(
            "<Button-1>",
            self.on_click
        )

    # ==================================================
    # Load reads
    # ==================================================

    def load_reads(
        self,
        reads
    ):


        self.reads = reads


        print(
            "Running MAFFT alignment..."
        )


        self.alignment = align_reads(
            reads
        )


        print(
            "Alignment finished."
        )


        self.create_mapping()


        self.draw()



    # ==================================================
    # Load existing alignment
    # ==================================================

    def load_alignment_reads(
        self,
        alignment,
        reads
    ):


        self.alignment = alignment

        self.reads = reads


        self.create_mapping()


        self.draw()



    # ==================================================
    # Create alignment -> trace mapping
    # ==================================================

    def create_mapping(self):


        self.maps = {}



        for record in self.alignment:


            name = record.id



            for read in self.reads:


                if read.filename == name:


                    self.maps[name] = (

                        alignment_to_trace_positions(

                            str(record.seq),

                            read

                        )

                    )


                    break
    # ==================================================
    # Draw alignment chromatogram
    # ==================================================

    def draw(self):


        self.canvas.delete(
            "all"
        )


        if self.alignment is None:

            return

        # =====================
        # Quality Consensus
        # =====================

        self.consensus, self.confidence = build_quality_consensus(

            self.reads,

            self.alignment

        )

        # =====================
        # Draw consensus
        # =====================

        consensus_y = 60


        self.canvas.create_text(

            5,

            consensus_y,

            text="Consensus",

            anchor="w",

            font=(

                "Courier",

                10,

                "bold"

            )

        )


        for i, base in enumerate(

            self.consensus

        ):


            x = self.trace_to_canvas_x(

                i + 1

            )


            self.canvas.create_text(

                x,

                consensus_y,

                text=base,

                font=(

                    "Courier",

                    10,

                    "bold"

                ),

                fill=self.base_color(

                    base

                )

            )

        for row, record in enumerate(
            self.alignment
        ):


            name = record.id


            read = None


            for r in self.reads:


                if r.filename == name:

                    read = r

                    break



            if read is None:

                continue



            aligned_seq = str(record.seq)


            mapping = self.maps.get(
                name
            )


            if mapping is None:

                continue



            y_base = (

                row *

                self.row_height

                +

                170

            )



            # =====================
            # Sample name
            # =====================

            self.canvas.create_text(

                5,

                y_base,

                text=name,

                anchor="w",

                font=(

                    "Courier",

                    10,

                    "bold"

                )

            )



            # =====================
            # Draw bases
            # =====================

            for col in range(

                1,

                len(aligned_seq)+1

            ):



                base = aligned_seq[
                    col-1
                ]



                # gap

                if base == "-":

                    continue



                trace_pos = mapping.get(
                    col
                )


                if trace_pos is None:

                    continue



                x = self.trace_to_canvas_x(

                    col

                )



                self.canvas.create_text(

                    x,

                    y_base-35,

                    text=base,

                    font=(

                        "Courier",

                        10,

                        "bold"

                    ),

                    fill=self.base_color(
                        base
                    )

                )



            # =====================
            # Draw trace
            # =====================

            self.draw_trace(

                read,

                mapping,

                y_base

            )



        bbox = self.canvas.bbox(
            "all"
        )


        if bbox:


            self.canvas.configure(
                scrollregion=bbox
            )




    # ==================================================
    # Alignment column -> canvas X
    # ==================================================

    def trace_to_canvas_x(
        self,
        alignment_column
    ):


        return (

            self.name_width

            +

            (

                alignment_column-1

            )

            *

            self.base_width

        )
    # ==================================================
    # Base color
    # ==================================================

    def base_color(
        self,
        base
    ):


        colors = {

            "A": "green",

            "T": "red",

            "G": "black",

            "C": "blue"

        }


        return colors.get(

            base.upper(),

            "gray"

        )



    # ==================================================
    # Draw chromatogram trace
    # ==================================================

    def draw_trace(
        self,
        read,
        mapping,
        y_base
    ):


        colors = {

            "A": "green",

            "T": "red",

            "G": "black",

            "C": "blue"

        }



        # ==================================
        # Use trimmed chromatogram
        # ==================================

        if hasattr(
            read,
            "trimmed_traces"
        ):

            traces = read.trimmed_traces

        else:

            traces = read.traces



        if len(traces["A"]) == 0:

            return



        # ==================================
        # Build trace points by alignment
        # ==================================

        for base, color in colors.items():


            trace = traces[base]


            points = []



            for col, trace_pos in mapping.items():


                #
                # gap
                #
                # alignment上で "-" の場合
                # trace_pos は None
                #
                if trace_pos is None:

                    if len(points) > 4:


                        self.canvas.create_line(

                            points,

                            fill=color,

                            width=1.3,

                            smooth=True

                        )


                    points = []


                    continue



                #
                # alignment座標
                #

                x = self.trace_to_canvas_x(

                    col

                )



                #
                # trace index
                #

                pos = int(
                    trace_pos
                )



                if pos >= len(trace):

                    continue



                signal = trace[pos]



                y = (

                    y_base

                    -

                    signal * 0.05

                )



                points.extend(

                    [

                        x,

                        y

                    ]

                )



            #
            # Draw remaining segment
            #

            if len(points) > 4:


                self.canvas.create_line(

                    points,

                    fill=color,

                    width=1.3,

                    smooth=True

                )

    # ==================================================
    # Alignment click event
    # ==================================================

    def on_click(
        self,
        event
    ):


        x = self.canvas.canvasx(
            event.x
        )

        y = self.canvas.canvasy(
            event.y
        )


        # row判定

        row = int(

            y
            /
            self.row_height

        )


        if row >= len(self.alignment):

            return



        record = list(
            self.alignment
        )[row]


        sample_name = record.id



        # alignment column

        if x < self.name_width:

            return



        column = int(

            (
                x
                -
                self.name_width

            )
            /
            self.base_width

        ) + 1



        sequence = str(
            record.seq
        )


        if column > len(sequence):

            return



        base = sequence[
            column-1
        ]



        trace_position = None



        if sample_name in self.maps:


            trace_position = self.maps[sample_name].get(

                column

            )



        print(
            "============================"
        )

        print(
            "Alignment click"
        )

        print(
            "Sample:",
            sample_name
        )

        print(
            "Alignment position:",
            column
        )

        print(
            "Trace position:",
            trace_position
        )

        print(
            "Base:",
            base
        )

        print(
            "============================"
        )



        if self.click_callback:


            self.click_callback(

                sample_name,

                trace_position,

                base

            )

    def goto_trace_position(
        self,
        sample_name,
        trace_position
    ):


        for name, mapping in self.maps.items():


            if name == sample_name:


                for col, pos in mapping.items():


                    if pos == trace_position:


                        x = self.trace_to_canvas_x(
                            col
                        )


                        self.canvas.xview_moveto(

                            x /
                            self.canvas.bbox("all")[2]

                        )


                        return