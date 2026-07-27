# core/alignment_mapper.py


def alignment_to_trace_positions(
    aligned_sequence,
    read
):
    """
    Convert MAFFT alignment columns
    to chromatogram peak positions.
    """


    mapping = {}


    seq_index = 0



    peak_positions = read.trimmed_base_positions



    for aln_index, base in enumerate(
        aligned_sequence,
        start=1
    ):



        # gap

        if base == "-":


            mapping[aln_index] = None


            continue



        #
        # non-gap base
        #

        if seq_index < len(
            peak_positions
        ):


            mapping[aln_index] = (
                peak_positions[seq_index]
            )


        else:


            mapping[aln_index] = None



        seq_index += 1



    return mapping



def trace_to_alignment_positions(
    mapping
):


    reverse = {}


    for aln_pos, trace_pos in mapping.items():


        if trace_pos is not None:


            reverse[trace_pos] = aln_pos



    return reverse