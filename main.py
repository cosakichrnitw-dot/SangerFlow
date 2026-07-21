from pathlib import Path

from core.pipeline import process_folder
from core.report import create_summary_excel
from core.merge import merge_sequences


OUTPUT_DIR = Path("output")


def run_analysis(
    input_folder,
    callback=None
):
    """
    Execute SangerFlow workflow.
    GUI calls this function.
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


    # ---------------------
    # AB1 processing
    # ---------------------

    if callback:
        callback("Processing AB1 files...")
    else:
        print("\nProcessing AB1 files...\n")


    results = process_folder(
        input_folder,
        FASTA_DIR,
        callback=callback
    )


    # ---------------------
    # Excel report
    # ---------------------

    if callback:
        callback("Generating Excel report...")
    else:
        print("\nGenerating Excel report...")


    create_summary_excel(
        results,
        REPORT_FILE
    )


    message = f"Saved: {REPORT_FILE}"

    if callback:
        callback(message)
    else:
        print(message)



    # ---------------------
    # FASTA merge
    # ---------------------

    if callback:
        callback("Merging FASTA...")
    else:
        print("\nMerging FASTA...")


    merge_result = merge_sequences(
        FASTA_DIR,
        MERGED_FASTA
    )


    message = (
        f"Merged {merge_result['sequence_count']} sequences"
    )


    if callback:
        callback(message)
    else:
        print(message)



    if callback:
        callback("Analysis complete.")


    return results



def main():

    print("====================")
    print("      SangerFlow")
    print("====================")


    INPUT_DIR = Path("input")


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