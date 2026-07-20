from core.ab1_reader import read_ab1
from core.trimming import trim_sequence
from core.exporter import save_fasta
from core.blast import blast_sequence
from core.report import save_blast_results
from core.quality import quality_report

import sys
import os


def run_pipeline(ab1_file):

    print("=== SangerFlow Pipeline ===")

    print("\n[1] Reading AB1...")
    sample = read_ab1(ab1_file)


    print("[2] Quality analysis...")
    report = quality_report(sample)

    print(report)


    print("\n[3] Trimming...")
    sample = trim_sequence(sample)

    print(
        f"Trimmed length: {len(sample.trimmed_sequence)} bp"
    )


    basename = os.path.splitext(
        os.path.basename(ab1_file)
    )[0]


    print("\n[4] Saving FASTA...")

    save_fasta(
        sample,
        f"{basename}_trimmed.fas"
    )


    print("\n[5] Running BLAST...")

    results = blast_sequence(
        sample.trimmed_sequence
    )


    print("\nTop hit:")
    print(results[0])


    print("\n[6] Saving reports...")

    files = save_blast_results(
        results,
        f"{basename}_BLAST"
    )


    print(files)

    print("\n=== Finished ===")



if __name__ == "__main__":

    if len(sys.argv) < 2:

        print(
            "Usage: python pipeline.py sample.ab1"
        )

        sys.exit()


    run_pipeline(
        sys.argv[1]
    )