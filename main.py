from pathlib import Path

from core.pipeline import process_folder
from core.report import create_summary_excel
from core.merge import merge_sequences



INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")

FASTA_DIR = OUTPUT_DIR / "fasta"

REPORT_FILE = OUTPUT_DIR / "summary.xlsx"

MERGED_FASTA = OUTPUT_DIR / "merged.fas"



def main():

    print("====================")
    print("      SangerFlow")
    print("====================")


    OUTPUT_DIR.mkdir(
        exist_ok=True
    )


    print("\nInput folder:")
    print(INPUT_DIR)


    print("\nProcessing AB1 files...\n")


    results = process_folder(
        INPUT_DIR,
        FASTA_DIR
    )


    print("\nGenerating Excel report...")


    create_summary_excel(
        results,
        REPORT_FILE
    )


    print(
        "Saved:",
        REPORT_FILE
    )


    print("\nMerging FASTA...")


    merge_result = merge_sequences(
        FASTA_DIR,
        MERGED_FASTA
    )


    print(
        f"Merged {merge_result['sequence_count']} sequences"
    )


    print("\n====================")
    print("Finished")
    print("====================")


    print("\nSummary:")


    for r in results:

        print(
            r["sample"],
            r["qc_status"],
            r["species"]
        )



if __name__ == "__main__":

    main()