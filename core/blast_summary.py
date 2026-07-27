from collections import Counter


# ==================================================
# Get best BLAST hit per sample
# ==================================================

def get_best_hits(blast_results):
    """
    Extract best BLAST hit for each sample.

    Parameters
    ----------
    blast_results : list
        BLAST result dictionaries

    Returns
    -------
    list
        Best hit per sample
    """

    best = {}


    for result in blast_results:

        sample = result.get(
            "sample",
            "Unknown"
        )


        if sample not in best:

            best[sample] = result

            continue


        # Higher identity first
        if result["identity"] > best[sample]["identity"]:

            best[sample] = result


        elif (
            result["identity"] ==
            best[sample]["identity"]
            and
            result["coverage"] >
            best[sample]["coverage"]
        ):

            best[sample] = result



    return list(best.values())





# ==================================================
# Species summary
# ==================================================

def species_summary(blast_results):
    """
    Count identified species.

    Returns
    -------
    list
        Summary table
    """


    counter = Counter()


    for result in blast_results:


        species = result.get(

            "species",

            "Unknown"

        )


        counter[species] += 1



    summary = []


    for species, count in counter.most_common():


        summary.append(

            {
                "species": species,
                "count": count
            }

        )


    return summary





# ==================================================
# Classification summary
# ==================================================

def make_summary(blast_results):
    """
    Create complete BLAST summary.

    Returns
    -------
    dict
    """

    return {

        "best_hits":
            get_best_hits(
                blast_results
            ),

        "species_summary":
            species_summary(
                blast_results
            )

    }