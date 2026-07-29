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
        Aligned sequences

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



        if len(column) == 0:


            consensus.append("-")

            continue



        counts = Counter(column)



        most_common = counts.most_common()



        if len(most_common) > 1:


            if most_common[0][1] == most_common[1][1]:


                consensus.append("N")

                continue



        consensus.append(

            most_common[0][0]

        )



    return "".join(consensus)





# ==================================================
# Quality aware consensus
# ==================================================

def build_quality_consensus(
    reads,
    alignment
):

    """
    Build consensus using Phred quality scores.

    Parameters
    ----------
    reads :
        Read objects containing sequence and quality

    alignment :
        Biopython MultipleSeqAlignment


    Returns
    -------
    tuple

        consensus sequence,
        confidence scores

    """



    if len(reads) == 0:

        return "", []



    aligned_sequences = []


    for record in alignment:

        aligned_sequences.append(

            str(record.seq)

        )



    length = len(

        aligned_sequences[0]

    )



    consensus = []

    confidence = []



    for pos in range(length):


        base_scores = {}



        for read, seq in zip(

            reads,

            aligned_sequences

        ):



            if pos >= len(seq):

                continue



            base = seq[pos].upper()



            if base == "-":

                continue



            # original trace position

            try:


                q = read.quality[pos]


            except:


                q = 0



            if base not in base_scores:


                base_scores[base] = 0



            base_scores[base] += q



        if len(base_scores) == 0:


            consensus.append("-")

            confidence.append(0)

            continue



        sorted_scores = sorted(

            base_scores.items(),

            key=lambda x: x[1],

            reverse=True

        )



        best_base = sorted_scores[0][0]

        best_score = sorted_scores[0][1]


        total_score = sum(

            base_scores.values()

        )



        conf = (

            best_score /

            total_score

            *

            100

        )



        consensus.append(

            best_base

        )


        confidence.append(

            round(

                conf,

                1

            )

        )



    return (

        "".join(consensus),

        confidence

    )