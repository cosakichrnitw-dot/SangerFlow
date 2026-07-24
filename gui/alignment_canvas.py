import tkinter as tk


class AlignmentCanvas(tk.Frame):


    def __init__(
        self,
        parent
    ):

        super().__init__(parent)



        # =====================
        # Layout
        # =====================

        self.name_width = 150

        self.base_width = 15

        self.row_height = 25


        self.alignment = {}



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



        # Base colors

        self.base_colors = {

            "A": "green",

            "C": "blue",

            "G": "black",

            "T": "red",

            "-": "gray"

        }



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


        max_length = max(

            len(seq)

            for seq in self.alignment.values()

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

                    text=str(i+1),

                    font=(

                        "Courier",

                        8

                    )

                )



                self.canvas.create_line(

                    x,

                    ruler_y + 5,

                    x,

                    ruler_y + 10

                )



        # =====================
        # Alignment
        # =====================


        start_y = 50



        for row, name in enumerate(names):


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



                self.canvas.create_text(

                    x,

                    y,

                    text=base,

                    fill=self.base_colors.get(

                        base,

                        "black"

                    ),

                    font=(

                        "Courier",

                        11,

                        "bold"

                    )

                )



        # Scroll area


        width = (

            self.name_width

            +

            max_length * self.base_width

        )


        height = (

            start_y

            +

            len(names) * self.row_height

        )



        self.canvas.config(

            scrollregion=(

                0,

                0,

                width,

                height

            )

        )