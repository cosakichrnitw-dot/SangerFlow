from core.config import load_qc_config


def longest_quality_block(quality, threshold=30):
    """
    Calculate longest consecutive region
    with quality >= threshold.
    """

    longest = 0
    current = 0

    for q in quality:

        if q >= threshold:
            current += 1

            if current > longest:
                longest = current

        else:
            current = 0

    return longest


def waveform_qc(sample):

    config = load_qc_config()

    quality = sample.quality

    length = len(quality)


    if length == 0:
        return {
            "status": "FAIL",
            "reason": "No quality data"
        }


    average_q = sum(quality) / length


    longest_q30 = longest_quality_block(
    quality,
    threshold=30
    )


    q20_rate = (
        sum(q >= 20 for q in quality)
        / length
        * 100
    )


    q30_rate = (
        sum(q >= 30 for q in quality)
        / length
        * 100
    )


    # terminal quality

    terminal_size = config["terminal_quality"]["terminal_size"]


    five_prime = quality[:terminal_size]

    three_prime = quality[-terminal_size:]


    five_prime_q = (
        sum(five_prime)
        / len(five_prime)
    )


    three_prime_q = (
        sum(three_prime)
        / len(three_prime)
    )


    # judgement

    problems = []


    if average_q < config["average_quality"]["warning"]:
        problems.append(
            "Low average quality"
        )


    if q30_rate < config["q30_rate"]["warning"]:
        problems.append(
            "Low Q30 rate"
        )


    if five_prime_q < config["terminal_quality"]["five_prime_min"]:
        problems.append(
            "Poor 5' end"
        )


    if three_prime_q < config["terminal_quality"]["three_prime_min"]:
        problems.append(
        "Poor 3' end"
        )
        


    if (
    average_q < config["average_quality"]["fail"]
    or
    q30_rate < config["q30_rate"]["fail"]
):

        status = "FAIL"

    elif len(problems) == 0:

        status = "PASS"

    else:

        status = "WARNING"



    return {

        "status": status,

        "average_quality": round(
            average_q,
            2
        ),

        "q20_rate": round(
            q20_rate,
            2
        ),

        "q30_rate": round(
            q30_rate,
            2
        ),

        "longest_q30_block": longest_q30,

        "five_prime_quality": round(
            five_prime_q,
            2
        ),

        "three_prime_quality": round(
            three_prime_q,
            2
        ),

        "problems": problems

    }