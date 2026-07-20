from openpyxl import Workbook
from pathlib import Path


def create_summary_excel(results, filename):
    """
    Create Excel summary report.
    """

    filename = Path(filename)

    filename.parent.mkdir(
        exist_ok=True
    )


    wb = Workbook()


    # =========================
    # BLAST Summary
    # =========================

    ws1 = wb.active
    ws1.title = "BLAST Summary"


    ws1.append(
        [
            "Sample",
            "Species",
            "Identity (%)",
            "Coverage (%)",
            "Alignment length",
            "E-value"
        ]
    )


    for r in results:

        if r.get("species", ""):

            ws1.append(
                [
                    r["sample"],
                    r["species"],
                    r["identity"],
                    r["coverage"],
                    r["alignment_length"],
                    r["e_value"]
                ]
            )


    # =========================
    # QC Summary
    # =========================

    ws2 = wb.create_sheet(
        "QC Summary"
    )


    ws2.append(
        [
            "Sample",
            "QC Status",
            "QC Problems",
            "Raw length",
            "Trim length",
            "Average Quality",
            "Q20 (%)",
            "Q30 (%)",
            "Longest Q30 block",
            "5' Quality",
            "3' Quality"
        ]
    )


    for r in results:

        ws2.append(
            [
                r["sample"],
                r["qc_status"],
                r["qc_problems"],
                r["raw_length"],
                r["trim_length"],
                r["average_quality"],
                r["q20_rate"],
                r["q30_rate"],
                r["longest_q30_block"],
                r["five_prime_quality"],
                r["three_prime_quality"]
            ]
        )


    # =========================
    # Column width
    # =========================

    for ws in [ws1, ws2]:

        for column in ws.columns:

            max_length = 0

            letter = column[0].column_letter

            for cell in column:

                if cell.value:

                    max_length = max(
                        max_length,
                        len(str(cell.value))
                    )


            ws.column_dimensions[letter].width = min(
                max_length + 3,
                40
            )


    wb.save(filename)