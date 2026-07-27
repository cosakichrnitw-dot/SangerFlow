import tkinter as tk

from core.consensus import build_consensus
from core.alignment_stats import alignment_summary



class AlignmentCanvas(tk.Frame):


    def __init__(
        self,
        parent,
        click_callback=None
    ):

        super().__init__(parent)
        self.click_callback = click_callback



        # =====================
        # Layout
        # =====================

        self.name_width = 150

        self.base_width = 15

        self.row_height = 25


        self.alignment = {}
        self.consensus = ""



        # =====================
        # Base colors
        # =====================

        self.base_colors = {

            "A": "green",

            "C": "blue",

            "G": "black",

            "T": "red",

            "-": "gray",

            "N": "purple"

        }



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
        # Canvas
        # =====================

        self.canvas = tk.Canvas(

            self,

            bg="white",

            xscrollcommand=self.h_scrollbar.set,

            yscrollcommand=self.v_scrollbar.set

        )


        self.canvas.pack(

            fill="both",

            expand=True

        )



        self.h_scrollbar.config(

            command=self.canvas.xview

        )


        self.v_scrollbar.config(

            command=self.canvas.yview

        )

        # =====================
        # Mouse click event
        # =====================

        self.canvas.bind(
            "<Button-1>",
            self.on_click
        )



    # ==================================================
    # Load FASTA alignment
    # ==================================================

    def load_alignment(

        self,

        filepath

    ):


        self.alignment = {}



        name = None

        sequence = []



        with open(

            filepath,

            "r"

        ) as f:



            for line in f:



                line = line.strip()



                if not line:

                    continue



                if line.startswith(">"):



                    if name is not None:

                        self.alignment[name] = "".join(sequence)



                    name = line[1:]

                    sequence = []



                else:


                    sequence.append(

                        line.upper()

                    )



            if name is not None:

                self.alignment[name] = "".join(sequence)



        self.draw()

    # ==================================================
    # Draw alignment
    # ==================================================

    def draw(self):


        self.canvas.delete(

            "all"

        )



        if len(self.alignment) == 0:

            return



        names = list(

            self.alignment.keys()

        )


        sequences = list(

            self.alignment.values()

        )


        consensus = build_consensus(

            sequences

        )

        self.consensus = consensus

        stats = alignment_summary(

            self.alignment,

        )


        max_length = max(

            len(seq)

            for seq in sequences

        )

        # =====================
        # Alignment information
        # =====================

        info_text = (

            f"Sequences: {stats['sequence_count']}    "

            f"Length: {stats['alignment_length']} bp    "

            f"Variable sites: {stats['variable_sites']}"

        )


        self.canvas.create_text(

            10,

            5,

            text=info_text,

            anchor="w",

            font=(

                "Courier",

                10,

                "bold"

            )

        )

        # =====================
        # Position ruler
        # =====================

        ruler_y = 20



        for i in range(

            max_length

        ):


            x = (

                self.name_width

                +

                i * self.base_width

            )



            if i % 10 == 0:


                self.canvas.create_text(

                    x,

                    ruler_y,

                    text=str(i + 1),

                    font=(

                        "Courier",

                        8

                    )

                )


                self.canvas.create_line(

                    x,

                    ruler_y + 5,

                    x,

                    ruler_y + 12

                )



        # =====================
        # Consensus row
        # =====================

        consensus_y = 55



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

            consensus

        ):


            x = (

                self.name_width

                +

                i * self.base_width

            )



            self.canvas.create_text(

                x,

                consensus_y,

                text=base,

                fill=self.base_colors.get(

                    base,

                    "black"

                ),

                font=(

                    "Courier",

                    10,

                    "bold"

                )

            )



        # =====================
        # Alignment rows
        # =====================


        start_y = 90



        for row, name in enumerate(

            names

        ):


            y = (

                start_y

                +

                row * self.row_height

            )



            # Sample name


            self.canvas.create_text(

                5,

                y,

                text=name,

                anchor="w",

                font=(

                    "Courier",

                    10,

                    "bold"

                )

            )



            seq = self.alignment[name]



            for i, base in enumerate(seq):


                base = base.upper()



                x = (

                    self.name_width

                    +

                    i * self.base_width

                )



                # ---------------------
                # Consensus comparison
                # ---------------------

                if i < len(consensus):


                    if base == consensus[i]:

                        display_base = "."


                        color = "gray"



                    else:


                        display_base = base


                        color = self.base_colors.get(

                            base,

                            "black"

                        )


                else:


                    display_base = base

                    color = self.base_colors.get(

                        base,

                        "black"

                    )



                self.canvas.create_text(

                    x,

                    y,

                    text=display_base,

                    fill=color,

                    font=(

                        "Courier",

                        11,

                        "bold"

                    )

                )



        # =====================
        # Scroll region
        # =====================


        width = (

            self.name_width

            +

            max_length * self.base_width

            +

            50

        )


        height = (

            start_y

            +

            len(names) * self.row_height

            +

            30

        )


        self.canvas.config(

            scrollregion=(

                0,

                0,

                width,

                height

            )

        )


    # ==================================================
    # Alignment click event
    # ==================================================

    def on_click(
        self,
        event
    ):


        # Canvas coordinates
        x = self.canvas.canvasx(
            event.x
        )

        y = self.canvas.canvasy(
            event.y
        )


        # Alignment rows start here
        start_y = 90


        if y < start_y:

            return


        row = int(

            (y - start_y)

            /

            self.row_height

        )


        names = list(

            self.alignment.keys()

        )


        if row >= len(names):

            return


        sample_name = names[row]


        if x < self.name_width:

            return


        column = int(

            (x - self.name_width)

            /

            self.base_width

        )


        sequence = self.alignment[

            sample_name

        ]


        if column >= len(sequence):

            return


        base = sequence[column]


        print(
            "Clicked:"
        )

        print(
            "Sample:",
            sample_name
        )

        print(
            "Alignment position:",
            column + 1
        )

        print(
            "Base:",
            base
        )

        if self.click_callback:

            self.click_callback(

                sample_name,

                column + 1,

                base

            )