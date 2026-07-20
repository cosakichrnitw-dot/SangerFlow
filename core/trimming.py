def find_trim_region(
    quality,
    threshold=20,
    window=10
):
    """
    Find high-quality region using sliding window.

    Parameters
    ----------
    quality : list
        Phred quality scores

    threshold : int
        Minimum average quality

    window : int
        Window size

    Returns
    -------
    start, end
    """

    length = len(quality)


    # Find start position
    start = 0

    for i in range(length - window):

        window_quality = quality[i:i+window]

        average = sum(window_quality) / window

        if average >= threshold:
            start = i
            break


    # Find end position

    end = length

    for i in range(length-window, 0, -1):

        window_quality = quality[i:i+window]

        average = sum(window_quality) / window

        if average >= threshold:
            end = i + window
            break


    return start, end



def trim_sequence(
    sample,
    threshold=20,
    window=10
):
    """
    Trim low quality ends from Sanger read.
    """


    start, end = find_trim_region(
        sample.quality,
        threshold,
        window
    )


    sample.trim_start = start
    sample.trim_end = end


    sample.trimmed_sequence = (
        sample.sequence[start:end]
    )


    return sample