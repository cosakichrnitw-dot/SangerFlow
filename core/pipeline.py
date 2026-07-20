from pathlib import Path

from core.ab1_reader import read_ab1
from core.trimming import trim_sequence
from core.exporter import save_fasta
from core.blast import blast_sequence
from core.quality import quality_report
from core.waveform_qc import waveform_qc


def process_file(filepath, fasta_dir=None):
    """
    Process one AB1 file.

    Returns
    -------
    dict
        Analysis result
    """

    filepath = Path(filepath)

    sample_name = filepath.stem


    # =====================
    # Read AB1
    # =====================

    sample = read_ab1(
        str(filepath)
    )


    # =====================
    # QC
    # =====================

    qc = waveform_qc(
        sample
    )


    q = quality_report(
        sample
    )


    result = {

        "sample": sample_name,

        "qc_status": qc["status"],

        "qc_problems": "; ".join(
            qc["problems"]
        ),

        "raw_length": q["length"],

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

    }


    # =====================
    # Skip bad reads
    # =====================

    if qc["status"] == "FAIL":

        return result



    # =====================
    # Trim
    # =====================

    sample = trim_sequence(
        sample
    )


    trim_length = len(
        sample.trimmed_sequence
    )


    result["trim_length"] = trim_length



    if trim_length < 100:

        result["qc_status"] = "FAIL"

        result["qc_problems"] += "; Trimmed sequence too short"

        return result



    # =====================
    # FASTA export
    # =====================

    if fasta_dir:

        fasta_dir = Path(fasta_dir)

        fasta_dir.mkdir(
            exist_ok=True
        )


        save_fasta(
            sample,
            str(
                fasta_dir /
                f"{sample_name}_trimmed.fas"
            )
        )



    # =====================
    # BLAST
    # =====================

    blast = blast_sequence(
        sample.trimmed_sequence
    )


    top = blast[0]


    result["species"] = top["species"]

    result["identity"] = top["identity"]

    result["coverage"] = top["coverage"]

    result["alignment_length"] = top["alignment_length"]

    result["e_value"] = top["e_value"]



    return result




def process_folder(folder, fasta_dir=None):

    folder = Path(folder)

    files = sorted(
        folder.glob("*.ab1")
    )

    results = []

    for filepath in files:

        try:

            result = process_file(
                filepath,
                fasta_dir
            )

            results.append(result)

        except Exception as e:

            results.append({
                "sample": filepath.stem,
                "error": str(e)
            })

    return results