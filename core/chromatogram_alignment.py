import subprocess
import shutil
from Bio import AlignIO
from io import StringIO

from tools.mafft_tool import resolve_mafft_executable



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

def align_reads(
    reads,
    *,
    strategy="Auto",
    gap_opening_penalty=None,
    offset=None,
    maxiterate=None,
    adjust_direction=False,
    mafft_executable=None,
):
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


    strategy_options = {
        "Auto": (["--auto"], None),
        "FFT-NS-2": (["--retree", "2"], 0),
        "FFT-NS-i": (["--retree", "2"], 1000),
        "L-INS-i": (["--localpair"], 1000),
        "G-INS-i": (["--globalpair"], 1000),
    }
    if strategy not in strategy_options:
        raise ValueError("unsupported MAFFT strategy")
    strategy_flags, strategy_maxiterate = strategy_options[strategy]
    resolved_executable = resolve_mafft_executable(mafft_executable, which=shutil.which)
    command = [resolved_executable, *strategy_flags]
    if gap_opening_penalty is not None:
        command.extend(["--op", str(float(gap_opening_penalty))])
    if offset is not None:
        command.extend(["--ep", str(float(offset))])
    resolved_maxiterate = strategy_maxiterate if maxiterate is None else int(maxiterate)
    if resolved_maxiterate is not None:
        command.extend(["--maxiterate", str(resolved_maxiterate)])
    if adjust_direction:
        command.append("--adjustdirection")
    command.append("-")
    result = subprocess.run(

        command,

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

def align_fasta(filepath, *, mafft_executable=None):
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



    resolved_executable = resolve_mafft_executable(mafft_executable, which=shutil.which)
    result = subprocess.run(

        [

            resolved_executable,

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
