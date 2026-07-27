import math



# ==================================================
# Find trim region (Modified Mott)
# ==================================================

def find_trim_region(
    quality,
    error_limit=0.05
):


    if len(quality) == 0:

        return 0, 0



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




# ==================================================
# Apply trimming
# ==================================================

def trim_sequence(
    sample,
    error_limit=0.05
):


    start, end = find_trim_region(

        sample.quality,

        error_limit

    )



    # =====================
    # Trim information
    # =====================

    sample.trim_start = start

    sample.trim_end = end



    # =====================
    # Sequence
    # =====================

    sample.trimmed_sequence = (

        sample.sequence[start:end]

    )



    # =====================
    # Quality
    # =====================

    sample.trimmed_quality = (

        sample.quality[start:end]

    )



    # =====================
    # Trace coordinate
    # =====================

    if start < len(sample.base_positions):


        trace_start = (

            sample.base_positions[start]

        )


    else:


        trace_start = 0



    if end < len(sample.base_positions):


        trace_end = (

            sample.base_positions[end]

        )


    else:


        trace_end = len(

            sample.traces["A"]

        )



    # =====================
    # Peak positions
    # 0基準化
    # =====================

    sample.trimmed_base_positions = [


        pos - trace_start


        for pos in sample.base_positions[start:end]


    ]



    # =====================
    # Chromatogram traces
    # =====================

    trimmed_traces = {}



    for base, trace in sample.traces.items():


        trimmed_traces[base] = (

            trace[

                trace_start:trace_end

            ]

        )



    sample.trimmed_traces = trimmed_traces


    print(
        "========== TRIMMED DATA DEBUG =========="
    )


    print(
        "file:",
        sample.filename
    )


    print(
        "trim_start:",
        sample.trim_start
    )


    print(
        "trim_end:",
        sample.trim_end
    )


    print(
        "trimmed_sequence length:",
        len(sample.trimmed_sequence)
    )


    print(
        "trimmed_base_positions first 5:",
        sample.trimmed_base_positions[:5]
    )


    print(
        "trimmed_trace length:",
        len(sample.trimmed_traces["A"])
    )


    print(
        "========================================="
    )



    return sample