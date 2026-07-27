from pathlib import Path


def save_fasta(
    sample,
    output_path,
    use_trimmed=True
):
    """
    Save Sanger sequence as FASTA file.

    Parameters
    ----------
    sample : SangerRead
        Sanger read object

    output_path : str
        Output fasta path

    use_trimmed : bool
        Save trimmed sequence if True
    """

    if use_trimmed:
        sequence = sample.trimmed_sequence
    else:
        sequence = sample.sequence


    if not sequence:
        raise ValueError(
            "Sequence is empty"
        )


    name = Path(sample.filename).stem


    fasta_name = (
        f">{name}_trimmed"
        if use_trimmed
        else f">{name}"
    )


    with open(output_path, "w") as f:

        f.write(fasta_name + "\n")

        # FASTA convention:
        # line length 60-80 bp

        for i in range(0, len(sequence), 60):

            f.write(
                sequence[i:i+60] + "\n"
            )

def export_consensus_fasta(
    consensus,
    filepath,
    name="Consensus"
):
    """
    Export consensus sequence as FASTA.
    """


    with open(
        filepath,
        "w"
    ) as f:


        f.write(
            f">{name}\n"
        )


        # FASTA standard:
        # 60 bp lines

        for i in range(
            0,
            len(consensus),
            60
        ):

            f.write(

                consensus[i:i+60]

                +

                "\n"

            )