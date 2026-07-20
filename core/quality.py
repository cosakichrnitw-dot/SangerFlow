def calculate_average_quality(sample):
    """
    Calculate average Phred quality score.
    """

    if not sample.quality:
        return 0.0

    return sum(sample.quality) / len(sample.quality)



def calculate_q20_rate(sample):
    """
    Calculate percentage of bases with Phred score >= 20.
    """

    if not sample.quality:
        return 0.0

    q20_count = sum(
        1 for q in sample.quality
        if q >= 20
    )

    return q20_count / len(sample.quality) * 100



def calculate_q30_rate(sample):
    """
    Calculate percentage of bases with Phred score >= 30.
    """

    if not sample.quality:
        return 0.0

    q30_count = sum(
        1 for q in sample.quality
        if q >= 30
    )

    return q30_count / len(sample.quality) * 100



def quality_report(sample):
    """
    Generate quality summary.
    """

    average = calculate_average_quality(sample)
    q20 = calculate_q20_rate(sample)
    q30 = calculate_q30_rate(sample)

    return {
        "filename": sample.filename,
        "length": len(sample.sequence),
        "average_quality": average,
        "q20_rate": q20,
        "q30_rate": q30,
    }