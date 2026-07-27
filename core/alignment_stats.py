def count_variable_sites(
    alignment
):
    """
    Count variable nucleotide sites.
    
    Gaps are ignored.
    Only A/C/G/T variation is counted.
    """


    sequences = list(
        alignment.values()
    )


    if len(sequences) == 0:

        return 0



    length = max(
        len(seq)
        for seq in sequences
    )


    count = 0



    for i in range(length):


        column = []


        for seq in sequences:


            if i < len(seq):

                base = seq[i].upper()


                if base in [

                    "A",

                    "C",

                    "G",

                    "T"

                ]:

                    column.append(base)



        # 2種類以上の塩基がある場合

        if len(set(column)) > 1:

            count += 1



    return count




def alignment_summary(
    alignment
):


    consensus_length = max(

        len(seq)

        for seq in alignment.values()

    )


    return {


        "sequence_count":

            len(alignment),



        "alignment_length":

            consensus_length,


        "variable_sites":

            count_variable_sites(

                alignment

            )

    }