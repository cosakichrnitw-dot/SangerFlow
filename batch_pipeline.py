from pathlib import Path

from openpyxl import Workbook

from core.ab1_reader import read_ab1
from core.trimming import trim_sequence
from core.exporter import save_fasta
from core.blast import blast_sequence
from core.quality import quality_report
from core.waveform_qc import waveform_qc


INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")
FASTA_DIR = OUTPUT_DIR / "fasta"


def create_summary_excel(results, filename):

    wb = Workbook()


    # =========================
    # BLAST Summary
    # =========================

    ws1 = wb.active
    ws1.title = "BLAST Summary"


    blast_headers = [
        "Sample",
        "Species",
        "Identity (%)",
        "Coverage (%)",
        "Alignment length",
        "E-value"
    ]


    ws1.append(
        blast_headers
    )


    for r in results:

        if r["species"] != "":

            ws1.append([
                r["sample"],
                r["species"],
                r["identity"],
                r["coverage"],
                r["alignment_length"],
                r["e_value"]
            ])



    # =========================
    # QC Summary
    # =========================

    ws2 = wb.create_sheet(
        "QC Summary"
    )


    qc_headers = [
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


    ws2.append(
        qc_headers
    )


    for r in results:

        ws2.append([

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

        ])



    # =========================
    # Auto column width
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





def run_batch():

    OUTPUT_DIR.mkdir(exist_ok=True)
    FASTA_DIR.mkdir(exist_ok=True)


    summary = []

    failed = []


    files = sorted(
        INPUT_DIR.glob("*.ab1")
    )


    print(
        f"{len(files)} AB1 files found"
    )


    for filepath in files:

        sample_name = filepath.stem


        print("\n====================")
        print(f"Processing: {sample_name}")


        try:

            # Read AB1

            sample = read_ab1(
                str(filepath)
            )


            # Waveform QC

            qc = waveform_qc(
                sample
            )


            # Basic quality

            q = quality_report(
                sample
            )


            print(
                "QC:",
                qc["status"]
            )


            # FAIL samples skip BLAST

            if qc["status"] == "FAIL":

                summary.append({

                    "sample": sample_name,
                    "qc_status": qc["status"],
                    "qc_problems": "; ".join(
                        qc["problems"]
                    ),

                    "raw_length": len(sample.sequence),
                    "trim_length": "",

                    "average_quality": qc["average_quality"],
                    "q20_rate": qc["q20_rate"],
                    "q30_rate": qc["q30_rate"],

                    "longest_q30_block": qc["longest_q30_block"],

                    "five_prime_quality": qc["five_prime_quality"],
                    "three_prime_quality": qc["three_prime_quality"],

                    "species": "",
                    "identity": "",
                    "coverage": "",
                    "alignment_length": "",
                    "e_value": ""
                })


                print(
                    "SKIP BLAST:",
                    qc["problems"]
                )

                continue



            # Trimming

            sample = trim_sequence(
                sample
            )


            trim_length = len(
                sample.trimmed_sequence
            )


            if trim_length < 100:

                raise ValueError(
                    "Trimmed sequence too short"
                )


            # Save FASTA

            save_fasta(
                sample,
                str(
                    FASTA_DIR /
                    f"{sample_name}_trimmed.fas"
                )
            )


            # BLAST

            blast = blast_sequence(
                sample.trimmed_sequence
            )


            top = blast[0]


            summary.append({

                "sample": sample_name,

                "qc_status": qc["status"],

                "qc_problems": "; ".join(
                    qc["problems"]
                ),


                "raw_length": q["length"],

                "trim_length": trim_length,


                "average_quality": qc["average_quality"],

                "q20_rate": qc["q20_rate"],

                "q30_rate": qc["q30_rate"],


                "longest_q30_block": qc["longest_q30_block"],

                "five_prime_quality": qc["five_prime_quality"],

                "three_prime_quality": qc["three_prime_quality"],


                "species": top["species"],

                "identity": top["identity"],

                "coverage": top["coverage"],

                "alignment_length": top["alignment_length"],

                "e_value": top["e_value"]

            })


            print(
                "OK:",
                top["species"],
                top["identity"]
            )


        except Exception as e:


            print(
                "FAILED:",
                e
            )


            failed.append({

                "sample": sample_name,

                "error": str(e)

            })


    # Save Excel

    create_summary_excel(
        summary,
        OUTPUT_DIR / "summary.xlsx"
    )


    print("\nFinished")


    pass_count = sum(
        r["qc_status"] == "PASS"
        for r in summary
    )


    warning_count = sum(
        r["qc_status"] == "WARNING"
        for r in summary
    )


    fail_count = sum(
        r["qc_status"] == "FAIL"
        for r in summary
    )


    print(
        f"PASS: {pass_count}"
    )

    print(
        f"WARNING: {warning_count}"
    )

    print(
        f"FAIL: {fail_count}"
    )



if __name__ == "__main__":

    run_batch()