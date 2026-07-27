import tkinter as tk


class ButtonBar(tk.Frame):

    def __init__(self, parent, callbacks):

        super().__init__(parent)


        self.pack(
            pady=5
        )


        buttons = [

            (
                "Open AB1",
                callbacks["open_file"]
            ),

            (
                "Open Folder",
                callbacks["open_folder"]
            ),

            (
                "Open Alignment",
                callbacks["open_alignment"]
            ),

            (
                "Align Chromatograms",
                callbacks["align_chromatograms"]
            ),

            (
                "Show Trim Region",
                callbacks["toggle_trim_region"]
            ),

            (
                "BLAST",
                callbacks["open_blast_dialog"]
            ),

            (
                "Quality Report",
                callbacks["open_quality_panel"]
            )

        ]


        for text, command in buttons:


            button = tk.Button(

                self,

                text=text,

                command=command,

                width=15

            )


            button.pack(

                side="left",

                padx=5

            )