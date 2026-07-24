import math



def find_trim_region(
    quality,
    error_limit=0.05
):
    """
    Modified Mott trimming algorithm.

    Based on the method used by
    Phred / Geneious-style trimming.

    Parameters
    ----------
    quality : list
        Phred quality scores

    error_limit : float
        Maximum allowed error probability


    Returns
    -------
    start : int
        Trim start position

    end : int
        Trim end position
    """



    if len(quality) == 0:
        return 0, 0



    # ==================================
    # Convert Q score to trimming score
    # ==================================

    scores = []


    for q in quality:


        error_probability = (
            10 ** (-q / 10)
        )


        score = (
            error_limit
            -
            error_probability
        )


        scores.append(score)



    # ==================================
    # Find maximum scoring segment
    # ==================================

    best_score = 0

    current_score = 0


    best_start = 0

    best_end = len(scores)


    current_start = 0



    for i, score in enumerate(scores):


        current_score += score



        if current_score > best_score:

            best_score = current_score

            best_start = current_start

            best_end = i + 1



        if current_score < 0:

            current_score = 0

            current_start = i + 1



    return (
        best_start,
        best_end
    )




def trim_sequence(
    sample,
    error_limit=0.05
):
    """
    Apply Modified Mott trimming
    to SangerRead object.
    """



    start, end = find_trim_region(
        sample.quality,
        error_limit
    )



    sample.trim_start = start

    sample.trim_end = end



    sample.trimmed_sequence = (
        sample.sequence[start:end]
    )



    return sample