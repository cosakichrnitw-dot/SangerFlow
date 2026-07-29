import subprocess
from Bio import AlignIO
from io import StringIO



# ==================================================
# Create FASTA from AB1 reads
# ==================================================

def make_alignment_fasta(reads):


    fasta = ""


    for read in reads:


        fasta += (

            f">{read.filename}\n"

            f"{read.trimmed_sequence}\n"

        )


    return fasta




# ==================================================
# Run MAFFT
# ==================================================

def align_reads(reads):
    """
    Align trimmed AB1 sequences using MAFFT.
    """


    if len(reads) == 0:

        raise ValueError(
            "No AB1 reads supplied for alignment."
        )



    fasta = make_alignment_fasta(

        reads

    )


    result = subprocess.run(

        [

            "mafft",

            "--auto",

            "-"

        ],

        input=fasta,

        text=True,

        capture_output=True

    )

    if result.returncode != 0:

        raise RuntimeError(

            result.stderr

        )


    alignment = AlignIO.read(

        StringIO(result.stdout),

        "fasta"

    )


    return alignment

def convert_alignment_to_dict(alignment):


    result = {}


    for record in alignment:


        result[record.id] = str(
            record.seq
        )


    return result

# ==================================================
# Align existing FASTA file
# ==================================================

def align_fasta(
    filepath
):
    """
    Align existing FASTA sequences using MAFFT.

    Parameters
    ----------
    filepath : str
        FASTA file path

    Returns
    -------
    MultipleSeqAlignment
        MAFFT alignment result
    """


    with open(
        filepath,
        "r"
    ) as f:

        fasta = f.read()



    print(
        "========== FASTA MAFFT INPUT =========="
    )


    print(
        fasta
    )


    print(
        "========================================"
    )



    result = subprocess.run(

        [

            "mafft",

            "--auto",

            "-"

        ],

        input=fasta,

        text=True,

        capture_output=True

    )


    if result.returncode != 0:

        raise RuntimeError(

            result.stderr

        )



    alignment = AlignIO.read(

        StringIO(result.stdout),

        "fasta"

    )


    return alignment