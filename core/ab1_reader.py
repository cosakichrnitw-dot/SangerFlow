from Bio import SeqIO


def read_ab1(filepath):
    """
    Read Sanger sequencing AB1 file.

    Returns
    -------
    dict
        sequence, quality and chromatogram traces
    """

    record = SeqIO.read(filepath, "abi")

    sequence = str(record.seq)

    quality = record.letter_annotations["phred_quality"]

    # ABI chromatogram data
    abi_data = record.annotations["abif_raw"]

    traces = {
        "G": abi_data["DATA9"],
        "A": abi_data["DATA10"],
        "T": abi_data["DATA11"],
        "C": abi_data["DATA12"],
    }

    return {
        "sequence": sequence,
        "quality": quality,
        "length": len(sequence),
        "traces": traces
    }