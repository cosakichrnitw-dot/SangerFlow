import tkinter as tk


class SamplePanel(tk.Frame):

    def __init__(self, parent):

        super().__init__(
            parent,
            width=250,
            relief="groove",
            borderwidth=2
        )


        self.pack_propagate(False)


        # title

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


        # list

        self.listbox = tk.Listbox(
            self,
            font=(
                "Courier",
                11
            )
        )


        self.listbox.pack(
            fill="both",
            expand=True,
            padx=5,
            pady=5
        )



    def update_samples(
        self,
        reads
    ):

        self.listbox.delete(
            0,
            tk.END
        )


        for read in reads:

            self.listbox.insert(
                tk.END,
                read.filename
            )