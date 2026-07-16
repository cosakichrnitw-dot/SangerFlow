from Bio import SeqIO


def read_ab1(filepath):
    """
    Read Sanger sequencing AB1 file.

    Parameters
    ----------
    filepath : str
        Path to .ab1 file

    Returns
    -------
    dict
        sequence information
    """

    record = SeqIO.read(filepath, "abi")

    sequence = str(record.seq)

    quality = record.letter_annotations["phred_quality"]

    return {
        "sequence": sequence,
        "quality": quality,
        "length": len(sequence)
    }