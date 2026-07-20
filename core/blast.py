from Bio.Blast import NCBIWWW
from Bio.Blast import NCBIXML
from Bio import Entrez

import re
import ssl
import certifi


# Fix SSL certificate issue on macOS
ssl._create_default_https_context = (
    lambda: ssl.create_default_context(
        cafile=certifi.where()
    )
)


def extract_species(title):
    """
    Extract species name from BLAST title.
    """

    # Example:
    # gi|xxx|gb|xxx Rhynchobatus springeri voucher...

    match = re.search(
        r"\|\s*([A-Z][a-z]+ [a-z]+)",
        title
    )

    if match:
        return match.group(1)


    # fallback
    words = title.split()

    for i in range(len(words)-1):

        if (
            words[i][0].isupper()
            and words[i+1][0].islower()
        ):
            return (
                words[i]
                + " "
                + words[i+1]
            )

    return "Unknown"



def blast_sequence(
    sequence,
    database="nt",
    program="blastn",
    email=None
):

    """
    Run NCBI BLAST.

    Returns
    -------
    list
        formatted BLAST results
    """


    if email:
        Entrez.email = email


    result_handle = NCBIWWW.qblast(
        program,
        database,
        sequence
    )


    blast_record = NCBIXML.read(
        result_handle
    )


    results = []


    for alignment in blast_record.alignments[:10]:

        hsp = alignment.hsps[0]


        identity = (
            hsp.identities /
            hsp.align_length
            * 100
        )


        coverage = (
            hsp.align_length /
            len(sequence)
            * 100
        )


        species = extract_species(
            alignment.title
        )


        results.append(
            {
                "species": species,
                "identity": round(identity, 3),
                "coverage": round(coverage, 3),
                "alignment_length": hsp.align_length,
                "e_value": hsp.expect,
                "title": alignment.title
            }
        )


    return results