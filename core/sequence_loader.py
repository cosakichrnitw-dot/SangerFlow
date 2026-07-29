from pathlib import Path

from core.ab1_reader import read_ab1
from core.trimming import trim_sequence

from core.quality import (
    calculate_hq_percent,
    calculate_average_quality,
    calculate_q20_rate,
    calculate_q30_rate
)


# ==================================================
# Load single AB1
# ==================================================

def load_ab1_file(filepath):


    read = read_ab1(

        filepath

    )


    trim_sequence(

        read

    )


    read.hq_percent = calculate_hq_percent(

        read

    )


    read.average_quality = calculate_average_quality(

        read

    )


    read.q20_rate = calculate_q20_rate(

        read

    )


    read.q30_rate = calculate_q30_rate(

        read

    )


    return read



# ==================================================
# Load AB1 folder
# ==================================================

def load_ab1_folder(folder):

    reads = []


    for filepath in sorted(
        Path(folder).glob("*.ab1")
    ):

        try:

            read = load_ab1_file(
                filepath
            )


            print("")


            reads.append(
                read
            )


        except Exception as e:

            print(
                f"Failed loading {filepath.name}"
            )

            print(e)


    return reads