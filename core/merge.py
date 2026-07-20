from pathlib import Path
from Bio import SeqIO


def merge_fasta_files(
    input_dir,
    output_file
):
    """
    Merge multiple FASTA files into one FASTA file.

    Parameters
    ----------
    input_dir : str or Path
        Folder containing fasta files

    output_file : str or Path
        Output merged fasta filename

    Returns
    -------
    int
        Number of merged sequences
    """


    input_dir = Path(input_dir)
    output_file = Path(output_file)


    fasta_files = sorted(
        list(input_dir.glob("*.fas"))
        +
        list(input_dir.glob("*.fasta"))
    )


    if len(fasta_files) == 0:

        raise FileNotFoundError(
            "No FASTA files found"
        )


    records = []


    for fasta in fasta_files:

        for record in SeqIO.parse(
            fasta,
            "fasta"
        ):

            records.append(record)



    output_file.parent.mkdir(
        exist_ok=True
    )


    SeqIO.write(
        records,
        output_file,
        "fasta"
    )


    return len(records)



def merge_sequences(
    input_dir,
    output_file,
    mode="fasta"
):
    """
    Unified merge function.

    mode:
        fasta : merge existing fasta files
        ab1   : reserved for future AB1 pipeline
    """


    if mode == "fasta":

        count = merge_fasta_files(
            input_dir,
            output_file
        )


    elif mode == "ab1":

        raise NotImplementedError(
            "AB1 merge will be implemented with pipeline"
        )


    else:

        raise ValueError(
            "Unknown merge mode"
        )


    return {
        "output": str(output_file),
        "sequence_count": count
    }