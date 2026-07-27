import tkinter as tk
from tkinter import filedialog


class BlastDialog(tk.Toplevel):

    def __init__(self, parent):

        super().__init__(parent)


        self.title(
            "BLAST Settings"
        )

        self.resizable(
            False,
            False
        )


        self.result = None

        self.input_path = None



        # ==================================================
        # Target
        # ==================================================

        tk.Label(
            self,
            text="Target"
        ).pack(
            anchor="w",
            padx=10,
            pady=(10,0)
        )


        self.target_var = tk.StringVar(
            value="folder"
        )


        tk.Radiobutton(
            self,
            text="AB1 Folder",
            variable=self.target_var,
            value="folder"
        ).pack(
            anchor="w",
            padx=20
        )


        tk.Radiobutton(
            self,
            text="FASTA File",
            variable=self.target_var,
            value="fasta"
        ).pack(
            anchor="w",
            padx=20
        )



        # ==================================================
        # Input selection
        # ==================================================

        self.path_label = tk.Label(
            self,
            text="No input selected",
            width=50
        )

        self.path_label.pack(
            padx=10,
            pady=5
        )


        tk.Button(
            self,
            text="Select Input",
            command=self.select_input
        ).pack(
            pady=5
        )



        # ==================================================
        # Hits
        # ==================================================

        tk.Label(
            self,
            text="Top Hits"
        ).pack(
            anchor="w",
            padx=10,
            pady=(10,0)
        )


        self.hit_var = tk.IntVar(
            value=3
        )


        for text,value in [
            ("Top 3",3),
            ("Top 5",5),
            ("Top 10",10)
        ]:

            tk.Radiobutton(
                self,
                text=text,
                variable=self.hit_var,
                value=value
            ).pack(
                anchor="w",
                padx=20
            )



        # ==================================================
        # Database
        # ==================================================

        tk.Label(
            self,
            text="Database"
        ).pack(
            anchor="w",
            padx=10,
            pady=(10,0)
        )


        self.db_var = tk.StringVar(
            value="nt"
        )


        tk.Radiobutton(
            self,
            text="nt",
            variable=self.db_var,
            value="nt"
        ).pack(
            anchor="w",
            padx=20
        )


        tk.Radiobutton(
            self,
            text="refseq",
            variable=self.db_var,
            value="refseq"
        ).pack(
            anchor="w",
            padx=20
        )



        # ==================================================
        # Export
        # ==================================================

        self.export_excel = tk.BooleanVar(
            value=True
        )


        tk.Checkbutton(
            self,
            text="Export Excel",
            variable=self.export_excel
        ).pack(
            anchor="w",
            padx=10,
            pady=10
        )



        # ==================================================
        # Run
        # ==================================================

        tk.Button(
            self,
            text="Run BLAST",
            command=self.run
        ).pack(
            pady=15
        )




    # ==================================================
    # Select input
    # ==================================================

    def select_input(self):


        target = self.target_var.get()



        if target == "folder":


            path = filedialog.askdirectory()



        else:


            path = filedialog.askopenfilename(

                filetypes=[

                    (
                        "FASTA files",
                        "*.fas *.fasta"
                    )

                ]

            )



        if path:


            self.input_path = path


            self.path_label.config(

                text=path

            )




    # ==================================================
    # Run
    # ==================================================

    def run(self):


        if self.input_path is None:


            return



        save_path = None



        if self.export_excel.get():


            save_path = filedialog.asksaveasfilename(

                title="Save BLAST Report",

                defaultextension=".xlsx",

                filetypes=[

                    (
                        "Excel files",
                        "*.xlsx"
                    )

                ]

            )


            if not save_path:


                return




        self.result = {


            "target":
                self.target_var.get(),


            "input_path":
                self.input_path,


            "hits":
                self.hit_var.get(),


            "database":
                self.db_var.get(),


            "excel":
                self.export_excel.get(),


            "save_path":
                save_path

        }



        self.destroy()