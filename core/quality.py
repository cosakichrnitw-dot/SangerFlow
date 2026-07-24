# ==================================================
# Average Quality
# ==================================================

def calculate_average_quality(sample):
    """
    Calculate average Phred quality score.
    """

    if not sample.quality:
        return 0.0

    return (
        sum(sample.quality)
        /
        len(sample.quality)
    )



# ==================================================
# Q20
# ==================================================

def calculate_q20_rate(sample):
    """
    Calculate percentage of bases
    with Phred score >= 20.
    """

    if not sample.quality:
        return 0.0


    q20_count = sum(
        1
        for q in sample.quality
        if q >= 20
    )


    return (
        q20_count
        /
        len(sample.quality)
        *
        100
    )



# ==================================================
# Q30
# ==================================================

def calculate_q30_rate(sample):
    """
    Calculate percentage of bases
    with Phred score >= 30.
    """

    if not sample.quality:
        return 0.0


    q30_count = sum(
        1
        for q in sample.quality
        if q >= 30
    )


    return (
        q30_count
        /
        len(sample.quality)
        *
        100
    )



# ==================================================
# Quality summary
# ==================================================

def quality_report(sample):
    """
    Generate quality summary.
    """


    return {

        "filename":
            sample.filename,


        "length":
            len(sample.sequence),


        "average_quality":
            calculate_average_quality(sample),


        "q20_rate":
            calculate_q20_rate(sample),


        "q30_rate":
            calculate_q30_rate(sample)

    }



# ==================================================
# HQ%
# Geneious style
# ==================================================

def calculate_hq_percent(
        read,
        threshold=30
):
    """
    Calculate HQ percentage.

    HQ% =
    trimmed bases with Phred >= threshold
    /
    total trimmed bases
    *100


    Default:
    Q30 based HQ%
    """


    quality = read.quality


    if len(quality) == 0:
        return 0.0



    start = getattr(
        read,
        "trim_start",
        0
    )


    end = getattr(
        read,
        "trim_end",
        len(quality)
    )


    start = max(
        0,
        start
    )


    end = min(
        len(quality),
        end
    )



    trimmed_quality = quality[start:end]


    if len(trimmed_quality) == 0:
        return 0.0



    high_quality_count = sum(

        1

        for q in trimmed_quality

        if q >= threshold

    )



    return (

        high_quality_count

        /

        len(trimmed_quality)

        *

        100

    )