from collections import Counter


# ==================================================
# Build consensus sequence
# ==================================================

def build_consensus(sequences):
    """
    Build majority-rule consensus sequence.

    Parameters
    ----------
    sequences : list[str]
        Aligned sequences (same length)

    Returns
    -------
    str
        Consensus sequence
    """

    if len(sequences) == 0:
        return ""

    length = len(sequences[0])

    consensus = []

    for i in range(length):

        column = []

        for seq in sequences:

            if i < len(seq):

                base = seq[i].upper()

                if base != "-":
                    column.append(base)

        # all gaps

        if len(column) == 0:
            consensus.append("-")
            continue

        counts = Counter(column)

        most_common = counts.most_common()

        # tie

        if len(most_common) > 1:

            if most_common[0][1] == most_common[1][1]:

                consensus.append("N")
                continue

        consensus.append(most_common[0][0])

    return "".join(consensus)