import tkinter as tk


class SamplePanel(tk.Frame):

    def __init__(
        self,
        parent
    ):

        super().__init__(
            parent,
            width=250,
            relief="groove",
            borderwidth=2
        )


        self.pack_propagate(False)


        self.reads = []

        self.callback = None

        self.vars = []



        # =====================
        # Title
        # =====================

        self.label = tk.Label(
            self,
            text="Samples",
            font=(
                "Arial",
                14,
                "bold"
            )
        )

        self.label.pack(
            pady=5
        )

        # =====================
        # Selection buttons
        # =====================

        button_frame = tk.Frame(self)

        button_frame.pack(
            fill="x",
            padx=5,
            pady=(0, 5)
        )

        tk.Button(
            button_frame,
            text="All",
            command=self.select_all,
            width=4
        ).pack(
            side="left",
            padx=2
        )

        tk.Button(
            button_frame,
            text="None",
            command=self.clear_all,
            width=4
        ).pack(
            side="left",
            padx=2
        )

        tk.Button(
            button_frame,
            text="Invert",
            command=self.invert_selection,
            width=4
        ).pack(
            side="left",
            padx=2
        )

        # =====================
        # Scroll area
        # =====================

        self.canvas = tk.Canvas(
            self,
            bg="white"
        )


        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview
        )


        self.frame = tk.Frame(
            self.canvas
        )


        self.frame.bind(
            "<Configure>",
            lambda e:
            self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )


        self.canvas.create_window(
            (0,0),
            window=self.frame,
            anchor="nw"
        )


        self.canvas.configure(
            yscrollcommand=self.scrollbar.set
        )


        self.scrollbar.pack(
            side="right",
            fill="y"
        )


        self.canvas.pack(
            side="left",
            fill="both",
            expand=True
        )



    # ==================================================
    # Callback
    # ==================================================

    def set_callback(
        self,
        callback
    ):

        self.callback = callback



    # ==================================================
    # Update samples
    # ==================================================

    def update_samples(
        self,
        reads
    ):


        self.reads = reads


        for widget in self.frame.winfo_children():

            widget.destroy()


        self.vars = []



        for i, read in enumerate(reads):


            var = tk.BooleanVar()


            check = tk.Checkbutton(

                self.frame,

                text=read.filename,

                variable=var,

                anchor="w",

                font=(

                    "Courier",

                    10

                ),

                command=self.selection_changed

            )


            check.pack(

                fill="x",

                padx=5,

                pady=2

            )


            self.vars.append(

                var

            )



        # 初期状態
        for var in self.vars:

            var.set(True)


        self.selection_changed()



    # ==================================================
    # Selection changed
    # ==================================================

    def selection_changed(
        self
    ):


        if self.callback is None:

            return



        selected_reads = []



        for i, var in enumerate(self.vars):


            if var.get():

                selected_reads.append(

                    self.reads[i]

                )



        self.callback(

            selected_reads

        )

    # ==================================================
    # Select all
    # ==================================================

    def select_all(self):

        for var in self.vars:

            var.set(True)

        self.selection_changed()


    # ==================================================
    # Clear selection
    # ==================================================

    def clear_all(self):

        for var in self.vars:

            var.set(False)

        self.selection_changed()


    # ==================================================
    # Invert selection
    # ==================================================

    def invert_selection(self):

        for var in self.vars:

            var.set(
                not var.get()
            )

        self.selection_changed()