from pathlib import Path


from core.ab1_reader import read_ab1

from core.quality import (
    calculate_hq_percent,
    quality_report
)

from core.blast import blast_folder

from core.blast_exporter import (
    export_blast_excel
)



# ==================================================
# Run BLAST Folder Controller
# ==================================================

def run_blast_folder(
    folder,
    save_path,
    hits=3,
    database="nt"
):


    reads = []

    quality_results = []



    print(
        "Loading AB1 files..."
    )



    for filepath in sorted(

        Path(folder).glob("*.ab1")

    ):


        try:


            read = read_ab1(

                filepath

            )


            reads.append(

                read

            )



            report = quality_report(

                read

            )


            read.hq_percent = calculate_hq_percent(

                read

            )


            report["hq_percent"] = (

                read.hq_percent

            )


            quality_results.append(

                report

            )



        except Exception as e:


            print(

                f"Failed loading {filepath}"

            )


            print(e)



    if len(reads) == 0:

        raise ValueError(
            "No AB1 files found."
        )



    print(

        f"{len(reads)} sequences loaded."

    )



    # =============================
    # BLAST
    # =============================

    blast_results = blast_folder(

        reads,

        database=database,

        max_hits=hits

    )



    print(

        "BLAST completed."

    )



    # =============================
    # Excel Export
    # =============================

    export_blast_excel(

        blast_results,

        quality_results,

        save_path

    )


    print(

        f"Saved: {save_path}"

    )


    return save_path