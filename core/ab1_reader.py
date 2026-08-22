from Bio import SeqIO

from core.path_utils import source_filename

from core.models import SangerRead


def read_ab1(filepath):
    """
    Read ABI chromatogram file and return SangerRead object.
    """

    record = SeqIO.read(filepath, "abi")

    abi = record.annotations["abif_raw"]

    # Chromatogram trace data
    traces = {
        "G": abi["DATA9"],
        "A": abi["DATA10"],
        "T": abi["DATA11"],
        "C": abi["DATA12"],
    }

    # Base peak positions
    if "PLOC2" in abi:
        positions = abi["PLOC2"]
    else:
        positions = abi["PLOC1"]

    sequence = str(record.seq)

    quality = record.letter_annotations["phred_quality"]

    # Average quality
    average_quality = sum(quality) / len(quality)


    sample = SangerRead(
        filename=source_filename(filepath),
        sequence=sequence,
        quality=quality,
        traces=traces,
        base_positions=positions,
        average_quality=average_quality,
    )

    return sample
