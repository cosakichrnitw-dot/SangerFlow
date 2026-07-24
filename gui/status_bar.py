import tkinter as tk


class StatusBar(tk.Frame):

    def __init__(self, parent):

        super().__init__(
            parent,
            relief="sunken",
            borderwidth=1
        )

        self.label = tk.Label(

            self,

            text="Ready",

            anchor="w"

        )

        self.label.pack(

            fill="x",

            padx=5

        )

    def set_text(
        self,
        text
    ):

        self.label.config(
            text=text
        )