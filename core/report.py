import csv
from openpyxl import Workbook
import os


def save_blast_results(
        results,
        filename="blast_results"
):

    """
    Save BLAST results as CSV and Excel.

    Parameters
    ----------
    results : list
        BLAST result dictionaries

    filename : str
        output filename without extension
    """


    os.makedirs(
        "output",
        exist_ok=True
    )


    csv_path = (
        f"output/{filename}.csv"
    )

    xlsx_path = (
        f"output/{filename}.xlsx"
    )


    headers = [
        "Species",
        "Identity (%)",
        "Coverage (%)",
        "Alignment length",
        "E-value",
        "Title"
    ]


    # =====================
    # CSV
    # =====================

    with open(
        csv_path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.writer(f)

        writer.writerow(headers)


        for r in results:

            writer.writerow(
                [
                    r["species"],
                    r["identity"],
                    r["coverage"],
                    r["alignment_length"],
                    r["e_value"],
                    r["title"]
                ]
            )


    # =====================
    # Excel
    # =====================

    wb = Workbook()

    ws = wb.active

    ws.title = "BLAST Results"


    ws.append(headers)


    for r in results:

        ws.append(
            [
                r["species"],
                r["identity"],
                r["coverage"],
                r["alignment_length"],
                r["e_value"],
                r["title"]
            ]
        )


    # Column width adjustment

    for column in ws.columns:

        max_length = 0

        column_letter = column[0].column_letter


        for cell in column:

            if cell.value:

                max_length = max(
                    max_length,
                    len(str(cell.value))
                )


        ws.column_dimensions[
            column_letter
        ].width = min(
            max_length + 3,
            60
        )


    wb.save(
        xlsx_path
    )


    return {
        "csv": csv_path,
        "xlsx": xlsx_path
    }