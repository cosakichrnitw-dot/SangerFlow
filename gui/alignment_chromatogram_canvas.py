# gui/alignment_chromatogram_canvas.py

import tkinter as tk


from core.chromatogram_alignment import align_reads

from core.alignment_mapper import (
    alignment_to_trace_positions
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



            print(
                "ALIGNMENT DEBUG:",
                name,
                aligned_seq[:100]
            )



            mapping = self.maps.get(
                name
            )


            if mapping is None:

                continue



            y_base = (

                row *

                self.row_height

                +

                100

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