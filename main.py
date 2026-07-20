from pathlib import Path

from core.pipeline import process_folder
from core.report import create_summary_excel
from core.merge import merge_sequences



OUTPUT_DIR = Path("output")



def run_analysis(input_folder):
    """
    Execute SangerFlow workflow.

    This function will be called from GUI.
    """


    input_folder = Path(input_folder)


    FASTA_DIR = OUTPUT_DIR / "fasta"

    REPORT_FILE = OUTPUT_DIR / "summary.xlsx"

    MERGED_FASTA = OUTPUT_DIR / "merged.fas"



    OUTPUT_DIR.mkdir(
        exist_ok=True
    )

    FASTA_DIR.mkdir(
        exist_ok=True
    )



    print("\nProcessing AB1 files...\n")


    results = process_folder(
        input_folder,
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



    return results




def main():


    print("====================")
    print("      SangerFlow")
    print("====================")


    INPUT_DIR = Path("input")


    print("\nInput folder:")
    print(INPUT_DIR)



    results = run_analysis(
        INPUT_DIR
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